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

R-002: the headline-numbers metric list itself lives in report_spec.yaml's
executive_summary.metrics, not in this module -- see headline_numbers()
below, which is the one exception to this file's "no report_spec.yaml
entry" claim above (true only of the caveat box and the section wiring,
not of the metric list since R-002).
"""
import yaml

from utils import get_nested, format_value
from generation.orchestrator import SPEC_PATH, _not_applicable_path, _resolve_population

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
    not_applicable to this run's schema/population.

    Metric list comes from report_spec.yaml's executive_summary.metrics
    (R-002) -- read fresh here rather than passed in, matching
    orchestrator.py's own reload-per-call pattern for the same file. Each
    entry's base_label is resolved against this run's report_scope with
    the same _resolve_population() every population: note in
    report_spec.yaml already uses, so a metric like worth_premium (100%
    Health, no restriction for a LACRO-scoped report; Health & credit-life
    only for an Africa/Vietnam-scoped one) gets the correct label either
    way rather than a single hardcoded phrase."""
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    metrics = spec.get("executive_summary", {}).get("metrics", [])
    report_scope = (analysis.get("meta") or {}).get("report_scope")

    rows = []
    for m in metrics:
        sup_path = m["suppressed_path"]
        not_app = bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
        if not_app:
            continue
        v = get_nested(analysis, m["value_path"])
        n = get_nested(analysis, m["n_path"])
        sup = bool(get_nested(analysis, sup_path, default=False))
        base_label = _resolve_population(m.get("base_label"), report_scope)
        rows.append({
            "label": m["label"],
            "value": format_value(v, m["fmt"], suppressed=sup, not_applicable=False),
            "n": n if n is not None else None,
            "base_label": base_label or "",
            "_fmt": m["fmt"],
            "_raw_value": v,
            "_suppressed": sup,
        })
    _disambiguate_tied_percentages(rows)
    for r in rows:
        del r["_fmt"], r["_raw_value"], r["_suppressed"]
    return rows


def _disambiguate_tied_percentages(rows: list) -> None:
    """Bump colliding "pct" rows from 1 decimal to 2, in place, so two
    genuinely different values that both round to the same 1-decimal
    percentage (e.g. worth_premium=80.07% and claim_process_understanding=
    80.13%, both "80.1%" at 1 decimal) don't sit next to each other in a
    four-row table reading like a copy-paste error. Only escalates the
    rows that actually tie -- every other row keeps the same 1-decimal
    precision as the rest of the report -- and only ever escalates once
    (1 decimal -> 2), which is enough to separate any pair this table's
    metrics can plausibly produce; a genuine tie at 2 decimals (not seen
    in production data) is left as-is rather than escalating further.
    SUPPRESSED/NOT APPLICABLE rows are excluded -- those strings
    "colliding" is not a rounding artifact and adding decimals to them
    would be meaningless."""
    groups: dict = {}
    for r in rows:
        if r["_fmt"] == "pct" and not r["_suppressed"] and r["_raw_value"] is not None:
            groups.setdefault(r["value"], []).append(r)
    for tied in groups.values():
        if len(tied) > 1:
            for r in tied:
                r["value"] = f"{r['_raw_value'] * 100:.2f}%"


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
