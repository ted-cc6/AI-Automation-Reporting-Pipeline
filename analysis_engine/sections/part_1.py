"""analysis_engine/sections/part_1.py — Part 1: Client Understanding & Value Perception."""
import logging

import pandas as pd

from analysis_engine.stats import bottom_two_box, disaggregate, SCOPE_SENTINEL

log = logging.getLogger("analysis_engine.sections.part_1")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
# "Which channel do you PREFER for submitting a claim?" -- asked of every
# respondent regardless of claim history (it sits with the other client
# understanding/preference questions in the survey, right after Claim Process
# Understanding). NOT a record of how any specific claim was actually filed --
# do not scope this to claimants only (moved from part_2.py, which had wrongly
# restricted it to the claimant base and implied it was actual-usage data).
COL_CLAIM_CHANNEL_PREFERRED     = "q_claim_channel_preferred"

# All four use inverted Likert scales (1 = best response); bottom_two_box is correct.
_METRICS = [
    (COL_COVERAGE_UNDERSTANDING,      "coverage_understanding"),
    (COL_CLAIM_PROCESS_UNDERSTANDING, "claim_process_understanding"),
    (COL_WORTH_PREMIUM,               "worth_premium"),
    (COL_RENEWAL_INTENT,              "renewal_intent"),
]


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}"}


def _dist(series: pd.Series) -> list:
    """Sorted frequency distribution for a single-select Categorical column."""
    valid = series[series.notna() & (series != SCOPE_SENTINEL)]
    n = len(valid)
    if n == 0:
        return []
    vc = valid.value_counts()
    return [{"value": str(v), "n": int(c), "pct": float(c / n)} for v, c in vc.items()]


def calculate(ds, segment_masks: dict) -> dict:
    """Part 1: Client Understanding & Value Perception (base: all respondents)."""
    log.info(f"Part 1: calculating all_respondents (n={len(ds.df)})")
    metrics = {}
    for col, key in _METRICS:
        if col not in ds.df.columns:
            log.warning(f"Part 1: column '{col}' missing — skipping '{key}'")
            metrics[key] = {"headline": _missing_col(col), "segments": {}}
        else:
            metrics[key] = {
                "headline": bottom_two_box(ds.df[col]),
                "segments": disaggregate(ds.df, col, bottom_two_box, segment_masks),
            }

    if COL_CLAIM_CHANNEL_PREFERRED not in ds.df.columns:
        log.warning(f"Part 1: column '{COL_CLAIM_CHANNEL_PREFERRED}' missing — skipping 'claim_channel_preferred'")
        channel_preferred = {"base": "all_respondents", "n_base": len(ds.df), "distribution": []}
    else:
        channel_preferred = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "distribution": _dist(ds.df[COL_CLAIM_CHANNEL_PREFERRED]),
        }

    return {
        "base": "all_respondents",
        "n_base": len(ds.df),
        "metrics": metrics,
        "claim_channel_preferred": channel_preferred,
    }
