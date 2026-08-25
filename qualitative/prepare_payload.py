"""qualitative/prepare_payload.py

Phase 1: Read survey parquet, build enriched JSON payload for Gemini.
"""
import json
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent

CONFIG_PATH = ROOT / "qualitative" / "config.yaml"
PARQUET_PATH = ROOT / "data" / "survey_clean.parquet"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _nps_bucket_for_score(score: "int | None", thresholds: dict) -> "str | None":
    """Resolve a respondent's promoter/passive/detractor bucket from their
    own q_nps_score, using the same thresholds Africa's three separate
    conditional columns implicitly encode via which column got filled.
    Needed for a schema like LARCO's, which asks one always-on NPS
    follow-up instead of three score-gated ones (see column_cfg's
    nps_group == "by_score" below) -- the raw column alone can't tell you
    which bucket a response belongs to, only the respondent's score can.
    """
    if score is None:
        return None
    if score >= thresholds["promoter_min"]:
        return "promoter"
    if score >= thresholds["passive_min"]:
        return "passive"
    return "detractor"  # <= detractor_max by construction (contiguous thresholds)


def _build_response_record(row_id: str, text: str, row: pd.Series,
                            group: str, nps_group: "str | None") -> dict:
    """Build enriched response dict for one respondent's answer."""
    rec = {
        "id": row_id,
        "text": str(text).strip(),
        "sex": str(row.get("q_sex", "")) or None,
        "client_age": (None if pd.isna(row.get("q_client_age"))
                       else int(row["q_client_age"])),
        "branch": str(row.get("branch", "")) or None,
        "country": str(row.get("country", "")) or None,
        # Canonical claimant definition (matches analysis_engine/segments.py's
        # "claimant" segment and Part 6's own scorecard): q_claim_submitted,
        # NOT flag_paid_claimant -- the latter is narrower (claim approved AND
        # paid out), which silently excluded claimants whose claim was denied
        # or still pending. Found during R-006a Stage 1 (docs/report_spec.md)
        # while computing Part 6's sentiment base: this flag disagreed with
        # the report's own "55 claimants" figure by 6 respondents.
        "is_claimant": (False if pd.isna(row.get("q_claim_submitted"))
                        else bool(row["q_claim_submitted"])),
        # Canonical caregiver definition (matches analysis_engine/segments.py's
        # "caregiver" segment): answered Yes OR No to child wellbeing (i.e. has
        # children to report on) -- NOT "Yes" only, which would wrongly exclude
        # caregivers whose child's wellbeing did not improve.
        "is_caregiver": bool(row.get("flag_child_wellbeing_denominator", False)),
        "is_female": (str(row.get("q_sex", "")) == "Female"),
    }
    # NPS-specific enrichment
    if group == "nps":
        rec["nps_group"] = nps_group
        rec["nps_score"] = (None if pd.isna(row.get("q_nps_score"))
                            else int(row["q_nps_score"]))
        # worth_premium doesn't exist for every schema (e.g. LARCO -- see
        # data_loader_larco/column_mapping.csv) -- row.get() already
        # returns None for a missing column via pd.Series.get(), so this
        # degrades to "not worth it = False / unknown" rather than raising.
        rec["worth_premium_value"] = (
            None if pd.isna(row.get("q_worth_premium"))
            else int(row["q_worth_premium"]))
        rec["not_worth_it"] = (
            False if pd.isna(row.get("q_worth_premium"))
            else int(row["q_worth_premium"]) >= 4)
    return rec


def build_payload(df: pd.DataFrame, config: dict,
                  min_len: int = None) -> dict:
    """Build the complete payload dict to send to Gemini."""
    if min_len is None:
        min_len = config.get("min_text_length", 10)

    payload = {
        "nps_promoters": [],
        "nps_passives": [],
        "nps_detractors": [],
        "claim_no_reason_other": [],
        "claim_challenges_other_support": [],
        "sparse_other": [],
    }

    for col_cfg in config["columns"]:
        key = col_cfg["key"]
        if key not in df.columns:
            continue

        group = col_cfg["group"]
        # "by_score" (LARCO's single always-on NPS follow-up column) is
        # resolved per-row below via q_nps_score; a fixed value (Africa's
        # three score-gated columns) is the same for every row in this column.
        fixed_nps_group = col_cfg.get("nps_group") if group == "nps" else None
        by_score = fixed_nps_group == "by_score"

        for idx in df.index:
            raw = df.at[idx, key]
            if pd.isna(raw):
                continue
            text = str(raw).strip()
            if len(text) < min_len:
                continue

            row = df.loc[idx]
            nps_grp = fixed_nps_group
            if group == "nps" and by_score:
                score = None if pd.isna(row.get("q_nps_score")) else int(row["q_nps_score"])
                nps_grp = _nps_bucket_for_score(score, config["nps_thresholds"])
                if nps_grp is None:
                    continue  # no score to bucket this response by -- skip rather than guess

            row_id = f"row_{idx:04d}"
            rec = _build_response_record(row_id, text, row, group, nps_grp)

            if group == "nps":
                if nps_grp == "promoter":
                    payload["nps_promoters"].append(rec)
                elif nps_grp == "passive":
                    payload["nps_passives"].append(rec)
                else:
                    payload["nps_detractors"].append(rec)

            elif group == "claims_other":
                if key in ("q_claim_challenges__other_text",
                           "q_claim_challenges__support_text"):
                    rec["source_column"] = key
                    payload["claim_challenges_other_support"].append(rec)
                else:
                    rec["source_column"] = key
                    payload["claim_no_reason_other"].append(rec)

            else:  # sparse_other
                rec["source_column"] = key
                rec["question_context"] = col_cfg["question_context"]
                payload["sparse_other"].append(rec)

    return payload


def print_payload_stats(payload: dict) -> None:
    total_responses = sum(len(v) for v in payload.values())
    total_chars = len(json.dumps(payload, ensure_ascii=False))
    print("── Payload statistics ───────────────────────────────")
    for group, items in payload.items():
        print(f"  {group:<35}: {len(items):>4} responses")
    print(f"  {'TOTAL responses':<35}: {total_responses:>4}")
    print(f"  {'Total characters':<35}: {total_chars:>8,}")
    print(f"  {'Estimated input tokens (~4 chars)':<35}: {total_chars // 4:>8,}")
    print("─────────────────────────────────────────────────────")


def main() -> None:
    config = load_config()
    df = pd.read_parquet(PARQUET_PATH)
    payload = build_payload(df, config)
    print_payload_stats(payload)


if __name__ == "__main__":
    main()
