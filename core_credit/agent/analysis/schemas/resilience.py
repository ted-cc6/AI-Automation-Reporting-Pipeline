"""Contract for Part 7 -- Resilience."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, QualitativeSynthesis, RankedOptions, Verbatim, WrittenText


class ResilienceSection(BaseModel):
    savings_increased: MetricResult  # 7.1
    savings_increased_analysis: Optional[WrittenText] = None
    shock_incidence: MetricResult  # 7.2
    shock_impacts: RankedOptions  # 7.2, main impacts (income/assets/health)
    shock_incidence_analysis: Optional[WrittenText] = None
    coping_mechanisms: RankedOptions  # 7.3
    negative_coping_share: MetricResult  # 7.3, client-protection flag
    other_coping_qualitative: Optional[QualitativeSynthesis] = None  # 7.3, RESILIENCE03c free text
    coping_mechanisms_analysis: Optional[WrittenText] = None
    vf_reduced_shock_severity: MetricResult  # 7.4
    vf_reduced_shock_severity_analysis: Optional[WrittenText] = None
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
