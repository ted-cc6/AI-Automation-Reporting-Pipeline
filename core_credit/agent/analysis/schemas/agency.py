"""Contract for Part 6 -- Agency."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, RankedOptions, Verbatim, WrittenText


class AgencySection(BaseModel):
    loan_purpose_achieved_fully: MetricResult  # 6.1
    loan_purpose_achieved_partially: MetricResult  # 6.1
    loan_purpose_achieved: Optional[MetricResult] = None  # combined "Yes, in full" + "Yes, partially" --
    # the dashboard spec's "Goal Achievement" basis, feeds the Agency theme score ONLY (CC-010).
    # Optional so section outputs produced before CC-010 still load; a fresh run always populates it.
    loan_purpose_achieved_analysis: Optional[WrittenText] = None  # covers both 6.1 metrics together
    household_influence_improved: MetricResult  # 6.2
    household_influence_improvements: Optional[RankedOptions] = None  # 6.2 -- CC-024: AGENCY04a
    # "in what ways?", asked only of clients who reported an improvement. Feeds the 6.2 follow-on
    # sentence naming the most common improvement. Optional so pre-CC-024 outputs still load.
    household_influence_improved_analysis: Optional[WrittenText] = None
    community_respect_improved: MetricResult  # 6.3
    community_respect_improved_analysis: Optional[WrittenText] = None
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
