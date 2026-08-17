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

# (label, suppressed_path, cross_reference_note) -- known schema/population-
# variant metrics whose not_applicable flag (derived from suppressed_path,
# see generation/orchestrator.py's _not_applicable_path()) is worth calling
# out in one consolidated caveat box, instead of scattered "NOT APPLICABLE"
# mentions across the report. Curated, not a generic tree-walk, so every
# entry gets a precise human label rather than a guessed one.
#
# cross_reference_note is None only when there is nothing further worth
# telling the reader. Renewal Intent and Combined Product Understanding
# both get one:
#   - Renewal Intent's not_applicable flag fires exclusively because the
#     LACRO/legacy-LARCO survey instrument never maps this column at all
#     (confirmed against both schemas' column mappings) -- there is no
#     other circumstance that sets it, so a plain "not collected by this
#     survey instrument" note is accurate every time this fires.
#   - Combined Product Understanding is LARCO's own single combined
#     question (see analysis_engine/sections/part_1.py), genuinely not
#     collected by the 2026 unified schema this caveat box would be
#     listing it for -- but the underlying CONCEPT is reported at length
#     there, via two separate split questions. Without the note, the plain
#     caveat sentence ("does not collect the following, so they do not
#     appear elsewhere in this report") reads as contradicting Part 1's own
#     product-understanding reporting a few pages away; the note
#     disambiguates "this specific single-question metric" from "the topic
#     in general."
_NOT_APPLICABLE_CANDIDATES = [
    ("Coverage Understanding", "parts.part_1.metrics.coverage_understanding.headline.suppressed", None),
    ("Claim Process Understanding", "parts.part_1.metrics.claim_process_understanding.headline.suppressed", None),
    ("Worth Premium", "parts.part_1.metrics.worth_premium.headline.suppressed", None),
    ("Renewal Intent", "parts.part_1.metrics.renewal_intent.headline.suppressed",
     "not collected by the LACRO survey instrument"),
    ("Combined Product Understanding", "parts.part_1.metrics.product_understanding.headline.suppressed",
     "reported instead in Part 1 as two split metrics, Coverage Understanding and "
     "Claim Process Understanding"),
    ("Confidence in Payout", "parts.part_3.metrics.confidence_pay.headline.suppressed", None),
    ("Negative Coping", "parts.part_3.metrics.negative_coping.headline.suppressed", None),
    ("Experienced Insured Event (claims funnel step)", "parts.part_2.claims_funnel.experienced_event.suppressed", None),
    ("Claim Paid Outcome", "parts.part_2.claims_funnel.claim_paid.suppressed", None),
    ("Payout Adequacy", "parts.part_2.claims_funnel.payout_adequacy.suppressed", None),
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
    reader encountering scattered NOT APPLICABLE notes throughout. Entries
    with a cross_reference_note (see _NOT_APPLICABLE_CANDIDATES) render as
    "Label (note)" so a reader isn't left wondering why a metric the caveat
    box calls uncollected still appears to be reported elsewhere."""
    out = []
    for label, sup_path, note in _NOT_APPLICABLE_CANDIDATES:
        if bool(get_nested(analysis, _not_applicable_path(sup_path), default=False)):
            out.append(f"{label} ({note})" if note else label)
    return out
