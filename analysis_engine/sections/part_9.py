"""analysis_engine/sections/part_9.py — Part 9: Additional Services.

Non-claim benefits bundled alongside the insurance product (teleconsultation,
face-to-face consultations, discounted/free medicines, lab tests, health
events) -- distinct from the claims-payout benefits covered elsewhere in the
report. This is the module the LARCO manager's email described as newly
added for LAC ("benefits beyond claim payouts... are a major part of their
insurance products").

The exact same two questions (q_bundled_services_used, q_services_helped)
already exist in the Africa/Vietnam mapping (data_loader/column_mapping.csv,
cols 52-61) but at ~0.4% fill -- effectively unused there, which is why this
section was never built for Africa. Only run for LARCO (see run_analysis.py's
SECTIONS gating) -- if it were run against Africa's data too, every metric
below would just come back suppressed (n well under LOW_N_THRESHOLD).

As of this module's authoring, LARCO's own raw CSV export does NOT yet
contain these two columns either (data_loader_larco/column_mapping.csv has
no rows for them -- see that file's notes). This calculator is intentionally
schema-agnostic: it checks column presence directly rather than assuming
LARCO has the data, so it degrades to a clean "column missing" result now
and lights up automatically, with no code changes, once a corrected LARCO
export actually contains these columns under the same canonical names.
"""
import logging

import pandas as pd

from analysis_engine.stats import disaggregate, ranked_options, share_selecting

log = logging.getLogger("analysis_engine.sections.part_9")

COL_SERVICES_USED = "q_bundled_services_used"
COL_SERVICES_HELPED = "q_services_helped"

# Children of q_bundled_services_used excluding option 'f' ("None") --
# mirrors analysis_engine/segments.py's COL_BUNDLED_CHILDREN list (kept
# local rather than imported since that one is paired with a private
# module-level mask helper there, not meant as a cross-module import).
_SERVICE_CHILDREN = [
    "q_bundled_services_used__a",
    "q_bundled_services_used__b",
    "q_bundled_services_used__c",
    "q_bundled_services_used__d",
    "q_bundled_services_used__e",
    "q_bundled_services_used__g",
]

# code_single_select() only strips a leading "x. " prefix (see
# data_loader_transformer.py) -- "a. Very helpful" -> "Very helpful", etc.
_HELPFUL_VALUES = ["Very helpful", "Somewhat helpful"]


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}"}


def _used_any_service_mask(df):
    """True where the respondent selected at least one real service option
    (i.e. anything other than 'None'). Missing child columns are silently
    skipped (OR of what's present), matching segments.py's _bundled_mask()."""
    mask = pd.Series(False, index=df.index)
    for col in _SERVICE_CHILDREN:
        if col in df.columns:
            mask |= df[col] == True  # noqa: E712
    return mask


def calculate(ds, segment_masks: dict) -> dict:
    """Part 9: Additional Services.

    services_used: which services respondents used, base = all respondents
    (most will have selected "None" or left it blank -- that's the point of
    the metric, not a data-quality problem).

    services_helped: whether the services helped as wanted, base = only
    respondents who used at least one real service (this question is
    conditional in the source survey -- "If [did access the services]...").
    """
    log.info(f"Part 9: calculating (n_total={len(ds.df)})")

    if COL_SERVICES_USED not in ds.df.columns:
        log.warning(f"Part 9: column '{COL_SERVICES_USED}' missing — section not applicable to this dataset")
        services_used = {
            "base": "all_respondents", "n_base": len(ds.df),
            "headline": _missing_col(COL_SERVICES_USED), "segments": {},
        }
    else:
        services_used = {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": ranked_options(ds.df[COL_SERVICES_USED]),
            "segments": disaggregate(ds.df, COL_SERVICES_USED, ranked_options, segment_masks),
        }

    if COL_SERVICES_HELPED not in ds.df.columns:
        log.warning(f"Part 9: column '{COL_SERVICES_HELPED}' missing — section not applicable to this dataset")
        services_helped = {
            "base": "used_any_service", "n_base": 0,
            "headline": _missing_col(COL_SERVICES_HELPED), "segments": {},
        }
    else:
        used_mask = _used_any_service_mask(ds.df)
        scoped_df = ds.df[used_mask]
        services_helped = {
            "base": "used_any_service",
            "n_base": int(used_mask.sum()),
            "headline": share_selecting(scoped_df[COL_SERVICES_HELPED], values=_HELPFUL_VALUES),
            "segments": disaggregate(
                scoped_df, COL_SERVICES_HELPED, share_selecting, segment_masks, values=_HELPFUL_VALUES,
            ),
        }

    return {
        "services_used": services_used,
        "services_helped": services_helped,
    }
