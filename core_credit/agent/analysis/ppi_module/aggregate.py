"""Aggregates ppi_module.pipeline's per-country PPI results into the report-ready
MetricResult shape the writer needs for the template's 2.1 subsection (poverty likelihood
across poverty lines).

Each CountryPovertyResult already carries a MEAN poverty likelihood per line code -- a
per-client probability of falling below that line, averaged across the country's scored
clients -- not a boolean top-box share. That means this deliberately does NOT reuse
metrics_engine.engine.metric_result(), which crosstabs a boolean mask: the input shape here
is fundamentally different (a value ppi_module already averaged, not a raw per-respondent
answer). Weighting each country's mean by its own n_scored when rolling up to a portfolio-wide
figure reproduces the same number as if the mean had been taken directly over every scored
client in one pass, since a weighted average by count is mathematically the same as pooling.

No external MFI Index benchmark exists for these poverty lines -- confirmed against
benchmark_module.mapping.METRIC_ID_TO_INDICATOR_NAME, which has no PPI/poverty entry, because
60 Decibels doesn't report a PPI-comparable indicator. BenchmarkComparison is deliberately left
unset rather than guessed; the country/region breakdown below is how the template's "compare to
the regional/global benchmark where available" instruction is met honestly -- with VisionFund's
own internal cuts, not an external number that doesn't exist.

n_scored is CountryPovertyResult's one overall count (the max across that country's lines, per
pipeline.py), not a count scoped to this specific line -- the schema doesn't track a finer-grained
per-line n. Using it as the per-line weight is a reasonable approximation, not exact, since a
handful of clients could in principle score on one line's lookup row but not another's.
"""

from __future__ import annotations

from typing import Optional

from schemas.common import MetricResult, SegmentAxis, SegmentedValue
from schemas.poverty_likelihood import CountryPovertyResult

from .country_policy import TARGET_LINES

LINE_LABELS = {
    "USD190day2011PPP": "$1.90/day (2011 PPP)",
    "USD215day2017PPP": "$2.15/day (2017 PPP)",
    "USD320day2011PPP": "$3.20/day (2011 PPP)",
}

NO_BENCHMARK_NOTE = (
    "No external MFI Index benchmark exists for PPI poverty lines this wave. Country and "
    "region cuts above are VisionFund's own portfolio breakdown, not an outside comparison."
)


def _weighted_mean(pairs: list[tuple[float, int]]) -> Optional[float]:
    total_n = sum(n for _, n in pairs)
    if total_n == 0:
        return None
    return sum(value * n for value, n in pairs) / total_n


_LOW_COVERAGE_THRESHOLD = 0.9


def _country_label(name: str, n_scored: int, n_total: int) -> str:
    """Confirmed the hard way that giving the writer a bare country name and a scored n with
    no total lets a severe-undercoverage figure (Zambia: 32 of 281 clients scored, i.e. 89%
    of the country's respondents excluded) reach the finished report as an unqualified
    headline number. Folding the coverage directly into the label -- the one piece of text
    that reliably survives into whatever the model writes about this row -- means the caveat
    travels with the number instead of depending on the model choosing to mention n_total,
    which it wasn't given anywhere else at this call site.
    """
    if n_total <= 0 or n_scored >= n_total * _LOW_COVERAGE_THRESHOLD:
        return name
    coverage_pct = round(100 * n_scored / n_total)
    return f"{name} (only {n_scored} of {n_total} clients scored, {coverage_pct}% coverage)"


def aggregate_poverty_line_shares(
    country_results: list[CountryPovertyResult],
    country_to_region: dict,
    country_to_name: dict,
) -> list:
    """One MetricResult per TARGET_LINES entry that at least one country actually reports,
    in the template's own priority order ($1.90, then $2.15, then $3.20). Countries that don't
    report a given line (NOT_AVAILABLE, or a guide with no populated column for it) are simply
    absent from that line's by_segment -- not shown as a zero.
    """
    metrics = []
    for line_code in TARGET_LINES:
        contributors = [
            (r.country_code, r.values[line_code], r.n_scored, r.n_total)
            for r in country_results
            if r.values.get(line_code) is not None
        ]
        if not contributors:
            continue

        overall_value = _weighted_mean([(v, n) for _, v, n, _ in contributors])
        overall_n = sum(n for _, _, n, _ in contributors)
        overall_n_total = sum(n_total for _, _, _, n_total in contributors)

        by_segment = [
            SegmentedValue(
                axis=SegmentAxis.COUNTRY,
                value_label=_country_label(country_to_name.get(country_code, country_code), n, n_total),
                share=value / 100,
                n=n,
            )
            for country_code, value, n, n_total in contributors
        ]

        by_region: dict = {}
        for country_code, value, n, _n_total in contributors:
            region = country_to_region.get(country_code)
            if region is not None:
                by_region.setdefault(region, []).append((value, n))
        for region, pairs in by_region.items():
            region_value = _weighted_mean(pairs)
            by_segment.append(
                SegmentedValue(
                    axis=SegmentAxis.REGION,
                    value_label=region,
                    share=None if region_value is None else region_value / 100,
                    n=sum(n for _, n in pairs),
                )
            )

        coverage_note = (
            f"Portfolio-wide base: {overall_n} of {overall_n_total} surveyed clients across "
            f"{len(contributors)} countries were successfully PPI-scored for this line "
            f"({round(100 * overall_n / overall_n_total) if overall_n_total else 0}% coverage). "
            f"Always state this scored base when citing the overall or any country figure below."
        )

        metrics.append(
            MetricResult(
                metric_id=f"poverty_likelihood_{line_code}",
                label=f"Below {LINE_LABELS.get(line_code, line_code)}",
                overall=SegmentedValue(
                    axis=SegmentAxis.OVERALL,
                    value_label="Overall",
                    share=None if overall_value is None else overall_value / 100,
                    n=overall_n,
                ),
                by_segment=by_segment,
                benchmark=None,
                notes=f"{NO_BENCHMARK_NOTE} {coverage_note}",
            )
        )
    return metrics


def country_to_region_map(df, country_col: str, region_col: str) -> dict:
    """Builds {country_code: region} straight from the analysis-ready CSV -- verified against
    the real data that every client sharing a country also shares one region (see
    ppi_module/tests/test_aggregate.py), so taking the first non-blank value per country is safe.
    """
    out: dict = {}
    for country_code, group in df.groupby(country_col):
        code = str(country_code).strip()
        if not code:
            continue
        regions = [str(v).strip() for v in group[region_col] if str(v).strip()]
        if regions:
            out[code] = regions[0]
    return out
