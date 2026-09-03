"""The config dataclasses a section needs to be buildable by the generic graph.

Deliberately narrow in scope: this covers the pattern most subsections actually follow (a
top-box share, optionally benchmarked, optionally cut against a differently-boxed benchmark
figure) plus one optional qualitative free-text pass and the writer prompts that consume both.
It does NOT cover every shape the template uses -- ranked multi-select lists (e.g. Child
Wellbeing's "what improved"), NPS (Client Satisfaction), Client Profile's means/categoricals,
or Poverty Likelihood's PPI-based computation. Sections needing those still get a config here
for whichever of their subsections *do* fit the top-box pattern; the rest is a known,
explicitly flagged gap (see registry.py), not something silently forced into this shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from writer.section_prompts import SubsectionPrompt


@dataclass(frozen=True)
class MetricConfig:
    """One top-box metric this section needs computed."""

    metric_id: str
    label: str
    source_column: str
    top_box_values: frozenset
    base_column: Optional[str] = None
    base_values: Optional[frozenset] = None
    """Restricts the metric's base to rows where base_column's value is in base_values --
    e.g. Child Wellbeing's 4.1 is only asked of caregivers, and Client Protection's "reported
    when unfair" is only asked of clients who experienced unfair treatment at all. None means
    the whole survey population is the base, which is true for most metrics."""
    benchmark_comparable_values: Optional[frozenset] = None
    """Set when the MFI Index benchmark is scored on a different (usually narrower) box than
    top_box_values -- e.g. our own headline is "very much + slightly improved" but the
    benchmark is "very much" alone. None means top_box_values IS the comparable basis already
    (true for simple yes/no or single-category metrics like first-time access)."""
    has_benchmark: bool = True
    """False for metrics with no MFI Index indicator at all (per benchmark_module's
    DELIBERATELY_EXCLUDED_METRICS or a blank cell in the source sheet) -- the lookup already
    returns not_available_reason gracefully either way, so this mainly documents intent."""


@dataclass(frozen=True)
class RankedMetricConfig:
    """A "select all that apply" multi-select question this section needs computed as a ranked
    distribution (metrics_engine.multiselect_distribution -> RankedOptions).

    This is the config-driven path's equivalent of what the bespoke drivers already do for
    child-wellbeing "what improved", resilience coping mechanisms, and NPS promoter reasons --
    the MetricConfig/top-box machinery cannot express it (CC-024). The output is a RankedOptions;
    the section schema needs a field of that type, wired via
    SectionConfig.ranked_metric_schema_fields.
    """

    metric_id: str
    label: str  # heads the block in the writer's data_summary
    slot_columns: tuple  # the K variable-slot columns, e.g. AGENCY04a_resp_{1,2,3}_en
    base_column: Optional[str] = None  # restrict the base to rows whose base_column value is in base_values
    base_values: Optional[frozenset] = None
    exclude_labels: frozenset = frozenset()  # sentinel "none of these" / "n/a" options to drop from the ranking


@dataclass(frozen=True)
class QualitativeConfig:
    """The free-text pass this section needs, if it has one at all.

    SectionConfig.qualitative being None is a legitimate, common state (e.g. Financial Access
    has no dedicated follow-up text field in the survey) -- not a placeholder for "not built
    yet". Sections with qualitative=None simply never get verbatims in their Insight.
    """

    schema_field: str  # e.g. "qol_drivers" -- the QualitativeSynthesis field on the section schema
    section_label: str  # QualitativeSynthesis.source_field
    source_columns: tuple
    task_instructions: str


@dataclass(frozen=True)
class SectionConfig:
    section_id: str  # e.g. "business_household_impact" -- matches the schemas/ module name
    schema_class: type  # the Pydantic section class to assemble, e.g. BusinessHouseholdImpactSection

    metrics: tuple  # tuple[MetricConfig, ...]
    metric_schema_fields: dict  # metric_id -> schema field name holding that MetricResult

    subsection_prompts: tuple  # tuple[SubsectionPrompt, ...] -- the "plain" write_subsection calls
    subsection_metric_ids: dict  # subsection_id -> tuple[metric_id, ...] it summarizes in its data_summary
    #                              (a metric_id here may be a plain MetricConfig OR a RankedMetricConfig)
    written_text_fields: dict  # subsection_id -> schema field name holding that WrittenText

    insight_prompt: SubsectionPrompt  # every Part has exactly one Insight
    insight_metric_ids: tuple  # tuple[metric_id, ...] -- usually every metric in the section
    insight_text_field: str
    insight_verbatims_field: str

    ranked_metrics: tuple = ()  # tuple[RankedMetricConfig, ...] -- multi-select distributions (CC-024)
    ranked_metric_schema_fields: dict = field(default_factory=dict)  # ranked metric_id -> schema field (RankedOptions)

    qualitative: Optional[QualitativeConfig] = None
    qualitative_schema_field: Optional[str] = None  # schema field holding the QualitativeSynthesis itself

    validated: bool = False
    """True once this config has actually been run against real data and its output manually
    reviewed (the same bar Business & Household Impact and Financial Access were held to) --
    False means the config was drafted from the template and verified column values, but has
    not yet been proven the way every other real-data-touching piece of this project was
    before being trusted. Check this before treating a section's output as final."""


def validate_section_config(config: SectionConfig) -> list:
    """Structural, no-LLM, no-data consistency check: every dict key this config wires up
    actually points at something real. Catches typos in the hand-written config files (a
    subsection_id that doesn't match its SubsectionPrompt, a metric_id referenced in
    subsection_metric_ids that was never defined in metrics, a schema field that doesn't
    exist on schema_class) before they'd otherwise only surface as a confusing runtime error
    partway through an expensive real run.
    """
    errors: list = []
    metric_ids = {m.metric_id for m in config.metrics}
    ranked_ids = {rm.metric_id for rm in config.ranked_metrics}
    all_metric_ids = metric_ids | ranked_ids
    schema_fields = set(config.schema_class.model_fields.keys())
    subsection_ids = {p.subsection_id for p in config.subsection_prompts}

    if metric_ids & ranked_ids:
        errors.append(f"metric_id(s) claimed by both a MetricConfig and a RankedMetricConfig: {sorted(metric_ids & ranked_ids)}")

    for metric_id, field_name in config.metric_schema_fields.items():
        if metric_id not in metric_ids:
            errors.append(f"metric_schema_fields references unknown metric_id {metric_id!r}")
        if field_name not in schema_fields:
            errors.append(f"metric_schema_fields[{metric_id!r}] targets unknown schema field {field_name!r}")

    for metric_id in metric_ids:
        if metric_id not in config.metric_schema_fields:
            errors.append(f"metric {metric_id!r} has no entry in metric_schema_fields")

    for metric_id, field_name in config.ranked_metric_schema_fields.items():
        if metric_id not in ranked_ids:
            errors.append(f"ranked_metric_schema_fields references unknown ranked metric_id {metric_id!r}")
        if field_name not in schema_fields:
            errors.append(f"ranked_metric_schema_fields[{metric_id!r}] targets unknown schema field {field_name!r}")

    for metric_id in ranked_ids:
        if metric_id not in config.ranked_metric_schema_fields:
            errors.append(f"ranked metric {metric_id!r} has no entry in ranked_metric_schema_fields")

    for subsection_id, ids in config.subsection_metric_ids.items():
        if subsection_id not in subsection_ids:
            errors.append(f"subsection_metric_ids references unknown subsection_id {subsection_id!r}")
        for metric_id in ids:
            if metric_id not in all_metric_ids:
                errors.append(f"subsection_metric_ids[{subsection_id!r}] references unknown metric_id {metric_id!r}")

    for subsection_id in subsection_ids:
        if subsection_id not in config.subsection_metric_ids:
            errors.append(f"subsection {subsection_id!r} has no entry in subsection_metric_ids")
        if subsection_id not in config.written_text_fields:
            errors.append(f"subsection {subsection_id!r} has no entry in written_text_fields")

    for subsection_id, field_name in config.written_text_fields.items():
        if field_name not in schema_fields:
            errors.append(f"written_text_fields[{subsection_id!r}] targets unknown schema field {field_name!r}")

    for metric_id in config.insight_metric_ids:
        if metric_id not in metric_ids:
            errors.append(f"insight_metric_ids references unknown metric_id {metric_id!r}")

    if config.insight_text_field not in schema_fields:
        errors.append(f"insight_text_field {config.insight_text_field!r} is not a schema field")
    if config.insight_verbatims_field not in schema_fields:
        errors.append(f"insight_verbatims_field {config.insight_verbatims_field!r} is not a schema field")

    if config.qualitative is not None:
        if config.qualitative_schema_field is None:
            errors.append("qualitative is set but qualitative_schema_field is None -- its output would be discarded")
        elif config.qualitative_schema_field not in schema_fields:
            errors.append(f"qualitative_schema_field {config.qualitative_schema_field!r} is not a schema field")

    return errors
