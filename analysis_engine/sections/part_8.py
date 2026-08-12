"""analysis_engine/sections/part_8.py — Part 8: Kling Index — Product Outcomes.

DASHBOARD-ONLY BY DESIGN, not a gap: this section's composite score is computed
and stored in analysis_results.json (and shown in the dashboard UI) for every
run, Africa/Vietnam and LARCO alike, but it has never had -- and currently has
no -- corresponding entry in generation/report_spec.yaml, so it never appears
in the generated .docx (see report_spec.yaml's top-of-file note, run_analysis.py's
SECTIONS list, and generation/assembler.py's `builders` dict, each of which
notes this explicitly at the point a future reader would otherwise read the
absence as an oversight). Confirmed as a deliberate, reviewed decision (not
something LARCO's addition broke) rather than silently "fixing" it by adding
a Part 8 write-up nobody asked for.
"""
import logging

import pandas as pd

from analysis_engine.stats import (
    bottom_two_box,
    share_selecting,
    nps_score,
    claims_funnel,
    composite_index,
    LOW_N_THRESHOLD,
)

log = logging.getLogger("analysis_engine.sections.part_8")

# --- Column constants ---
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_CONFIDENCE_PAY              = "q_confidence_pay"
COL_ALTERNATIVE_ACCESS          = "q_alternative_access"

_ALTERNATIVE_ACCESS_DIFFICULT = ["Very difficult", "Slightly difficult"]

_CLAIMS_EXPERIENCE_NOTE = (
    "Claims Experience is restricted to claimants (q_claim_submitted == True) within "
    "each scope. Segments with fewer than 30 claimants will have this dimension "
    "suppressed and excluded from the composite."
)


def _dim_product_understanding(df: pd.DataFrame) -> dict:
    """Mean TTB of coverage and claim-process understanding. Score: 0–1."""
    sub_scores: dict = {}
    available_values = []
    available_ns     = []

    for key, col in [
        ("coverage_understanding",      COL_COVERAGE_UNDERSTANDING),
        ("claim_process_understanding", COL_CLAIM_PROCESS_UNDERSTANDING),
    ]:
        if col not in df.columns:
            sub_scores[key] = {"value": None, "suppressed": True, "n_valid": 0,
                               "suppress_reason": f"column '{col}' missing"}
            continue
        r = bottom_two_box(df[col], scale_min=1)
        sub_scores[key] = r
        if not r["suppressed"] and r["value"] is not None:
            available_values.append(r["value"])
            available_ns.append(r["n_valid"])

    if not available_values:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": "no sub-scores available", "sub_scores": sub_scores}

    return {
        "value":          sum(available_values) / len(available_values),
        "suppressed":     False,
        "n_valid":        min(available_ns),
        "suppress_reason": None,
        "sub_scores":     sub_scores,
    }


def _dim_claims_experience(df: pd.DataFrame) -> dict:
    """Proportion of claimants whose claim was paid. Score: 0–1.

    not_applicable when this schema doesn't collect claim outcomes at all
    (see claims_funnel()'s claim_paid.not_applicable) -- distinct from
    ordinary low-n suppression, since claimants may well be plentiful (LARCO
    has 230) but the outcome was simply never asked."""
    funnel         = claims_funnel(df)
    not_applicable = bool(funnel["claim_paid"].get("not_applicable", False))
    n_claimants    = funnel["claim_paid"]["n_total"]   # = n who submitted claims
    n_paid         = funnel["claim_paid"]["n"]
    suppressed     = not_applicable or n_claimants < LOW_N_THRESHOLD

    return {
        "value":          funnel["claim_paid"]["pct_of_claimants"] if not suppressed else None,
        "suppressed":     suppressed,
        "n_valid":        n_claimants,
        "suppress_reason": (
            "claim outcome not collected in this dataset's schema" if not_applicable else
            (f"n_valid={n_claimants} below threshold={LOW_N_THRESHOLD}" if suppressed else None)
        ),
        "n_paid":         n_paid,
    }


def _dim_trust(df: pd.DataFrame) -> dict:
    """Mean of confidence_pay TTB and normalized NPS ((nps+100)/200). Score: 0–1."""
    sub_scores:       dict = {}
    available_values: list = []
    available_ns:     list = []

    if COL_CONFIDENCE_PAY in df.columns:
        cp = bottom_two_box(df[COL_CONFIDENCE_PAY], scale_min=1)
        sub_scores["confidence_pay"] = cp
        if not cp["suppressed"] and cp["value"] is not None:
            available_values.append(cp["value"])
            available_ns.append(cp["n_valid"])

    nps = nps_score(df)
    if not nps["suppressed"] and nps["value"] is not None:
        nps_norm = (nps["value"] + 100) / 200
        sub_scores["nps_normalized"] = {
            "value":          nps_norm,
            "nps_raw":        nps["value"],
            "n_valid":        nps["n_valid"],
            "suppressed":     False,
            "suppress_reason": None,
        }
        available_values.append(nps_norm)
        available_ns.append(nps["n_valid"])
    else:
        sub_scores["nps_normalized"] = {
            "value":      None,
            "suppressed": True,
            "n_valid":    nps["n_valid"],
        }

    if not available_values:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": "no trust sub-scores available", "sub_scores": sub_scores}

    return {
        "value":          sum(available_values) / len(available_values),
        "suppressed":     False,
        "n_valid":        min(available_ns),
        "suppress_reason": None,
        "sub_scores":     sub_scores,
    }


def _dim_access(df: pd.DataFrame) -> dict:
    """Ease of getting alternative insurance: 1 – share finding it difficult. Score: 0–1."""
    if COL_ALTERNATIVE_ACCESS not in df.columns:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": f"column '{COL_ALTERNATIVE_ACCESS}' missing"}

    alt = share_selecting(df[COL_ALTERNATIVE_ACCESS], _ALTERNATIVE_ACCESS_DIFFICULT)
    if alt["suppressed"] or alt["value"] is None:
        return {"value": None, "suppressed": True, "n_valid": alt["n_valid"],
                "suppress_reason": alt.get("suppress_reason"), "sub_scores": {"difficulty_rate": alt}}

    return {
        "value":          1.0 - alt["value"],
        "suppressed":     False,
        "n_valid":        alt["n_valid"],
        "suppress_reason": None,
        "sub_scores": {"difficulty_rate": alt},
    }


def _compute_kling(df: pd.DataFrame) -> dict:
    """Compute the four dimension scores and composite index for a given DataFrame scope."""
    dimension_results = {
        "product_understanding": _dim_product_understanding(df),
        "claims_experience":     _dim_claims_experience(df),
        "trust":                 _dim_trust(df),
        "access":                _dim_access(df),
    }
    composite = composite_index(dimension_results, min_dimensions=2)
    composite["dimensions_detail"] = dimension_results
    return composite


def calculate(ds, segment_masks: dict) -> dict:
    """Part 8: Kling Index — composite product-outcome score (overall + per segment)."""
    log.info(f"Part 8: computing Kling Index (n_base={len(ds.df)}, "
             f"n_segments={len(segment_masks)})")

    headline = _compute_kling(ds.df)
    log.info(
        f"Part 8: headline score={headline['value']}, "
        f"dims_included={headline['dimensions_included']}, "
        f"dims_excluded={headline['dimensions_excluded']}"
    )

    segments: dict = {}
    for seg_name, full_mask in segment_masks.items():
        seg_mask = full_mask.reindex(ds.df.index, fill_value=False)
        seg_df   = ds.df[seg_mask]
        segments[seg_name] = _compute_kling(seg_df)
        log.info(
            f"Part 8: segment '{seg_name}' (n={seg_mask.sum()}) "
            f"score={segments[seg_name]['value']}"
        )

    return {
        "base":                    "all_respondents",
        "n_base":                  len(ds.df),
        "dimensions":              ["product_understanding", "claims_experience",
                                    "trust", "access"],
        "method":                  "Unweighted mean of four 0–1 dimension scores (min 2 of 4 required)",
        "min_dimensions_required": 2,
        "claims_experience_note":  _CLAIMS_EXPERIENCE_NOTE,
        "headline":                headline,
        "segments":                segments,
    }
