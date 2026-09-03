"""Contract for Part 4 -- Child Wellbeing."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import GapComparison, MetricResult, QualitativeSynthesis, RankedOptions, Verbatim, WrittenText


class CaregiverGapStandardisation(BaseModel):
    """4.2, one row per outcome (CC-026): the observed caregiver-minus-non-caregiver gap after
    re-weighting both groups to a common country distribution, plus the share of the observed
    gap that country mix accounts for. Computed by
    metrics_engine.engine.directly_standardised_gap over the countries with a non-caregiver
    base at or above metrics_engine.engine.LOW_N_THRESHOLD. Parallel to
    ChildWellbeingSection.caregiver_vs_other -- same order, same length."""

    outcome: str
    raw_gap: Optional[float] = None  # = the matching GapComparison.gap, carried so the row is self-contained
    standardised_gap: Optional[float] = None  # None if no country has a usable non-caregiver base this wave
    composition_share: Optional[float] = None  # (raw_gap - standardised_gap) / raw_gap; >1 or sign-flipped when standardisation reverses the gap
    top_composition_countries: list[str] = Field(
        default_factory=list, description="countries accounting for most of raw_gap - standardised_gap"
    )


class CaregiverStandardisationSupport(BaseModel):
    """4.2 (CC-026): which countries the 4.2 standardisation was computed over, so the
    exclusion is visible rather than silent. `included` / `excluded` map country ->
    non-caregiver respondent count (across all outcomes)."""

    n_threshold: int = 30
    method: str = (
        "direct standardisation to the full analysis-ready sample's country distribution, "
        "renormalised over the included countries"
    )
    caregiver_n: int = 0
    non_caregiver_n: int = 0
    included: dict[str, int] = Field(default_factory=dict)
    excluded: dict[str, int] = Field(default_factory=dict)
    concentration_note: str = ""  # e.g. "ECU and MNE hold 28% of the 967 non-caregiver respondents between them"


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
    caregiver_standardisation: list[CaregiverGapStandardisation] = Field(
        default_factory=list,
        description="4.2 (CC-026): country-standardised counterpart to each caregiver_vs_other "
        "row, same order and length. None of this wave's raw gaps survive standardisation -- "
        "most of each gap is which countries the two groups sit in, not caregiver status.",
    )  # 4.2
    caregiver_standardisation_support: Optional[CaregiverStandardisationSupport] = None  # 4.2 (CC-026)
    caregiver_vs_other_analysis: Optional[WrittenText] = None  # 4.2
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
