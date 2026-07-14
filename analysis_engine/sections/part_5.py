"""analysis_engine/sections/part_5.py — Part 5: CWB Drivers (Spearman correlations + regression)."""
import logging

import pandas as pd

from analysis_engine.stats import spearman_correlation, logistic_regression, top_two_box, share_selecting, scorecard_row

log = logging.getLogger("analysis_engine.sections.part_5")

# --- Column constants ---
COL_CHILD_WELLBEING             = "q_child_wellbeing"
COL_FINANCIAL_STRESS            = "q_financial_stress"
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
COL_CONFIDENCE_PAY              = "q_confidence_pay"
COL_NPS_SCORE                   = "q_nps_score"
COL_ECONOMIC_STRAIN_PROXY       = "q_child_improvements__d"
COL_HEALTHCARE_ACCESS           = "q_healthcare_access"

# Matches analysis_engine/sections/part_4.py's HEALTHCARE_ACCESS_POSITIVE_VALUES exactly.
HEALTHCARE_ACCESS_POSITIVE_VALUES = ["Yes", "Yes, a lot", "Yes, somewhat"]

# Planned in the original report spec as subsection 5.2 ("Caregivers vs non
# caregivers — financial stress & healthcare access") but never built until now.
_CAREGIVER_COMPARISON_NOTE = (
    "Financial stress is measured among clients who experienced an insured event "
    "in the last 12 months (same base as Part 3's financial stress metric); "
    "healthcare access is measured among health-insurance clients who needed "
    "care (same base as Part 4's healthcare access metric)."
)

# (key, column, encoding): encoding=None → pass as-is; "boolean_to_int" → map True/False → 1/0
_DRIVERS = [
    ("financial_stress",            COL_FINANCIAL_STRESS,            None),
    ("coverage_understanding",      COL_COVERAGE_UNDERSTANDING,      None),
    ("claim_process_understanding", COL_CLAIM_PROCESS_UNDERSTANDING, None),
    ("worth_premium",               COL_WORTH_PREMIUM,               None),
    ("renewal_intent",              COL_RENEWAL_INTENT,              None),
    ("confidence_pay",              COL_CONFIDENCE_PAY,              None),
    ("nps_score",                   COL_NPS_SCORE,                   None),
    ("economic_strain_relief_proxy", COL_ECONOMIC_STRAIN_PROXY,      "boolean_to_int"),
]

_ECONOMIC_STRAIN_NOTE = (
    "q_child_improvements__d — Reduced need to work extra hours after a shock "
    "(proxy for economic strain relief)"
)

COL_IS_CROP        = "is_crop"
COL_IS_CREDIT_LIFE = "is_credit_life"

# (output_key, source_name, source_type)
#   "column"  → read directly from cwb_base[source_name]
#   "segment" → pulled from the shared segment_masks dict, reindexed onto cwb_base.index
_REGRESSION_PREDICTORS = [
    ("is_crop",                COL_IS_CROP,               "column"),
    ("is_credit_life",         COL_IS_CREDIT_LIFE,        "column"),
    ("bundled_service_client", "bundled_service_client",  "segment"),
    ("first_time_access",      "first_time_access",       "segment"),
]

_REGRESSION_REFERENCE_NOTE = (
    "insurance_type reference category: is_health (implicit baseline — not included as "
    "a predictor, to avoid the dummy-variable trap)"
)


def _build_regression_predictors(cwb_base: "pd.DataFrame", segment_masks: dict) -> "pd.DataFrame":
    """Build the product-uptake predictor frame for logistic_regression().

    A predictor is silently omitted (not an error) when its source column or segment
    is unavailable in this run — keeps the regression reusable across future country
    datasets that may not have every product-uptake source.
    """
    predictors = pd.DataFrame(index=cwb_base.index)
    for key, source, source_type in _REGRESSION_PREDICTORS:
        if source_type == "column":
            if source not in cwb_base.columns:
                log.warning(f"Part 5 regression: column '{source}' missing — omitting predictor '{key}'")
                continue
            predictors[key] = cwb_base[source].astype("Int8")
        else:  # "segment"
            mask = segment_masks.get(source)
            if mask is None:
                log.warning(f"Part 5 regression: segment '{source}' unavailable — omitting predictor '{key}'")
                continue
            predictors[key] = mask.reindex(cwb_base.index, fill_value=False).astype("Int8")
    return predictors


def _build_caregiver_comparison(ds, segment_masks: dict) -> dict:
    """Caregiver vs non-caregiver comparison on financial stress & healthcare
    access -- planned since the original report spec, never previously built."""
    n_caregiver = int(segment_masks["caregiver"].sum()) if "caregiver" in segment_masks else 0
    n_non_caregiver = int(segment_masks["non_caregiver"].sum()) if "non_caregiver" in segment_masks else 0
    log.info(f"Part 5: caregiver comparison (n_caregiver={n_caregiver}, n_non_caregiver={n_non_caregiver})")

    metrics: dict = {}

    if COL_FINANCIAL_STRESS in ds.insured_event_base.columns:
        metrics["financial_stress_high"] = scorecard_row(
            ds.insured_event_base, COL_FINANCIAL_STRESS, top_two_box, segment_masks,
            "High Financial Stress", "caregiver", "non_caregiver",
        )
    else:
        log.warning(f"Part 5: column '{COL_FINANCIAL_STRESS}' missing — skipping caregiver comparison row 'financial_stress_high'")

    if COL_HEALTHCARE_ACCESS in ds.health.columns:
        metrics["healthcare_access"] = scorecard_row(
            ds.health, COL_HEALTHCARE_ACCESS, share_selecting, segment_masks,
            "Healthcare Access Improved", "caregiver", "non_caregiver",
            values=HEALTHCARE_ACCESS_POSITIVE_VALUES,
        )
    else:
        log.warning(f"Part 5: column '{COL_HEALTHCARE_ACCESS}' missing — skipping caregiver comparison row 'healthcare_access'")

    return {
        "groups": {
            "caregiver":     {"label": "Caregiver",     "n": n_caregiver},
            "non_caregiver": {"label": "Non-Caregiver",  "n": n_non_caregiver},
        },
        "note": _CAREGIVER_COMPARISON_NOTE,
        "metrics": metrics,
    }


def calculate(ds, segment_masks: dict) -> dict:
    """Part 5: CWB Drivers — Spearman correlations + logistic regression within child_wellbeing_base."""
    cwb_base = ds.child_wellbeing_base
    log.info(f"Part 5: calculating child_wellbeing_base (n={len(cwb_base)})")

    caregiver_comparison = _build_caregiver_comparison(ds, segment_masks)

    if COL_CHILD_WELLBEING not in cwb_base.columns:
        log.warning(f"Part 5: outcome column '{COL_CHILD_WELLBEING}' missing — cannot compute drivers")
        return {
            "base": "child_wellbeing_base",
            "n_base": len(cwb_base),
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "method": "Spearman rank correlation",
            "drivers": {},
            "regression": {"error": "outcome column missing", "coefficients": {}},
            "caregiver_comparison": caregiver_comparison,
        }

    # Encode outcome: Yes=1, No=0; unmapped categories (e.g. "Do not support any children") → NA
    cwb_outcome = cwb_base[COL_CHILD_WELLBEING].map({"Yes": 1, "No": 0}).astype("Int8")

    correlations: dict = {}
    for key, col, encoding in _DRIVERS:
        if col not in cwb_base.columns:
            log.warning(f"Part 5: column '{col}' missing — skipping driver '{key}'")
            continue
        y = cwb_base[col].copy()
        if encoding == "boolean_to_int":
            y = y.map({True: 1, False: 0}).astype("Int8")
        result = spearman_correlation(cwb_outcome, y)
        if key == "economic_strain_relief_proxy":
            result["note"] = _ECONOMIC_STRAIN_NOTE
        correlations[key] = result

    predictor_df = _build_regression_predictors(cwb_base, segment_masks)
    if predictor_df.shape[1] == 0:
        regression_result = {
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "predictors": [],
            "reference_category_note": _REGRESSION_REFERENCE_NOTE,
            "method": "Logistic regression (statsmodels Logit)",
            "error": "no predictor columns available",
        }
    else:
        reg = logistic_regression(cwb_outcome, predictor_df)
        regression_result = {
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "predictors": list(predictor_df.columns),
            "reference_category_note": _REGRESSION_REFERENCE_NOTE,
            "method": "Logistic regression (statsmodels Logit)",
            **reg,
        }

    return {
        "base": "child_wellbeing_base",
        "n_base": len(cwb_base),
        "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
        "method": "Spearman rank correlation",
        "drivers": correlations,
        "regression": regression_result,
        "caregiver_comparison": caregiver_comparison,
    }
