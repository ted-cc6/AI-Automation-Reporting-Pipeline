"""
Unit tests for analysis_engine/sections/part_3.py -- focused on R-008's
coping component breakdown (session-10): flag_negative_coping collapses
four severe coping behaviours (sold assets/livestock, reduced food
consumption, took children out of school, closed business temporarily)
into one boolean before the narrative is written, so LM8's "can we mention
what that negative coping behavior is?" could never be answered. A
component found but too small to name without risking identifying a
specific respondent (n<=1) is counted in suppressed_components, not
listed by name -- confirmed with the user this is a disclosure-avoidance
threshold distinct from analysis_engine.stats.LOW_N_THRESHOLD (30), which
would suppress every component on real data (the flagged group itself is
far smaller than 30).
Run: pytest tests/test_part_3.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis_engine.sections.part_3 import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.insured_event_base = df


def _coping_df(n_c=0, n_d=0, n_e=0, n_f=0, n_none=0) -> pd.DataFrame:
    """n_c/d/e/f respondents each with exactly one severe component set;
    n_none respondents with none set (flag_negative_coping False)."""
    rows = []
    for _ in range(n_c):
        rows.append({"q_coping_mechanisms__c": True, "q_coping_mechanisms__d": False,
                      "q_coping_mechanisms__e": False, "q_coping_mechanisms__f": False})
    for _ in range(n_d):
        rows.append({"q_coping_mechanisms__c": False, "q_coping_mechanisms__d": True,
                      "q_coping_mechanisms__e": False, "q_coping_mechanisms__f": False})
    for _ in range(n_e):
        rows.append({"q_coping_mechanisms__c": False, "q_coping_mechanisms__d": False,
                      "q_coping_mechanisms__e": True, "q_coping_mechanisms__f": False})
    for _ in range(n_f):
        rows.append({"q_coping_mechanisms__c": False, "q_coping_mechanisms__d": False,
                      "q_coping_mechanisms__e": False, "q_coping_mechanisms__f": True})
    for _ in range(n_none):
        rows.append({"q_coping_mechanisms__c": False, "q_coping_mechanisms__d": False,
                      "q_coping_mechanisms__e": False, "q_coping_mechanisms__f": False})
    df = pd.DataFrame(rows)
    df["flag_negative_coping"] = df[[
        "q_coping_mechanisms__c", "q_coping_mechanisms__d",
        "q_coping_mechanisms__e", "q_coping_mechanisms__f",
    ]].any(axis=1)
    return df


class TestCopingComponents:
    def test_matches_real_production_numbers(self):
        # Reproduces runs/lacro_final_check/: 7 sold assets, 1 closed
        # business, 0 reduced food, 0 took children out of school.
        ds = _FakeDataset(_coping_df(n_c=7, n_f=1, n_none=116))
        result = calculate(ds, segment_masks={})
        metric = result["metrics"]["negative_coping"]
        assert metric["components"] == [
            {"key": "sold_assets_livestock", "label": "Sold assets or livestock", "n": 7},
        ]
        assert metric["suppressed_components"] == 1

    def test_components_ranked_descending(self):
        ds = _FakeDataset(_coping_df(n_c=3, n_d=10, n_e=5, n_none=50))
        result = calculate(ds, segment_masks={})
        components = result["metrics"]["negative_coping"]["components"]
        assert [c["key"] for c in components] == [
            "reduced_food_consumption", "took_children_out_of_school", "sold_assets_livestock",
        ]
        assert result["metrics"]["negative_coping"]["suppressed_components"] == 0

    def test_zero_count_component_omitted_not_suppressed(self):
        ds = _FakeDataset(_coping_df(n_c=5, n_none=50))
        result = calculate(ds, segment_masks={})
        metric = result["metrics"]["negative_coping"]
        assert len(metric["components"]) == 1
        assert metric["suppressed_components"] == 0

    def test_all_components_suppressed_when_all_singleton(self):
        ds = _FakeDataset(_coping_df(n_c=1, n_d=1, n_none=100))
        result = calculate(ds, segment_masks={})
        metric = result["metrics"]["negative_coping"]
        assert metric["components"] == []
        assert metric["suppressed_components"] == 2

    def test_no_flagged_respondents_gives_empty_breakdown(self):
        ds = _FakeDataset(_coping_df(n_none=50))
        result = calculate(ds, segment_masks={})
        metric = result["metrics"]["negative_coping"]
        assert metric["components"] == []
        assert metric["suppressed_components"] == 0

    def test_missing_column_gives_empty_breakdown_not_a_crash(self):
        df = pd.DataFrame({"other_col": [1, 2, 3]})
        ds = _FakeDataset(df)
        result = calculate(ds, segment_masks={})
        metric = result["metrics"]["negative_coping"]
        assert metric["components"] == []
        assert metric["suppressed_components"] == 0
