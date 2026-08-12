"""Contract for Part 6 -- Agency."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, Verbatim, WrittenText


class AgencySection(BaseModel):
    loan_purpose_achieved_fully: MetricResult  # 6.1
    loan_purpose_achieved_partially: MetricResult  # 6.1
    loan_purpose_achieved_analysis: Optional[WrittenText] = None  # covers both 6.1 metrics together
    household_influence_improved: MetricResult  # 6.2
    household_influence_improved_analysis: Optional[WrittenText] = None
    community_respect_improved: MetricResult  # 6.3
    community_respect_improved_analysis: Optional[WrittenText] = None
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
