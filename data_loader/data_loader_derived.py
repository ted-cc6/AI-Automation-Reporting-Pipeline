"""
data_loader_derived.py — VisionFund Insurance Survey Data Loader
Step 4 of 5: Add derived boolean flag columns to survey_clean.parquet.
Runs after screening (data_loader_screening.py) so flags are never computed
on rows that get dropped as duplicates or test/QA data.

Usage:
    python data_loader/data_loader_derived.py --output-dir runs/2026_Q3
"""

import sys
import logging
import argparse
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Derived variable functions
# ---------------------------------------------------------------------------
# REQUIRED_COLS is the single source of truth for what each flag needs, used
# by main() to pre-check availability before calling the compute_* function
# below (mirrors analysis_engine/segments.py's SEGMENT_REGISTRY
# required_columns pattern) -- a source schema that doesn't ask the
# underlying question (e.g. LARCO has no q_insured_event_12m/
# q_coping_mechanisms or q_claim_result) legitimately skips that flag
# instead of crashing. The compute_* functions themselves keep raising
# KeyError on a missing required column -- that stays the right behavior
# for a genuine coding regression against a schema that's supposed to have
# the column (e.g. Africa/Vietnam); main() is what decides whether to call
# them at all for a given dataset.
REQUIRED_COLS = {
    "flag_negative_coping": [
        "q_insured_event_12m", "q_coping_mechanisms__c",
        "q_coping_mechanisms__d", "q_coping_mechanisms__e", "q_coping_mechanisms__f",
    ],
    "flag_promoter": ["q_nps_score"],
    "flag_paid_claimant": ["q_claim_result"],
    "flag_child_wellbeing_denominator": ["q_child_wellbeing"],
}


def compute_flag_negative_coping(df: pd.DataFrame) -> pd.array:
    """True if respondent used a severe coping strategy after an insured event.
    NaN for respondents who did not experience an insured event.
    """
    required = [
        "q_insured_event_12m",
        "q_coping_mechanisms__c",
        "q_coping_mechanisms__d",
        "q_coping_mechanisms__e",
        "q_coping_mechanisms__f",
    ]
    for col in required:
        if col not in df.columns:
            raise KeyError(f"compute_flag_negative_coping: required column '{col}' not found")

    in_scope = df["q_insured_event_12m"] == True  # noqa: E712
    any_severe = (
        df["q_coping_mechanisms__c"].fillna(False)
        | df["q_coping_mechanisms__d"].fillna(False)
        | df["q_coping_mechanisms__e"].fillna(False)
        | df["q_coping_mechanisms__f"].fillna(False)
    ).astype(pd.BooleanDtype())
    any_severe[~in_scope] = pd.NA
    return pd.array(any_severe, dtype=pd.BooleanDtype())


def compute_flag_promoter(df: pd.DataFrame) -> pd.array:
    """True if NPS score >= 9. NaN where q_nps_score is missing."""
    if "q_nps_score" not in df.columns:
        raise KeyError("compute_flag_promoter: required column 'q_nps_score' not found")
    vals = []
    for v in df["q_nps_score"]:
        if pd.isna(v):
            vals.append(pd.NA)
        else:
            vals.append(int(v) >= 9)
    return pd.array(vals, dtype=pd.BooleanDtype())


def compute_flag_paid_claimant(df: pd.DataFrame) -> pd.array:
    """True if claim was approved and paid. NaN where q_claim_result is NaN."""
    if "q_claim_result" not in df.columns:
        raise KeyError("compute_flag_paid_claimant: required column 'q_claim_result' not found")
    vals = []
    for v in df["q_claim_result"]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            vals.append(pd.NA)
        else:
            vals.append(str(v) == "It was approved and paid")
    return pd.array(vals, dtype=pd.BooleanDtype())


def compute_flag_child_wellbeing_denominator(df: pd.DataFrame) -> pd.array:
    """True if respondent is in the child wellbeing analysis base (answered Yes or No).
    False for 'Do not support any children' and NaN rows — never NaN itself.
    """
    if "q_child_wellbeing" not in df.columns:
        raise KeyError(
            "compute_flag_child_wellbeing_denominator: required column 'q_child_wellbeing' not found"
        )
    valid_values = {"Yes", "No"}
    vals = []
    for v in df["q_child_wellbeing"]:
        if v is None or (isinstance(v, float) and pd.isna(v)):
            vals.append(False)
        else:
            vals.append(str(v) in valid_values)
    return pd.array(vals, dtype=pd.BooleanDtype())


# ---------------------------------------------------------------------------
# Structural assertions (data-independent — valid for any quarterly CSV)
# ---------------------------------------------------------------------------

DEFAULT_VALID_INSURANCE_SLUGS = frozenset({"health", "crop", "credit_life"})
LARCO_VALID_INSURANCE_SLUGS = DEFAULT_VALID_INSURANCE_SLUGS | {"personal_accident"}


def run_assertions(df: pd.DataFrame, target_country: "str | None" = None,
                    skipped_flags: frozenset = frozenset(),
                    valid_insurance_slugs: frozenset = DEFAULT_VALID_INSURANCE_SLUGS) -> bool:
    """Verify structural correctness of derived flags. No exact counts.

    target_country: the country this run was scoped to (see
    data_loader_screening.py's country filter), or None for the default
    multi-country portfolio. Only used to relax the flag_negative_coping
    "at least one True" check below -- a population-size threshold isn't a
    safe proxy for "is this run scoped" here, since some single-country
    subsets can still be large (e.g. Vietnam's country config: crop
    insurance payout is automatic and triggered for every policyholder, so
    its in-scope population can be close to its full respondent count, not
    reliably small).

    skipped_flags: flags main() deliberately did not compute because this
    dataset's schema doesn't have the source column(s) they need (see
    REQUIRED_COLS) -- e.g. LARCO has no q_insured_event_12m/
    q_coping_mechanisms, so flag_negative_coping is legitimately absent
    rather than a coding bug. Every other check below still runs normally
    for any flag that WAS computed.
    """
    failures = []

    # All flag columns must be present and typed as boolean, unless main()
    # already logged them as a deliberate schema-driven skip.
    flag_cols = [
        "flag_negative_coping",
        "flag_promoter",
        "flag_paid_claimant",
        "flag_child_wellbeing_denominator",
    ]
    for col in flag_cols:
        if col not in df.columns:
            if col not in skipped_flags:
                failures.append(f"{col}: column missing")
            continue
        if str(df[col].dtype) != "boolean":
            failures.append(f"{col}: expected dtype 'boolean', got '{df[col].dtype}'")

    if "flag_negative_coping" in df.columns:
        insured_true = df["q_insured_event_12m"] == True  # noqa: E712
        # Must be non-null only within insured-event rows
        out_scope_not_na = int(df["flag_negative_coping"][~insured_true].notna().sum())
        if out_scope_not_na > 0:
            failures.append(
                f"flag_negative_coping: {out_scope_not_na} non-NaN value(s) "
                "outside insured-event rows"
            )
        # Must have at least one True on the default (unscoped) multi-country
        # portfolio -- guards against a coding regression always returning
        # False. A country-scoped run can legitimately have zero (e.g.
        # Vietnam's automatic/index-triggered payout means nobody may ever
        # need a severe coping strategy), so this is a warning, not a
        # failure, whenever target_country is set.
        n_true = int(df["flag_negative_coping"].sum())
        n_in_scope = int(insured_true.sum())
        if n_true == 0:
            if target_country:
                log.warning(
                    f"flag_negative_coping: zero True values out of {n_in_scope} "
                    f"insured-event respondents in a scoped run ({target_country!r}) "
                    "-- not treated as an error"
                )
            else:
                failures.append("flag_negative_coping: zero True values — possible coding error")

    if "flag_promoter" in df.columns:
        # Must be non-null only where q_nps_score is non-null
        nps_null = df["q_nps_score"].isna()
        promoter_non_null_where_nps_null = int(df.loc[nps_null, "flag_promoter"].notna().sum())
        if promoter_non_null_where_nps_null > 0:
            failures.append(
                f"flag_promoter: {promoter_non_null_where_nps_null} non-NaN value(s) "
                "where q_nps_score is NaN"
            )

    if "flag_child_wellbeing_denominator" in df.columns:
        # Must have no NaN values
        n_na = int(df["flag_child_wellbeing_denominator"].isna().sum())
        if n_na > 0:
            failures.append(f"flag_child_wellbeing_denominator: {n_na} unexpected NaN value(s)")

    # insurance_type must contain only valid slugs
    if "insurance_type" in df.columns:
        actual_slugs = set(df["insurance_type"].dropna().unique())
        unexpected = actual_slugs - valid_insurance_slugs
        if unexpected:
            failures.append(f"insurance_type: unexpected slug(s) {unexpected}")

    if failures:
        for f in failures:
            log.error(f"ASSERTION FAILED: {f}")
        return False
    return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

FLAG_COMPUTE_FNS = {
    "flag_negative_coping": compute_flag_negative_coping,
    "flag_promoter": compute_flag_promoter,
    "flag_paid_claimant": compute_flag_paid_claimant,
    "flag_child_wellbeing_denominator": compute_flag_child_wellbeing_denominator,
}


def main(output_dir: Path, target_country: "str | None" = None,
         dataset_schema: str = "africa_vietnam",
         report_scope: "str | None" = None) -> None:
    # report_scope (a region group, e.g. "lacro") narrows the population the
    # same way target_country does -- fed through the same parameter here
    # rather than threading a second one through run_assertions(), which
    # only ever uses this value as a boolean gate + a log message, never to
    # look anything up.
    scope_desc = target_country or report_scope
    parquet_path = output_dir / "survey_clean.parquet"
    if not parquet_path.exists():
        log.error(f"Parquet not found: {parquet_path}")
        sys.exit(1)

    log.info(f"Loading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    log.info(f"  {len(df):,} rows, {len(df.columns)} columns")

    if "insurance_type" not in df.columns:
        log.error("'insurance_type' column not found — run the transformer first")
        sys.exit(1)
    log.info("insurance_type distribution:\n" + df["insurance_type"].value_counts().to_string())

    log.info("Computing derived variables...")
    skipped_flags = set()
    for flag_name, compute_fn in FLAG_COMPUTE_FNS.items():
        missing = [c for c in REQUIRED_COLS[flag_name] if c not in df.columns]
        if missing:
            log.warning(
                f"{flag_name}: skipped -- missing required column(s) {missing} "
                f"(not asked in this dataset's source schema)"
            )
            skipped_flags.add(flag_name)
            continue
        df[flag_name] = compute_fn(df)

    valid_insurance_slugs = (
        LARCO_VALID_INSURANCE_SLUGS if dataset_schema == "larco" else DEFAULT_VALID_INSURANCE_SLUGS
    )

    log.info("Running structural assertions...")
    if not run_assertions(df, target_country=scope_desc, skipped_flags=frozenset(skipped_flags),
                           valid_insurance_slugs=valid_insurance_slugs):
        log.error("Assertions failed — output NOT written")
        sys.exit(1)
    log.info("All assertions passed.")

    log.info(f"Writing {parquet_path}")
    df.to_parquet(parquet_path, engine="pyarrow", index=False)

    summary_lines = ["", "Derived variables complete."]
    if "flag_negative_coping" in df.columns:
        insured_n = int((df["q_insured_event_12m"] == True).sum())  # noqa: E712
        summary_lines.append(
            f"  flag_negative_coping      : {int(df['flag_negative_coping'].sum())} True of {insured_n} in-scope rows"
        )
    if "flag_promoter" in df.columns:
        nps_n = int(df["q_nps_score"].notna().sum())
        summary_lines.append(
            f"  flag_promoter             : {int(df['flag_promoter'].sum())} True of {nps_n} scored rows"
        )
    if "flag_paid_claimant" in df.columns:
        summary_lines.append(
            f"  flag_paid_claimant        : {int(df['flag_paid_claimant'].sum())} True of {len(df):,} rows"
        )
    if "flag_child_wellbeing_denominator" in df.columns:
        summary_lines.append(
            f"  flag_child_wellbeing_denom: {int(df['flag_child_wellbeing_denominator'].sum())} True of {len(df):,} rows"
        )
    if skipped_flags:
        summary_lines.append(f"  Skipped (schema doesn't ask): {sorted(skipped_flags)}")
    summary_lines.append(f"  Output: {parquet_path} ({len(df.columns)} columns)")
    print("\n".join(summary_lines))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionFund Survey — Derived Variables")
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Run output directory containing survey_clean.parquet (modified in place)",
    )
    parser.add_argument(
        "--country", type=str, default=None, metavar="COUNTRY",
        help="If this run was scoped to a single country (see data_loader_screening.py "
             "--country), relaxes the flag_negative_coping structural assertion.",
    )
    parser.add_argument(
        "--dataset-schema", type=str, default="africa_vietnam",
        choices=("africa_vietnam", "larco"), metavar="SCHEMA",
        help="Which source-survey schema this parquet came from -- controls the "
             "insurance_type valid-slug allow-list. Default: 'africa_vietnam'.",
    )
    parser.add_argument(
        "--report-scope", type=str, default=None, metavar="SCOPE",
        help="If this run was scoped to a named region group (see data_loader_screening.py "
             "--report-scope), relaxes the flag_negative_coping structural assertion the "
             "same way --country does.",
    )
    args = parser.parse_args()
    main(args.output_dir, target_country=args.country, dataset_schema=args.dataset_schema,
         report_scope=args.report_scope)
