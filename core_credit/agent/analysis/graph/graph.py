"""Wires the generic, config-driven section graph. Works for any SectionConfig -- which
metrics, whether there's a qualitative pass, and how many subsections all come from the
config passed in as graph state, not from anything hardcoded here.

See nodes.py's module docstring for the full topology diagram and why write_insight_node and
assemble_section_node are both written defensively (multi-branch joins of different lengths).
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .nodes import (
    assemble_section_node,
    compute_metric_node,
    fan_out_metrics,
    fan_out_subsection_writes,
    load_data_node,
    merge_qualitative_node,
    metrics_ready_node,
    route_qualitative,
    skip_qualitative_node,
    theme_tag_batch_node,
    write_insight_node,
    write_subsection_node,
)
from .state import GraphState


def build_graph() -> StateGraph:
    builder = StateGraph(GraphState)

    builder.add_node("load_data_node", load_data_node)
    builder.add_node("compute_metric_node", compute_metric_node)
    builder.add_node("metrics_ready_node", metrics_ready_node)
    builder.add_node("theme_tag_batch_node", theme_tag_batch_node)
    builder.add_node("merge_qualitative_node", merge_qualitative_node)
    builder.add_node("skip_qualitative_node", skip_qualitative_node)
    builder.add_node("write_subsection_node", write_subsection_node)
    builder.add_node("write_insight_node", write_insight_node)
    builder.add_node("assemble_section_node", assemble_section_node)

    builder.add_edge(START, "load_data_node")

    # Metrics: dynamic parallel fan-out, one Send per MetricConfig in the section.
    builder.add_conditional_edges("load_data_node", fan_out_metrics, ["compute_metric_node"])
    builder.add_edge("compute_metric_node", "metrics_ready_node")

    # Qualitative: either a real batch fan-out + merge, or an immediate empty result --
    # never both, so write_insight_node always has exactly one path to `qualitative`.
    builder.add_conditional_edges(
        "load_data_node", route_qualitative, ["theme_tag_batch_node", "skip_qualitative_node"]
    )
    builder.add_edge("theme_tag_batch_node", "merge_qualitative_node")

    # Plain subsection writes: dynamic parallel fan-out, attached to metrics_ready_node
    # specifically so it only fires once (compute_metric_node itself fires N times).
    builder.add_conditional_edges("metrics_ready_node", fan_out_subsection_writes, ["write_subsection_node"])

    # write_insight_node has two predecessors of different lengths -- both routed in, and the
    # node itself is the defensive no-op-until-ready join (see its docstring).
    builder.add_edge("metrics_ready_node", "write_insight_node")
    builder.add_edge("merge_qualitative_node", "write_insight_node")
    builder.add_edge("skip_qualitative_node", "write_insight_node")

    # assemble_section_node is the same defensive-join pattern, joining the subsection
    # writes and the insight write.
    builder.add_edge("write_subsection_node", "assemble_section_node")
    builder.add_edge("write_insight_node", "assemble_section_node")
    builder.add_edge("assemble_section_node", END)

    return builder


def compile_graph(checkpointer: Optional[object] = None) -> CompiledStateGraph:
    return build_graph().compile(checkpointer=checkpointer)
