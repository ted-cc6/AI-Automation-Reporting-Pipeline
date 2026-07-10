"""analysis_engine/sections/part_6.py — Part 6: Claimant vs Non-Claimant Scorecard."""
import logging

from analysis_engine.stats import (
    top_two_box, bottom_two_box, share_true, scorecard_row as _scorecard_row_base,
)

log = logging.getLogger("analysis_engine.sections.part_6")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
COL_NEGATIVE_COPING             = "flag_negative_coping"
COL_FINANCIAL_STRESS            = "q_financial_stress"
COL_CONFIDENCE_PAY              = "q_confidence_pay"

_A = "claimant"
_B = "non_claimant"


def _scorecard_row(scoped_df, col_or_series, stat_fn, segment_masks, label, **stat_kwargs) -> dict:
    return _scorecard_row_base(scoped_df, col_or_series, stat_fn, segment_masks, label, _A, _B, **stat_kwargs)


def calculate(ds, segment_masks: dict) -> dict:
    """Part 6: Claimant vs Non-Claimant Scorecard."""
    n_a = int(segment_masks[_A].sum()) if _A in segment_masks else 0
    n_b = int(segment_masks[_B].sum()) if _B in segment_masks else 0
    log.info(f"Part 6: calculating scorecard (n_claimant={n_a}, n_non_claimant={n_b})")

    metrics = {
        "coverage_understanding": _scorecard_row(
            ds.df, COL_COVERAGE_UNDERSTANDING, bottom_two_box, segment_masks,
            "Coverage Understanding",
        ),
        "claim_process_understanding": _scorecard_row(
            ds.df, COL_CLAIM_PROCESS_UNDERSTANDING, bottom_two_box, segment_masks,
            "Claim Process Understanding",
        ),
        "worth_premium": _scorecard_row(
            ds.df, COL_WORTH_PREMIUM, bottom_two_box, segment_masks,
            "Worth Premium",
        ),
        "renewal_intent": _scorecard_row(
            ds.df, COL_RENEWAL_INTENT, bottom_two_box, segment_masks,
            "Renewal Intent",
        ),
        # insured_event_base scope: claimant ∩ base = all claimants; non_claimant ∩ base = leakage
        "negative_coping": _scorecard_row(
            ds.insured_event_base, COL_NEGATIVE_COPING, share_true, segment_masks,
            "Negative Coping",
        ),
        "financial_stress_high": _scorecard_row(
            ds.insured_event_base, COL_FINANCIAL_STRESS, top_two_box, segment_masks,
            "Financial Stress (High)",
        ),
        "confidence_pay": _scorecard_row(
            ds.df, COL_CONFIDENCE_PAY, bottom_two_box, segment_masks,
            "Confidence in Pay-out",
        ),
    }

    return {
        "groups": {
            _A: {"label": "Claimant",     "n": n_a},
            _B: {"label": "Non-Claimant", "n": n_b},
        },
        "metrics": metrics,
    }
