"""analysis_engine/sections/part_4.py — Part 4: Child Wellbeing Outcomes."""
import logging

import pandas as pd

from analysis_engine.stats import nps_score, share_selecting, share_true, disaggregate, SCOPE_SENTINEL

log = logging.getLogger("analysis_engine.sections.part_4")

# --- Column constants ---
COL_NPS_SCORE           = "q_nps_score"
COL_CHILD_WELLBEING     = "q_child_wellbeing"
COL_HEALTHCARE_ACCESS   = "q_healthcare_access"
COL_MEDICAL_COST_CHANGE = "q_medical_cost_change"

# Configurable positive-outcome values for healthcare access — update if survey wording changes.
# Includes "Yes" for Q2 2026 (binary) and anticipated granular options in future waves.
HEALTHCARE_ACCESS_POSITIVE_VALUES = ["Yes", "Yes, a lot", "Yes, somewhat"]

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
            "suppress_reason": f"column missing: {col}"}


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
        cwb_segments: dict = {}
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
        ha_dist = _dist(ha_series)
        # Verify at least one positive value exists in the data before calling share_selecting
        valid_str = set(
            ha_series[ha_series.notna() & (ha_series != SCOPE_SENTINEL)].astype(str)
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
            ha_headline = share_selecting(ha_series, values=HEALTHCARE_ACCESS_POSITIVE_VALUES)

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

    return {
        "nps": {
            "base": "all_respondents_with_score",
            "n_base": n_nps_valid,
            "result": nps_result,
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
