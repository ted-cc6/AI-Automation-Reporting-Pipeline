"""Part 5 -- Client Protection.

Run for real end to end via graph/run_graph.py (thread_id "protection-signals-v2", output at
graph/output/client_protection_protection-signals-v2.json): clean grounding on every
subsection, sensible box-type benchmarks, and protection_signals genuinely working -- 9 real
themes out of 423 mined responses (base_n = 53 IMPACT03c + 370 CLIENTSAT01b), correctly
excluding the ordinary rate/terms/speed complaints that dominate both source questions'
volume, with severity set on every theme (2 high: aggressive debt collection, unhonoured
sale promises; 4 medium; 3 low). The Insight step's verbatim pool -- previously always empty
since qualitative was None -- now cites real protection-relevant quotes too.

qualitative is wired up as follows: CP05/CP05a (the unfair-treatment questions) are coded, not
free text, so there's still no dedicated "describe what happened" field under Client Protection
itself -- IMPACT03c ("how has your quality of life become worse?") and CLIENTSAT01b (the NPS
detractor follow-up) are mined instead, with a protection-specific task prompt
(qualitative_agent.agent.PROTECTION_SIGNALS_TASK) that only tags genuine conduct/harassment/
misselling signals. Both sources are ALSO theme-tagged elsewhere (qol_drivers,
client_satisfaction.nps_followup_themes) for different purposes; tagging the same text twice
under a different lens was a deliberate choice over reusing those incidental severity flags,
since this is the one place low-volume, high-severity signals are explicitly asked for
("flag any issue... however low the volume").
"""

from __future__ import annotations

from qualitative_agent.agent import PROTECTION_SIGNALS_TASK
from schemas.client_protection import ClientProtectionSection
from writer.section_prompts import (
    CLIENT_PROTECTION_INSIGHT,
    COMPLAINTS_MECHANISM_TRUSTED,
    FAIR_TREATMENT_AND_REPORTING,
    FINANCIAL_WORRY_DECREASED,
    LOAN_TERMS_CLEAR,
    REDUCED_FOOD_INTAKE,
)

from ..config import MetricConfig, QualitativeConfig, SectionConfig

PROTECTION_SIGNAL_SOURCE_COLS = (
    "Impacts on Business, Household, and Children/IMPACT03c_resp_en",
    "Client Satisfaction/CLIENTSAT01b_resp_en",
)

CLIENT_PROTECTION_CONFIG = SectionConfig(
    section_id="client_protection",
    schema_class=ClientProtectionSection,
    metrics=(
        MetricConfig(
            metric_id="financial_worry_decreased",
            label="Financial worry decreased",
            source_column="Client Protection/CP02_resp_en",
            top_box_values=frozenset({"d. Slightly decreased", "e. Very much decreased"}),
            # MFI Index scores this on "very much decreased" alone.
            benchmark_comparable_values=frozenset({"e. Very much decreased"}),
        ),
        MetricConfig(
            metric_id="loan_terms_clear",
            label="Loan terms easy to understand",
            source_column="Client Protection/CP03_resp_en",
            top_box_values=frozenset({"a. Strongly agree", "b. Somewhat agree"}),
            # Provisional per benchmark_module's PROVISIONAL_CAVEATS: MFI Index is scored on
            # "strongly agree" alone, box-type binding unconfirmed with the source.
            benchmark_comparable_values=frozenset({"a. Strongly agree"}),
        ),
        MetricConfig(
            metric_id="complaints_mechanism_trusted",
            label="Trusts the complaints mechanism",
            source_column="Client Protection/CP04_resp_en",
            top_box_values=frozenset({"a. Strongly agree", "b. Somewhat agree"}),
            # No 60 Decibels value exists for this indicator at all (confirmed blank in the
            # source sheet) -- has_benchmark stays True since the lookup already reports that
            # gracefully via not_available_reason.
        ),
        MetricConfig(
            metric_id="no_unfair_treatment",
            label="Experienced no unfair treatment",
            source_column="Client Protection/CP05_resp_en",
            top_box_values=frozenset({"d. Never"}),
        ),
        MetricConfig(
            metric_id="reported_when_unfair",
            label="Reported the unfair treatment they experienced",
            source_column="Client Protection/CP05a_resp_en",
            base_column="Client Protection/CP05_resp_en",
            base_values=frozenset({"a. Regularly", "b. Sometimes", "c. Rarely (1 or 2 times)"}),
            top_box_values=frozenset(
                {"a. Yes, and received a satisfactory follow-up", "b. Yes, and received an unsatisfactory follow-up"}
            ),
            has_benchmark=False,  # in benchmark_module.DELIBERATELY_EXCLUDED_METRICS -- no 2025 benchmark exists
        ),
        MetricConfig(
            metric_id="did_not_reduce_food",
            label="Did not reduce household food to make repayments",
            source_column="Client Protection/CP06_resp_en",
            top_box_values=frozenset({"a. No change to food consumption"}),
        ),
    ),
    metric_schema_fields={
        "financial_worry_decreased": "financial_worry_decreased",
        "loan_terms_clear": "loan_terms_clear",
        "complaints_mechanism_trusted": "complaints_mechanism_trusted",
        "no_unfair_treatment": "no_unfair_treatment",
        "reported_when_unfair": "reported_when_unfair",
        "did_not_reduce_food": "did_not_reduce_food",
    },
    subsection_prompts=(
        FINANCIAL_WORRY_DECREASED,
        LOAN_TERMS_CLEAR,
        COMPLAINTS_MECHANISM_TRUSTED,
        FAIR_TREATMENT_AND_REPORTING,
        REDUCED_FOOD_INTAKE,
    ),
    subsection_metric_ids={
        "5.1": ("financial_worry_decreased",),
        "5.2": ("loan_terms_clear",),
        "5.3": ("complaints_mechanism_trusted",),
        "5.4": ("no_unfair_treatment", "reported_when_unfair"),
        "5.5": ("did_not_reduce_food",),
    },
    written_text_fields={
        "5.1": "financial_worry_decreased_analysis",
        "5.2": "loan_terms_clear_analysis",
        "5.3": "complaints_mechanism_trusted_analysis",
        "5.4": "no_unfair_treatment_analysis",
        "5.5": "did_not_reduce_food_analysis",
    },
    insight_prompt=CLIENT_PROTECTION_INSIGHT,
    insight_metric_ids=(
        "financial_worry_decreased",
        "loan_terms_clear",
        "complaints_mechanism_trusted",
        "no_unfair_treatment",
        "reported_when_unfair",
        "did_not_reduce_food",
    ),
    insight_text_field="insight_text",
    insight_verbatims_field="insight_verbatims",
    qualitative=QualitativeConfig(
        schema_field="protection_signals",
        section_label="protection_signals",
        source_columns=PROTECTION_SIGNAL_SOURCE_COLS,
        task_instructions=PROTECTION_SIGNALS_TASK,
    ),
    qualitative_schema_field="protection_signals",
    validated=True,
)
