"""
Stage 0/1 -- schema mapping (validated against a RoleMap, see mapping.py) +
ingest & clean.

Produces work/response_frame.parquet: one row per in-scope, consenting,
de-duplicated respondent, PII columns dropped, sex/disability normalized,
multi-select groups decoded into boolean columns, response_id minted from
the platform's own _uuid. Screening (test/QA rows, exact-content duplicate
submissions, non-consenting respondents, out-of-scope-country respondents)
is aligned with the Cupboard Week pipeline's data_loader_screening.py -- see
screening.py -- so both reports describe the same population from the same
raw export.
"""
from __future__ import annotations

import csv
import json
import uuid
from pathlib import Path

import pandas as pd

from gedsi_pipeline import config, mapping, screening
from gedsi_pipeline.mapping import RoleMap


def _read_raw_rows(csv_path=config.RAW_CSV_PATH) -> tuple[list[str], list[list[str]]]:
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter=";")
        header = next(reader)
        rows = [row for row in reader]
    return header, rows


def _clean_str(v: str | None) -> str | None:
    if v is None:
        return None
    v = v.strip()
    return v if v else None


def _strip_option_prefix(v: str | None) -> str | None:
    """'a. Male' -> 'Male', 'b. No' -> 'No'."""
    v = _clean_str(v)
    if v is None:
        return None
    if len(v) > 3 and v[1:3] == ". ":
        return v[3:].strip()
    return v


def build_response_frame(csv_path=None, role_map: RoleMap | None = None) -> tuple[pd.DataFrame, dict]:
    csv_path = csv_path or config.RAW_CSV_PATH
    role_map = role_map or config.DEFAULT_ROLE_MAP
    mapping.validate_role_map_against_csv(role_map, csv_path)
    header, rows = _read_raw_rows(csv_path)

    records = []
    for row in rows:
        # Pad short rows (shouldn't happen, but guards against ragged CSV rows)
        if len(row) < len(header):
            row = row + [""] * (len(header) - len(row))

        consent = _clean_str(row[role_map.consent_col])
        consent_ok = not (consent is None or consent.lower().startswith("b"))

        rec = {
            "response_id": _clean_str(row[role_map.uuid_col]) or str(uuid.uuid4()),
            # Screening-only: read here so duplicate/test-row detection can
            # use them, dropped again by screening.screen() before this
            # frame is ever written or reported on.
            "_client_id_raw": _clean_str(row[role_map.client_id_col]) if role_map.client_id_col is not None else None,
            "_enumerator_raw": _clean_str(row[role_map.enumerator_col]) if role_map.enumerator_col is not None else None,
            "_consent_ok": consent_ok,
            "region": _clean_str(row[role_map.demographic_cols["region"]]),
            "country": _clean_str(row[role_map.demographic_cols["country"]]),
            "branch": _clean_str(row[role_map.demographic_cols["branch"]]),
            "insurance_type": _clean_str(row[role_map.demographic_cols["insurance_type"]]),
            "age": _clean_str(row[role_map.demographic_cols["age"]]),
            "education": _strip_option_prefix(row[role_map.demographic_cols["education"]]),
            "household_size": _clean_str(row[role_map.demographic_cols["household_size"]]),
            "sex": _strip_option_prefix(row[role_map.demographic_cols["sex"]]),
            "disability": _strip_option_prefix(row[role_map.demographic_cols["disability"]]),
        }

        # Single-response quant indicators
        for role, (idx, _applies_to) in role_map.quant_indicators.items():
            rec[role] = _strip_option_prefix(row[idx]) if idx < len(row) else None

        # Multi-select groups -> one boolean column per option
        for group_name, (_parent_idx, options) in role_map.multiselect_groups.items():
            for option_label, col_idx in options.items():
                flag_col = f"{group_name}__{option_label}"
                val = row[col_idx] if col_idx < len(row) else ""
                rec[flag_col] = str(val).strip() == "1"

        # Primary qualitative free text
        for role, idx in role_map.qual_primary.items():
            rec[role] = _clean_str(row[idx]) if idx < len(row) else None

        # Supplementary qualitative free text
        for role, idx in role_map.qual_supplementary.items():
            rec[role] = _clean_str(row[idx]) if idx < len(row) else None

        records.append(rec)

    df = pd.DataFrame.from_records(records)

    # Typed columns
    df["age"] = pd.to_numeric(df["age"], errors="coerce")
    df["household_size"] = pd.to_numeric(df["household_size"], errors="coerce")
    df["nps_score"] = pd.to_numeric(df["nps_score"], errors="coerce")

    def nps_category(score):
        if pd.isna(score):
            return None
        if score >= 9:
            return "Promoter"
        if score >= 7:
            return "Passive"
        return "Detractor"

    df["nps_category"] = df["nps_score"].apply(nps_category)
    df["disability_flag"] = df["disability"].eq("Yes")

    n_raw = len(rows)
    df, screen_stats = screening.screen(df)
    screen_stats["n_raw"] = n_raw
    screen_stats["n_final"] = len(df)

    print(
        f"Ingest: {n_raw} raw rows -> {len(df)} in-scope respondents "
        f"({screen_stats['n_test_removed']} test/QA, "
        f"{screen_stats['n_duplicates_removed']} duplicate, "
        f"{screen_stats['n_non_consenting_removed']} non-consenting, "
        f"{screen_stats['n_out_of_scope_removed']} out-of-scope-country removed)."
    )
    return df, screen_stats


def main(csv_path=None, role_map: RoleMap | None = None, work_dir: Path | None = None):
    df, screen_stats = build_response_frame(csv_path, role_map)
    work_dir = work_dir or config.WORK_DIR
    response_frame_path = work_dir / "response_frame.parquet"
    work_dir.mkdir(parents=True, exist_ok=True)
    df.to_parquet(response_frame_path, index=False)
    print(f"Wrote {response_frame_path} ({len(df)} rows, {len(df.columns)} columns)")

    screening_summary_path = work_dir / "screening_summary.json"
    screening_summary_path.write_text(json.dumps(screen_stats, indent=2), encoding="utf-8")
    print(f"Wrote {screening_summary_path}")

    # Sanity summary
    print("\nSex counts:\n", df["sex"].value_counts(dropna=False))
    print("\nDisability counts:\n", df["disability"].value_counts(dropna=False))
    print("\nCountry counts:\n", df["country"].value_counts(dropna=False))
    print("\nInsurance type counts:\n", df["insurance_type"].value_counts(dropna=False))
    pii_terms = ["username", "device info", "client's id number"]
    leaked = [c for c in df.columns if any(t in c.lower() for t in pii_terms)]
    assert not leaked, f"PII columns leaked into response frame: {leaked}"
    screening_leaked = [c for c in df.columns if c in ("_client_id_raw", "_enumerator_raw", "_consent_ok")]
    assert not screening_leaked, f"Screening-only transient columns leaked into response frame: {screening_leaked}"
    print("\nNo PII columns present. OK.")


if __name__ == "__main__":
    main()
