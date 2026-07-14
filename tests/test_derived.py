"""
Unit tests for data_loader/data_loader_derived.py — the derived boolean flag
columns and structural assertions that gate the pipeline before parquet write.
Run: pytest tests/test_derived.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from data_loader.data_loader_derived import (
    compute_flag_child_wellbeing_denominator,
    compute_flag_negative_coping,
    compute_flag_paid_claimant,
    compute_flag_promoter,
    run_assertions,
)


def _bool_array(values):
    return pd.array(values, dtype="boolean")


# ---------------------------------------------------------------------------
# flag_negative_coping
# ---------------------------------------------------------------------------

class TestFlagNegativeCoping:
    def _df(self, insured, c, d, e, f):
        return pd.DataFrame({
            "q_insured_event_12m":     _bool_array(insured),
            "q_coping_mechanisms__c":  _bool_array(c),
            "q_coping_mechanisms__d":  _bool_array(d),
            "q_coping_mechanisms__e":  _bool_array(e),
            "q_coping_mechanisms__f":  _bool_array(f),
        })

    def test_true_when_any_severe_option_selected_and_in_scope(self):
        df = self._df(
            insured=[True, True, True],
            c=[True, False, False],
            d=[False, False, False],
            e=[False, False, False],
            f=[False, False, False],
        )
        result = compute_flag_negative_coping(df)
        assert list(result) == [True, False, False]

    def test_nan_when_no_insured_event_regardless_of_coping_answers(self):
        df = self._df(
            insured=[False, False],
            c=[True, True],   # even with a "severe" answer, out of scope → NaN
            d=[False, False],
            e=[False, False],
            f=[False, False],
        )
        result = compute_flag_negative_coping(df)
        assert pd.isna(result[0]) and pd.isna(result[1])

    def test_missing_column_raises_keyerror_not_silent_nan(self):
        df = pd.DataFrame({"q_insured_event_12m": _bool_array([True])})
        with pytest.raises(KeyError):
            compute_flag_negative_coping(df)


# ---------------------------------------------------------------------------
# flag_promoter
# ---------------------------------------------------------------------------

class TestFlagPromoter:
    def test_true_for_score_9_and_above(self):
        df = pd.DataFrame({"q_nps_score": pd.array([10, 9, 8, 0, None], dtype="Int16")})
        result = compute_flag_promoter(df)
        assert list(result)[:4] == [True, True, False, False]
        assert pd.isna(result[4])

    def test_missing_column_raises_keyerror(self):
        with pytest.raises(KeyError):
            compute_flag_promoter(pd.DataFrame({"other": [1]}))


# ---------------------------------------------------------------------------
# flag_paid_claimant
# ---------------------------------------------------------------------------

class TestFlagPaidClaimant:
    def test_true_only_for_exact_approved_and_paid_string(self):
        df = pd.DataFrame({
            "q_claim_result": [
                "It was approved and paid",
                "It was rejected",
                None,
            ]
        })
        result = compute_flag_paid_claimant(df)
        assert result[0] == True   # noqa: E712
        assert result[1] == False  # noqa: E712
        assert pd.isna(result[2])


# ---------------------------------------------------------------------------
# flag_child_wellbeing_denominator
# ---------------------------------------------------------------------------

class TestFlagChildWellbeingDenominator:
    def test_yes_no_are_true_other_values_and_na_are_false_never_na(self):
        df = pd.DataFrame({
            "q_child_wellbeing": [
                "Yes", "No", "Do not support any children", None,
            ]
        })
        result = compute_flag_child_wellbeing_denominator(df)
        assert list(result) == [True, True, False, False]
        assert result.isna().sum() == 0  # this flag is never NaN, by design


# ---------------------------------------------------------------------------
# run_assertions — structural gate before parquet write
# ---------------------------------------------------------------------------

class TestRunAssertions:
    def _valid_df(self):
        return pd.DataFrame({
            "q_insured_event_12m":               _bool_array([True, True, False]),
            "q_nps_score":                        pd.array([9, None, 5], dtype="Int16"),
            "q_child_wellbeing":                  ["Yes", "No", None],
            "insurance_type":                     ["health", "crop", "credit_life"],
            "flag_negative_coping":               _bool_array([True, pd.NA, pd.NA]),
            "flag_promoter":                      _bool_array([True, pd.NA, False]),
            "flag_paid_claimant":                 _bool_array([False, False, False]),
            "flag_child_wellbeing_denominator":   _bool_array([True, True, False]),
        })

    def test_passes_on_structurally_valid_frame(self):
        assert run_assertions(self._valid_df()) is True

    def test_fails_when_flag_column_missing(self):
        df = self._valid_df().drop(columns=["flag_promoter"])
        assert run_assertions(df) is False

    def test_fails_when_negative_coping_leaks_outside_insured_scope(self):
        df = self._valid_df()
        # Row 2 (index 2) did NOT experience an insured event but has a non-NaN flag
        df.loc[2, "flag_negative_coping"] = True
        assert run_assertions(df) is False

    def test_fails_when_child_wellbeing_denominator_has_nan(self):
        df = self._valid_df()
        df.loc[0, "flag_child_wellbeing_denominator"] = pd.NA
        assert run_assertions(df) is False

    def test_fails_on_unexpected_insurance_type_slug(self):
        df = self._valid_df()
        df.loc[0, "insurance_type"] = "life_insurance"  # not a valid slug
        assert run_assertions(df) is False
