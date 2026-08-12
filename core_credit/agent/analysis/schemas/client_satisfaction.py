"""Contract for Part 8 -- Client Satisfaction."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import BenchmarkComparison, RankedOptions, SegmentedValue, QualitativeSynthesis, Verbatim, WrittenText


class NPSResult(BaseModel):
    score: float = Field(..., description="Promoter share minus detractor share, x100")
    promoter_share: float = Field(..., ge=0, le=1)
    passive_share: float = Field(..., ge=0, le=1)
    detractor_share: float = Field(..., ge=0, le=1)
    n: int = Field(..., ge=0)
    by_segment: list[SegmentedValue] = Field(default_factory=list)
    benchmark: Optional[BenchmarkComparison] = None


class ClientSatisfactionSection(BaseModel):
    nps: NPSResult  # 8.1
    nps_analysis: Optional[WrittenText] = None  # 8.1
    promoter_drivers: RankedOptions  # 8.2
    detractor_pain_points: RankedOptions  # 8.2
    nps_followup_themes: list[QualitativeSynthesis] = Field(
        default_factory=list, description="Theme-tagged NPS follow-up text, split by score band 9-10 / 7-8 / 0-6"
    )
    drivers_analysis: Optional[WrittenText] = None  # 8.2
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
