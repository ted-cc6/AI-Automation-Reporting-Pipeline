"""Part 3 -- Business & Household Impact. The reference config: migrated from the original
hand-written driver (driver/build_business_household_impact.py) and the Part-3-only graph,
both of which already proved this exact shape end to end against the real, full dataset.
"""

from __future__ import annotations

from qualitative_agent.agent import QUALITY_OF_LIFE_DRIVERS_TASK
from qualitative_agent.data_prep import QUALITY_OF_LIFE_DRIVER_COLS
from schemas.business_household_impact import BusinessHouseholdImpactSection
from writer.section_prompts import BUSINESS_HOUSEHOLD_IMPACT_INSIGHT, BUSINESS_INCOME_CHANGE, QUALITY_OF_LIFE_CHANGE

from ..config import MetricConfig, QualitativeConfig, SectionConfig

VERY_MUCH_ONLY = frozenset({"a. Very much improved"})
TOP_2_BOX = frozenset({"a. Very much improved", "b. Slightly improved"})

BUSINESS_HOUSEHOLD_IMPACT_CONFIG = SectionConfig(
    section_id="business_household_impact",
    schema_class=BusinessHouseholdImpactSection,
    metrics=(
        MetricConfig(
            metric_id="business_income_change",
            label="Business income improved",
            source_column="Impacts on Business, Household, and Children/IMPACT02_resp_en",
            top_box_values=TOP_2_BOX,
            benchmark_comparable_values=VERY_MUCH_ONLY,
        ),
        MetricConfig(
            metric_id="quality_of_life_change",
            label="Quality of life improved",
            source_column="Impacts on Business, Household, and Children/IMPACT03_resp_en",
            top_box_values=TOP_2_BOX,
            benchmark_comparable_values=VERY_MUCH_ONLY,
        ),
    ),
    metric_schema_fields={
        "business_income_change": "business_income_change",
        "quality_of_life_change": "quality_of_life_change",
    },
    subsection_prompts=(BUSINESS_INCOME_CHANGE, QUALITY_OF_LIFE_CHANGE),
    subsection_metric_ids={
        "3.1": ("business_income_change",),
        "3.2": ("quality_of_life_change",),
    },
    written_text_fields={
        "3.1": "business_income_analysis",
        "3.2": "quality_of_life_analysis",
    },
    insight_prompt=BUSINESS_HOUSEHOLD_IMPACT_INSIGHT,
    insight_metric_ids=("business_income_change", "quality_of_life_change"),
    insight_text_field="insight_text",
    insight_verbatims_field="insight_verbatims",
    qualitative=QualitativeConfig(
        schema_field="qol_drivers",
        section_label="quality_of_life_drivers",
        source_columns=QUALITY_OF_LIFE_DRIVER_COLS,
        task_instructions=QUALITY_OF_LIFE_DRIVERS_TASK,
    ),
    qualitative_schema_field="qol_drivers",
    validated=True,
)
