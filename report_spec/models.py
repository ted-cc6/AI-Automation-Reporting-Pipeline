from __future__ import annotations

from enum import Enum
from typing import Annotated

from pydantic import BaseModel, Field


class Segment(str, Enum):
    caregivers = "caregivers"
    first_time_access = "first_time_access"
    female = "female"
    male = "male"
    female_hh_heads = "female_hh_heads"
    pwd_households = "pwd_households"
    climate_shock = "climate_shock"
    claimant = "claimant"
    non_claimant = "non_claimant"
    bundled_service = "bundled_service"


class MetricMethod(str, Enum):
    top_two_box = "top_two_box"
    bottom_two_box = "bottom_two_box"
    share = "share"
    frequency_rank = "frequency_rank"
    claims_funnel = "claims_funnel"
    nps_score = "nps_score"
    nps_split = "nps_split"
    correlation = "correlation"
    significance_test = "significance_test"
    gap_analysis = "gap_analysis"
    benchmark_comparison = "benchmark_comparison"
    confidence_interval = "confidence_interval"
    regression = "regression"


class FillMode(str, Enum):
    auto = "auto"
    bespoke = "bespoke"
    hybrid = "hybrid"


class OutputType(str, Enum):
    analysis_prose = "analysis_prose"
    ranked_list = "ranked_list"
    table = "table"
    scorecard_table = "scorecard_table"
    correlation_table = "correlation_table"
    insight_prose = "insight_prose"
    verbatim_block = "verbatim_block"
    subtheme_summary = "subtheme_summary"


class SurveySection(str, Enum):
    product_understanding = "product_understanding"
    claims_experience = "claims_experience"
    focus_other_services = "focus_other_services"
    child_financial_wellbeing = "child_financial_wellbeing"
    client_satisfaction = "client_satisfaction"
    access = "access"
    health_insurance = "health_insurance"
    crop_insurance = "crop_insurance"
    enhanced_credit_life = "enhanced_credit_life"
    client_profile = "client_profile"


class ResponseType(str, Enum):
    likert_4 = "likert_4"
    likert_5 = "likert_5"
    binary = "binary"
    multi_select_2 = "multi_select_2"
    multi_select_n = "multi_select_n"
    single_select = "single_select"
    numeric_open = "numeric_open"
    open_text = "open_text"


class Priority(str, Enum):
    required = "required"
    nice_to_have = "nice_to_have"


class VisualSource(str, Enum):
    powerbi_screenshot = "powerbi_screenshot"
    auto_generated = "auto_generated"


class ThemeMethod(str, Enum):
    genai_assisted = "genai_assisted"
    manual = "manual"
    genai_then_manual = "genai_then_manual"


class SubthemeFrequencyUnit(str, Enum):
    count = "count"
    percent = "percent"
    both = "both"


class ReportMetadata(BaseModel):
    model_config = {"extra": "forbid"}

    name: str
    template_version: Annotated[str, Field(pattern=r"^\d+\.\d+$")]
    reporting_period: str | None = None
    regions: list[str] | None = None
    priority_segments: Annotated[list[Segment], Field(min_length=1)]
    benchmark_dataset_id: str | None = None
    notes: str | None = None


class SourceQuestion(BaseModel):
    model_config = {"extra": "forbid"}

    question_ref: Annotated[str, Field(pattern=r"^q_[a-z0-9_]+$")]
    question_text: str | None = None
    survey_section: SurveySection | None = None
    response_type: ResponseType | None = None
    conditional_on: Annotated[str, Field(pattern=r"^q_[a-z0-9_]+")] | None = None


class Metric(BaseModel):
    model_config = {"extra": "forbid"}

    method: MetricMethod
    variables: Annotated[list[Annotated[str, Field(pattern=r"^q_[a-z0-9_]+$")]], Field(min_length=1)]
    against: Annotated[str, Field(pattern=r"^q_[a-z0-9_]+")] | None = None
    top_n: Annotated[int, Field(ge=1, le=10)] | None = None
    label: str | None = None
    benchmark_source: str | None = None


class DisaggregationItem(BaseModel):
    model_config = {"extra": "forbid"}

    segment: Segment
    priority: Priority


class VisualConfig(BaseModel):
    model_config = {"extra": "forbid"}

    powerbi_name: str
    source: VisualSource
    visual_type: str | None = None
    description: str | None = None


class QualitativeConfig(BaseModel):
    model_config = {"extra": "forbid"}

    questions: Annotated[list[Annotated[str, Field(pattern=r"^q_[a-z0-9_]+$")]], Field(min_length=1)]
    verbatims_required: bool
    verbatim_count: Annotated[int, Field(ge=1, le=5)] | None = None
    verbatim_profile_fields: list[str] | None = None
    theme_method: ThemeMethod
    client_protection_flag: bool | None = None
    subtheme_frequency_unit: SubthemeFrequencyUnit | None = None
    separate_concern_categories: list[str] | None = None


class Subsection(BaseModel):
    model_config = {"extra": "forbid"}

    subsection_id: Annotated[str, Field(pattern=r"^[1-7]\.([1-9][0-9]*|insight)$")]
    title: str
    fill_mode: FillMode
    word_cap: int | None = None
    source_questions: list[SourceQuestion] = Field(default_factory=list)
    metrics: list[Metric] | None = None
    disaggregation: list[DisaggregationItem] | None = None
    visual: VisualConfig | None = None
    qualitative: QualitativeConfig | None = None
    benchmark_overlay: bool = False
    outputs: Annotated[list[OutputType], Field(min_length=1)]
    notes: str | None = None

    @property
    def is_insight(self) -> bool:
        return self.subsection_id.endswith(".insight")

    def source_question_refs(self) -> set[str]:
        return {sq.question_ref for sq in self.source_questions}


class Part(BaseModel):
    model_config = {"extra": "forbid"}

    part_id: Annotated[int, Field(ge=1, le=7)]
    title: str
    subsections: Annotated[list[Subsection], Field(min_length=1)]

    def insight_subsection(self) -> Subsection | None:
        for s in self.subsections:
            if s.is_insight:
                return s
        return None


class ReportSpec(BaseModel):
    model_config = {"extra": "forbid"}

    report_metadata: ReportMetadata
    parts: Annotated[list[Part], Field(min_length=7, max_length=7)]

    # --- Convenience API ---

    def subsections(self) -> list[tuple[Part, Subsection]]:
        """Flat list of (part, subsection) pairs in document order."""
        return [(part, sub) for part in self.parts for sub in part.subsections]

    def auto_subsections(self) -> list[tuple[Part, Subsection]]:
        return [(p, s) for p, s in self.subsections() if s.fill_mode == FillMode.auto]

    def hybrid_subsections(self) -> list[tuple[Part, Subsection]]:
        return [(p, s) for p, s in self.subsections() if s.fill_mode == FillMode.hybrid]

    def bespoke_subsections(self) -> list[tuple[Part, Subsection]]:
        return [(p, s) for p, s in self.subsections() if s.fill_mode == FillMode.bespoke]

    def all_source_questions(self) -> list[SourceQuestion]:
        seen: set[str] = set()
        result: list[SourceQuestion] = []
        for _, sub in self.subsections():
            for sq in sub.source_questions:
                if sq.question_ref not in seen:
                    seen.add(sq.question_ref)
                    result.append(sq)
        return result

    def referenced_variables(self) -> set[str]:
        """All question_refs referenced in any metric's variables or against."""
        refs: set[str] = set()
        for _, sub in self.subsections():
            if sub.metrics:
                for m in sub.metrics:
                    refs.update(m.variables)
                    if m.against:
                        refs.add(m.against)
        return refs

    def derived_variables(self) -> set[str]:
        """
        Variables referenced in metrics but not declared in source_questions
        of their subsection. These are KNOWN_GAP candidates — intentionally
        derived from raw columns (e.g. composite flags, NPS promoter flag).
        """
        derived: set[str] = set()
        for _, sub in self.subsections():
            if not sub.metrics:
                continue
            declared = sub.source_question_refs()
            for m in sub.metrics:
                for v in m.variables:
                    if v not in declared:
                        derived.add(v)
                if m.against and m.against not in declared:
                    derived.add(m.against)
        return derived
