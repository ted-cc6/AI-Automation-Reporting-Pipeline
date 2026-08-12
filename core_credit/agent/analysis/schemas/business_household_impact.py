"""Contract for Part 3 -- Business & Household Impact."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, QualitativeSynthesis, Verbatim, WrittenText


class BusinessHouseholdImpactSection(BaseModel):
    business_income_change: MetricResult  # 3.1, top-2-box
    business_income_analysis: Optional[WrittenText] = None  # 3.1 written prose
    quality_of_life_change: MetricResult  # 3.2, top-2-box
    quality_of_life_analysis: Optional[WrittenText] = None  # 3.2 written prose
    qol_drivers: Optional[QualitativeSynthesis] = None  # 3.3
    insight_text: Optional[WrittenText] = None  # Insight for Business and Household Impact
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
