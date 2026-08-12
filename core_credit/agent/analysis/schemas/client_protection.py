"""Contract for Part 5 -- Client Protection."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field

from .common import MetricResult, QualitativeSynthesis, Verbatim, WrittenText


class ClientProtectionSection(BaseModel):
    financial_worry_decreased: MetricResult  # 5.1
    financial_worry_decreased_analysis: Optional[WrittenText] = None
    loan_terms_clear: MetricResult  # 5.2
    loan_terms_clear_analysis: Optional[WrittenText] = None
    complaints_mechanism_trusted: MetricResult  # 5.3
    complaints_mechanism_trusted_analysis: Optional[WrittenText] = None
    no_unfair_treatment: MetricResult  # 5.4
    reported_when_unfair: Optional[MetricResult] = None  # 5.4 sub-base: those who experienced unfair treatment
    no_unfair_treatment_analysis: Optional[WrittenText] = None  # covers both 5.4 metrics together
    did_not_reduce_food: MetricResult  # 5.5
    did_not_reduce_food_analysis: Optional[WrittenText] = None
    protection_signals: Optional[QualitativeSynthesis] = None  # qualitative, severity-tiered (IMPACT03c + CLIENTSAT01b)
    insight_text: Optional[WrittenText] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
