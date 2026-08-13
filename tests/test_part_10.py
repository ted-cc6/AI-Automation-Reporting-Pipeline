"""
Unit tests for analysis_engine/sections/part_10.py -- the wave-over-wave
Trend Comparison section (LACRO only). Covers the definition-match
fingerprint (a changed question/scale/base between waves must be flagged
explicitly, not silently compared as if the two numbers measured the same
thing) and the comparability/common-country-population design (Requirement
5: non-comparable indicators never get a prior value at all; comparable
indicators compute their delta against the five countries common to both
waves while the headline figure stays full-scope).
Run: pytest tests/test_part_10.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis_engine.sections.part_10 import (
    COMMON_LACRO_COUNTRIES,
    NEW_COUNTRY_2026,
    _INDICATOR_DEFINITIONS,
    _compare_indicator,
    _current_snapshot,
    _filter_to_common_countries,
    calculate,
)


def _snap(value=0.5, n_valid=500, definition=None):
    return {
        "value": value, "n_valid": n_valid, "n_total": n_valid,
        "suppressed": False, "suppress_reason": None, "not_applicable": False,
        "definition": definition,
    }


class TestComparableIndicators:
    def test_comparable_indicator_uses_common_scope_for_delta(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        current_full = _snap(value=0.772, definition=d)
        current_common = _snap(value=0.767, definition=d)
        prior = _snap(value=0.736, definition=d)
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparable=True,
        )
        assert row["comparable"] is True
        assert row["current_full_scope"] == current_full
        assert row["current_common_scope"] == current_common
        assert row["delta"] == pytest.approx(0.767 - 0.736)
        assert row["significance"] is not None

    def test_nps_branch_uses_common_scope_and_reports_raw_delta(self):
        d = _INDICATOR_DEFINITIONS["client_satisfaction_nps"]
        current_full = _snap(value=48.3, definition=d)
        current_common = _snap(value=46.2, definition=d)
        prior = _snap(value=36.2, definition=d)
        row = _compare_indicator(
            "client_satisfaction_nps", "Client Satisfaction (NPS)", current_full,
            current_common, prior, comparable=True,
        )
        assert row["delta"] == pytest.approx(46.2 - 36.2)
        assert row["delta_unit"] == "NPS points"
        assert row["significance"]["test"] is not None
        assert row["significance"]["p_value"] is None


class TestNonComparableIndicators:
    def test_non_comparable_indicator_gets_no_prior_or_delta(self):
        current_full = _snap(value=0.445)
        row = _compare_indicator(
            "access_to_alternatives", "Access to Alternatives", current_full,
            current_common=_snap(value=0.44), prior=_snap(value=0.30),
            comparable=False,
        )
        assert row["comparable"] is False
        assert row["current_full_scope"] == current_full
        assert row["current_common_scope"] is None
        assert row["prior"] is None
        assert row["delta"] is None
        assert row["delta_unit"] is None
        assert row["significance"] is None
        assert row["definition_match"] is None
        assert row["incomparability_reason"]

    def test_non_comparable_indicator_ignores_prior_even_if_given(self):
        # Even when a prior value IS available, comparable=False must not
        # leak it into the row -- the writer must never see a number it
        # could mistake for a valid comparison.
        row = _compare_indicator(
            "product_understanding", "Product Understanding", _snap(value=None),
            current_common=_snap(value=0.5), prior=_snap(value=0.4),
            comparable=False,
        )
        assert row["prior"] is None
        assert row["delta"] is None


class TestDefinitionMatch:
    def test_identical_definitions_match(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        current_full = _snap(definition=d)
        current_common = _snap(definition=d)
        prior = _snap(definition=d)
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparable=True,
        )
        assert row["definition_match"] is True

    def test_different_definitions_flagged_as_mismatch(self):
        current_full = _snap(definition=_INDICATOR_DEFINITIONS["first_time_access"])
        current_common = _snap(definition=_INDICATOR_DEFINITIONS["first_time_access"])
        prior = _snap(definition={"column": "q_prior_access_OLD", "rule": "different rule", "base": "all_respondents"})
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparable=True,
        )
        assert row["definition_match"] is False

    def test_missing_definition_on_either_side_is_unknown_not_mismatch(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        # Prior predates the fingerprint feature -- no "definition" key at all.
        current_full = _snap(definition=d)
        current_common = _snap(definition=d)
        prior = {"value": 0.4, "n_valid": 400}  # no "definition" key
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparable=True,
        )
        assert row["definition_match"] is None

    def test_nps_branch_also_gets_definition_match(self):
        d = _INDICATOR_DEFINITIONS["client_satisfaction_nps"]
        current_full = _snap(value=20.0, definition=d)
        current_common = _snap(value=20.0, definition=d)
        prior = _snap(value=15.0, definition={"column": "different", "rule": "x", "base": "y"})
        row = _compare_indicator(
            "client_satisfaction_nps", "Client Satisfaction (NPS)", current_full,
            current_common, prior, comparable=True,
        )
        assert row["definition_match"] is False
        # NPS's own special-cased fields must still be present alongside it.
        assert row["delta_unit"] == "NPS points"
        assert row["significance"]["test"] is not None


class TestCurrentSnapshotDefinitions:
    def _df(self):
        return pd.DataFrame({
            "q_prior_access": pd.array([True, False], dtype="boolean"),
            "q_alternative_access": ["Not difficult", "Very difficult"],
            "q_child_wellbeing": ["Yes", "No"],
            "q_nps_score": pd.array([9, 3], dtype="Int16"),
            "q_product_understanding_combined": ["I know everything", "I know a little"],
        })

    def test_every_indicator_carries_its_definition(self):
        df = self._df()
        snapshot = _current_snapshot(df, df)
        for key, definition in _INDICATOR_DEFINITIONS.items():
            assert snapshot[key]["definition"] == definition

    def test_missing_column_still_carries_its_definition(self):
        df = pd.DataFrame({"unrelated": [1, 2]})
        snapshot = _current_snapshot(df, df)
        assert snapshot["first_time_access"]["definition"] == _INDICATOR_DEFINITIONS["first_time_access"]
        assert snapshot["first_time_access"]["not_applicable"] is True

    def test_takes_explicit_population_not_a_dataset_object(self):
        # calculate() calls this twice (full scope, common-country scope)
        # from the same df -- the function must accept plain DataFrames
        # rather than reading ds.df/ds.child_wellbeing_base itself.
        full = self._df()
        common = full.iloc[:1]
        snap_full = _current_snapshot(full, full)
        snap_common = _current_snapshot(common, common)
        assert snap_full["first_time_access"]["n_valid"] == 2
        assert snap_common["first_time_access"]["n_valid"] == 1


class TestFilterToCommonCountries:
    def test_keeps_only_common_countries(self):
        df = pd.DataFrame({
            "country": ["Bolivia", "Dominican Republic", "Ecuador", "Dominican Republic"],
            "value": [1, 2, 3, 4],
        })
        filtered = _filter_to_common_countries(df)
        assert set(filtered["country"]) == {"Bolivia", "Ecuador"}
        assert NEW_COUNTRY_2026 not in set(filtered["country"])

    def test_missing_country_column_returns_df_unchanged(self):
        df = pd.DataFrame({"value": [1, 2, 3]})
        filtered = _filter_to_common_countries(df)
        assert len(filtered) == 3


class TestCalculateSampleComposition:
    class _FakeDataset:
        def __init__(self, df):
            self.df = df
            self.child_wellbeing_base = df

    def test_reports_new_country_count_and_share(self):
        countries = COMMON_LACRO_COUNTRIES[:1] * 6 + [NEW_COUNTRY_2026] * 4
        df = pd.DataFrame({
            "country": countries,
            "q_prior_access": pd.array([True] * 10, dtype="boolean"),
        })
        ds = self._FakeDataset(df)
        result = calculate(ds, segment_masks={})
        comp = result["sample_composition"]
        assert comp["n_total"] == 10
        assert comp["n_new_country"] == 4
        assert comp["new_country_share"] == pytest.approx(0.4)
        assert comp["common_countries"] == COMMON_LACRO_COUNTRIES
        assert comp["new_country"] == NEW_COUNTRY_2026

    def test_current_key_stays_full_scope_for_backward_compatibility(self):
        # _build_trend_data() reads package["current"] directly -- this key
        # must keep meaning "full report scope", not the common-country one.
        df = pd.DataFrame({
            "country": [NEW_COUNTRY_2026] * 5,
            "q_prior_access": pd.array([True, True, False, False, False], dtype="boolean"),
        })
        ds = self._FakeDataset(df)
        result = calculate(ds, segment_masks={})
        assert result["current"]["first_time_access"]["n_valid"] == 5

