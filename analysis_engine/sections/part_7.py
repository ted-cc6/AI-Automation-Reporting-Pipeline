"""analysis_engine/sections/part_7.py — Part 7: Female vs Male Scorecard."""
import logging

from analysis_engine.stats import (
    top_two_box, bottom_two_box, share_true, share_selecting, disaggregate, significance_test,
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
    disag = disaggregate(scoped_df, col_or_series, stat_fn, segment_masks, **stat_kwargs)
    _absent = {"value": None, "n_valid": 0, "suppressed": True, "suppress_reason": "segment absent"}
    a = disag.get(_A, _absent)
    b = disag.get(_B, _absent)

    if a.get("value") is not None and b.get("value") is not None:
        sig = significance_test(
            round(a["value"] * a["n_valid"]), a["n_valid"],
            round(b["value"] * b["n_valid"]), b["n_valid"],
        )
    else:
        sig = None

    row = {"label": label}
    row.update(disag)   # all segment keys present (including any country-config segments)
    row["significance"] = sig
    return row


def calculate(ds, segment_masks: dict) -> dict:
    """Part 7: Female vs Male Scorecard."""
    n_a = int(segment_masks[_A].sum()) if _A in segment_masks else 0
    n_b = int(segment_masks[_B].sum()) if _B in segment_masks else 0
    log.info(f"Part 7: calculating scorecard (n_female={n_a}, n_male={n_b})")

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
        "negative_coping": _scorecard_row(
            ds.insured_event_base, COL_NEGATIVE_COPING, share_true, segment_masks,
            "Negative Coping",
        ),
        "child_wellbeing": _scorecard_row(
            ds.child_wellbeing_base, COL_CHILD_WELLBEING, share_selecting, segment_masks,
            "Child Wellbeing", values=["Yes"],
        ),
        "confidence_pay": _scorecard_row(
            ds.df, COL_CONFIDENCE_PAY, bottom_two_box, segment_masks,
            "Confidence in Pay-out",
        ),
    }

    return {
        "groups": {
            _A: {"label": "Female", "n": n_a},
            _B: {"label": "Male",   "n": n_b},
        },
        "metrics": metrics,
    }
