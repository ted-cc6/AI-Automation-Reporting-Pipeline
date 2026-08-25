"""analysis_engine/sections/part_4.py — Part 4: Child Wellbeing Outcomes."""
import logging

import pandas as pd

from analysis_engine.stats import (
    nps_score, share_selecting, share_true, disaggregate, spearman_correlation, SCOPE_SENTINEL,
)

log = logging.getLogger("analysis_engine.sections.part_4")

# --- Column constants ---
COL_NPS_SCORE                   = "q_nps_score"
COL_CHILD_WELLBEING             = "q_child_wellbeing"
COL_HEALTHCARE_ACCESS           = "q_healthcare_access"
COL_MEDICAL_COST_CHANGE         = "q_medical_cost_change"
COL_FINANCIAL_STRESS            = "q_financial_stress"
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
COL_CONFIDENCE_PAY              = "q_confidence_pay"

# Same driver set as Part 5's Child Wellbeing Drivers (analysis_engine/sections/part_5.py),
# minus nps_score itself -- here NPS is the outcome being predicted, not a predictor.
_SATISFACTION_DRIVERS = [
    ("financial_stress",            COL_FINANCIAL_STRESS),
    ("coverage_understanding",      COL_COVERAGE_UNDERSTANDING),
    ("claim_process_understanding", COL_CLAIM_PROCESS_UNDERSTANDING),
    ("worth_premium",               COL_WORTH_PREMIUM),
    ("renewal_intent",              COL_RENEWAL_INTENT),
    ("confidence_pay",              COL_CONFIDENCE_PAY),
]

# Configurable positive-outcome values for healthcare access — update if survey wording changes.
# Includes "Yes" for Q2 2026 (binary) and anticipated granular options in future waves.
HEALTHCARE_ACCESS_POSITIVE_VALUES = ["Yes", "Yes, a lot", "Yes, somewhat"]

# "Did not need care at all" -- a real, common response value (not a blank/
# NaN cell, and not SCOPE_SENTINEL, which marks a question outside this
# client's PRODUCT scope, not this skip-logic within an already-in-scope
# health client) -- must be excluded from the base the same way
# medical_cost_change's own sibling NA value already is below, or it
# silently inflates n_valid with respondents this question was never really
# asking. Confirmed in real production data: 1,273 of 1,721 LACRO health
# clients hold this value, dropping the headline share from the correct
# 152/448=33.9% (of clients who actually needed care) to a wrong
# 152/1721=8.8% before this fix -- self-contradictory alongside the
# "among clients who needed care" phrasing that (correctly) described the
# intended narrower base all along. Public (no leading underscore): R-007
# (docs/report_spec.md, session-10) found the identical defect in Part 5's
# caregiver-vs-non-caregiver healthcare_access row (part_5.py's
# _build_caregiver_comparison() used ds.health directly, unfiltered) --
# shared here rather than re-declaring the same literal in two places,
# which is exactly how they drifted apart the first time.
HEALTHCARE_ACCESS_NA = "Not applicable (I/my family have not needed medical care)"

# Medical cost change — string values treated as "improved" (lower costs)
_MEDICAL_COST_IMPROVED = frozenset(["Much lower", "Slightly lower"])
_MEDICAL_COST_NA       = "Not applicable (I have not needed medical care)"


def _dist(series: pd.Series) -> list:
    """Sorted frequency distribution for a single-select Categorical column."""
    valid = series[series.notna() & (series != SCOPE_SENTINEL)]
    n = len(valid)
    if n == 0:
        return []
    vc = valid.value_counts()
    return [{"value": str(v), "n": int(c), "pct": float(c / n)} for v, c in vc.items()]


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


def _missing_driver(col: str, n_total: int) -> dict:
    """Placeholder matching spearman_correlation()'s return shape for a driver
    whose column doesn't exist in this dataset's schema -- so the key is still
    present in the JSON (not silently absent) and orchestrator.py's
    get_nested() doesn't fall through to a "?" in the rendered table."""
    return {
        "value": None, "n_valid": 0, "n_total": n_total, "suppressed": True,
        "suppress_reason": f"column missing: {col}", "not_applicable": True,
        "p_value": None, "significant": False, "ci_lower": None, "ci_upper": None,
        "ci_level": 0.95,
    }


def calculate(ds, segment_masks: dict) -> dict:
    """Part 4: Child Wellbeing Outcomes."""
    log.info(
        f"Part 4: calculating "
        f"(child_wellbeing_base n={len(ds.child_wellbeing_base)}, health n={len(ds.health)})"
    )

    # 4.1 NPS — base: all respondents with a score
    n_nps_valid = (
        int(ds.df[COL_NPS_SCORE].notna().sum()) if COL_NPS_SCORE in ds.df.columns else 0
    )
    nps_result = nps_score(ds.df)

    # 4.2 Child wellbeing — base: child_wellbeing_base
    if COL_CHILD_WELLBEING not in ds.child_wellbeing_base.columns:
        log.warning(f"Part 4: column '{COL_CHILD_WELLBEING}' missing")
        cwb_headline = _missing_col(COL_CHILD_WELLBEING)
        cwb_segments: dict = {seg: _missing_col(COL_CHILD_WELLBEING) for seg in segment_masks}
    else:
        cwb_headline = share_selecting(
            ds.child_wellbeing_base[COL_CHILD_WELLBEING], values=["Yes"]
        )
        cwb_segments = disaggregate(
            ds.child_wellbeing_base, COL_CHILD_WELLBEING,
            share_selecting, segment_masks, values=["Yes"],
        )

    # 4.3 Healthcare access — base: health respondents only
    if COL_HEALTHCARE_ACCESS not in ds.health.columns:
        log.warning(f"Part 4: column '{COL_HEALTHCARE_ACCESS}' missing")
        ha_headline = _missing_col(COL_HEALTHCARE_ACCESS)
        ha_dist: list = []
    else:
        ha_series = ds.health[COL_HEALTHCARE_ACCESS]
        # Full raw distribution (all 3 categories, including "did not need
        # care") for diagnostic/dashboard use -- unlike ha_headline below,
        # this is not currently rendered into the report itself.
        ha_dist = _dist(ha_series)
        # The headline share's base is clients who actually needed care --
        # exclude "did not need care" before checking for positive values or
        # computing the share, the same way medical_cost_change's own
        # sibling NA value is excluded just below.
        ha_needed_care = ha_series[ha_series != HEALTHCARE_ACCESS_NA]
        valid_str = set(
            ha_needed_care[ha_needed_care.notna() & (ha_needed_care != SCOPE_SENTINEL)].astype(str)
        )
        if not any(v in valid_str for v in HEALTHCARE_ACCESS_POSITIVE_VALUES):
            log.warning(
                f"Part 4: healthcare_access — no positive values {HEALTHCARE_ACCESS_POSITIVE_VALUES} "
                f"found in data (actual values: {valid_str})"
            )
            ha_headline = {
                **_missing_col(COL_HEALTHCARE_ACCESS),
                "suppress_reason": "no matching values found",
                "matched_values": HEALTHCARE_ACCESS_POSITIVE_VALUES,
            }
        else:
            ha_headline = share_selecting(ha_needed_care, values=HEALTHCARE_ACCESS_POSITIVE_VALUES)

    # 4.4 Medical cost change — base: health respondents; lower string values = improved
    if COL_MEDICAL_COST_CHANGE not in ds.health.columns:
        log.warning(f"Part 4: column '{COL_MEDICAL_COST_CHANGE}' missing")
        mc_headline = _missing_col(COL_MEDICAL_COST_CHANGE)
    else:
        base_series = ds.health[COL_MEDICAL_COST_CHANGE]
        cost_improved = base_series.map(
            lambda x: (
                pd.NA if (pd.isna(x) or x == _MEDICAL_COST_NA)
                else True if x in _MEDICAL_COST_IMPROVED
                else False
            )
        ).astype("boolean")
        mc_headline = share_true(cost_improved)

    # 4.5 Satisfaction drivers -- Spearman correlations of the same Likert questions
    # used in Part 5's Child Wellbeing Drivers, but against q_nps_score as the outcome
    # instead of q_child_wellbeing. Base is ds.df (NPS is asked of all respondents).
    satisfaction_drivers: dict = {}
    if COL_NPS_SCORE not in ds.df.columns:
        log.warning(f"Part 4: outcome column '{COL_NPS_SCORE}' missing — cannot compute satisfaction drivers")
        for key, col in _SATISFACTION_DRIVERS:
            satisfaction_drivers[key] = _missing_driver(col, 0)
    else:
        nps_outcome = ds.df[COL_NPS_SCORE]
        for key, col in _SATISFACTION_DRIVERS:
            if col not in ds.df.columns:
                log.warning(f"Part 4: column '{col}' missing — driver '{key}' not applicable to this dataset")
                satisfaction_drivers[key] = _missing_driver(col, len(ds.df))
                continue
            satisfaction_drivers[key] = spearman_correlation(nps_outcome, ds.df[col])

    return {
        "nps": {
            "base": "all_respondents_with_score",
            "n_base": n_nps_valid,
            "result": nps_result,
        },
        "satisfaction_drivers": {
            "base": "all_respondents",
            "n_base": n_nps_valid,
            "outcome_variable": "q_nps_score (0=worst, 10=best)",
            "method": "Spearman rank correlation",
            "drivers": satisfaction_drivers,
        },
        "child_wellbeing": {
            "base": "child_wellbeing_base",
            "n_base": len(ds.child_wellbeing_base),
            "headline": cwb_headline,
            "segments": cwb_segments,
        },
        "healthcare_access": {
            "base": "health_respondents",
            "n_base": len(ds.health),
            "positive_values_used": HEALTHCARE_ACCESS_POSITIVE_VALUES,
            "headline": ha_headline,
            "distribution": ha_dist,
        },
        "medical_cost_change": {
            "base": "health_respondents",
            "n_base": len(ds.health),
            "note": "'Much lower' and 'Slightly lower' coded as improved; 'Not applicable' coded as null",
            "headline": mc_headline,
        },
    }
