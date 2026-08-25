"""analysis_engine/sections/part_6.py — Part 6: Claimant vs Did-Not-File Scorecard.

_B's population ("non_claimant" internally -- the JSON key is unchanged for
API/path stability, only its display label changed) is clients who
experienced an insured event but did NOT file a claim, not the much larger
population who simply never had a claimable event at all. q_claim_submitted
is only ever asked of clients who experienced an insured event (a skip-logic
gate matching claims_funnel()'s own design in stats.py), so both `_A ==
True` and `_B == False` naturally land within that same insured_event_base
subset -- pandas boolean comparisons against NaN are always False, so
clients who were never asked (no insured event) match NEITHER mask and are
silently excluded from this whole comparison, not folded into _B. A real
generated report labelled _B "Non-Claimant" and showed its NPS (37.7)
right next to the portfolio-wide NPS (48.3) as if they were directly
comparable -- they describe different populations entirely.

R-011 (session-10): "Non-Filer" fixed that scope confusion but is itself
opaque -- a reader still cannot tell what population it names from the
word alone. LABEL_CLAIMANT/QUALIFIER_CLAIMANT/LABEL_NON_FILER below state
the population directly in the rendered column header instead ("Claimant
(filed, n=55)" / "Did not file (n=69)"); generation/assembler.py's
build_part_6() also renders an explicit note beneath the table stating
both groups are restricted to clients who reported an insured event.
"""
import logging

from analysis_engine.stats import (
    top_two_box, bottom_two_box, share_true, share_selecting, nps_scorecard_row,
    scorecard_row as _scorecard_row_base,
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
COL_CHILD_WELLBEING             = "q_child_wellbeing"

_A = "claimant"
_B = "non_claimant"

# R-011 (docs/report_spec.md, session-10): "Non-Claimant" was tried and
# retracted (see docs/maintenance/known-issues-log.md:71-81 and this
# module's own docstring) because the label alone let a reader infer the
# much larger population who never had a claimable event at all.
# "Non-Filer" fixed the scope confusion but traded it for a label opaque
# about what the group actually is. Neither single word states the
# population; stating it directly, rather than trusting a reader to
# infer it from one word, is the actual fix -- see _group_header() in
# generation/assembler.py for how QUALIFIER_CLAIMANT folds into the
# rendered column header ("Claimant (filed, n=55)").
LABEL_CLAIMANT = "Claimant"
QUALIFIER_CLAIMANT = "filed"
LABEL_NON_FILER = "Did not file"


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
        log.warning(f"Part 6: column '{col}' missing — '{label}' not applicable to this dataset")
        return _missing_scorecard_row(label, col, segment_masks)
    return _scorecard_row(scoped_df, col, stat_fn, segment_masks, label, **stat_kwargs)


def calculate(ds, segment_masks: dict) -> dict:
    """Part 6: Claimant vs Non-Claimant Scorecard."""
    n_a = int(segment_masks[_A].sum()) if _A in segment_masks else 0
    n_b = int(segment_masks[_B].sum()) if _B in segment_masks else 0
    log.info(f"Part 6: calculating scorecard (n_claimant={n_a}, n_non_claimant={n_b})")

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
        # insured_event_base scope: claimant ∩ base = all claimants; non_claimant ∩ base = leakage
        "negative_coping": _scorecard_row_safe(
            ds.insured_event_base, COL_NEGATIVE_COPING, share_true, segment_masks,
            "Negative Coping",
        ),
        "financial_stress_high": _scorecard_row_safe(
            ds.insured_event_base, COL_FINANCIAL_STRESS, top_two_box, segment_masks,
            "Financial Stress (High)", scale_max=5,
        ),
        "confidence_pay": _scorecard_row_safe(
            ds.df, COL_CONFIDENCE_PAY, bottom_two_box, segment_masks,
            "Confidence in Pay-out", scale_min=1,
        ),
        # NPS isn't a proportion -- nps_scorecard_row() uses a Mann-Whitney U test
        # instead of the two-proportion z-test every other row here uses.
        "nps": nps_scorecard_row(
            ds.df, segment_masks, "Net Promoter Score", _A, _B,
        ),
        # child_wellbeing_base is narrower than ds.df (clients with children in
        # the household) -- a different population than every other row above.
        "child_wellbeing": _scorecard_row_safe(
            ds.child_wellbeing_base, COL_CHILD_WELLBEING, share_selecting, segment_masks,
            "Child Wellbeing Improved", values=["Yes"],
        ),
    }

    return {
        "groups": {
            # R-011: label + qualifier fold into one column header, e.g.
            # "Claimant (filed, n=55)" / "Did not file (n=69)" -- see the
            # module-level LABEL_CLAIMANT/QUALIFIER_CLAIMANT/LABEL_NON_FILER
            # comment for why neither group is called "Non-Claimant".
            _A: {"label": LABEL_CLAIMANT, "n": n_a, "qualifier": QUALIFIER_CLAIMANT},
            _B: {"label": LABEL_NON_FILER, "n": n_b},
        },
        "metrics": metrics,
    }
