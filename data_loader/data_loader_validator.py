"""
data_loader_validator.py — VisionFund Insurance Survey Data Loader
Step 5 of 5: Validate survey_clean.parquet and write data_quality_report.md.

Usage:
    python data_loader/data_loader_validator.py --output-dir runs/2026_Q3
"""

import sys
import argparse
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from report_spec import load_spec

SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXPECTED_DTYPES: dict[str, set[str]] = {
    "likert_4":       {"Int8"},
    "likert_5":       {"Int8"},
    "binary":         {"boolean"},
    "single_select":  {"category"},
    "multi_select_n": {"object"},
    "multi_select_2": {"object"},
    "numeric_open":   {"Int16"},
    "open_text":      {"string", "str"},
}

RANGE_CHECKS = [
    ("q_nps_score",                   0,   10, "0–10"),
    ("q_coverage_understanding",       1,    4, "1–4"),
    ("q_claim_process_understanding",  1,    4, "1–4"),
    ("q_financial_stress",             1,    5, "1–5"),
    ("q_confidence_pay",               1,    5, "1–5"),
    ("q_worth_premium",                1,    5, "1–5"),
    ("q_renewal_intent",               1,    5, "1–5"),
    ("q_client_age",                  18,  100, "18–100"),
]

SCOPE_CHECKS: dict[str, dict] = {
    "health": {
        "flag": "is_health",
        "cols": ["q_healthcare_access", "q_medical_cost_change"],
    },
    "crop": {
        "flag": "is_crop",
        "cols": ["q_crop_recovery_speed", "q_crop_farming_change", "q_renewal_intent"],
    },
    "credit_life": {
        "flag": "is_credit_life",
        "cols": [
            "q_credit_other_benefits",
            "q_credit_other_benefits__a",
            "q_credit_other_benefits__b",
            "q_credit_other_benefits__c",
            "q_credit_other_benefits__d",
            "q_credit_other_benefits__e",
            "q_credit_additional_value",
        ],
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def dtype_str(series: pd.Series) -> str:
    return str(series.dtype)


def filled_mask(series: pd.Series) -> pd.Series:
    """Boolean mask: True where the cell carries a value (non-null / non-empty-list).

    For object-dtype columns (list columns), empty list [] is treated as not-filled.
    PyArrow may return pyarrow.ListScalar objects; .as_py() converts them to Python.
    """
    if dtype_str(series) != "object":
        return series.notna()

    def _filled(x) -> bool:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return False
        if hasattr(x, "as_py"):
            x = x.as_py()
            return x is not None and bool(x)
        try:
            return len(x) > 0
        except TypeError:
            return bool(x)

    return series.apply(_filled)


# ---------------------------------------------------------------------------
# Check 1 — Spec alignment
# ---------------------------------------------------------------------------

def check_1_spec_alignment(df: pd.DataFrame, spec) -> tuple[list, list[str], list[str]]:
    rows: list = []
    errors: list[str] = []
    warnings: list[str] = []

    for sq in spec.all_source_questions():
        qref = sq.question_ref
        rtype = sq.response_type.value if sq.response_type else None

        if qref not in df.columns:
            errors.append(f"Check 1: '{qref}' missing from parquet (spec type: {rtype})")
            rows.append((qref, rtype or "—", "—", "FAIL ✗", "Column absent from parquet"))
            continue

        actual = dtype_str(df[qref])

        if rtype is None:
            rows.append((qref, "—", actual, "PASS ✓", "No response_type in spec"))
            continue

        if rtype not in EXPECTED_DTYPES:
            rows.append((qref, rtype, actual, "PASS ✓", f"response_type '{rtype}' not dtype-validated"))
            continue

        acceptable = EXPECTED_DTYPES[rtype]
        if actual in acceptable:
            rows.append((qref, rtype, actual, "PASS ✓", ""))
        elif qref == "q_sex" and actual == "category":
            warnings.append(
                f"Check 1: {qref} stored as 'category' (Male/Female labels) — "
                "intentional deviation from binary spec type"
            )
            rows.append((qref, rtype, actual, "WARN ⚠", "Intentional: stores labels Male/Female as category"))
        else:
            errors.append(
                f"Check 1: '{qref}' dtype mismatch — spec={rtype}, "
                f"expected one of {sorted(acceptable)}, got '{actual}'"
            )
            rows.append((qref, rtype, actual, "FAIL ✗", f"Expected {sorted(acceptable)}, got '{actual}'"))

    return rows, errors, warnings


# ---------------------------------------------------------------------------
# Check 2 — Value range checks
# ---------------------------------------------------------------------------

def check_2_value_ranges(df: pd.DataFrame) -> tuple[list, list[str]]:
    rows: list = []
    errors: list[str] = []

    for col, lo, hi, rng in RANGE_CHECKS:
        if col not in df.columns:
            errors.append(f"Check 2: column '{col}' missing from parquet")
            rows.append((col, rng, "—", "FAIL ✗ (missing)"))
            continue

        valid = df[col].notna()
        in_range = valid & (df[col] >= lo) & (df[col] <= hi)
        violations = int(valid.sum()) - int(in_range.sum())

        if violations > 0:
            status = f"FAIL ✗ ({violations} row(s))"
            errors.append(f"Check 2: '{col}' has {violations} value(s) outside [{lo}, {hi}]")
        else:
            status = "PASS ✓"

        rows.append((col, rng, str(violations), status))

    return rows, errors


# ---------------------------------------------------------------------------
# Check 3 — Skip-logic consistency
# ---------------------------------------------------------------------------

def check_3_skip_logic(df: pd.DataFrame) -> tuple[list, list[str], list[str]]:
    rows: list = []
    errors: list[str] = []
    warnings: list[str] = []

    insured_true   = df["q_insured_event_12m"] == True   # noqa: E712
    submitted_false = df["q_claim_submitted"]  == False  # noqa: E712
    submitted_true  = df["q_claim_submitted"]  == True   # noqa: E712
    child_yes = df["q_child_wellbeing"] == "Yes"

    checks = [
        ("SL-1", "q_claim_submitted non-null only where q_insured_event_12m == True",
         "q_claim_submitted", insured_true),
        ("SL-2", "q_no_claim_reason non-null only where q_claim_submitted == False",
         "q_no_claim_reason", submitted_false),
        ("SL-3", "q_claim_result non-null only where q_claim_submitted == True",
         "q_claim_result", submitted_true),
        ("SL-4", "q_claim_challenges_experienced non-null only where q_claim_submitted == True",
         "q_claim_challenges_experienced", submitted_true),
        ("SL-5", "q_child_improvements non-empty list only where q_child_wellbeing == 'Yes'",
         "q_child_improvements", child_yes),
        ("SL-6", "flag_negative_coping non-null only where q_insured_event_12m == True",
         "flag_negative_coping", insured_true),
    ]

    for check_id, desc, col, valid_mask in checks:
        if col not in df.columns:
            errors.append(f"Check 3 {check_id}: column '{col}' missing from parquet")
            rows.append((check_id, desc, "—", "—", "—", "FAIL ✗ (missing)"))
            continue

        should_be_null = ~valid_mask
        base_n = int(should_be_null.sum())
        is_filled = filled_mask(df[col])
        violations = int((is_filled & should_be_null).sum())
        pct = violations / base_n * 100 if base_n > 0 else 0.0

        if violations > 0 and pct > 1.0:
            status = "FAIL ✗"
            errors.append(
                f"Check 3 {check_id}: {violations} violations ({pct:.2f}% of "
                f"{base_n} at-risk rows — exceeds 1% threshold)"
            )
        elif violations > 0:
            status = "WARN ⚠"
            warnings.append(
                f"Check 3 {check_id}: {violations} violations ({pct:.2f}% of {base_n} at-risk rows)"
            )
        else:
            status = "PASS ✓"

        rows.append((check_id, desc, str(base_n), str(violations), f"{pct:.2f}%", status))

    return rows, errors, warnings


# ---------------------------------------------------------------------------
# Check 4 — Insurance-type scope
# ---------------------------------------------------------------------------

def check_4_scope(df: pd.DataFrame) -> tuple[list, list[str]]:
    rows: list = []
    errors: list[str] = []

    for scope_name, cfg in SCOPE_CHECKS.items():
        flag_col = cfg["flag"]
        in_scope = df[flag_col] == True  # noqa: E712
        out_of_scope = ~in_scope

        for col in cfg["cols"]:
            if col not in df.columns:
                errors.append(f"Check 4: column '{col}' missing from parquet")
                rows.append((col, scope_name, "—", "FAIL ✗ (missing)"))
                continue

            is_filled = filled_mask(df[col])
            violations = int((is_filled & out_of_scope).sum())

            if violations > 0:
                status = "FAIL ✗"
                errors.append(
                    f"Check 4: '{col}' has {violations} non-null row(s) outside {scope_name} scope"
                )
            else:
                status = "PASS ✓"

            rows.append((col, scope_name, str(violations), status))

    return rows, errors


# ---------------------------------------------------------------------------
# Check 5 — Derived variable sanity (structural — no exact counts)
# ---------------------------------------------------------------------------

def check_5_derived(df: pd.DataFrame, target_country: "str | None" = None) -> tuple[list, list[str], list[str]]:
    """Structural checks that hold for any quarterly dataset.

    target_country: the country this run was scoped to (see
    data_loader_screening.py's country filter), or None for the default
    multi-country portfolio. Mirrors data_loader_derived.py's own
    run_assertions() -- this check is intentionally a separate,
    independent re-verification (not shared code), so it needs the same
    country-scope awareness applied to it directly rather than inherited.
    """
    rows: list = []
    errors: list[str] = []
    warnings: list[str] = []

    insured_true = df["q_insured_event_12m"] == True  # noqa: E712

    # ── flag_negative_coping ────────────────────────────────────────────────

    neg_true = int(df["flag_negative_coping"].sum())
    n_in_scope = int(insured_true.sum())
    ok_pos = neg_true > 0
    rows.append(("flag_negative_coping — True count", "> 0", str(neg_true),
                 "PASS ✓" if ok_pos else ("WARN ⚠" if target_country else "FAIL ✗")))
    if not ok_pos:
        if target_country:
            warnings.append(
                f"Check 5: flag_negative_coping has zero True values out of {n_in_scope} "
                f"insured-event respondents in country-scoped run ({target_country!r}) — "
                "not treated as an error"
            )
        else:
            errors.append("Check 5: flag_negative_coping has zero True values — likely a coding error")

    out_scope_not_na = int(df["flag_negative_coping"][~insured_true].notna().sum())
    ok_scope = out_scope_not_na == 0
    rows.append(("flag_negative_coping — non-NaN outside insured-event rows",
                 "= 0 violations", str(out_scope_not_na), "PASS ✓" if ok_scope else "FAIL ✗"))
    if not ok_scope:
        errors.append(
            f"Check 5: flag_negative_coping has {out_scope_not_na} non-NaN value(s) "
            "outside insured-event rows"
        )

    # ── flag_promoter ────────────────────────────────────────────────────────

    ok_promo_dtype = dtype_str(df["flag_promoter"]) == "boolean"
    rows.append(("flag_promoter — dtype", "boolean", dtype_str(df["flag_promoter"]),
                 "PASS ✓" if ok_promo_dtype else "FAIL ✗"))
    if not ok_promo_dtype:
        errors.append(f"Check 5: flag_promoter dtype '{dtype_str(df['flag_promoter'])}' is not 'boolean'")

    nps_null = df["q_nps_score"].isna()
    promo_leak = int(df.loc[nps_null, "flag_promoter"].notna().sum())
    ok_promo_scope = promo_leak == 0
    rows.append(("flag_promoter — non-NaN where q_nps_score is NaN",
                 "= 0 violations", str(promo_leak), "PASS ✓" if ok_promo_scope else "FAIL ✗"))
    if not ok_promo_scope:
        errors.append(
            f"Check 5: flag_promoter has {promo_leak} non-NaN value(s) where q_nps_score is NaN"
        )

    # ── flag_paid_claimant ───────────────────────────────────────────────────

    ok_paid_dtype = dtype_str(df["flag_paid_claimant"]) == "boolean"
    rows.append(("flag_paid_claimant — dtype", "boolean", dtype_str(df["flag_paid_claimant"]),
                 "PASS ✓" if ok_paid_dtype else "FAIL ✗"))
    if not ok_paid_dtype:
        errors.append(
            f"Check 5: flag_paid_claimant dtype '{dtype_str(df['flag_paid_claimant'])}' is not 'boolean'"
        )

    # ── flag_child_wellbeing_denominator ─────────────────────────────────────

    denom_na = int(df["flag_child_wellbeing_denominator"].isna().sum())
    ok_denom = denom_na == 0
    rows.append(("flag_child_wellbeing_denominator — NaN count", "= 0", str(denom_na),
                 "PASS ✓" if ok_denom else "FAIL ✗"))
    if not ok_denom:
        errors.append(
            f"Check 5: flag_child_wellbeing_denominator has {denom_na} unexpected NaN value(s)"
        )

    # ── insurance_type ───────────────────────────────────────────────────────

    valid_slugs = {"health", "crop", "credit_life"}
    actual_slugs = set(df["insurance_type"].dropna().unique())
    unexpected = actual_slugs - valid_slugs
    ok_ins = not unexpected
    rows.append(("insurance_type — valid slug values only",
                 "⊆ {'health','crop','credit_life'}", str(sorted(actual_slugs)),
                 "PASS ✓" if ok_ins else "FAIL ✗"))
    if not ok_ins:
        errors.append(f"Check 5: insurance_type has unexpected value(s): {unexpected}")

    return rows, errors, warnings


# ---------------------------------------------------------------------------
# Check 6 — Fill rates
# ---------------------------------------------------------------------------

def check_6_fill_rates(df: pd.DataFrame, spec) -> list:
    rows: list = []

    insured_mask   = df["q_insured_event_12m"] == True   # noqa: E712
    submitted_mask = df["q_claim_submitted"]   == True   # noqa: E712
    health_mask    = df["is_health"]           == True   # noqa: E712
    nps_valid      = df["q_nps_score"].notna()
    detractor_mask = nps_valid & (df["q_nps_score"] <= 6)
    passive_mask   = nps_valid & (df["q_nps_score"] >= 7) & (df["q_nps_score"] <= 8)
    promoter_mask  = nps_valid & (df["q_nps_score"] >= 9)

    def make_row(qref: str, scope_label: str, mask, note: str) -> tuple:
        if qref not in df.columns:
            return (qref, scope_label, "—", "—", "column missing")
        denom_series = df.loc[mask, qref] if mask is not None else df[qref]
        denom_n = int(len(denom_series))
        fill_n = int(filled_mask(denom_series).sum())
        fill_pct = f"{fill_n / denom_n * 100:.1f}%" if denom_n > 0 else "N/A"
        return (qref, scope_label, str(denom_n), fill_pct, note)

    q_definitions = [
        ("q_worth_premium",               "all",           None,           ""),
        ("q_nps_score",                   "all",           None,           ""),
        ("q_nps_detractor_followup",      "NPS 0–6",       detractor_mask, "conditional on NPS ≤ 6 — low fill expected"),
        ("q_sex",                         "all",           None,           ""),
        ("q_nps_passive_followup",        "NPS 7–8",       passive_mask,   "conditional on NPS 7–8 — low fill expected"),
        ("q_nps_promoter_followup",       "NPS 9–10",      promoter_mask,  "conditional on NPS ≥ 9 — low fill expected"),
        ("q_confidence_pay",              "all",           None,           ""),
        ("q_financial_stress",            "all",           None,           ""),
        ("q_insured_event_12m",           "all",           None,           ""),
        ("q_claim_submitted",             "insured event", insured_mask,   "conditional on insured event"),
        ("q_claim_result",                "submitted claim", submitted_mask, "conditional — low fill expected"),
        ("q_coverage_understanding",      "all",           None,           ""),
        ("q_claim_process_understanding", "all",           None,           ""),
        ("q_coping_mechanisms",           "insured event", insured_mask,   "multi-select list; conditional on insured event"),
        ("q_prior_access",                "all",           None,           ""),
        ("q_alternative_access",          "all",           None,           ""),
        ("q_child_wellbeing",             "all",           None,           ""),
        ("q_healthcare_access",           "health only",   health_mask,    "health-insurance scope only"),
    ]

    seen_refs = {sq.question_ref for sq in spec.all_source_questions()}
    for qref, scope_label, mask, note in q_definitions:
        if qref in seen_refs:
            rows.append(make_row(qref, scope_label, mask, note))

    rows.append(make_row("flag_negative_coping",             "insured event", insured_mask, "NaN outside insured-event scope by design"))
    rows.append(make_row("flag_promoter",                    "all",           None,         "NaN where q_nps_score is missing"))
    rows.append(make_row("flag_paid_claimant",               "all",           None,         ""))
    rows.append(make_row("flag_child_wellbeing_denominator", "all",           None,         "False for non-caregiver and NA rows"))

    return rows


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _md_table(headers: list[str], rows: list[tuple]) -> list[str]:
    lines = ["| " + " | ".join(headers) + " |"]
    lines.append("|" + "|".join("---" for _ in headers) + "|")
    for row in rows:
        lines.append("| " + " | ".join(str(c) for c in row) + " |")
    return lines


def build_report(
    df: pd.DataFrame, spec,
    c1_rows, c1_errors, c1_warnings,
    c2_rows, c2_errors,
    c3_rows, c3_errors, c3_warnings,
    c4_rows, c4_errors,
    c5_rows, c5_errors, c5_warnings,
    c6_rows,
    all_errors: list[str],
    all_warnings: list[str],
) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_sq = len(spec.all_source_questions())
    n_mv = len(spec.referenced_variables())
    result = "PASS" if not all_errors else "FAIL"
    ne, nw = len(all_errors), len(all_warnings)

    lines: list[str] = [
        "# Data Quality Report — VisionFund Insurance Survey",
        f"Generated: {ts}",
        "",
        "## Summary",
        f"- Dataset: {len(df):,} rows × {len(df.columns)} columns",
        f"- Spec: {n_sq} source questions, {n_mv} metric variables referenced",
        f"- Result: **{result}** ({ne} error(s), {nw} warning(s))",
        "",
    ]

    if all_errors:
        lines.append("### Errors")
        for e in all_errors:
            lines.append(f"- {e}")
        lines.append("")

    if all_warnings:
        lines.append("### Warnings")
        for w in all_warnings:
            lines.append(f"- {w}")
        lines.append("")

    lines += ["## Check 1: Spec Alignment", ""]
    lines += _md_table(
        ["question_ref", "spec_type", "parquet_dtype", "status", "note"],
        [(f"`{qref}`", rtype, dtype, status, note)
         for qref, rtype, dtype, status, note in c1_rows],
    )
    lines.append("")

    lines += ["## Check 2: Value Ranges", ""]
    lines += _md_table(
        ["column", "valid_range", "violations", "status"],
        [(f"`{col}`", rng, viol, status) for col, rng, viol, status in c2_rows],
    )
    lines.append("")

    lines += [
        "## Check 3: Skip-Logic Consistency", "",
        "_base_n = rows outside the valid scope. ERROR threshold: violation > 1% of base_n._", "",
    ]
    lines += _md_table(
        ["check_id", "description", "base_n", "violations", "pct_of_base", "status"],
        c3_rows,
    )
    lines.append("")

    lines += ["## Check 4: Insurance-Type Scope", ""]
    lines += _md_table(
        ["column", "scope", "out_of_scope_non_null", "status"],
        [(f"`{col}`", scope, viol, status) for col, scope, viol, status in c4_rows],
    )
    lines.append("")

    lines += ["## Check 5: Derived Variable Sanity", ""]
    lines += _md_table(["variable", "expected", "actual", "status"], c5_rows)
    lines.append("")

    lines += ["## Check 6: Fill Rates", ""]
    lines += _md_table(
        ["question_ref", "scope", "denominator_n", "fill_rate", "note"],
        [(f"`{qref}`", scope, denom, fill, note)
         for qref, scope, denom, fill, note in c6_rows],
    )
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def _log_check(n: str, errors: int, warnings: int) -> None:
    parts = []
    if errors:
        parts.append(f"{errors} error(s)")
    if warnings:
        parts.append(f"{warnings} warning(s)")
    suffix = f"  — {', '.join(parts)}" if parts else "  — clean"
    log.info(f"  Check {n}{suffix}")


def main(output_dir: Path, target_country: "str | None" = None) -> None:
    parquet_path = output_dir / "survey_clean.parquet"
    yaml_path    = PROJECT_ROOT / "insurance-report-spec.yaml"
    schema_path  = PROJECT_ROOT / "insurance-report-spec.schema.json"
    report_path  = output_dir  / "data_quality_report.md"

    if not parquet_path.exists():
        log.error(f"Parquet not found: {parquet_path}")
        sys.exit(1)
    log.info(f"Loading {parquet_path.name}")
    df = pd.read_parquet(parquet_path)
    log.info(f"  {len(df):,} rows × {len(df.columns)} columns")

    log.info("Loading report spec")
    result = load_spec(yaml_path, schema_path, strict=False)
    if result.spec is None:
        for f in result.findings:
            log.error(str(f))
        log.error("Spec failed to load — aborting")
        sys.exit(1)
    spec = result.spec
    log.info(f"  {len(spec.all_source_questions())} source questions, "
             f"{len(spec.referenced_variables())} metric variables")

    all_errors: list[str] = []
    all_warnings: list[str] = []

    log.info("Check 1: Spec Alignment")
    c1_rows, c1_errors, c1_warnings = check_1_spec_alignment(df, spec)
    all_errors.extend(c1_errors)
    all_warnings.extend(c1_warnings)
    _log_check("1", len(c1_errors), len(c1_warnings))

    log.info("Check 2: Value Ranges")
    c2_rows, c2_errors = check_2_value_ranges(df)
    all_errors.extend(c2_errors)
    _log_check("2", len(c2_errors), 0)

    log.info("Check 3: Skip-Logic Consistency")
    c3_rows, c3_errors, c3_warnings = check_3_skip_logic(df)
    all_errors.extend(c3_errors)
    all_warnings.extend(c3_warnings)
    _log_check("3", len(c3_errors), len(c3_warnings))

    log.info("Check 4: Insurance-Type Scope")
    c4_rows, c4_errors = check_4_scope(df)
    all_errors.extend(c4_errors)
    _log_check("4", len(c4_errors), 0)

    log.info("Check 5: Derived Variable Sanity")
    c5_rows, c5_errors, c5_warnings = check_5_derived(df, target_country=target_country)
    all_errors.extend(c5_errors)
    all_warnings.extend(c5_warnings)
    _log_check("5", len(c5_errors), len(c5_warnings))

    log.info("Check 6: Fill Rates (INFO only)")
    c6_rows = check_6_fill_rates(df, spec)
    log.info(f"  {len(c6_rows)} variable(s) reported")

    report_md = build_report(
        df, spec,
        c1_rows, c1_errors, c1_warnings,
        c2_rows, c2_errors,
        c3_rows, c3_errors, c3_warnings,
        c4_rows, c4_errors,
        c5_rows, c5_errors, c5_warnings,
        c6_rows,
        all_errors, all_warnings,
    )
    report_path.write_text(report_md, encoding="utf-8")
    log.info(f"Report written → {report_path}")

    if all_errors:
        log.error(f"FAIL — {len(all_errors)} error(s), {len(all_warnings)} warning(s)")
        print(f"\nValidator FAILED — {len(all_errors)} error(s). See {report_path}")
        sys.exit(1)
    else:
        log.info(f"PASS — 0 errors, {len(all_warnings)} warning(s)")
        print(f"\nValidator PASSED — {len(all_warnings)} warning(s). See {report_path}")
        sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionFund Survey Validator")
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Run output directory containing survey_clean.parquet; writes data_quality_report.md here",
    )
    parser.add_argument(
        "--country", type=str, default=None, metavar="COUNTRY",
        help="If this run was scoped to a single country (see data_loader_screening.py "
             "--country), relaxes Check 5's flag_negative_coping structural assertion.",
    )
    args = parser.parse_args()
    main(args.output_dir, target_country=args.country)
