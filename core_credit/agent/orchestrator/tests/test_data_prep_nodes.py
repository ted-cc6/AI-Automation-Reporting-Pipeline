from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd

from orchestrator.data_prep_nodes import (
    REQUIRED_COLUMNS,
    _find_wrote_path,
    _import_build_tools,
    _missing_required_columns,
    check_rows_node,
    route_after_data_prep,
)
from orchestrator.data_prep_nodes import COLUMN_CLEAN_DIR, ROW_CHECK_DIR


def _msg(content):
    return SimpleNamespace(content=content)


def test_find_wrote_path_extracts_the_exact_path():
    messages = [
        _msg("some earlier reasoning"),
        _msg("Wrote trimmed CSV: /tmp/foo_trimmed.csv\nWrote manifest: /tmp/foo_manifest.json\nRows: 100"),
    ]
    assert _find_wrote_path(messages, "trimmed CSV") == "/tmp/foo_trimmed.csv"
    assert _find_wrote_path(messages, "manifest") == "/tmp/foo_manifest.json"


def test_find_wrote_path_returns_none_when_the_agent_never_saved():
    # This is the anomaly-halt case: the agent explained a problem instead of calling save_*.
    messages = [_msg("ANOMALY WARNING: very few columns were kept. Stopping without saving.")]
    assert _find_wrote_path(messages, "trimmed CSV") is None


def test_find_wrote_path_ignores_non_string_content():
    messages = [_msg([{"type": "text", "text": "structured content, not a plain string"}])]
    assert _find_wrote_path(messages, "trimmed CSV") is None


def test_route_after_data_prep_fans_out_to_all_nine_theme_builders_when_ready():
    result = route_after_data_prep({"data_ready": True, "csv_path": "/tmp/analysis_ready.csv"})
    assert isinstance(result, list)
    assert len(result) == 9
    assert "build_client_profile" in result
    assert "build_client_satisfaction" in result


def test_route_after_data_prep_fails_when_not_ready():
    assert route_after_data_prep({"data_ready": False}) == "fail"


def test_route_after_data_prep_fails_when_csv_path_missing_even_if_flag_true():
    # Defensive: data_ready=True with no csv_path shouldn't be trusted.
    assert route_after_data_prep({"data_ready": True}) == "fail"


def test_check_rows_node_short_circuits_if_column_clean_already_failed():
    # Must not attempt to build tools / invoke an agent when there's nothing to check.
    result = check_rows_node({"data_ready": False, "failure_reason": "Column Cleaner failed."})
    assert result == {}


def test_import_build_tools_does_not_leak_modules_across_calls():
    _import_build_tools(COLUMN_CLEAN_DIR, ("rules",))
    import sys

    assert "tools" not in sys.modules
    assert "rules" not in sys.modules
    _import_build_tools(ROW_CHECK_DIR, ("checks",))
    assert "tools" not in sys.modules
    assert "checks" not in sys.modules


def test_missing_required_columns_detects_a_real_gap(tmp_path):
    # Regression test for the real incident: Column Cleaner dropped
    # Introduction/SurveyVersion, and nothing caught it until a section crashed ~10 minutes in.
    csv_path = tmp_path / "missing_one.csv"
    present = [c for c in REQUIRED_COLUMNS if c != "Introduction/SurveyVersion"]
    pd.DataFrame(columns=present + ["some_other_col"]).to_csv(csv_path, index=False)

    missing = _missing_required_columns(str(csv_path))
    assert missing == ["Introduction/SurveyVersion"]


def test_missing_required_columns_empty_when_everything_present(tmp_path):
    csv_path = tmp_path / "complete.csv"
    pd.DataFrame(columns=list(REQUIRED_COLUMNS) + ["some_other_col"]).to_csv(csv_path, index=False)

    assert _missing_required_columns(str(csv_path)) == []


def test_check_rows_node_fails_fast_when_a_required_column_was_dropped(tmp_path):
    csv_path = tmp_path / "incomplete_analysis_ready.csv"
    present = [c for c in REQUIRED_COLUMNS if c != "Introduction/Global unique client id"]
    pd.DataFrame(columns=present).to_csv(csv_path, index=False)

    fake_messages = [SimpleNamespace(content=f"Wrote analysis-ready CSV: {csv_path}\nWrote QA report: {tmp_path}/qa.json")]
    with patch("orchestrator.data_prep_nodes._import_build_tools"), \
         patch("orchestrator.data_prep_nodes._load_config", return_value={}), \
         patch("orchestrator.data_prep_nodes.ChatAnthropic"), \
         patch("orchestrator.data_prep_nodes.create_agent") as mock_create_agent:
        mock_create_agent.return_value.invoke.return_value = {"messages": fake_messages}
        result = check_rows_node({"trimmed_csv_path": "fake.csv", "run_id": "test"})

    assert result["data_ready"] is False
    assert "Introduction/Global unique client id" in result["failure_reason"]
