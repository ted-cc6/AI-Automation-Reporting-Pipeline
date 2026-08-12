"""Contract for Part 1 -- Financial Access."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, Verbatim, WrittenText


class FinancialAccessSection(BaseModel):
    first_time_access: MetricResult  # 1.1
    first_time_access_analysis: Optional[WrittenText] = None
    alternative_lender_hard_to_find: MetricResult  # 1.2
    alternative_lender_hard_to_find_analysis: Optional[WrittenText] = None
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
