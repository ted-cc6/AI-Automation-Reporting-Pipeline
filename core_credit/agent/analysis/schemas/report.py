"""Top-level container: one instance of this is the full report's structured data."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel

from .agency import AgencySection
from .business_household_impact import BusinessHouseholdImpactSection
from .child_wellbeing import ChildWellbeingSection
from .client_profile import ClientProfileSection
from .client_protection import ClientProtectionSection
from .client_satisfaction import ClientSatisfactionSection
from .client_voices import ClientVoicesSection
from .executive_summary import ExecutiveSummarySection
from .financial_access import FinancialAccessSection
from .gender_scorecard import GenderScorecardSection
from .poverty_likelihood import PovertyLikelihoodSection
from .resilience import ResilienceSection


class CoreCreditImpactReport(BaseModel):
    """run_id and model_version exist so any figure in this report can be traced back to the
    real run and model that produced it -- added after a real incident where the same wave's
    qualitative theme-tagging produced materially different findings across two separate runs
    (e.g. one theme's share moved from 53.4% to 59.8%) with nothing in the document itself
    saying which run's numbers a reader was looking at. Anthropic's API has no seed parameter
    (confirmed: no `seed` field on ChatAnthropic, and `temperature` is rejected outright by
    Sonnet 5), so bit-for-bit reproducibility of an LLM-tagged qualitative pass isn't
    achievable right now -- this is the honest fallback: not eliminating the variance, but
    making every run's output traceable to exactly the run and model version that made it.
    """

    reporting_period: str
    generated_at: str
    run_id: Optional[str] = None
    model_version: Optional[str] = None

    client_profile: ClientProfileSection
    financial_access: FinancialAccessSection
    poverty_likelihood: PovertyLikelihoodSection
    business_household_impact: BusinessHouseholdImpactSection
    child_wellbeing: ChildWellbeingSection
    client_protection: ClientProtectionSection
    agency: AgencySection
    resilience: ResilienceSection
    client_satisfaction: ClientSatisfactionSection

    # Cross-cutting sections: only fillable once every theme section above is done.
    executive_summary: Optional[ExecutiveSummarySection] = None
    gender_scorecard: Optional[GenderScorecardSection] = None
    client_voices: Optional[ClientVoicesSection] = None
