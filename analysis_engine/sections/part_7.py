"""analysis_engine/sections/part_7.py — Part 7: Female vs Male Scorecard."""
import logging

from analysis_engine.stats import (
    bottom_two_box, share_true, share_selecting, scorecard_row as _scorecard_row_base,
)

log = logging.getLogger("analysis_engine.sections.part_7")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_WORTH_PREMIUM               = "q_worth_premium"
COL_RENEWAL_INTENT              = "q_renewal_intent"
COL_NEGATIVE_COPING             = "flag_negative_coping"
COL_CHILD_WELLBEING             = "q_child_wellbeing"
COL_CONFIDENCE_PAY              = "q_confidence_pay"

_A = "female"
_B = "male"


def _scorecard_row(scoped_df, col_or_series, stat_fn, segment_masks, label, **stat_kwargs) -> dict:
    return _scorecard_row_base(scoped_df, col_or_series, stat_fn, segment_masks, label, _A, _B, **stat_kwargs)


def _missing_scorecard_row(label: str, col: str, segment_masks: dict) -> dict:
    missing = {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
               "suppress_reason": f"column missing: {col}", "not_applicable": True}
    row = {"label": label, **{seg: dict(missing) for seg in segment_masks}}
    row["significance"] = None
    return row


def _scorecard_row_safe(scoped_df, col: str, stat_fn, segment_masks, label, **stat_kwargs) -> dict:
    """Like _scorecard_row(), but degrades to a clean "column missing" row
    instead of crashing when col isn't in this dataset's schema (e.g. LARCO
    has no q_coverage_understanding/q_worth_premium/etc. -- see
    data_loader_larco/column_mapping.csv's notes). disaggregate() itself
    would otherwise raise KeyError on scoped_df[col] unconditionally."""
    if col not in scoped_df.columns:
        log.warning(f"Part 7: column '{col}' missing — '{label}' not applicable to this dataset")
        return _missing_scorecard_row(label, col, segment_masks)
    return _scorecard_row(scoped_df, col, stat_fn, segment_masks, label, **stat_kwargs)


def calculate(ds, segment_masks: dict) -> dict:
    """Part 7: Female vs Male Scorecard."""
    n_a = int(segment_masks[_A].sum()) if _A in segment_masks else 0
    n_b = int(segment_masks[_B].sum()) if _B in segment_masks else 0
    log.info(f"Part 7: calculating scorecard (n_female={n_a}, n_male={n_b})")

    metrics = {
        "coverage_understanding": _scorecard_row_safe(
            ds.df, COL_COVERAGE_UNDERSTANDING, bottom_two_box, segment_masks,
            "Coverage Understanding", scale_min=1,
        ),
        "claim_process_understanding": _scorecard_row_safe(
            ds.df, COL_CLAIM_PROCESS_UNDERSTANDING, bottom_two_box, segment_masks,
            "Claim Process Understanding", scale_min=1,
        ),
        "worth_premium": _scorecard_row_safe(
            ds.df, COL_WORTH_PREMIUM, bottom_two_box, segment_masks,
            "Worth Premium", scale_min=1,
        ),
        "renewal_intent": _scorecard_row_safe(
            ds.df, COL_RENEWAL_INTENT, bottom_two_box, segment_masks,
            "Renewal Intent", scale_min=1,
        ),
        "negative_coping": _scorecard_row_safe(
            ds.insured_event_base, COL_NEGATIVE_COPING, share_true, segment_masks,
            "Negative Coping",
        ),
        "child_wellbeing": _scorecard_row_safe(
            ds.child_wellbeing_base, COL_CHILD_WELLBEING, share_selecting, segment_masks,
            "Child Wellbeing", values=["Yes"],
        ),
        "confidence_pay": _scorecard_row_safe(
            ds.df, COL_CONFIDENCE_PAY, bottom_two_box, segment_masks,
            "Confidence in Pay-out", scale_min=1,
        ),
    }

    return {
        "groups": {
            _A: {"label": "Female", "n": n_a},
            _B: {"label": "Male",   "n": n_b},
        },
        "metrics": metrics,
    }
