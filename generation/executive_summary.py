"""generation/executive_summary.py

Deterministic headline-numbers + data-availability caveat box for the
Executive Summary section (Phase D) -- computed directly from the already-
assembled analysis_results.json dict (every part's calculate() has already
run by the time this reads it), not from the raw survey DataFrame, so it
needs no entry in run_analysis.py's SECTIONS and no new analysis_engine
module. The "top findings"/"top actions" that also belong in this section
come from the qualitative pipeline's Task 7 instead (qualitative_results.json,
see qualitative/llm_call.py) -- generation/assembler.py's
_add_executive_summary() merges both into one section.
"""
from utils import get_nested, format_value
from generation.orchestrator import _not_applicable_path

# (label, value_path, n_path, suppressed_path, fmt) -- a curated set of
# headline metrics broadly meaningful across both dataset schemas (Africa/
# Vietnam and LARCO). filed_claim is never not_applicable by design (see
# analysis_engine/stats.py's claims_funnel() -- it's always computed against
# either the insured-event base or the full population, whichever this
# schema has); the other four use their own not_applicable flag to degrade
# gracefully per schema/population without needing a schema check here.
_HEADLINE_METRICS = [
    ("Net Promoter Score",
     "parts.part_4.nps.result.value", "parts.part_4.nps.result.n_valid",
     "parts.part_4.nps.result.suppressed", "nps"),
    ("Children's Wellbeing Improved",
     "parts.part_4.child_wellbeing.headline.value", "parts.part_4.child_wellbeing.headline.n_valid",
     "parts.part_4.child_wellbeing.headline.suppressed", "pct"),
    ("First-Time Access to Insurance",
     "parts.part_3.metrics.no_prior_access.headline.value", "parts.part_3.metrics.no_prior_access.headline.n_valid",
     "parts.part_3.metrics.no_prior_access.headline.suppressed", "pct"),
    ("Filed a Claim",
     "parts.part_2.claims_funnel.filed_claim.pct_of_event_base", "parts.part_2.claims_funnel.filed_claim.n_total",
     "parts.part_2.claims_funnel.filed_claim.suppressed", "pct"),
]

# (label, suppressed_path) -- known schema/population-variant metrics whose
# not_applicable flag (derived from suppressed_path, see
# generation/orchestrator.py's _not_applicable_path()) is worth calling out
# in one consolidated caveat box, instead of scattered "NOT APPLICABLE"
# mentions across the report. Curated, not a generic tree-walk, so every
# entry gets a precise human label rather than a guessed one.
_NOT_APPLICABLE_CANDIDATES = [
    ("Coverage Understanding", "parts.part_1.metrics.coverage_understanding.headline.suppressed"),
    ("Claim Process Understanding", "parts.part_1.metrics.claim_process_understanding.headline.suppressed"),
    ("Worth Premium", "parts.part_1.metrics.worth_premium.headline.suppressed"),
    ("Renewal Intent", "parts.part_1.metrics.renewal_intent.headline.suppressed"),
    ("Combined Product Understanding", "parts.part_1.metrics.product_understanding.headline.suppressed"),
    ("Confidence in Payout", "parts.part_3.metrics.confidence_pay.headline.suppressed"),
    ("Negative Coping", "parts.part_3.metrics.negative_coping.headline.suppressed"),
    ("Experienced Insured Event (claims funnel step)", "parts.part_2.claims_funnel.experienced_event.suppressed"),
    ("Claim Paid Outcome", "parts.part_2.claims_funnel.claim_paid.suppressed"),
    ("Payout Adequacy", "parts.part_2.claims_funnel.payout_adequacy.suppressed"),
]


def headline_numbers(analysis: dict) -> list:
    """Curated headline metrics for the executive summary's top-of-report
    numbers table -- each entry omitted entirely (not shown as N/A) when
    not_applicable to this run's schema/population."""
    rows = []
    for label, val_path, n_path, sup_path, fmt in _HEADLINE_METRICS:
        not_app = bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
        if not_app:
            continue
        v = get_nested(analysis, val_path)
        n = get_nested(analysis, n_path)
        sup = bool(get_nested(analysis, sup_path, default=False))
        rows.append({
            "label": label,
            "value": format_value(v, fmt, suppressed=sup, not_applicable=False),
            "n": n if n is not None else None,
        })
    return rows


def data_availability_caveats(analysis: dict) -> list:
    """Human-readable list of metrics not applicable to this run's dataset
    schema or population -- one consolidated caveat box instead of the
    reader encountering scattered NOT APPLICABLE notes throughout."""
    return [
        label for label, sup_path in _NOT_APPLICABLE_CANDIDATES
        if bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
    ]
