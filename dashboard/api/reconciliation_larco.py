"""dashboard/api/reconciliation_larco.py

LLM-assisted column-mapping reconciliation for the LARCO source schema.
Same validate_dataset/apply_decisions shape and column_mapping.csv format
(raw_index/raw_column_header/category/question_ref/parent_ref/
response_type/scope/output_name/notes) as reconciliation.py (the Africa/
Vietnam pipeline's equivalent) -- LARCO uses the exact same Cupboard Week
data-loader engines, just pointed at data_loader_larco/'s canonical mapping
instead. The genuinely schema-agnostic helpers (LLM-response validation/
repair, recommendation enrichment, mapping-CSV writing) are imported from
reconciliation.py rather than duplicated; only what's actually
schema-specific is reimplemented here: the canonical paths, the LLM system
prompt (tuned for LARCO's own survey wording), the scratch-file naming for
this schema's intermediates, and dataset_schema="larco" threaded into the
verification replay (data_loader_derived.py/data_loader_validator.py's
schema-aware checks -- see Phase 2 -- would otherwise validate a LARCO
parquet against Africa's insurance_type slugs and validation spec).

(GEDSI's gedsi_reconciliation.py, by contrast, IS a full separate
implementation -- its verification and role taxonomy are genuinely
different, not just a different canonical file. LARCO needs neither: it's
the same pipeline shape as Cupboard Week end to end.)

The FINAL promoted mapping/value-map filenames
({upload_id}_column_mapping.csv / {upload_id}_value_coding_map.yaml) are
deliberately identical to reconciliation.py's -- dashboard/api/
pipeline_runner.py's reconciled-mapping lookup already checks exactly that
path regardless of which reconciliation module produced it, and one
upload_id only ever belongs to one schema in practice. Only the
intermediate/scratch artifacts (recommendation JSON, verify directory) get
a "_larco" suffix, to avoid any accidental collision if both reconciliation
endpoints were ever called for the same upload_id.
"""
import json
import logging
import shutil
from pathlib import Path

import pandas as pd
import yaml

from data_loader import data_loader_derived, data_loader_profiler, data_loader_transformer, data_loader_validator
from data_loader.data_loader_transformer import load_mapping, load_yaml as load_value_map
from data_loader.mapping_diff import MappingDiffResult, diff_columns, read_csv_header_row
from dashboard.api.config import PROJECT_ROOT, UPLOADS_DIR
from dashboard.api.models import LlmConfig
from dashboard.api.reconciliation import (
    _enrich,
    _extract_report_section,
    _validate_and_repair,
    _write_mapping_csv,
    build_llm_payload,
)
from llm_providers import call_llm

log = logging.getLogger(__name__)

DATASET_SCHEMA = "larco"
DATA_LOADER_LARCO_DIR = PROJECT_ROOT / "data_loader_larco"
CANONICAL_MAPPING_PATH = DATA_LOADER_LARCO_DIR / "column_mapping.csv"
CANONICAL_VALUE_MAP_PATH = DATA_LOADER_LARCO_DIR / "value_coding_map.yaml"

SAMPLE_VALUES_PER_COLUMN = 3


# ---------------------------------------------------------------------------
# Scratch paths
# ---------------------------------------------------------------------------

def upload_csv_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.csv"


def upload_reconciliation_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_larco_reconciliation.json"


def upload_mapping_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_column_mapping.csv"


def upload_value_map_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_value_coding_map.yaml"


def upload_verify_dir(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_larco_verify"


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are assisting with reconciling a VisionFund LARCO (Ecuador/Mexico/
Guatemala/Honduras/Bolivia) insurance survey CSV export against a
hand-maintained column mapping used by an automated data pipeline. A new
export has columns that could not be automatically matched to the existing
mapping by header text or position. Your job is to propose how to reconcile
the residual: for each OLD mapping question with no confident CSV match,
and each NEW CSV column with no confident mapping match, propose exactly
one recommendation.

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
  (verbatim) to {"int": <1-based rank>, "label": <clean text>}. The
  FIRST-listed / most positive option must be int=1, increasing integers
  progressively less positive (1=most positive convention, matching this
  survey's other Likert questions). Base this only on the example raw
  values given for that column. LARCO's raw option text usually has no
  leading letter prefix (unlike VisionFund's Africa/Vietnam survey) -- use
  the raw text as-is. If more than 6 distinct options are plausible, use
  single_select instead.

For every recommendation also include:
- confidence: a number from 0.0 to 1.0.
- rationale: one sentence explaining your reasoning.

Respond with ONLY a JSON array of recommendation objects -- no prose, no
markdown fences, no wrapping object.
""".strip()


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
        log.warning("LARCO reconciliation LLM response was not valid JSON; falling back to synthetic recommendations.")
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


def _run_verification_pipeline(csv_path: Path, mapping_path: Path, value_map_path: Path,
                                verify_dir: Path) -> tuple[bool, list[str], list[str]]:
    try:
        data_loader_profiler.main(csv_path, mapping_path, verify_dir)
        data_loader_transformer.main(csv_path, mapping_path, value_map_path, verify_dir)
        try:
            data_loader_derived.main(verify_dir, dataset_schema=DATASET_SCHEMA)
        except SystemExit as exc:
            if exc.code not in (None, 0):
                raise RuntimeError(f"derived step failed (exit code {exc.code})") from exc
        try:
            data_loader_validator.main(verify_dir, dataset_schema=DATASET_SCHEMA)
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
