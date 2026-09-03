import pytest

from schemas.common import MetricResult, SegmentAxis, SegmentedValue, Verbatim, WrittenText
from section_configs.config import (
    MetricConfig,
    QualitativeConfig,
    RankedMetricConfig,
    SectionConfig,
    validate_section_config,
)
from section_configs.registry import SECTION_CONFIGS


class _FakeModel:
    """Stands in for a Pydantic schema class -- just needs .model_fields for the validator."""

    model_fields = {
        "metric_a": None, "metric_a_analysis": None, "insight_text": None,
        "insight_verbatims": None, "qual": None, "ranked_a": None,
    }


def _ranked() -> RankedMetricConfig:
    return RankedMetricConfig(metric_id="ranked_a", label="Ranked A", slot_columns=("c1", "c2"))


def _minimal_config(**overrides) -> SectionConfig:
    from writer.section_prompts import SubsectionPrompt

    prompt = SubsectionPrompt(subsection_id="x.1", title="X", word_cap=80, instructions="do it")
    insight = SubsectionPrompt(subsection_id="x-insight", title="Insight", word_cap=120, instructions="wrap up")
    defaults = dict(
        section_id="fake_section",
        schema_class=_FakeModel,
        metrics=(MetricConfig(metric_id="metric_a", label="A", source_column="col_a", top_box_values=frozenset({"Yes"})),),
        metric_schema_fields={"metric_a": "metric_a"},
        subsection_prompts=(prompt,),
        subsection_metric_ids={"x.1": ("metric_a",)},
        written_text_fields={"x.1": "metric_a_analysis"},
        insight_prompt=insight,
        insight_metric_ids=("metric_a",),
        insight_text_field="insight_text",
        insight_verbatims_field="insight_verbatims",
    )
    defaults.update(overrides)
    return SectionConfig(**defaults)


def test_valid_config_has_no_errors():
    assert validate_section_config(_minimal_config()) == []


def test_catches_metric_schema_field_referencing_unknown_metric():
    config = _minimal_config(metric_schema_fields={"metric_a": "metric_a", "ghost_metric": "metric_a_analysis"})
    errors = validate_section_config(config)
    assert any("ghost_metric" in e for e in errors)


def test_catches_metric_missing_from_metric_schema_fields():
    config = _minimal_config(metric_schema_fields={})
    errors = validate_section_config(config)
    assert any("metric_a" in e and "metric_schema_fields" in e for e in errors)


def test_catches_subsection_metric_ids_referencing_unknown_subsection():
    config = _minimal_config(subsection_metric_ids={"x.1": ("metric_a",), "y.99": ("metric_a",)})
    errors = validate_section_config(config)
    assert any("y.99" in e for e in errors)


def test_catches_subsection_metric_ids_referencing_unknown_metric():
    config = _minimal_config(subsection_metric_ids={"x.1": ("ghost_metric",)})
    errors = validate_section_config(config)
    assert any("ghost_metric" in e for e in errors)


def test_catches_subsection_missing_written_text_field():
    config = _minimal_config(written_text_fields={})
    errors = validate_section_config(config)
    assert any("x.1" in e and "written_text_fields" in e for e in errors)


def test_catches_written_text_field_not_on_schema():
    config = _minimal_config(written_text_fields={"x.1": "not_a_real_field"})
    errors = validate_section_config(config)
    assert any("not_a_real_field" in e for e in errors)


def test_catches_insight_metric_ids_referencing_unknown_metric():
    config = _minimal_config(insight_metric_ids=("ghost_metric",))
    errors = validate_section_config(config)
    assert any("ghost_metric" in e for e in errors)


def test_catches_qualitative_set_without_schema_field():
    config = _minimal_config(
        qualitative=QualitativeConfig(
            schema_field="qual", section_label="test", source_columns=("col",), task_instructions="tag it"
        ),
        qualitative_schema_field=None,
    )
    errors = validate_section_config(config)
    assert any("discarded" in e for e in errors)


def test_qualitative_with_schema_field_is_fine():
    config = _minimal_config(
        qualitative=QualitativeConfig(
            schema_field="qual", section_label="test", source_columns=("col",), task_instructions="tag it"
        ),
        qualitative_schema_field="qual",
    )
    assert validate_section_config(config) == []


def test_ranked_metric_wired_to_a_subsection_and_schema_field_is_valid():
    config = _minimal_config(
        ranked_metrics=(_ranked(),),
        ranked_metric_schema_fields={"ranked_a": "ranked_a"},
        subsection_metric_ids={"x.1": ("metric_a", "ranked_a")},
    )
    assert validate_section_config(config) == []


def test_ranked_metric_without_schema_field_entry_errors():
    config = _minimal_config(ranked_metrics=(_ranked(),))
    errors = validate_section_config(config)
    assert any("ranked_a" in e and "ranked_metric_schema_fields" in e for e in errors)


def test_ranked_metric_schema_field_not_on_schema_errors():
    config = _minimal_config(
        ranked_metrics=(_ranked(),),
        ranked_metric_schema_fields={"ranked_a": "not_a_field"},
    )
    errors = validate_section_config(config)
    assert any("not_a_field" in e for e in errors)


def test_metric_id_claimed_by_both_a_plain_and_a_ranked_config_errors():
    config = _minimal_config(
        ranked_metrics=(RankedMetricConfig(metric_id="metric_a", label="dup", slot_columns=("c",)),),
        ranked_metric_schema_fields={"metric_a": "ranked_a"},
    )
    errors = validate_section_config(config)
    assert any("both" in e for e in errors)


@pytest.mark.parametrize("section_id", list(SECTION_CONFIGS.keys()))
def test_every_registered_config_is_structurally_valid(section_id):
    """The real payoff: every config actually in the registry, including the drafted ones,
    passes the same structural check -- catches a wiring typo without needing real data or
    an LLM call.
    """
    errors = validate_section_config(SECTION_CONFIGS[section_id])
    assert errors == [], f"{section_id}: {errors}"


def test_registry_has_no_duplicate_metric_ids_within_a_section():
    for section_id, config in SECTION_CONFIGS.items():
        ids = [m.metric_id for m in config.metrics]
        assert len(ids) == len(set(ids)), f"{section_id} has duplicate metric_ids: {ids}"
