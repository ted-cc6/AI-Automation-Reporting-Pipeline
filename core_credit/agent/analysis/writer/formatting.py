"""Turns a MetricResult / NPSResult into a compact, plain-text summary for the writer prompt.

Deliberately terse and numeric, not prose -- the writer chain does the prose-writing; this
just gives it a clean, unambiguous view of the real numbers so it has nothing to guess at.
"""

from __future__ import annotations

from schemas.client_satisfaction import NPSResult
from schemas.common import MetricResult, RankedOptions, SegmentedValue
from schemas.poverty_likelihood import CountryVsNationalRate


def _format_segmented(sv: SegmentedValue) -> str:
    if sv.share is not None:
        return f"{sv.share:.1%} (n={sv.n})"
    if sv.mean is not None:
        return f"mean={sv.mean:.1f} (n={sv.n})"
    return f"no data (n={sv.n})"


def format_metric_result(mr: MetricResult) -> str:
    lines = [f"{mr.label}: overall {_format_segmented(mr.overall)}"]
    for seg in mr.by_segment:
        lines.append(f"  - {seg.axis.value}={seg.value_label}: {_format_segmented(seg)}")
    if mr.benchmark and mr.benchmark.external_mfi_index is not None:
        caveat = f" [CAVEAT: {mr.benchmark.external_mfi_index_caveat}]" if mr.benchmark.external_mfi_index_caveat else ""
        definition = f' -- defined by the source as "{mr.benchmark.external_mfi_index_definition}"' if mr.benchmark.external_mfi_index_definition else ""
        lines.append(f"  - MFI Index benchmark: {mr.benchmark.external_mfi_index:.1%} ({mr.benchmark.external_mfi_index_year}){definition}{caveat}")
        if mr.benchmark_comparable_value is not None and mr.benchmark_comparable_value.share is not None:
            lines.append(
                f"  - Our own figure on the SAME basis as that benchmark (use this one for the "
                f"comparison, not 'overall' above): {_format_segmented(mr.benchmark_comparable_value)}"
            )
    if mr.notes:
        lines.append(f"  - Note: {mr.notes}")
    return "\n".join(lines)


_LOW_COVERAGE_THRESHOLD = 0.9


def format_national_comparison(rows: list[CountryVsNationalRate]) -> str:
    """Note: unlike SegmentedValue.share (a 0-1 fraction), portfolio_poverty_likelihood and
    national_poverty_rate are already percentage points (e.g. 21.6 means 21.6%) -- see
    benchmark_module/reference_data.py's own docstring on this -- so these are formatted with
    a plain '%' suffix, not Python's ':.1%' spec, which would multiply by 100 again.

    Confirmed the hard way that a country figure resting on a small scored fraction (e.g.
    Zambia: 32 of 281 clients) reached a real report as an unqualified headline with no
    caveat anywhere nearby -- the coverage flag below is deliberately inline with the number
    it qualifies, the same fix as aggregate_poverty_line_shares' country labels for 2.1.
    """
    lines = ["MFI poverty likelihood vs. national poverty rate, by country:"]
    for row in rows:
        portfolio = f"{row.portfolio_poverty_likelihood:.1f}%" if row.portfolio_poverty_likelihood is not None else "no data"
        national = f"{row.national_poverty_rate:.1f}%" if row.national_poverty_rate is not None else "no national rate on file"
        verdict = ""
        if row.poorer_than_national is True:
            verdict = " -- portfolio is POORER than the national rate (targeting the poor)"
        elif row.poorer_than_national is False:
            verdict = " -- portfolio is LESS poor than the national rate"
        coverage = ""
        if row.n_scored is not None and row.n_total and row.n_scored < row.n_total * _LOW_COVERAGE_THRESHOLD:
            coverage_pct = round(100 * row.n_scored / row.n_total)
            coverage = f" [LOW COVERAGE: only {row.n_scored} of {row.n_total} clients scored, {coverage_pct}%]"
        lines.append(f"  - {row.country_code}: portfolio {portfolio} vs. national {national}{verdict}{coverage}")
    return "\n".join(lines)


def format_ranked_options(label: str, options: RankedOptions) -> str:
    lines = [f"{label} (base n={options.base_n}):"]
    for opt in options.options:
        lines.append(f"  - {opt.label}: {opt.share:.1%} (n={opt.n})")
    return "\n".join(lines)


def format_nps_result(nps: NPSResult) -> str:
    lines = [
        f"NPS: {nps.score:.0f} (promoters {nps.promoter_share:.1%}, passives {nps.passive_share:.1%}, "
        f"detractors {nps.detractor_share:.1%}, n={nps.n})"
    ]
    for seg in nps.by_segment:
        lines.append(f"  - {seg.axis.value}={seg.value_label}: {_format_segmented(seg)}")
    if nps.benchmark and nps.benchmark.external_mfi_index is not None:
        caveat = f" [CAVEAT: {nps.benchmark.external_mfi_index_caveat}]" if nps.benchmark.external_mfi_index_caveat else ""
        lines.append(f"  - MFI Index benchmark: {nps.benchmark.external_mfi_index:.0f} ({nps.benchmark.external_mfi_index_year}){caveat}")
    return "\n".join(lines)
