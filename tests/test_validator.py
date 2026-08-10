"""
Unit tests for data_loader/data_loader_validator.py's Check 5 (Derived
Variable Sanity) -- specifically the flag_negative_coping "at least one
True" assertion. This is a second, independent copy of the same check
data_loader_derived.py's run_assertions() makes (by design -- Check 5 is a
standalone re-verification, not shared code), so it needed the identical
country-scope fix applied separately. Regression coverage for the bug that
blocked Vietnam reports at the validator step after the derived-step fix
already landed.
Run: pytest tests/test_validator.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from data_loader.data_loader_validator import check_5_derived


def _bool_array(values):
    return pd.array(values, dtype="boolean")


def _base_df(n_insured: int, n_total: int, neg_coping_all_false: bool = True) -> pd.DataFrame:
    insured = _bool_array([True] * n_insured + [False] * (n_total - n_insured))
    neg_coping = _bool_array(
        ([False] * n_insured if neg_coping_all_false else [True] + [False] * (n_insured - 1))
        + [pd.NA] * (n_total - n_insured)
    ) if n_insured > 0 else _bool_array([pd.NA] * n_total)
    return pd.DataFrame({
        "q_insured_event_12m":              insured,
        "flag_negative_coping":             neg_coping,
        "flag_promoter":                    _bool_array([True] * (n_total // 2) + [False] * (n_total - n_total // 2)),
        "q_nps_score":                       pd.array([8] * n_total, dtype="Int16"),
        "flag_paid_claimant":               _bool_array([False] * n_total),
        "flag_child_wellbeing_denominator": _bool_array([True] * n_total),
        "insurance_type":                    ["crop"] * n_total,
    })


class TestCheck5NegativeCopingZeroTrueAssertion:
    def test_zero_true_fails_on_unscoped_default_run(self):
        df = _base_df(n_insured=500, n_total=1000)
        rows, errors, warnings = check_5_derived(df, target_country=None)
        assert any("flag_negative_coping" in e and "coding error" in e for e in errors)
        assert warnings == []

    def test_zero_true_passes_with_warning_when_country_scoped(self):
        df = _base_df(n_insured=147, n_total=147)
        rows, errors, warnings = check_5_derived(df, target_country="vietnam")
        assert errors == []
        assert any("flag_negative_coping" in w for w in warnings)

    def test_zero_insured_event_respondents_at_all_passes_when_scoped(self):
        # The exact shape reported in production: zero respondents even
        # flagged as having experienced an insured event.
        df = _base_df(n_insured=0, n_total=147)
        rows, errors, warnings = check_5_derived(df, target_country="vietnam")
        assert errors == []
        assert any("0 insured-event respondents" in w for w in warnings)

    def test_zero_true_still_fails_for_same_data_when_not_marked_scoped(self):
        df = _base_df(n_insured=147, n_total=147)
        rows, errors, warnings = check_5_derived(df, target_country=None)
        assert any("flag_negative_coping" in e for e in errors)

    def test_at_least_one_true_passes_regardless_of_scope(self):
        df = _base_df(n_insured=10, n_total=20, neg_coping_all_false=False)
        _, errors_unscoped, _ = check_5_derived(df, target_country=None)
        _, errors_scoped, _ = check_5_derived(df, target_country="vietnam")
        assert errors_unscoped == []
        assert errors_scoped == []

    def test_row_status_is_warn_not_fail_when_scoped(self):
        df = _base_df(n_insured=147, n_total=147)
        rows, _, _ = check_5_derived(df, target_country="vietnam")
        neg_coping_row = next(r for r in rows if r[0] == "flag_negative_coping — True count")
        assert neg_coping_row[3] == "WARN ⚠"

    def test_other_check_5_assertions_still_fire_regardless_of_scope(self):
        # A genuine structural bug (non-NaN outside insured-event rows)
        # must still be caught even on a country-scoped run -- only the
        # population-scale-dependent "at least one True" check is relaxed.
        df = _base_df(n_insured=5, n_total=10)
        df.loc[9, "flag_negative_coping"] = True  # row 9 is NOT insured (index >= 5)
        rows, errors, warnings = check_5_derived(df, target_country="vietnam")
        assert any("non-NaN" in e for e in errors)
