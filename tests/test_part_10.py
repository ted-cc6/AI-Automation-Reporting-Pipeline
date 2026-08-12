"""
Unit tests for analysis_engine/sections/part_10.py -- the wave-over-wave
Trend Comparison section (LARCO only). Focused on the definition-match
fingerprint (Phase E): a changed question/scale/base between waves must be
flagged explicitly, not silently compared as if the two numbers measured the
same thing.
Run: pytest tests/test_part_10.py -v
"""
from __future__ import annotations

from analysis_engine.sections.part_10 import (
    _INDICATOR_DEFINITIONS,
    _compare_indicator,
    _current_snapshot,
)


def _snap(value=0.5, n_valid=500, definition=None):
    return {
        "value": value, "n_valid": n_valid, "n_total": n_valid,
        "suppressed": False, "suppress_reason": None, "not_applicable": False,
        "definition": definition,
    }


class TestDefinitionMatch:
    def test_identical_definitions_match(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        current = _snap(definition=d)
        prior = _snap(definition=d)
        row = _compare_indicator("first_time_access", "First-Time Access", current, prior)
        assert row["definition_match"] is True

    def test_different_definitions_flagged_as_mismatch(self):
        current = _snap(definition=_INDICATOR_DEFINITIONS["first_time_access"])
        prior = _snap(definition={"column": "q_prior_access_OLD", "rule": "different rule", "base": "all_respondents"})
        row = _compare_indicator("first_time_access", "First-Time Access", current, prior)
        assert row["definition_match"] is False

    def test_missing_definition_on_either_side_is_unknown_not_mismatch(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        # Prior predates the fingerprint feature -- no "definition" key at all.
        current = _snap(definition=d)
        prior = {"value": 0.4, "n_valid": 400}  # no "definition" key
        row = _compare_indicator("first_time_access", "First-Time Access", current, prior)
        assert row["definition_match"] is None

    def test_nps_branch_also_gets_definition_match(self):
        d = _INDICATOR_DEFINITIONS["client_satisfaction_nps"]
        current = _snap(value=20.0, definition=d)
        prior = _snap(value=15.0, definition={"column": "different", "rule": "x", "base": "y"})
        row = _compare_indicator("client_satisfaction_nps", "Client Satisfaction (NPS)", current, prior)
        assert row["definition_match"] is False
        # NPS's own special-cased fields must still be present alongside it.
        assert row["delta_unit"] == "NPS points"
        assert row["significance"]["test"] is not None


class TestCurrentSnapshotDefinitions:
    class _FakeDataset:
        def __init__(self, df):
            self.df = df
            self.child_wellbeing_base = df

    def test_every_indicator_carries_its_definition(self):
        import pandas as pd
        df = pd.DataFrame({
            "q_prior_access": pd.array([True, False], dtype="boolean"),
            "q_alternative_access": ["Not difficult", "Very difficult"],
            "q_child_wellbeing": ["Yes", "No"],
            "q_nps_score": pd.array([9, 3], dtype="Int16"),
            "q_product_understanding_combined": ["I know everything", "I know a little"],
        })
        snapshot = _current_snapshot(self._FakeDataset(df))
        for key, definition in _INDICATOR_DEFINITIONS.items():
            assert snapshot[key]["definition"] == definition

    def test_missing_column_still_carries_its_definition(self):
        import pandas as pd
        df = pd.DataFrame({"unrelated": [1, 2]})
        snapshot = _current_snapshot(self._FakeDataset(df))
        assert snapshot["first_time_access"]["definition"] == _INDICATOR_DEFINITIONS["first_time_access"]
        assert snapshot["first_time_access"]["not_applicable"] is True
