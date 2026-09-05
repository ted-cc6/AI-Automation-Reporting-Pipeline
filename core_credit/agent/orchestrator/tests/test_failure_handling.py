"""CC-038: proves diagnose_failure() correctly reports which nodes completed before a crash,
against a REAL (temp-file) SQLite checkpointer and a graph with one node that deliberately
raises. The assumption this whole fix rests on is that LangGraph persists a completed node's
state write even when a LATER node in the same run raises, so get_state() after the crash
still shows what finished -- this test proves that assumption rather than trusting it. No LLM
calls; reuses test_graph_topology.py's stub nodes and monkeypatch approach.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

import orchestrator.graph as graph_module
from graph.checkpointing import sqlite_checkpointer
from orchestrator.run_orchestrator import diagnose_failure

from .test_graph_topology import (
    _assemble_report_stub,
    _check_rows_stub,
    _clean_columns_stub,
    _done_stub,
    _make_section_stub,
    _qa_review_stub,
    _render_docx_stub,
    _resolve_dashboard_visuals_stub,
)


def _raising_node(state):
    raise ValueError("simulated node failure")


def _patch_stubs_with_one_failure(monkeypatch, failing_node_attr: str):
    monkeypatch.setattr(graph_module, "clean_columns_node", _clean_columns_stub)
    monkeypatch.setattr(graph_module, "check_rows_node", _check_rows_stub)
    monkeypatch.setattr(graph_module, "resolve_dashboard_visuals_node", _resolve_dashboard_visuals_stub)
    for attr, section_id in [
        ("build_client_profile_node", "client_profile"),
        ("build_financial_access_node", "financial_access"),
        ("build_poverty_likelihood_node", "poverty_likelihood"),
        ("build_business_household_impact_node", "business_household_impact"),
        ("build_child_wellbeing_node", "child_wellbeing"),
        ("build_client_protection_node", "client_protection"),
        ("build_agency_node", "agency"),
        ("build_resilience_node", "resilience"),
        ("build_client_satisfaction_node", "client_satisfaction"),
    ]:
        monkeypatch.setattr(graph_module, attr, _raising_node if attr == failing_node_attr else _make_section_stub(section_id))
    monkeypatch.setattr(graph_module, "build_gender_scorecard_node", _make_section_stub("gender_scorecard"))
    monkeypatch.setattr(graph_module, "build_client_voices_node", _make_section_stub("client_voices"))
    monkeypatch.setattr(graph_module, "build_executive_summary_node", _make_section_stub("executive_summary"))
    monkeypatch.setattr(graph_module, "assemble_report_node", _assemble_report_stub)
    monkeypatch.setattr(graph_module, "render_docx_node", _render_docx_stub)
    monkeypatch.setattr(graph_module, "qa_review_node", _qa_review_stub)
    monkeypatch.setattr(graph_module, "done_node", _done_stub)


def test_diagnose_failure_reports_sections_that_completed_before_the_crash(monkeypatch):
    _patch_stubs_with_one_failure(monkeypatch, "build_client_satisfaction_node")

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.db")
        with sqlite_checkpointer(db_path) as checkpointer:
            compiled = graph_module.build_graph().compile(checkpointer=checkpointer)
            graph_config = {"configurable": {"thread_id": "test-crash"}}
            inputs = {"raw_csv_path": "fake_raw.csv", "run_id": "test-crash", "benchmarks_path": "fake.xlsx"}

            with pytest.raises(ValueError, match="simulated node failure"):
                compiled.invoke(inputs, config=graph_config)

            diagnosis = diagnose_failure(compiled, graph_config, ValueError("simulated node failure"))

    assert "client_satisfaction" in diagnosis["sections_missing"]
    assert "client_satisfaction" not in diagnosis["sections_completed"]
    # the 8 other theme sections run concurrently with client_satisfaction and don't depend on
    # it (see graph.py's edges), so they must have completed and been checkpointed before the
    # crash -- this is the actual claim under test, not just that the dict has the right shape
    for sid in [
        "client_profile", "financial_access", "poverty_likelihood", "business_household_impact",
        "child_wellbeing", "client_protection", "agency", "resilience",
    ]:
        assert sid in diagnosis["sections_completed"], f"{sid} should have completed before the crash"
    assert diagnosis["exception_type"] == "ValueError"
    assert diagnosis["exception_message"] == "simulated node failure"


def test_diagnose_failure_when_nothing_completed_yet(monkeypatch):
    # clean_columns is the very first node -- failing there means no section ever started.
    monkeypatch.setattr(graph_module, "clean_columns_node", _raising_node)
    monkeypatch.setattr(graph_module, "resolve_dashboard_visuals_node", _resolve_dashboard_visuals_stub)

    with tempfile.TemporaryDirectory() as tmp:
        db_path = str(Path(tmp) / "checkpoints.db")
        with sqlite_checkpointer(db_path) as checkpointer:
            compiled = graph_module.build_graph().compile(checkpointer=checkpointer)
            graph_config = {"configurable": {"thread_id": "test-crash-early"}}
            inputs = {"raw_csv_path": "fake_raw.csv", "run_id": "test-crash-early", "benchmarks_path": "fake.xlsx"}

            with pytest.raises(ValueError, match="simulated node failure"):
                compiled.invoke(inputs, config=graph_config)

            diagnosis = diagnose_failure(compiled, graph_config, ValueError("simulated node failure"))

    assert diagnosis["sections_completed"] == []
    assert len(diagnosis["sections_missing"]) == 12


def test_diagnose_failure_handles_get_state_itself_raising(monkeypatch):
    # Defensive path: if get_state() can't be called at all (e.g. a corrupted checkpoint), the
    # diagnosis must still return a usable dict rather than raising a second exception on top
    # of the first.
    class _BrokenCompiled:
        def get_state(self, config):
            raise RuntimeError("checkpoint unreadable")

    diagnosis = diagnose_failure(_BrokenCompiled(), {}, ValueError("original failure"))
    assert diagnosis["sections_completed"] == []
    assert len(diagnosis["sections_missing"]) == 12
    assert diagnosis["exception_message"] == "original failure"
