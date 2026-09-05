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
    # CC-032: there used to be a benchmark_comparable_value field here, mirroring
    # MetricResult's -- but nothing in _theme_scores() ever wrote to it (unlike MetricResult,
    # where individual sections DO populate it from their own stricter-box mask). It read as
    # populated because the exec-summary table silently fell back to printing the plain Score
    # whenever it was None. Removed rather than wired up: 5 of 7 themes are CC-011 unweighted
    # means of several constituents on different box definitions, so there is no single
    # "comparable basis" for the theme as a whole -- the same reasoning CC-011 already applied
    # to `benchmark` itself. See docs/core_credit_report_spec.md CC-032 for the full reasoning.


class ExecutiveSummarySection(BaseModel):
    theme_scores: list[ThemeScore] = Field(default_factory=list)
    n_respondents: int
    n_mfis: int
    n_countries: int
    reporting_period: str
    generated_date: str
    analysis_text: Optional[WrittenText] = None
