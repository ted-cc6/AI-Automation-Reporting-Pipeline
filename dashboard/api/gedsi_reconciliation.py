"""dashboard/api/gedsi_reconciliation.py

LLM-assisted column-mapping reconciliation for the GEDSI Insurance Survey
(Gender Study) pipeline. Same validate_dataset/apply_decisions shape as
reconciliation.py (the Cupboard Week pipeline's equivalent), but built
around GENDSI's role-typed column_mapping.csv (demographic / consent /
system_uuid / quant_indicator / multiselect_parent / multiselect_option /
qual_primary / qual_supplementary / pii_drop / unused -- see
gedsi_pipeline/mapping.py) instead of Cupboard Week's question_ref/
response_type mapping.

Nothing here ever touches the canonical gedsi_pipeline/column_mapping.csv --
every artifact is scoped to an upload_id under dashboard/api/uploads/,
promoted to the "reconciled" filename only after
gedsi_pipeline.ingest.build_response_frame() (stage 1 of the real pipeline)
runs clean against it. That's a lighter re-verification than Cupboard
Week's 4-stage data_loader replay, because GENDSI's own stage 1 already does
everything a reconciled mapping needs proven against: it loads the CSV,
resolves every role, and asserts no PII column leaked through.
"""
import json
import logging
from pathlib import Path

import pandas as pd

from dashboard.api.config import GENDSI_ROOT, UPLOADS_DIR
from dashboard.api.models import LlmConfig
from llm_providers import call_llm

from gedsi_pipeline import mapping as gedsi_mapping
from gedsi_pipeline import mapping_diff as gedsi_mapping_diff
from gedsi_pipeline.ingest import build_response_frame
from gedsi_pipeline.mapping_diff import MappingDiffResult

log = logging.getLogger(__name__)

CANONICAL_MAPPING_PATH = GENDSI_ROOT / "gedsi_pipeline" / "column_mapping.csv"

# What a "new_question" recommendation is allowed to resolve to. Deliberately
# excludes demographic/consent/system_uuid/qual_primary/multiselect_parent --
# those are fixed, singular roles the pipeline already expects exactly one
# of; a genuine new counterpart for one of those should be a "rename"
# instead. qual_primary specifically can't be invented at all: qual_engine's
# QUESTION_CONTEXT prompt text is hand-written per fixed question key, so a
# brand-new primary question would have no coding prompt to run against.
ALLOWED_NEW_ROLE_TYPES = frozenset({"quant_indicator", "qual_supplementary", "multiselect_option", "unused"})
SAMPLE_VALUES_PER_COLUMN = 3
MAPPING_FIELDNAMES = gedsi_mapping_diff.MAPPING_FIELDNAMES


# ---------------------------------------------------------------------------
# Scratch paths
# ---------------------------------------------------------------------------

def upload_csv_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}.csv"


def upload_reconciliation_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_gedsi_reconciliation.json"


def upload_mapping_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_gedsi_column_mapping.csv"


def upload_verify_mapping_path(upload_id: str) -> Path:
    return UPLOADS_DIR / f"{upload_id}_gedsi_column_mapping_verify.csv"


# ---------------------------------------------------------------------------
# LLM prompt
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """
You are assisting with reconciling a VisionFund GEDSI insurance survey CSV
export against a hand-maintained column mapping used by an automated
analysis pipeline. A new export has columns that could not be automatically
matched to the existing mapping by header text or position. Your job is to
propose how to reconcile the residual: for each OLD mapping role with no
confident CSV match, and each NEW CSV column with no confident mapping
match, propose exactly one recommendation.

Choose one type per recommendation:
- "rename": an OLD mapping role and a NEW CSV column are the same
  underlying field, just reworded or moved. Only propose this when you are
  confident the meaning is preserved -- the role keeps its exact original
  type (demographic, quant_indicator, multiselect_option, etc.); only its
  position and header text change.
- "new_question": a NEW CSV column has no prior counterpart. You must also
  propose suggested_role_type, exactly one of:
  * "quant_indicator": a genuinely new closed-ended (single-choice) survey
    question worth quantitative analysis. Propose suggested_role_name, a
    new snake_case identifier not colliding with any existing role name
    shown below.
  * "qual_supplementary": free text worth keeping as illustrative quotes
    (an open-ended or "if other, please specify" style field). Propose
    suggested_role_name.
  * "multiselect_option": a new checkbox option belonging to an EXISTING
    multi-select question group (e.g. one more item added to a "which
    services did you use" checklist). Propose suggested_group_name, which
    MUST exactly match one of the existing_multiselect_groups listed below,
    and suggested_option_label, the option's exact label text.
  * "unused": the column is Kobo platform metadata, a section-intro note,
    or otherwise not worth analyzing. Use this whenever you are unsure --
    it is always a safe default.
  Never propose a brand-new demographic, consent, system_uuid, qual_primary,
  or multiselect_parent role -- these are fixed, singular roles the
  pipeline already expects exactly one of; if one of these seems to have a
  new counterpart, propose "rename" instead, pairing it with the matching
  OLD residual role below.
- "dropped": an OLD mapping role has no NEW CSV column counterpart -- it
  was removed from the survey.

Every OLD residual role and every NEW residual CSV column should appear in
exactly one recommendation ("rename" consumes one of each; "new_question"
and "dropped" each consume one).

For every recommendation also include:
- confidence: a number from 0.0 to 1.0.
- rationale: one sentence explaining your reasoning.

Respond with ONLY a JSON array of recommendation objects -- no prose, no
markdown fences, no wrapping object.
""".strip()


def build_llm_payload(diff: MappingDiffResult, df: pd.DataFrame, mapping: pd.DataFrame) -> dict:
    existing_role_names = sorted({
        r for r in mapping["role_name"] if isinstance(r, str) and r.strip()
    })
    existing_multiselect_groups = sorted({
        g for g in mapping["group_name"] if isinstance(g, str) and g.strip()
    })

    unmatched_old_roles = [
        {
            "raw_index": r.raw_index,
            "header": r.header,
            "role_type": r.role_type,
            "role_name": r.role_name or None,
            "group_name": r.group_name or None,
            "option_label": r.option_label or None,
        }
        for r in diff.unmatched_rows()
    ]

    unmatched_new_csv_columns = []
    for c in diff.unmatched_csv_columns():
        series = df.iloc[:, c.csv_index].astype(str).str.strip()
        samples = [v for v in series.unique().tolist() if v][:SAMPLE_VALUES_PER_COLUMN]
        unmatched_new_csv_columns.append({
            "csv_index": c.csv_index, "header": c.header, "sample_values": samples,
        })

    return {
        "existing_role_names": existing_role_names,
        "existing_multiselect_groups": existing_multiselect_groups,
        "unmatched_old_roles": unmatched_old_roles,
        "unmatched_new_csv_columns": unmatched_new_csv_columns,
    }


def _clamp_confidence(v) -> float:
    try:
        return max(0.0, min(1.0, float(v)))
    except (TypeError, ValueError):
        return 0.0


def _dedupe_role_name(candidate: str, taken: set[str]) -> str:
    base = candidate.strip().lower().replace(" ", "_") or "new_role"
    name = base
    n = 2
    while name in taken:
        name = f"{base}_{n}"
        n += 1
    return name


def _validate_and_repair(raw_items: list, diff: MappingDiffResult, mapping: pd.DataFrame) -> list[dict]:
    valid_old_idx = {r.raw_index for r in diff.unmatched_rows()}
    valid_new_idx = {c.csv_index for c in diff.unmatched_csv_columns()}

    taken_role_names = {r for r in mapping["role_name"] if isinstance(r, str) and r.strip()}
    existing_groups = {g for g in mapping["group_name"] if isinstance(g, str) and g.strip()}
    existing_options_per_group: dict[str, set[str]] = {}
    for _, row in mapping[mapping["role_type"] == "multiselect_option"].iterrows():
        existing_options_per_group.setdefault(row["group_name"], set()).add(row["option_label"])

    covered_old: set[int] = set()
    covered_new: set[int] = set()
    repaired: list[dict] = []

    def _empty_new_question_fields() -> dict:
        return {
            "suggested_role_type": None, "suggested_role_name": None,
            "suggested_group_name": None, "suggested_option_label": None,
            "suggested_applies_to": None,
        }

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
                **_empty_new_question_fields(),
            })

        elif item_type == "dropped":
            old_idx = item.get("old_raw_index")
            if old_idx not in valid_old_idx:
                continue
            covered_old.add(old_idx)
            repaired.append({
                "type": "dropped", "confidence": confidence, "rationale": rationale,
                "old_raw_index": old_idx, "new_csv_index": None,
                **_empty_new_question_fields(),
            })

        elif item_type == "new_question":
            new_idx = item.get("new_csv_index")
            if new_idx not in valid_new_idx:
                continue
            covered_new.add(new_idx)

            role_type = item.get("suggested_role_type")
            notes = []
            if role_type not in ALLOWED_NEW_ROLE_TYPES:
                notes.append(f"unsupported role type {role_type!r} coerced to unused")
                role_type = "unused"

            role_name = group_name = option_label = None
            applies_to = item.get("suggested_applies_to") or None

            if role_type in ("quant_indicator", "qual_supplementary"):
                role_name = _dedupe_role_name(str(item.get("suggested_role_name") or f"new_col_{new_idx}"), taken_role_names)
                taken_role_names.add(role_name)
            elif role_type == "multiselect_option":
                candidate_group = str(item.get("suggested_group_name") or "").strip()
                candidate_option = str(item.get("suggested_option_label") or "").strip()
                if candidate_group not in existing_groups or not candidate_option:
                    notes.append("multiselect group missing/unrecognized; downgraded to qual_supplementary")
                    role_type = "qual_supplementary"
                elif candidate_option in existing_options_per_group.get(candidate_group, set()):
                    notes.append(f"option label already exists in group {candidate_group!r}; downgraded to qual_supplementary")
                    role_type = "qual_supplementary"
                else:
                    group_name, option_label = candidate_group, candidate_option
                    existing_options_per_group.setdefault(group_name, set()).add(option_label)

                if role_type == "qual_supplementary":  # downgraded above
                    role_name = _dedupe_role_name(str(item.get("suggested_role_name") or f"new_col_{new_idx}"), taken_role_names)
                    taken_role_names.add(role_name)

            full_rationale = rationale if not notes else f"{rationale} ({'; '.join(notes)})"
            repaired.append({
                "type": "new_question", "confidence": confidence, "rationale": full_rationale,
                "old_raw_index": None, "new_csv_index": new_idx,
                "suggested_role_type": role_type, "suggested_role_name": role_name,
                "suggested_group_name": group_name, "suggested_option_label": option_label,
                "suggested_applies_to": applies_to,
            })

    # Synthetic fallback for anything the LLM left uncovered, so every
    # residual item always has exactly one recommendation card.
    for idx in sorted(valid_old_idx - covered_old):
        repaired.append({
            "type": "dropped", "confidence": 0.0,
            "rationale": "No recommendation returned by the model for this role; treated as dropped pending review.",
            "old_raw_index": idx, "new_csv_index": None,
            **_empty_new_question_fields(),
        })
    for idx in sorted(valid_new_idx - covered_new):
        repaired.append({
            "type": "new_question", "confidence": 0.0,
            "rationale": "No recommendation returned by the model for this column; recorded as unused pending review.",
            "old_raw_index": None, "new_csv_index": idx,
            "suggested_role_type": "unused", "suggested_role_name": None,
            "suggested_group_name": None, "suggested_option_label": None, "suggested_applies_to": None,
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
            "old_role_type": old_row.role_type if old_row else None,
            "old_role_name": (old_row.role_name or None) if old_row else None,
            "old_group_name": (old_row.group_name or None) if old_row else None,
            "old_option_label": (old_row.option_label or None) if old_row else None,
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
        log.warning("GEDSI reconciliation LLM response was not valid JSON; falling back to synthetic recommendations.")
        raw_items = []

    repaired = _validate_and_repair(raw_items, diff, mapping)
    return _enrich(repaired, diff, col_names)


def _verify_mapping(csv_path: Path, mapping_path: Path) -> tuple[bool, list[str]]:
    """Lighter re-verification than Cupboard Week's 4-stage data_loader
    replay: GENDSI's own stage 1 (build_response_frame) already loads the
    CSV, resolves every role, and asserts no PII column leaked through --
    that's everything a reconciled mapping needs proven against."""
    try:
        role_map = gedsi_mapping.load_role_map(mapping_path)
        build_response_frame(csv_path, role_map)
    except Exception as exc:
        log.warning(f"GEDSI mapping verification failed for {mapping_path}: {exc}")
        return False, [str(exc)]
    return True, []


def _build_reconciled_mapping(
    mapping: pd.DataFrame,
    diff: MappingDiffResult,
    col_names: list[str],
    recommendations: list[dict],
    decisions: dict[str, bool],
    upload_id: str,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Builds the reconciled mapping table for one upload.

    Two kinds of correction happen here, and only one of them ever involves
    a human/LLM judgment call:
      1. Auto-applied moved-row corrections (diff.all_moved_rows()) -- these
         were already resolved unambiguously by unique header text, for
         EVERY row including pii_drop/unused ones that never surface as a
         recommendation. Unlike Cupboard Week's data_loader_transformer,
         GENDSI's ingest.build_response_frame() does no such re-resolution
         at runtime, so if reconciliation doesn't persist these, a column
         that silently shifted position (e.g. because an unrelated column
         earlier in the file was dropped) would silently read from the
         wrong place forever.
      2. Recommendation-driven patches (rename/dropped/new_question) --
         genuinely ambiguous changes a human explicitly approved or
         rejected.
    """
    working = mapping.copy().set_index("raw_index", drop=False)

    for moved in diff.all_moved_rows():
        working.loc[moved.raw_index, "raw_index"] = moved.matched_csv_index
        working.loc[moved.raw_index, "raw_column_header"] = col_names[moved.matched_csv_index]

    renamed_count = new_question_count = dropped_count = 0
    to_drop: list[int] = []
    claimed_new_idx: set[int] = set()
    next_raw_index = int(working["raw_index"].max()) + 1 if len(working) else 0

    for rec in recommendations:
        approved = decisions.get(rec["id"], False)
        rec["approved"] = approved
        if not approved:
            continue

        if rec["type"] == "rename":
            old_idx = rec["old_raw_index"]
            if old_idx in working.index:
                working.loc[old_idx, "raw_index"] = rec["new_csv_index"]
                working.loc[old_idx, "raw_column_header"] = rec["new_header"]
                claimed_new_idx.add(rec["new_csv_index"])
                renamed_count += 1

        elif rec["type"] == "dropped":
            old_idx = rec["old_raw_index"]
            if old_idx in working.index:
                to_drop.append(old_idx)
                dropped_count += 1

        elif rec["type"] == "new_question":
            new_row = {
                "raw_index": rec["new_csv_index"],
                "raw_column_header": rec["new_header"],
                "role_type": rec["suggested_role_type"],
                "role_name": rec.get("suggested_role_name") or "",
                "group_name": rec.get("suggested_group_name") or "",
                "option_label": rec.get("suggested_option_label") or "",
                "applies_to": rec.get("suggested_applies_to") or "",
                "notes": f"reconciled: LLM-proposed (upload {upload_id})",
            }
            working.loc[next_raw_index] = new_row
            next_raw_index += 1
            claimed_new_idx.add(rec["new_csv_index"])
            new_question_count += 1

    if to_drop:
        working = working.drop(index=to_drop)

    # Fill any still-uncovered new CSV column (a rejected/ignored
    # recommendation) with a synthetic "unused" row, preserving Phase 1's
    # 100%-column-coverage invariant. Purely bookkeeping: ingest.py never
    # reads a role it doesn't have, so this changes nothing behaviorally.
    covered = set(int(i) for i in working["raw_index"]) | claimed_new_idx
    for rec in recommendations:
        if rec["type"] == "new_question" and not decisions.get(rec["id"], False):
            idx = rec["new_csv_index"]
            if idx not in covered:
                working.loc[next_raw_index] = {
                    "raw_index": idx, "raw_column_header": col_names[idx],
                    "role_type": "unused", "role_name": "", "group_name": "",
                    "option_label": "", "applies_to": "",
                    "notes": f"reconciled: recommendation not approved (upload {upload_id})",
                }
                next_raw_index += 1
                covered.add(idx)

    working = working.reset_index(drop=True)
    counts = {"renamed_count": renamed_count, "new_question_count": new_question_count, "dropped_count": dropped_count}
    return working, counts


def _verify_and_promote(upload_id: str, working: pd.DataFrame) -> tuple[bool, list[str]]:
    verify_mapping_path = upload_verify_mapping_path(upload_id)
    working.to_csv(verify_mapping_path, index=False, columns=MAPPING_FIELDNAMES)

    passed, errors = _verify_mapping(upload_csv_path(upload_id), verify_mapping_path)

    if passed:
        verify_mapping_path.replace(upload_mapping_path(upload_id))
    else:
        verify_mapping_path.unlink(missing_ok=True)
    return passed, errors


# ---------------------------------------------------------------------------
# validate_dataset
# ---------------------------------------------------------------------------

def validate_dataset(upload_id: str, llm: LlmConfig) -> dict:
    csv_path = upload_csv_path(upload_id)
    col_names = gedsi_mapping_diff.read_csv_header_row(csv_path)
    mapping = gedsi_mapping_diff.load_mapping_table(CANONICAL_MAPPING_PATH)

    diff = gedsi_mapping_diff.diff_columns(mapping, col_names)
    if not diff.has_residual:
        if diff.all_moved_rows():
            # Nothing needs a human decision, but at least one column
            # (possibly one that never surfaces as a recommendation, like
            # pii_drop/unused) shifted position and was resolved
            # unambiguously by header text. Persist that silently, the same
            # way Cupboard Week's runtime transformer self-heals it on every
            # run -- GENDSI's ingest has no equivalent runtime resolution,
            # so reconciliation has to be the one to fix it up front.
            working, _counts = _build_reconciled_mapping(mapping, diff, col_names, [], {}, upload_id)
            passed, errors = _verify_and_promote(upload_id, working)
            if not passed:
                # Extremely unlikely (a pure header-text-resolved move
                # failing PII/role validation) but surface it rather than
                # silently claiming "clean" over a mapping that won't load.
                raise RuntimeError(f"Auto-reconciled mapping failed verification: {errors}")
        return {"clean": True, "recommendations": [], "residual_old_count": 0, "residual_new_count": 0}

    df = pd.read_csv(csv_path, delimiter=";", encoding="utf-8-sig", dtype=str, keep_default_na=False, low_memory=False)
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

    csv_path = upload_csv_path(upload_id)
    col_names = gedsi_mapping_diff.read_csv_header_row(csv_path)
    mapping = gedsi_mapping_diff.load_mapping_table(CANONICAL_MAPPING_PATH)
    diff = gedsi_mapping_diff.diff_columns(mapping, col_names)

    working, counts = _build_reconciled_mapping(mapping, diff, col_names, recommendations, decisions, upload_id)

    # Persist the approve/reject decisions back onto the stored recommendation set.
    with open(rec_path, "w", encoding="utf-8") as f:
        json.dump(recommendations, f, indent=2, ensure_ascii=False)

    passed, errors = _verify_and_promote(upload_id, working)

    return {
        "validator_passed": passed,
        "errors": errors,
        "warnings": [],
        **counts,
    }
