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


def _build_response_record(row_id: str, text: str, row: pd.Series,
                            col_cfg: dict) -> dict:
    """Build enriched response dict for one respondent's answer."""
    rec = {
        "id": row_id,
        "text": str(text).strip(),
        "sex": str(row.get("q_sex", "")) or None,
        "client_age": (None if pd.isna(row.get("q_client_age"))
                       else int(row["q_client_age"])),
        "branch": str(row.get("branch", "")) or None,
        "is_claimant": (False if pd.isna(row.get("flag_paid_claimant"))
                        else bool(row["flag_paid_claimant"])),
        # Canonical caregiver definition (matches analysis_engine/segments.py's
        # "caregiver" segment): answered Yes OR No to child wellbeing (i.e. has
        # children to report on) -- NOT "Yes" only, which would wrongly exclude
        # caregivers whose child's wellbeing did not improve.
        "is_caregiver": bool(row.get("flag_child_wellbeing_denominator", False)),
        "is_female": (str(row.get("q_sex", "")) == "Female"),
    }
    # NPS-specific enrichment
    if col_cfg["group"] == "nps":
        rec["nps_group"] = col_cfg["nps_group"]
        rec["nps_score"] = (None if pd.isna(row.get("q_nps_score"))
                            else int(row["q_nps_score"]))
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

        for idx in df.index:
            raw = df.at[idx, key]
            if pd.isna(raw):
                continue
            text = str(raw).strip()
            if len(text) < min_len:
                continue

            row_id = f"row_{idx:04d}"
            rec = _build_response_record(row_id, text, df.loc[idx], col_cfg)

            if group == "nps":
                nps_grp = col_cfg["nps_group"]
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
