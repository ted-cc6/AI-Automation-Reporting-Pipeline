"""Wires every node into the one top-level graph -- see the four-tier diagram this was built
from: Prepare and validate data -> Build component metrics -> Build derived outputs -> Render
and review.
"""

from __future__ import annotations

from typing import Optional

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .assembly_node import assemble_report_node
from .dashboard_node import resolve_dashboard_visuals_node
from .data_prep_nodes import check_rows_node, clean_columns_node, fail_node, route_after_data_prep
from .done_node import done_node
from .render_nodes import qa_review_node, render_docx_node
from .section_nodes import (
    build_agency_node,
    build_business_household_impact_node,
    build_child_wellbeing_node,
    build_client_profile_node,
    build_client_protection_node,
    build_client_satisfaction_node,
    build_financial_access_node,
    build_poverty_likelihood_node,
    build_resilience_node,
)
from .state import OrchestratorState
from .synthesis_nodes import build_client_voices_node, build_executive_summary_node, build_gender_scorecard_node

THEME_NODE_NAMES = (
    "build_client_profile",
    "build_financial_access",
    "build_poverty_likelihood",
    "build_business_household_impact",
    "build_child_wellbeing",
    "build_client_protection",
    "build_agency",
    "build_resilience",
    "build_client_satisfaction",
)


def build_graph() -> StateGraph:
    graph = StateGraph(OrchestratorState)

    # Tier -1: data prep
    graph.add_node("clean_columns", clean_columns_node)
    graph.add_node("check_rows", check_rows_node)
    graph.add_node("fail", fail_node)

    # Independent branch: dashboard visuals (no dependency on anything else)
    graph.add_node("resolve_dashboard_visuals", resolve_dashboard_visuals_node)

    # Tier 0: theme sections
    graph.add_node("build_client_profile", build_client_profile_node)
    graph.add_node("build_financial_access", build_financial_access_node)
    graph.add_node("build_poverty_likelihood", build_poverty_likelihood_node)
    graph.add_node("build_business_household_impact", build_business_household_impact_node)
    graph.add_node("build_child_wellbeing", build_child_wellbeing_node)
    graph.add_node("build_client_protection", build_client_protection_node)
    graph.add_node("build_agency", build_agency_node)
    graph.add_node("build_resilience", build_resilience_node)
    graph.add_node("build_client_satisfaction", build_client_satisfaction_node)

    # Tier 1: cross-cutting
    graph.add_node("build_gender_scorecard", build_gender_scorecard_node)
    graph.add_node("build_client_voices", build_client_voices_node)
    graph.add_node("build_executive_summary", build_executive_summary_node)

    # Tier 2/3
    graph.add_node("assemble_report", assemble_report_node)
    graph.add_node("render_docx", render_docx_node)
    graph.add_node("qa_review", qa_review_node)
    graph.add_node("done", done_node)

    # --- edges ---

    graph.add_edge(START, "clean_columns")
    graph.add_edge(START, "resolve_dashboard_visuals")
    graph.add_edge("clean_columns", "check_rows")
    graph.add_conditional_edges("check_rows", route_after_data_prep)
    graph.add_edge("fail", END)

    # Tier 1's real dependencies, not a blanket barrier
    for src in ("build_business_household_impact", "build_resilience", "build_child_wellbeing", "build_client_satisfaction"):
        graph.add_edge(src, "build_gender_scorecard")
    graph.add_edge("build_client_satisfaction", "build_client_voices")
    for src in THEME_NODE_NAMES:
        graph.add_edge(src, "build_executive_summary")

    # assemble_report needs all 12 -- defensive (see assembly_node.py)
    for src in THEME_NODE_NAMES + ("build_gender_scorecard", "build_client_voices", "build_executive_summary"):
        graph.add_edge(src, "assemble_report")

    graph.add_edge("assemble_report", "render_docx")
    graph.add_edge("resolve_dashboard_visuals", "render_docx")
    graph.add_edge("assemble_report", "qa_review")

    graph.add_edge("render_docx", "done")
    graph.add_edge("qa_review", "done")
    graph.add_edge("done", END)

    return graph


def compile_graph(checkpointer: Optional[object] = None) -> CompiledStateGraph:
    return build_graph().compile(checkpointer=checkpointer)
