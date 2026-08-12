"""Public API: resolves a metric_id (and optionally a country/region) into a BenchmarkComparison,
or a country into its national poverty rate, or a whole PPI run into the Poverty Likelihood
section's 2.2 national-comparison table.
"""

from __future__ import annotations

from typing import Optional

from schemas.common import BenchmarkComparison, SectionStatus
from schemas.poverty_likelihood import CountryPovertyResult, CountryVsNationalRate

from .mapping import (
    COUNTRY_CODE_TO_NAME,
    DELIBERATELY_EXCLUDED_METRICS,
    METRIC_ID_TO_INDICATOR_NAME,
    NPS_BENCHMARK_SCALE_FACTOR,
    OUR_REGION_TO_SHEET_REGION,
    PROVISIONAL_CAVEATS,
)
from .reference_data import load_mfi_index_sheet, load_national_poverty_rates


def get_mfi_index_benchmark(
    metric_id: str,
    benchmarks_path: str,
    country: Optional[str] = None,
    region: Optional[str] = None,
) -> BenchmarkComparison:
    """Resolves the best available 60 Decibels comparison point for `metric_id`.

    Preference order when `country` is given: that country's own peer value, else
    that country's region, else global. With only `region` given: that region, else
    global. With neither: global. Every step that falls back is silent by design --
    "no MEER regional benchmark exists" is expected, not an error -- but a metric
    with genuinely no value anywhere comes back with not_available_reason explaining why.
    """
    if metric_id in DELIBERATELY_EXCLUDED_METRICS:
        return BenchmarkComparison(not_available_reason=DELIBERATELY_EXCLUDED_METRICS[metric_id])

    indicator_name = METRIC_ID_TO_INDICATOR_NAME.get(metric_id)
    if indicator_name is None:
        return BenchmarkComparison(not_available_reason=f"No 60 Decibels indicator mapped for metric_id={metric_id!r}.")

    rows_by_name = {row.indicator_name: row for row in load_mfi_index_sheet(benchmarks_path)}
    row = rows_by_name.get(indicator_name)
    if row is None:
        return BenchmarkComparison(not_available_reason=f"Indicator {indicator_name!r} not found in the benchmark sheet.")

    value, year = None, None
    if country:
        country_name = COUNTRY_CODE_TO_NAME.get(country)
        if country_name and country_name in row.country_values:
            value, year = row.country_values[country_name]
    if value is None and region:
        sheet_region = OUR_REGION_TO_SHEET_REGION.get(region)
        if sheet_region and sheet_region in row.regional_values:
            value, year = row.regional_values[sheet_region]
    if value is None:
        value, year = row.global_value, row.global_year

    if value is None:
        reason = "No 60 Decibels value found for this indicator at any level (global/regional/country)."
        if row.comment:
            reason = f"{reason} Comment on file: {row.comment}"
        return BenchmarkComparison(external_mfi_index_definition=row.external_definition, not_available_reason=reason)

    display_value = value * NPS_BENCHMARK_SCALE_FACTOR if metric_id == "nps" else value

    return BenchmarkComparison(
        external_mfi_index=display_value,
        external_mfi_index_year=year,
        external_mfi_index_definition=row.external_definition,
        external_mfi_index_caveat=PROVISIONAL_CAVEATS.get(metric_id),
    )


class NationalPovertyRate:
    """A single country's national poverty rate lookup result: percentage points, with provenance."""

    __slots__ = ("rate", "year", "source")

    def __init__(self, rate: float, year: Optional[int], source: Optional[str]):
        self.rate = rate
        self.year = year
        self.source = source


def get_national_poverty_rate(country_code: str, line_code: str, benchmarks_path: str) -> Optional[NationalPovertyRate]:
    """The national poverty rate for `country_code` on `line_code` (e.g. 'USD190day2011PPP'),
    in percentage points -- the same scale ppi_module.pipeline reports portfolio likelihood on.
    Returns None if the country or that specific line isn't in the reference file.
    """
    country_name = COUNTRY_CODE_TO_NAME.get(country_code)
    if country_name is None:
        return None
    for row in load_national_poverty_rates(benchmarks_path):
        if row.country_name == country_name:
            rate = row.rates.get(line_code)
            if rate is None:
                return None
            return NationalPovertyRate(rate=rate, year=row.year, source=row.source)
    return None


def build_national_comparison(
    country_results: list[CountryPovertyResult], benchmarks_path: str
) -> list[CountryVsNationalRate]:
    """Builds the Poverty Likelihood section's 2.2 table from ppi_module's per-country results.

    Compares against whichever poverty line each country was actually scored on -- the first
    non-null value in CountryPovertyResult.values, which pipeline.py already builds in the
    template's own priority order (USD190day2011PPP first where available, etc.), so no
    separate priority list is needed here.
    """
    out: list = []
    for result in country_results:
        if result.status == SectionStatus.NOT_AVAILABLE or not result.values:
            continue
        portfolio_value, chosen_line = None, None
        for line_code, value in result.values.items():
            if value is not None:
                portfolio_value, chosen_line = value, line_code
                break
        if portfolio_value is None:
            continue

        national = get_national_poverty_rate(result.country_code, chosen_line, benchmarks_path)
        out.append(
            CountryVsNationalRate(
                country_code=result.country_code,
                portfolio_poverty_likelihood=portfolio_value,
                national_poverty_rate=national.rate if national else None,
                poorer_than_national=(portfolio_value > national.rate) if national else None,
                n_scored=result.n_scored,
                n_total=result.n_total,
            )
        )
    return out
