"""analysis_engine/sections/part_5.py — Part 5: CWB Drivers (Spearman correlations + regression)."""
import logging

import pandas as pd

from analysis_engine.stats import spearman_correlation, logistic_regression

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


def calculate(ds, segment_masks: dict) -> dict:
    """Part 5: CWB Drivers — Spearman correlations + logistic regression within child_wellbeing_base."""
    cwb_base = ds.child_wellbeing_base
    log.info(f"Part 5: calculating child_wellbeing_base (n={len(cwb_base)})")

    if COL_CHILD_WELLBEING not in cwb_base.columns:
        log.warning(f"Part 5: outcome column '{COL_CHILD_WELLBEING}' missing — cannot compute drivers")
        return {
            "base": "child_wellbeing_base",
            "n_base": len(cwb_base),
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "method": "Spearman rank correlation",
            "drivers": {},
            "regression": {"error": "outcome column missing", "coefficients": {}},
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
    }
