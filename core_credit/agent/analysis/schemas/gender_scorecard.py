"""Contract for the cross-cutting Gender scorecard (template page 9)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import SignificanceResult, Verbatim, WrittenText


class GenderScorecardRow(BaseModel):
    metric_label: str
    female_share: Optional[float] = Field(default=None, ge=0, le=1)
    male_share: Optional[float] = Field(default=None, ge=0, le=1)
    gap: Optional[float] = None
    significance: Optional[SignificanceResult] = None


class GenderScorecardSection(BaseModel):
    rows: list[GenderScorecardRow] = Field(default_factory=list)
    analysis_text: Optional[WrittenText] = None
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
