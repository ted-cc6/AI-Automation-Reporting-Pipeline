"""CC-097: the year-over-year table that follows the Executive Summary. Built in code from
<run>_yoy_deltas.json (yoy/table.py); nothing in it is written by the LLM."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class YoYRow(BaseModel):
    label: str
    group: str = Field(description="who the figure describes, e.g. 'all clients', a country, 'Loan cycle 2'")
    value_2025: Optional[float] = None
    value_2026: Optional[float] = None
    change_pts: Optional[float] = None
    significant: bool = False
    is_score: bool = Field(default=False, description="True for the NPS score (points, not a share)")
    is_count: bool = Field(default=False, description="CC-099: values are answer counts (protection signals)")
    note: Optional[str] = None


class YearOverYearSection(BaseModel):
    comparison_wave: int
    report_wave: int
    comparison_countries: list[str] = Field(description="full names")
    excluded_countries: dict[str, str] = Field(default_factory=dict, description="name -> reason")
    partial_countries: list[str] = Field(default_factory=list, description="full names")
    provisional: bool = True
    note: str
    headline_rows: list[YoYRow]
    gender_rows: list[YoYRow] = Field(default_factory=list)
    loan_cycle_rows: list[YoYRow] = Field(default_factory=list)
    country_rows: list[YoYRow] = Field(default_factory=list)
    review_rows: list[YoYRow] = Field(default_factory=list, description="CC-095 swing-flagged figures, not narrated")
    theme_rows: list[YoYRow] = Field(default_factory=list, description="CC-099 significant theme-share changes")
    protection_rows: list[YoYRow] = Field(default_factory=list, description="CC-099 protection-signal counts, both years")
