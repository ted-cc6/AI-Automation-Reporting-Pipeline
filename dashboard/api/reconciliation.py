"""dashboard/api/reconciliation.py

LLM-assisted column-mapping reconciliation: deterministic diff (mapping_diff)
covers pure reordering for free; this module handles the residual (renamed/
dropped/new columns) via one LLM call, a persisted recommendation set for the
frontend's human approval gate, and applying approved decisions into a
per-upload scratch mapping that's re-verified through the real pipeline
before it's trusted for a run.

Nothing here ever touches the canonical data_loader/column_mapping.csv or
value_coding_map.yaml -- every artifact is scoped to an upload_id under
dashboard/api/uploads/, promoted to the "reconciled" filenames only after a
clean validator PASS (see apply_decisions).
"""
import json
import logging
import shutil
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml

from data_loader import data_loader_derived, data_loader_profiler, data_loader_transformer, data_loader_validator
from data_loader.data_loader_transformer import load_mapping, load_yaml as load_value_map
from data_loader.mapping_diff import MappingDiffResult, diff_columns, read_csv_header_row
from dashboard.api.config import PROJECT_ROOT, UPLOADS_DIR
from dashboard.api.models import LlmConfig
from llm_providers import call_llm

log = logging.getLogger(__name__)

DATA_LOADER_DIR = PROJECT_ROOT / "data_loader"
CANONICAL_MAPPING_PATH = DATA_LOADER_DIR / "column_mapping.csv"
CANONICAL_VALUE_MAP_PATH = DATA_LOADER_DIR / "value_coding_map.yaml"

ALLOWED_NEW_RESPONSE_TYPES = frozenset({"open_text", "single_select", "likert5", "nps_score", "age"})
SAMPLE_VALUES_PER_COLUMN = 3
MAPPING_FIELDNAMES = [
    "raw_index", "raw_column_header", "category", "question_ref",
    "parent_ref", "response_type", "scope", "output_name", "notes",
]


# ---------------------------------------------------------------------------
# Scratch paths
# ---------------------------------------------------------------------------

def upload_csv_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.csv"


def upload_reconciliation_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_reconciliation.json"


def upload_mapping_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_column_mapping.csv"


def upload_value_map_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_value_coding_map.yaml"


def upload_verify_dir(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_verify"


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are assisting with reconciling a VisionFund insurance survey CSV export
against a hand-maintained column mapping used by an automated data pipeline.
A new quarterly export has columns that could not be automatically matched to
the existing mapping by header text or position. Your job is to propose how
to reconcile the residual: for each OLD mapping question with no confident
CSV match, and each NEW CSV column with no confident mapping match, propose
exactly one recommendation.

Choose one type per recommendation:
- "rename": an OLD mapping question and a NEW CSV column are the same
  underlying question, just reworded. Only propose this when you are
  confident the meaning is preserved.
- "new_question": a NEW CSV column has no prior counterpart -- a genuinely
  new question added to the survey.
- "dropped": an OLD mapping question has no NEW CSV column counterpart --
  it was removed from the survey.

Every OLD residual question and every NEW residual CSV column should appear
in exactly one recommendation ("rename" consumes one of each; "new_question"
and "dropped" each consume one).

For "new_question" recommendations you must also propose:
- suggested_question_ref: a new snake_case identifier starting with "q_",
  not colliding with any existing question_ref shown in the payload.
- suggested_response_type: exactly one of "open_text", "single_select",
  "likert5", "nps_score", "age".
  * single_select: any lettered multiple-choice question, INCLUDING yes/no
    ones -- it is always a safe default choice.
  * likert5: only for a genuine ordinal agreement/rating scale with 2-6
    ordered options where the meaning of "more positive" is clear.
  * nps_score: only a 0-10 recommendation-likelihood question.
  * age: only a numeric age-in-years question.
  * open_text: anything free-form, or if you are unsure.
  Never propose "binary" or "multi_select_parent" -- they are not supported
  by this tool; use single_select or open_text instead and say so in the
  rationale if a column looks multi-select-shaped.
- If, and only if, suggested_response_type is "likert5": also propose
  suggested_value_map, an object mapping each observed raw option string
  (verbatim, including its leading letter prefix like "a. ") to
  {"int": <1-based rank>, "label": <clean text, prefix stripped>}. The
  FIRST-listed / most positive option must be int=1, increasing integers
  progressively less positive (a=1 most positive convention, matching this
  survey's other Likert questions). Base this only on the example raw values
  given for that column. If more than 6 distinct options are plausible, use
  single_select instead.

For every recommendation also include:
- confidence: a number from 0.0 to 1.0.
- rationale: one sentence explaining your reasoning.

Respond with ONLY a JSON array of recommendation objects -- no prose, no
markdown fences, no wrapping object.
""".strip()


def build_llm_payload(diff: MappingDiffResult, df: pd.DataFrame, mapping: pd.DataFrame) -> dict:
    existing_question_refs = sorted({
        q for q in mapping["question_ref"] if isinstance(q, str) and q.strip()
    })

    unmatched_old_questions = [
        {
            "raw_index": r.raw_index,
            "header": r.header,
            "category": r.category,
            "question_ref": r.question_ref,
            "response_type": r.response_type,
        }
        for r in diff.unmatched_rows()
    ]

    unmatched_new_csv_columns = []
    for c in diff.unmatched_csv_columns():
        series = df.iloc[:, c.csv_index].astype(str).str.strip()
        samples = [v for v in series.unique().tolist() if v][:SAMPLE_VALUES_PER_COLUMN]
        unmatched_new_csv_columns.append({
            "csv_index": c.csv_index,
            "header": c.header,
            "sample_values": samples,
        })

    return {
        "existing_question_refs": existing_question_refs,
        "unmatched_old_questions": unmatched_old_questions,
        "unmatched_new_csv_columns": unmatched_new_csv_columns,
    }


def _clamp_confidence(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _validate_value_map(raw) -> Optional[dict]:
    if not isinstance(raw, dict) or not raw:
        return None
    out = {}
    for k, v in raw.items():
        if not isinstance(k, str) or not isinstance(v, dict):
            return None
        try:
            n = int(v["int"])
        except (KeyError, TypeError, ValueError):
            return None
        label = v.get("label")
        if not isinstance(label, str) or not label.strip():
            return None
        out[k] = {"int": n, "label": label.strip()}
    return out


def _dedupe_question_ref(candidate: str, taken: set[str]) -> str:
    base = candidate if candidate.strip().startswith("q_") else f"q_{candidate.strip()}"
    base = base.strip().lower().replace(" ", "_") or "q_new_question"
    name = base
    n = 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    return name


def _validate_and_repair(raw_items: list, diff: MappingDiffResult, mapping: pd.DataFrame) -> list[dict]:
    valid_old_idx = {r.raw_index for r in diff.unmatched_rows()}
    valid_new_idx = {c.csv_index for c in diff.unmatched_csv_columns()}

    taken_qrefs = {q for q in mapping["question_ref"] if isinstance(q, str) and q.strip()}
    covered_old: set[int] = set()
    covered_new: set[int] = set()
    repaired: list[dict] = []

    for item in raw_items:
        if not isinstance(item, dict):
            continue
        item_type = item.get("type")
        confidence = _clamp_confidence(item.get("confidence"))
        rationale = str(item.get("rationale") or "").strip() or "(no rationale given)"

        if item_type == "rename":
            old_idx, new_idx = item.get("old_raw_index"), item.get("new_csv_index")
            if old_idx not in valid_old_idx or new_idx not in valid_new_idx:
                continue
            covered_old.add(old_idx)
            covered_new.add(new_idx)
            repaired.append({
                "type": "rename", "confidence": confidence, "rationale": rationale,
                "old_raw_index": old_idx, "new_csv_index": new_idx,
                "suggested_question_ref": None, "suggested_response_type": None,
                "suggested_value_map": None,
            })

        elif item_type == "dropped":
            old_idx = item.get("old_raw_index")
            if old_idx not in valid_old_idx:
                continue
            covered_old.add(old_idx)
            repaired.append({
                "type": "dropped", "confidence": confidence, "rationale": rationale,
                "old_raw_index": old_idx, "new_csv_index": None,
                "suggested_question_ref": None, "suggested_response_type": None,
                "suggested_value_map": None,
            })

        elif item_type == "new_question":
            new_idx = item.get("new_csv_index")
            if new_idx not in valid_new_idx:
                continue
            covered_new.add(new_idx)

            resp_type = item.get("suggested_response_type")
            notes = []
            if resp_type not in ALLOWED_NEW_RESPONSE_TYPES:
                notes.append(f"unsupported response type {resp_type!r} coerced to open_text")
                resp_type = "open_text"

            value_map = None
            if resp_type == "likert5":
                value_map = _validate_value_map(item.get("suggested_value_map"))
                if value_map is None:
                    notes.append("likert5 value map missing/malformed; downgraded to single_select")
                    resp_type = "single_select"

            qref = _dedupe_question_ref(str(item.get("suggested_question_ref") or ""), taken_qrefs)
            taken_qrefs.add(qref)

            full_rationale = rationale if not notes else f"{rationale} ({'; '.join(notes)})"
            repaired.append({
                "type": "new_question", "confidence": confidence, "rationale": full_rationale,
                "old_raw_index": None, "new_csv_index": new_idx,
                "suggested_question_ref": qref, "suggested_response_type": resp_type,
                "suggested_value_map": value_map,
            })

    # Synthetic fallback for anything the LLM left uncovered, so every
    # residual item always has exactly one recommendation card.
    for idx in sorted(valid_old_idx - covered_old):
        repaired.append({
            "type": "dropped", "confidence": 0.0,
            "rationale": "No recommendation returned by the model for this question; treated as dropped pending review.",
            "old_raw_index": idx, "new_csv_index": None,
            "suggested_question_ref": None, "suggested_response_type": None, "suggested_value_map": None,
        })
    for idx in sorted(valid_new_idx - covered_new):
        qref = _dedupe_question_ref(f"q_new_col_{idx}", taken_qrefs)
        taken_qrefs.add(qref)
        repaired.append({
            "type": "new_question", "confidence": 0.0,
            "rationale": "No recommendation returned by the model for this column; captured as free text pending review.",
            "old_raw_index": None, "new_csv_index": idx,
            "suggested_question_ref": qref, "suggested_response_type": "open_text", "suggested_value_map": None,
        })

    return repaired


def _enrich(repaired: list[dict], diff: MappingDiffResult, col_names: list[str]) -> list[dict]:
    old_by_idx = {r.raw_index: r for r in diff.unmatched_rows()}
    enriched = []
    for i, item in enumerate(repaired):
        old_row = old_by_idx.get(item["old_raw_index"]) if item["old_raw_index"] is not None else None
        enriched.append({
            "id": f"rec_{i}",
            **item,
            "old_header": old_row.header if old_row else None,
            "old_question_ref": old_row.question_ref if old_row else None,
            "old_category": old_row.category if old_row else None,
            "new_header": col_names[item["new_csv_index"]] if item["new_csv_index"] is not None else None,
            "approved": None,
        })
    return enriched


def call_reconciliation_llm(payload: dict, llm: LlmConfig, diff: MappingDiffResult,
                             mapping: pd.DataFrame, col_names: list[str]) -> list[dict]:
    raw_text = call_llm(
        provider=llm.provider,
        api_key=llm.api_key,
        system_prompt=SYSTEM_PROMPT,
        user_content=json.dumps(payload, ensure_ascii=False),
        max_output_tokens=8192,
        temperature=0.2,
        model=llm.model,
    )
    try:
        raw_items = json.loads(raw_text)
        if not isinstance(raw_items, list):
            raw_items = []
    except json.JSONDecodeError:
        log.warning("Reconciliation LLM response was not valid JSON; falling back to synthetic recommendations.")
        raw_items = []

    repaired = _validate_and_repair(raw_items, diff, mapping)
    return _enrich(repaired, diff, col_names)


# ---------------------------------------------------------------------------
# validate_dataset
# ---------------------------------------------------------------------------

def validate_dataset(upload_id: str, llm: LlmConfig) -> dict:
    csv_path = upload_csv_path(upload_id)
    col_names = read_csv_header_row(csv_path)
    mapping = load_mapping(CANONICAL_MAPPING_PATH)

    diff = diff_columns(mapping, col_names)
    if not diff.has_residual:
        return {"clean": True, "recommendations": [], "residual_old_count": 0, "residual_new_count": 0}

    df = data_loader_transformer.load_raw(csv_path)
    payload = build_llm_payload(diff, df, mapping)
    recommendations = call_reconciliation_llm(payload, llm, diff, mapping, col_names)

    with open(upload_reconciliation_path(upload_id), "w", encoding="utf-8") as f:
        json.dump(recommendations, f, indent=2, ensure_ascii=False)

    return {
        "clean": False,
        "recommendations": recommendations,
        "residual_old_count": len(diff.unmatched_rows()),
        "residual_new_count": len(diff.unmatched_csv_columns()),
    }


# ---------------------------------------------------------------------------
# apply_decisions
# ---------------------------------------------------------------------------

def _write_mapping_csv(mapping: pd.DataFrame, path: Path) -> None:
    mapping.to_csv(path, index=False, columns=MAPPING_FIELDNAMES)


def apply_decisions(upload_id: str, decisions: dict[str, bool]) -> dict:
    rec_path = upload_reconciliation_path(upload_id)
    if not rec_path.exists():
        raise ValueError(f"No reconciliation found for upload '{upload_id}' -- call /validate first.")

    with open(rec_path, encoding="utf-8") as f:
        recommendations: list[dict] = json.load(f)

    mapping = load_mapping(CANONICAL_MAPPING_PATH).copy()
    cmap = load_value_map(CANONICAL_VALUE_MAP_PATH)
    mapping = mapping.set_index("raw_index", drop=False)

    renamed_count = new_question_count = dropped_count = 0
    to_drop: list[int] = []
    next_raw_index = int(mapping["raw_index"].max()) + 1

    for rec in recommendations:
        rec_id = rec["id"]
        approved = decisions.get(rec_id, False)
        rec["approved"] = approved
        if not approved:
            continue

        if rec["type"] == "rename":
            old_idx = rec["old_raw_index"]
            if old_idx in mapping.index:
                mapping.loc[old_idx, "raw_index"] = rec["new_csv_index"]
                mapping.loc[old_idx, "raw_column_header"] = rec["new_header"]
                renamed_count += 1

        elif rec["type"] == "dropped":
            old_idx = rec["old_raw_index"]
            if old_idx in mapping.index:
                to_drop.append(old_idx)
                dropped_count += 1

        elif rec["type"] == "new_question":
            new_row = {
                "raw_index": rec["new_csv_index"],
                "raw_column_header": rec["new_header"],
                "category": "question_ref",
                "question_ref": rec["suggested_question_ref"],
                "parent_ref": "",
                "response_type": rec["suggested_response_type"],
                "scope": "",
                "output_name": "",
                "notes": f"reconciled: LLM-proposed (upload {upload_id})",
            }
            mapping.loc[next_raw_index] = new_row
            next_raw_index += 1
            new_question_count += 1

            if rec["suggested_response_type"] == "likert5" and rec.get("suggested_value_map"):
                cmap.setdefault("likert_5", {})[rec["suggested_question_ref"]] = rec["suggested_value_map"]

    if to_drop:
        mapping = mapping.drop(index=to_drop)
    mapping = mapping.reset_index(drop=True)

    # Persist the approve/reject decisions back onto the stored recommendation set.
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, indent=2, ensure_ascii=False)

    verify_dir = upload_verify_dir(upload_id)
    verify_dir.mkdir(parents=True, exist_ok=True)
    verify_mapping_path = verify_dir / "column_mapping.csv"
    verify_value_map_path = verify_dir / "value_coding_map.yaml"
    _write_mapping_csv(mapping, verify_mapping_path)
    with open(verify_value_map_path, "w", encoding="utf-8") as f:
        yaml.dump(cmap, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    passed, errors, warnings = _run_verification_pipeline(
        upload_csv_path(upload_id), verify_mapping_path, verify_value_map_path, verify_dir,
    )

    if passed:
        shutil.copy2(verify_mapping_path, upload_mapping_path(upload_id))
        shutil.copy2(verify_value_map_path, upload_value_map_path(upload_id))

    return {
        "validator_passed": passed,
        "errors": errors,
        "warnings": warnings,
        "renamed_count": renamed_count,
        "new_question_count": new_question_count,
        "dropped_count": dropped_count,
    }


def _extract_report_section(report_text: str, heading: str) -> list[str]:
    lines = report_text.splitlines()
    out, capturing = [], False
    for line in lines:
        if line.strip() == heading:
            capturing = True
            continue
        if capturing:
            if line.startswith("## ") or (line.startswith("### ") and line.strip() != heading):
                break
            if line.startswith("- "):
                out.append(line[2:].strip())
    return out


def _run_verification_pipeline(csv_path: Path, mapping_path: Path, value_map_path: Path,
                                verify_dir: Path) -> tuple[bool, list[str], list[str]]:
    try:
        data_loader_profiler.main(csv_path, mapping_path, verify_dir)
        data_loader_transformer.main(csv_path, mapping_path, value_map_path, verify_dir)
        try:
            data_loader_derived.main(verify_dir)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError(f"derived step failed (exit code {exc.code})") from exc
        try:
            data_loader_validator.main(verify_dir)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                report_path = verify_dir / "data_quality_report.md"
                errors = _extract_report_section(report_path.read_text(encoding="utf-8"), "### Errors") \
                    if report_path.exists() else [f"validator failed (exit code {exc.code})"]
                warnings = _extract_report_section(report_path.read_text(encoding="utf-8"), "### Warnings") \
                    if report_path.exists() else []
                return False, errors, warnings
    except Exception as exc:
        log.warning(f"Verification pipeline failed for {verify_dir}: {exc}")
        return False, [str(exc)], []

    report_path = verify_dir / "data_quality_report.md"
    warnings = _extract_report_section(report_path.read_text(encoding="utf-8"), "### Warnings") \
        if report_path.exists() else []
    return True, [], warnings
