"""Part 6 -- Agency. Run for real end to end via graph/run_graph.py (thread_id
"agency-real-run", output at graph/output/agency_agency-real-run.json): clean grounding on
every subsection, and a genuinely striking real finding worth flagging to the country team --
Montenegro's community respect improvement sits at 15.3% (n=262, not a small-sample artifact)
against Senegal/Mali/Kenya all above 95%.

qualitative=None deliberately, even though AGENCY04b ("describe the change" in household
influence) is a real free-text field: it's very thin (only 23 non-blank responses out of
5,827 this quarter) AND AgencySection has no QualitativeSynthesis field to hold the result
yet -- wiring up a qualitative pass with nowhere to put its output would mean paying for real
LLM calls and throwing the result away. Add a schema field first if this is worth pursuing.
"""

from __future__ import annotations

from schemas.agency import AgencySection
from writer.section_prompts import (
    AGENCY_INSIGHT,
    COMMUNITY_RESPECT_IMPROVED,
    HOUSEHOLD_INFLUENCE_IMPROVED,
    LOAN_PURPOSE_ACHIEVED,
)

from ..config import MetricConfig, SectionConfig

TOP_2_BOX_IMPROVED = frozenset({"a. Very much improved", "b. Slightly improved"})

AGENCY_CONFIG = SectionConfig(
    section_id="agency",
    schema_class=AgencySection,
    metrics=(
        MetricConfig(
            metric_id="loan_purpose_achieved_fully",
            label="Fully achieved the loan's purpose",
            source_column="Agency/AGENCY03_resp_en",
            top_box_values=frozenset({"a. Yes, in full"}),
            # Provisional per benchmark_module's PROVISIONAL_CAVEATS: MFI Index's "achieved ALL
            # their goals" is assumed to bind to this ("fully achieved"), not the partial figure.
        ),
        MetricConfig(
            metric_id="loan_purpose_achieved_partially",
            label="Partially achieved the loan's purpose",
            source_column="Agency/AGENCY03_resp_en",
            top_box_values=frozenset({"b. Yes, partially"}),
            has_benchmark=False,  # no separate MFI Index indicator for partial achievement
        ),
        MetricConfig(
            metric_id="household_influence_improved",
            label="Household influence improved",
            source_column="Agency/AGENCY04_resp_en",
            top_box_values=TOP_2_BOX_IMPROVED,
            has_benchmark=False,  # in benchmark_module.DELIBERATELY_EXCLUDED_METRICS
        ),
        MetricConfig(
            metric_id="community_respect_improved",
            label="Community respect improved",
            source_column="Agency/AGENCY05_resp_en",
            top_box_values=TOP_2_BOX_IMPROVED,
            # Mapped in benchmark_module, but the source sheet's cell is blank -- lookup
            # reports not_available_reason gracefully.
        ),
    ),
    metric_schema_fields={
        "loan_purpose_achieved_fully": "loan_purpose_achieved_fully",
        "loan_purpose_achieved_partially": "loan_purpose_achieved_partially",
        "household_influence_improved": "household_influence_improved",
        "community_respect_improved": "community_respect_improved",
    },
    subsection_prompts=(LOAN_PURPOSE_ACHIEVED, HOUSEHOLD_INFLUENCE_IMPROVED, COMMUNITY_RESPECT_IMPROVED),
    subsection_metric_ids={
        "6.1": ("loan_purpose_achieved_fully", "loan_purpose_achieved_partially"),
        "6.2": ("household_influence_improved",),
        "6.3": ("community_respect_improved",),
    },
    written_text_fields={
        "6.1": "loan_purpose_achieved_analysis",
        "6.2": "household_influence_improved_analysis",
        "6.3": "community_respect_improved_analysis",
    },
    insight_prompt=AGENCY_INSIGHT,
    insight_metric_ids=(
        "loan_purpose_achieved_fully",
        "loan_purpose_achieved_partially",
        "household_influence_improved",
        "community_respect_improved",
    ),
    insight_text_field="insight_text",
    insight_verbatims_field="insight_verbatims",
    qualitative=None,
    qualitative_schema_field=None,
    validated=True,
)
