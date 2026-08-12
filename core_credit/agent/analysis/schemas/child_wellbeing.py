"""Contract for Part 4 -- Child Wellbeing."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import GapComparison, MetricResult, QualitativeSynthesis, RankedOptions, Verbatim, WrittenText


class ChildWellbeingSection(BaseModel):
    improved_child_wellbeing: MetricResult  # 4.1, base = caregivers only
    what_improved: RankedOptions  # 4.1 ranked list
    other_improvements_qualitative: Optional[QualitativeSynthesis] = None  # 4.1, IMPACT04b free text
    improved_child_wellbeing_analysis: Optional[WrittenText] = None  # 4.1
    caregiver_vs_other: list[GapComparison] = Field(
        default_factory=list,
        description="8 rows: QoL, financial worry, community respect, business income, loan "
        "goal achieved, household influence, savings, NPS. Self-contained -- each row's mask "
        "is re-derived straight from the same CSV column other sections use, not read from "
        "their computed output -- but 5 of the 8 box definitions are borrowed from Client "
        "Protection and Agency, both still validated=False; revisit if those definitions change.",
    )  # 4.2
    caregiver_vs_other_analysis: Optional[WrittenText] = None  # 4.2
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
