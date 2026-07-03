"""analysis_engine/sections/part_1.py — Part 1: Client Understanding & Value Perception."""
import logging

from analysis_engine.stats import top_two_box, bottom_two_box, disaggregate

log = logging.getLogger("analysis_engine.sections.part_1")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"

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
    return {
        "base": "all_respondents",
        "n_base": len(ds.df),
        "metrics": metrics,
    }
