"""Contract for Part 2 -- Poverty Likelihood (PPI).

This is the richest of the section schemas because country coverage is
genuinely uneven: some countries score on $-a-day lines, Vietnam scores on
national percentiles, and several countries are not available at all this
wave (policy exclusion, missing scorecard, or an incomplete question set).
`CountryPovertyResult` is what the PPI module produces per country; the
section-level fields aggregate those into what the template's 2.1/2.2
subsections actually ask for.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

from .common import MetricResult, SectionStatus, Verbatim, WrittenText


class CountryPovertyResult(BaseModel):
    country_code: str
    mfi_name: Optional[str] = None
    status: SectionStatus
    status_reason: Optional[str] = Field(
        default=None, description="Why NOT_AVAILABLE/PARTIAL, e.g. 'Excluded by policy this wave'"
    )
    metric_type: Optional[Literal["dollar_line", "percentile"]] = None
    guide_id: Optional[str] = None
    survey_version: Optional[str] = None
    values: dict[str, Optional[float]] = Field(
        default_factory=dict, description="line_code -> average poverty likelihood %, e.g. {'USD190day2011PPP': 3.8}"
    )
    n_scored: int = 0
    n_total: int = 0
    n_unscored_label_conflict: int = Field(
        default=0,
        description="CC-025: of the unscored clients, how many are attributable ONLY to a "
        "scorecard label typo (a fixable PPI_scorecards.xlsx defect). 0 unless the guide has a "
        "conflicting-option-label question this wave (Kenya, Zambia).",
    )
    n_unscored_incomplete: int = Field(
        default=0,
        description="CC-025: of the unscored clients, how many failed on ordinary incomplete PPI "
        "responses rather than the label typo. Together with n_unscored_label_conflict this sums "
        "to n_total - n_scored. 0 unless the label-conflict split was computed.",
    )


class CountryVsNationalRate(BaseModel):
    country_code: str
    portfolio_poverty_likelihood: Optional[float] = None
    national_poverty_rate: Optional[float] = None  # filled in by the benchmark module later
    poorer_than_national: Optional[bool] = None
    n_scored: Optional[int] = None
    n_total: Optional[int] = None


class PovertyLikelihoodSection(BaseModel):
    country_results: list[CountryPovertyResult] = Field(default_factory=list)
    poverty_line_shares: list[MetricResult] = Field(
        default_factory=list, description="One MetricResult per line code, aggregated across countries that report it"
    )
    poverty_line_shares_analysis: Optional[WrittenText] = None  # 2.1
    national_comparison: list[CountryVsNationalRate] = Field(default_factory=list)  # 2.2
    national_comparison_analysis: Optional[WrittenText] = None  # 2.2
    na_footnote: Optional[str] = Field(
        default=None, description="Combined footnote listing every NA country and why"
    )
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
