"""Contract for the Executive Summary scorecard.

This section can only be produced after every theme section has been
computed, since it reads across all of them -- it belongs to the
cross-cutting synthesis step, not any single-section engine call.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import BenchmarkComparison, WrittenText


class ThemeScore(BaseModel):
    theme_name: str
    metric_label: str = Field(..., description="What headline_value actually measures, e.g. 'Fully achieved loan purpose'")
    headline_value: float
    is_percentage: bool = Field(
        default=True,
        description="False only for Client Satisfaction's NPS, which runs -100..100 -- every "
        "other theme's headline_value is a 0-1 share. Never compare a non-percentage score "
        "against the others on the same scale.",
    )
    benchmark: Optional[BenchmarkComparison] = None
    benchmark_comparable_value: Optional[float] = Field(
        default=None,
        description="headline_value's own figure on the SAME box-type basis as `benchmark` "
        "(usually 'very much' only, same as MetricResult.benchmark_comparable_value elsewhere) "
        "-- compare the benchmark against THIS, not headline_value, whenever both are present.",
    )


class ExecutiveSummarySection(BaseModel):
    theme_scores: list[ThemeScore] = Field(default_factory=list)
    n_respondents: int
    n_mfis: int
    n_countries: int
    reporting_period: str
    generated_date: str
    analysis_text: Optional[WrittenText] = None
