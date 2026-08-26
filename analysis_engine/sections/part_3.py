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

# R-008 (docs/report_spec.md, session-10): the four components
# data_loader_derived.py's compute_flag_negative_coping() ORs together to
# produce flag_negative_coping -- "used savings" (__a) and "borrowed money"
# (__b) are deliberately NOT part of this list; they're the two options the
# flag itself treats as ordinary, not severe, coping, so they are not part
# of what this breakdown is a breakdown OF.
_COPING_COMPONENTS = [
    ("sold_assets_livestock", "q_coping_mechanisms__c", "Sold assets or livestock"),
    ("reduced_food_consumption", "q_coping_mechanisms__d", "Reduced food consumption or essential spending"),
    ("took_children_out_of_school", "q_coping_mechanisms__e", "Took children out of school"),
    ("closed_business_temporarily", "q_coping_mechanisms__f", "Closed business temporarily"),
]

# Disclosure-avoidance threshold for NAMING an individual component -- distinct
# from analysis_engine.stats.LOW_N_THRESHOLD (30), which governs whether an
# entire metric ROW is reliable enough to report at all. That threshold
# applied here would suppress every component on real data (the flagged
# group itself is far smaller than 30 -- e.g. n=8 on runs/lacro_final_check/),
# making a named behaviour impossible even when one component is a clear,
# non-tiny majority (7 of 8) -- confirmed with the user (session-10) this is
# a genuinely different kind of threshold (identifiability of a named
# individual, not statistical reliability) and should not reuse the same
# constant. A count of exactly 1 is suppressed (a single respondent would be
# identifiable from a named category); anything else found is named.
_COPING_COMPONENT_SUPPRESS_AT_OR_BELOW = 1


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


def _build_coping_components(insured_event_base) -> "tuple[list, int]":
    """Ranked (descending) named component counts, plus how many components
    were found but suppressed for being too small to name without risking
    identifying a specific respondent (R-008). A component with n==0 never
    happened in this data and is omitted entirely -- it is not "suppressed",
    there is nothing to suppress. Sums to at most n_true of flag_negative_coping's
    own headline (a respondent can select more than one severe option)."""
    named, suppressed = [], 0
    for key, col, label in _COPING_COMPONENTS:
        if col not in insured_event_base.columns:
            continue
        n = int(insured_event_base[col].fillna(False).sum())
        if n == 0:
            continue
        if n <= _COPING_COMPONENT_SUPPRESS_AT_OR_BELOW:
            suppressed += 1
            continue
        named.append({"key": key, "label": label, "n": n})
    named.sort(key=lambda c: -c["n"])
    return named, suppressed


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
            "headline": _missing_col(col), "segments": {seg: _missing_col(col) for seg in segment_masks},
            "components": [], "suppressed_components": 0,
        }
    else:
        components, suppressed_components = _build_coping_components(ds.insured_event_base)
        metrics["negative_coping"] = {
            "base": "insured_event_base",
            "n_base": len(ds.insured_event_base),
            "headline": share_true(ds.insured_event_base[col]),
            "segments": disaggregate(ds.insured_event_base, col, share_true, segment_masks),
            "components": components,
            "suppressed_components": suppressed_components,
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
            "headline": _missing_col(col), "segments": {seg: _missing_col(col) for seg in segment_masks},
        }
    else:
        metrics["financial_stress_high"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": top_two_box(ds.df[col], scale_max=5),
            "segments": disaggregate(ds.df, col, top_two_box, segment_masks, scale_max=5),
        }

    # alternative_access_difficult — base: all_respondents
    col = COL_ALTERNATIVE_ACCESS
    if col not in ds.df.columns:
        log.warning(f"Part 3: column '{col}' missing — skipping 'alternative_access_difficult'")
        metrics["alternative_access_difficult"] = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(col), "segments": {seg: _missing_col(col) for seg in segment_masks},
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
            "headline": _missing_col(col), "segments": {seg: _missing_col(col) for seg in segment_masks},
        }
    else:
        metrics["confidence_pay"] = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": bottom_two_box(ds.df[col], scale_min=1),
            "segments": disaggregate(ds.df, col, bottom_two_box, segment_masks, scale_min=1),
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
            "headline": _missing_col(col), "segments": {seg: _missing_col(col) for seg in segment_masks},
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
