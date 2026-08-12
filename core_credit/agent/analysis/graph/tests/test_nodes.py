from langgraph.types import Send

from graph.nodes import (
    assemble_section_node,
    fan_out_metrics,
    fan_out_subsection_writes,
    route_qualitative,
    skip_qualitative_node,
    write_insight_node,
)
from schemas.common import (
    MetricResult,
    QualitativeSynthesis,
    SegmentAxis,
    SegmentedValue,
    Verbatim,
    WrittenText,
)
from section_configs.registry import SECTION_CONFIGS

FINANCIAL_ACCESS = SECTION_CONFIGS["financial_access"]  # real, validated, qualitative=None
BUSINESS_HOUSEHOLD_IMPACT = SECTION_CONFIGS["business_household_impact"]  # real, validated, qualitative set


def _metric_result(metric_id: str) -> MetricResult:
    return MetricResult(
        metric_id=metric_id,
        label=f"label for {metric_id}",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.9, n=100),
    )


def _written_text(subsection_id: str) -> WrittenText:
    return WrittenText(subsection_id=subsection_id, text="text", word_count=1, within_cap=True, ungrounded_percentages=[])


def _qualitative() -> QualitativeSynthesis:
    return QualitativeSynthesis(source_field="test", base_n=10, themes=[])


# --- fan_out_metrics ------------------------------------------------------------------


def test_fan_out_metrics_dispatches_one_send_per_configured_metric():
    state = {"section_config": FINANCIAL_ACCESS, "csv_path": "x.csv", "benchmarks_path": "b.xlsx"}
    sends = fan_out_metrics(state)
    assert len(sends) == 2
    assert all(isinstance(s, Send) for s in sends)
    assert all(s.node == "compute_metric_node" for s in sends)
    dispatched_ids = {s.arg["metric_config"].metric_id for s in sends}
    assert dispatched_ids == {"first_time_access", "alternative_lender_hard_to_find"}


def test_fan_out_metrics_passes_csv_and_benchmarks_path_through():
    state = {"section_config": FINANCIAL_ACCESS, "csv_path": "x.csv", "benchmarks_path": "b.xlsx"}
    sends = fan_out_metrics(state)
    assert all(s.arg["csv_path"] == "x.csv" and s.arg["benchmarks_path"] == "b.xlsx" for s in sends)


# --- route_qualitative -----------------------------------------------------------------


def test_route_qualitative_skips_when_section_has_no_qualitative_config():
    state = {"section_config": FINANCIAL_ACCESS}
    assert route_qualitative(state) == "skip_qualitative_node"


def test_route_qualitative_fans_out_when_section_has_qualitative_config():
    state = {
        "section_config": BUSINESS_HOUSEHOLD_IMPACT,
        "qualitative_responses": list(range(25)),
        "batch_size": 10,
    }
    sends = route_qualitative(state)
    assert isinstance(sends, list)
    assert len(sends) == 3  # 10, 10, 5
    assert all(s.node == "theme_tag_batch_node" for s in sends)


def test_skip_qualitative_node_produces_empty_synthesis_with_section_id_label():
    state = {"section_config": FINANCIAL_ACCESS}
    result = skip_qualitative_node(state)
    qual = result["qualitative"]
    assert qual.base_n == 0
    assert qual.themes == []
    assert qual.source_field == "financial_access"


# --- fan_out_subsection_writes -----------------------------------------------------------


def test_fan_out_subsection_writes_one_send_per_subsection_prompt():
    metric_results = {
        "first_time_access": _metric_result("first_time_access"),
        "alternative_lender_hard_to_find": _metric_result("alternative_lender_hard_to_find"),
    }
    state = {"section_config": FINANCIAL_ACCESS, "metric_results": metric_results}
    sends = fan_out_subsection_writes(state)
    assert len(sends) == 2
    assert all(s.node == "write_subsection_node" for s in sends)
    ids = {s.arg["prompt_config"].subsection_id for s in sends}
    assert ids == {"1.1", "1.2"}


def test_fan_out_subsection_writes_data_summary_only_includes_that_subsections_metrics():
    metric_results = {
        "first_time_access": _metric_result("first_time_access"),
        "alternative_lender_hard_to_find": _metric_result("alternative_lender_hard_to_find"),
    }
    state = {"section_config": FINANCIAL_ACCESS, "metric_results": metric_results}
    sends = fan_out_subsection_writes(state)
    by_id = {s.arg["prompt_config"].subsection_id: s.arg["data_summary"] for s in sends}
    # 1.1's summary should mention first_time_access's label, not the other metric's
    assert "label for first_time_access" in by_id["1.1"]
    assert "label for alternative_lender_hard_to_find" not in by_id["1.1"]
    assert by_id["1.1"] != by_id["1.2"]


# --- write_insight_node (defensive no-op path only -- the "ready" path calls a real LLM) ------


def test_write_insight_node_no_op_when_metrics_incomplete():
    state = {
        "section_config": FINANCIAL_ACCESS,
        "metric_results": {"first_time_access": _metric_result("first_time_access")},  # missing the 2nd metric
        "qualitative": _qualitative(),
    }
    assert write_insight_node(state) == {}


def test_write_insight_node_no_op_when_qualitative_missing():
    state = {
        "section_config": FINANCIAL_ACCESS,
        "metric_results": {
            "first_time_access": _metric_result("first_time_access"),
            "alternative_lender_hard_to_find": _metric_result("alternative_lender_hard_to_find"),
        },
        # qualitative missing entirely
    }
    assert write_insight_node(state) == {}


# --- assemble_section_node (generic, config-driven) ----------------------------------------


def _complete_financial_access_state() -> dict:
    return {
        "section_config": FINANCIAL_ACCESS,
        "metric_results": {
            "first_time_access": _metric_result("first_time_access"),
            "alternative_lender_hard_to_find": _metric_result("alternative_lender_hard_to_find"),
        },
        "written_texts": {
            "1.1": _written_text("1.1"),
            "1.2": _written_text("1.2"),
        },
        "insight_text": _written_text("1-insight"),
        "insight_verbatims": [],
    }


def test_assemble_section_node_no_op_when_a_subsection_write_is_missing():
    state = _complete_financial_access_state()
    del state["written_texts"]["1.2"]
    assert assemble_section_node(state) == {}


def test_assemble_section_node_no_op_when_insight_missing():
    state = _complete_financial_access_state()
    state["insight_text"] = None
    assert assemble_section_node(state) == {}


def test_assemble_section_node_produces_section_once_complete():
    state = _complete_financial_access_state()
    result = assemble_section_node(state)
    assert "section" in result
    section = result["section"]
    assert section.first_time_access_analysis.subsection_id == "1.1"
    assert section.alternative_lender_hard_to_find_analysis.subsection_id == "1.2"
    assert section.insight_text.subsection_id == "1-insight"
    assert section.insight_verbatims == []


def test_assemble_section_node_accepts_empty_verbatims_list_as_present():
    # An empty list is a valid, present value (no verbatims were used) -- must not be
    # mistaken for "missing" the way None is.
    state = _complete_financial_access_state()
    assert state["insight_verbatims"] == []
    result = assemble_section_node(state)
    assert "section" in result


def test_assemble_section_node_with_qualitative_field_set():
    state = {
        "section_config": BUSINESS_HOUSEHOLD_IMPACT,
        "metric_results": {
            "business_income_change": _metric_result("business_income_change"),
            "quality_of_life_change": _metric_result("quality_of_life_change"),
        },
        "written_texts": {"3.1": _written_text("3.1"), "3.2": _written_text("3.2")},
        "qualitative": _qualitative(),
        "insight_text": _written_text("3-insight"),
        "insight_verbatims": [Verbatim(quote="q", source_field="f")],
    }
    result = assemble_section_node(state)
    assert "section" in result
    assert result["section"].qol_drivers.base_n == 10
