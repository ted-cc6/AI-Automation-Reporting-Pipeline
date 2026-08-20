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
    _COMPARABILITY,
    _COMPARABILITY_REASON,
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
            prior, comparability="clean",
        )
        assert row["comparability"] == "clean"
        assert row["comparability_reason"] == _COMPARABILITY_REASON["first_time_access"]
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
            current_common, prior, comparability="clean",
        )
        assert row["delta"] == pytest.approx(46.2 - 36.2)
        assert row["delta_unit"] == "NPS points"
        assert row["significance"]["test"] is not None
        assert row["significance"]["p_value"] is None
        # Reader-facing text must describe the real reason without leaking
        # an implementation detail ("stored JSON") the reader has no need
        # to know about.
        assert "JSON" not in row["significance"]["test"]
        assert "never retained" in row["significance"]["test"]


class TestNonComparableIndicators:
    def test_not_comparable_indicator_gets_no_delta_but_keeps_its_prior_value(self):
        # session-5 (LM3, per Lorenz): a non-"clean" indicator still skips
        # the delta/significance test, but its real prior-wave value is
        # now RETAINED, not discarded -- suppressing a real number just
        # because the comparison isn't rigorous defeated the point of a
        # three-value Comparability column.
        current_full = _snap(value=0.14)
        prior = _snap(value=0.20)
        row = _compare_indicator(
            "product_understanding", "Product Understanding", current_full,
            current_common=_snap(value=0.15), prior=prior,
            comparability="not_comparable",
        )
        assert row["comparability"] == "not_comparable"
        assert row["current_full_scope"] == current_full
        assert row["current_common_scope"] is None
        assert row["prior"] == prior
        assert row["delta"] is None
        assert row["delta_unit"] is None
        assert row["significance"] is None
        assert row["definition_match"] is None
        assert row["comparability_reason"]

    def test_missing_prior_falls_back_to_a_missing_placeholder(self):
        # If the prior wave genuinely has nothing for this indicator (no
        # prior dict at all), _missing_col()'s placeholder is used --
        # never a silent None that would render as an empty cell with no
        # explanation.
        row = _compare_indicator(
            "product_understanding", "Product Understanding", _snap(value=None),
            current_common=_snap(value=0.5), prior=None,
            comparability="not_comparable",
        )
        assert row["prior"]["not_applicable"] is True
        assert row["delta"] is None

    def test_indicative_indicator_gets_no_delta_but_keeps_both_values(self):
        # R-004: "indicative" is gated exactly like "not_comparable" for
        # delta/significance (no computation change from today's boolean
        # False), but a figure exists on both sides for these two
        # indicators specifically (LM3) -- both must be retained.
        current_full = _snap(value=0.445)
        prior = _snap(value=0.30)
        row = _compare_indicator(
            "access_to_alternatives", "Access to Alternatives", current_full,
            current_common=_snap(value=0.44), prior=prior,
            comparability="indicative",
        )
        assert row["comparability"] == "indicative"
        assert row["current_common_scope"] is None
        assert row["prior"] == prior
        assert row["delta"] is None
        assert row["significance"] is None
        assert row["comparability_reason"]


class TestComparabilityTable:
    def test_every_indicator_has_a_permitted_status(self):
        for key, status in _COMPARABILITY.items():
            assert status in {"clean", "indicative", "not_comparable"}

    def test_every_indicator_has_a_non_empty_reason(self):
        # R-004: the two "clean" indicators previously had no reason at
        # all (a boolean True needed no explanation) -- every indicator
        # gets one now, including them.
        for key in _COMPARABILITY:
            assert _COMPARABILITY_REASON.get(key), f"{key} has no reason string"

    def test_only_clean_indicators_are_clean(self):
        # LM3 (Lorenz): access_to_alternatives and child_wellbeing_improvement
        # are "indicative", not "not_comparable" -- an instrument change with
        # a figure on both sides is a different situation from
        # product_understanding, which has no current-wave figure at all.
        assert _COMPARABILITY["first_time_access"] == "clean"
        assert _COMPARABILITY["client_satisfaction_nps"] == "clean"
        assert _COMPARABILITY["access_to_alternatives"] == "indicative"
        assert _COMPARABILITY["child_wellbeing_improvement"] == "indicative"
        assert _COMPARABILITY["product_understanding"] == "not_comparable"


class TestDefinitionMatch:
    def test_identical_definitions_match(self):
        d = _INDICATOR_DEFINITIONS["first_time_access"]
        current_full = _snap(definition=d)
        current_common = _snap(definition=d)
        prior = _snap(definition=d)
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparability="clean",
        )
        assert row["definition_match"] is True

    def test_different_definitions_flagged_as_mismatch(self):
        current_full = _snap(definition=_INDICATOR_DEFINITIONS["first_time_access"])
        current_common = _snap(definition=_INDICATOR_DEFINITIONS["first_time_access"])
        prior = _snap(definition={"column": "q_prior_access_OLD", "rule": "different rule", "base": "all_respondents"})
        row = _compare_indicator(
            "first_time_access", "First-Time Access", current_full, current_common,
            prior, comparability="clean",
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
            prior, comparability="clean",
        )
        assert row["definition_match"] is None

    def test_nps_branch_also_gets_definition_match(self):
        d = _INDICATOR_DEFINITIONS["client_satisfaction_nps"]
        current_full = _snap(value=20.0, definition=d)
        current_common = _snap(value=20.0, definition=d)
        prior = _snap(value=15.0, definition={"column": "different", "rule": "x", "base": "y"})
        row = _compare_indicator(
            "client_satisfaction_nps", "Client Satisfaction (NPS)", current_full,
            current_common, prior, comparability="clean",
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

    def test_current_common_is_persisted_alongside_current_full(self):
        # R-005: previously computed every run and discarded -- never
        # saved, so a future wave using THIS run as its own prior had no
        # five-country figure to read back. Now persisted as its own key.
        countries = COMMON_LACRO_COUNTRIES[:2] * 3 + [NEW_COUNTRY_2026] * 4
        df = pd.DataFrame({
            "country": countries,
            "q_prior_access": pd.array([True] * 10, dtype="boolean"),
        })
        ds = self._FakeDataset(df)
        result = calculate(ds, segment_masks={})
        assert "current_common" in result
        # Common-scope excludes the 4 Dominican Republic rows -- only the
        # 6 rows on the two common countries should count.
        assert result["current_common"]["first_time_access"]["n_valid"] == 6
        assert result["current"]["first_time_access"]["n_valid"] == 10

