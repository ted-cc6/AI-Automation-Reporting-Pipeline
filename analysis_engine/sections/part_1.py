"""analysis_engine/sections/part_1.py — Part 1: Client Understanding & Value Perception."""
import logging

import pandas as pd

from analysis_engine.stats import bottom_two_box, disaggregate, share_selecting, SCOPE_SENTINEL

log = logging.getLogger("analysis_engine.sections.part_1")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
# LARCO's combined understanding question (data_loader_larco/column_mapping.csv) --
# not_applicable for Africa/Vietnam runs (column absent), and stands in for the
# four Likert metrics above, which are themselves not_applicable for LARCO (its
# survey never asks coverage/claim-process understanding as separate questions).
# Also feeds analysis_engine/sections/part_10.py's wave-over-wave trend snapshot;
# both sections read the same column with the same "I know everything" positivity
# definition so the two numbers never disagree.
COL_PRODUCT_UNDERSTANDING_COMBINED = "q_product_understanding_combined"
_PRODUCT_UNDERSTANDING_GOOD = ["I know everything"]
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
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


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
            # Every segment gets its own not_applicable placeholder (not an empty
            # dict) -- report_spec.yaml's per-segment metric entries (e.g.
            # coverage_understanding_female) each resolve their own suppressed/
            # not_applicable path independently via get_nested(), so a missing
            # key there silently falls back to suppressed=False/not_applicable=
            # False/value=None, which orchestrator.py's format_value() renders
            # as "SUPPRESSED" -- wrong, and no longer dropped by the not_applicable
            # check in orchestrator.py's extract_metrics().
            metrics[key] = {"headline": _missing_col(col),
                             "segments": {seg: _missing_col(col) for seg in segment_masks}}
        else:
            metrics[key] = {
                "headline": bottom_two_box(ds.df[col], scale_min=1),
                "segments": disaggregate(ds.df, col, bottom_two_box, segment_masks, scale_min=1),
            }

    if COL_PRODUCT_UNDERSTANDING_COMBINED not in ds.df.columns:
        log.warning(f"Part 1: column '{COL_PRODUCT_UNDERSTANDING_COMBINED}' missing — skipping 'product_understanding'")
        metrics["product_understanding"] = {
            "headline": _missing_col(COL_PRODUCT_UNDERSTANDING_COMBINED),
            "segments": {seg: _missing_col(COL_PRODUCT_UNDERSTANDING_COMBINED) for seg in segment_masks},
        }
    else:
        metrics["product_understanding"] = {
            "headline": share_selecting(ds.df[COL_PRODUCT_UNDERSTANDING_COMBINED], values=_PRODUCT_UNDERSTANDING_GOOD),
            "segments": disaggregate(
                ds.df, COL_PRODUCT_UNDERSTANDING_COMBINED, share_selecting, segment_masks,
                values=_PRODUCT_UNDERSTANDING_GOOD,
            ),
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
