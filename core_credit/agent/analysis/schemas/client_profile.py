"""Contract for the "Client Profile & Methodology" section (template page 1)."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, RankedOptions, SegmentAxis, WrittenText


class ClientProfileSection(BaseModel):
    n_respondents: int
    n_mfis: int = Field(
        ..., description="Equal to n_countries -- VisionFund runs one MFI entity per country in this "
        "portfolio, and the analysis-ready data has no separate MFI identifier to check that against."
    )
    n_countries: int
    gender_split: RankedOptions
    age: MetricResult  # mean, not a share -- see SegmentedValue.mean
    household_size: MetricResult  # mean, not a share
    loan_cycle_mix: RankedOptions
    household_head_status: RankedOptions
    education_level: RankedOptions
    main_income_source: RankedOptions
    populated_segments: list[SegmentAxis] = Field(default_factory=list)
    unavailable_segments: list[str] = Field(
        default_factory=list,
        description="Segments flagged as not populated this wave, e.g. 'Savings usage'",
    )
    analysis_text: Optional[WrittenText] = None
    fieldwork_start_date: Optional[str] = Field(
        default=None,
        description="Earliest 'start' timestamp across all respondents (YYYY-MM-DD) -- replaces guessing the "
        "reporting period from the uploaded filename, which fails ('unknown period') whenever the file isn't "
        "named with a YYYYQN pattern.",
    )
    fieldwork_end_date: Optional[str] = Field(
        default=None, description="Latest 'end' timestamp across all respondents (YYYY-MM-DD)"
    )
