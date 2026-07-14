"""analysis_engine/sections/part_3.py — Part 3: Financial Resilience."""
import logging

from analysis_engine.stats import top_two_box, bottom_two_box, share_selecting, share_true, disaggregate

log = logging.getLogger("analysis_engine.sections.part_3")

# --- Column constants ---
COL_NEGATIVE_COPING    = "flag_negative_coping"
COL_FINANCIAL_STRESS   = "q_financial_stress"
COL_ALTERNATIVE_ACCESS = "q_alternative_access"
COL_CONFIDENCE_PAY     = "q_confidence_pay"
COL_PRIOR_ACCESS       = "q_prior_access"

_ALTERNATIVE_ACCESS_DIFFICULT = ["Very difficult", "Slightly difficult"]


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}"}


def calculate(ds, segment_masks: dict) -> dict:
    """Part 3: Financial Resilience (mixed bases per metric)."""
    log.info(
        f"Part 3: calculating mixed bases "
        f"(insured_event_base n={len(ds.insured_event_base)}, all_respondents n={len(ds.df)})"
    )
    metrics = {}

    # negative_coping — base: insured_event_base (q_coping_mechanisms has genuine
    # skip logic: "[If yes to experiencing an insured event]..." -- confirmed zero
    # non-insured-event respondents have an answer, so this scope is correct.
    # Base includes both claimants and those who had an event but didn't claim --
    # it is NOT "claimants" specifically (claimants alone are n=153, not n=363).
    col = COL_NEGATIVE_COPING
    if col not in ds.insured_event_base.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'negative_coping'")
        metrics["negative_coping"] = {
            "base": "insured_event_base", "n_base": len(ds.insured_event_base),
            "headline": _missing_col(col), "segments": {},
        }
    else:
        metrics["negative_coping"] = {
            "base": "insured_event_base",
            "n_base": len(ds.insured_event_base),
            "headline": share_true(ds.insured_event_base[col]),
            "segments": disaggregate(ds.insured_event_base, col, share_true, segment_masks),
        }

    # financial_stress_high — base: all_respondents. q_financial_stress ("How much
    # does the insurance help reduce your financial stress?") has NO skip logic --
    # confirmed 2,104 of 2,111 respondents answered it, including the large
    # majority who never experienced an insured event. It is independent of claim
    # and insured-event activity, unlike negative_coping above, so it must not be
    # restricted to the insured-event base or framed as following from a claim.
    col = COL_FINANCIAL_STRESS
    if col not in ds.df.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'financial_stress_high'")
        metrics["financial_stress_high"] = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(col), "segments": {},
        }
    else:
        metrics["financial_stress_high"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": top_two_box(ds.df[col]),
            "segments": disaggregate(ds.df, col, top_two_box, segment_masks),
        }

    # alternative_access_difficult — base: all_respondents
    col = COL_ALTERNATIVE_ACCESS
    if col not in ds.df.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'alternative_access_difficult'")
        metrics["alternative_access_difficult"] = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(col), "segments": {},
        }
    else:
        metrics["alternative_access_difficult"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": share_selecting(
                ds.df[col], values=_ALTERNATIVE_ACCESS_DIFFICULT
            ),
            "segments": disaggregate(
                ds.df, col, share_selecting, segment_masks,
                values=_ALTERNATIVE_ACCESS_DIFFICULT,
            ),
        }

    # confidence_pay — base: all_respondents
    col = COL_CONFIDENCE_PAY
    if col not in ds.df.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'confidence_pay'")
        metrics["confidence_pay"] = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(col), "segments": {},
        }
    else:
        metrics["confidence_pay"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": bottom_two_box(ds.df[col]),
            "segments": disaggregate(ds.df, col, bottom_two_box, segment_masks),
        }

    # no_prior_access ("first-time access to insurance") — base: all_respondents.
    # q_prior_access == True means the client already had some insurance before
    # VisionFund; this metric is the inverse (share with NO prior access, i.e.
    # VisionFund was their first insurer) -- a market-reach/inclusion metric,
    # distinct from the protection/coping metrics elsewhere in this part.
    col = COL_PRIOR_ACCESS
    if col not in ds.df.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'no_prior_access'")
        metrics["no_prior_access"] = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(col), "segments": {},
        }
    else:
        no_prior_access = ~ds.df[col]
        metrics["no_prior_access"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": share_true(no_prior_access),
            "segments": disaggregate(ds.df, no_prior_access, share_true, segment_masks),
        }

    return {"metrics": metrics}
