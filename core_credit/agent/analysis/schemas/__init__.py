"""Pydantic contracts for the Core Credit Impact Report pipeline.

These schemas are the interface between the deterministic engines (metrics,
PPI, benchmarks), the qualitative agent, and the writer step. Nothing here
depends on pandas, LangChain, or a specific data source -- they only
describe shapes.
"""

from .agency import AgencySection
from .business_household_impact import BusinessHouseholdImpactSection
from .child_wellbeing import ChildWellbeingSection
from .client_profile import ClientProfileSection
from .client_protection import ClientProtectionSection
from .client_satisfaction import ClientSatisfactionSection, NPSResult
from .client_voices import ClientVoicesSection
from .common import (
    BenchmarkComparison,
    GapComparison,
    MetricResult,
    QualitativeSynthesis,
    RankedOption,
    RankedOptions,
    SectionStatus,
    SegmentAxis,
    SegmentedValue,
    SignificanceResult,
    ThemeFinding,
    Verbatim,
    WrittenText,
)
from .executive_summary import ExecutiveSummarySection, ThemeScore
from .financial_access import FinancialAccessSection
from .gender_scorecard import GenderScorecardRow, GenderScorecardSection
from .poverty_likelihood import CountryPovertyResult, CountryVsNationalRate, PovertyLikelihoodSection
from .report import CoreCreditImpactReport
from .resilience import ResilienceSection

__all__ = [
    "AgencySection",
    "BenchmarkComparison",
    "BusinessHouseholdImpactSection",
    "ChildWellbeingSection",
    "ClientProfileSection",
    "ClientProtectionSection",
    "ClientSatisfactionSection",
    "ClientVoicesSection",
    "CoreCreditImpactReport",
    "CountryPovertyResult",
    "CountryVsNationalRate",
    "ExecutiveSummarySection",
    "FinancialAccessSection",
    "GapComparison",
    "GenderScorecardRow",
    "GenderScorecardSection",
    "MetricResult",
    "NPSResult",
    "PovertyLikelihoodSection",
    "QualitativeSynthesis",
    "RankedOption",
    "RankedOptions",
    "ResilienceSection",
    "SectionStatus",
    "SegmentAxis",
    "SegmentedValue",
    "SignificanceResult",
    "ThemeFinding",
    "ThemeScore",
    "Verbatim",
    "WrittenText",
]
