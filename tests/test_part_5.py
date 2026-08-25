"""
Unit tests for analysis_engine/sections/part_5.py -- focused on R-007's
caregiver-comparison healthcare_access base bug (session-10): the row used
ds.health directly, an ~4x-too-large base that includes clients who never
needed care at all, diluting a real 31.4% caregiver vs 46.7% non-caregiver
gap (p<0.05) down to a false-null 8.9% vs 8.6%. The same "did not need
care" exclusion Part 4's own headline healthcare_access figure already
applies (see analysis_engine/sections/part_4.py's HEALTHCARE_ACCESS_NA)
must also apply here.
Run: pytest tests/test_part_5.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis_engine.sections.part_4 import HEALTHCARE_ACCESS_NA
from analysis_engine.sections.part_5 import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame, health: "pd.DataFrame | None" = None):
        self.df = df
        self.health = health if health is not None else df
        self.child_wellbeing_base = df.iloc[0:0]  # empty -- not under test here


def _segment_masks(n_caregiver: int, n_non_caregiver: int) -> dict:
    return {
        "caregiver": pd.Series([True] * n_caregiver + [False] * n_non_caregiver),
        "non_caregiver": pd.Series([False] * n_caregiver + [True] * n_non_caregiver),
    }


class TestCaregiverHealthcareAccessBase:
    def test_did_not_need_care_excluded_from_caregiver_comparison_base(self):
        # 230 caregivers: 20 yes, 10 no, 200 did-not-need-care (needed_care=30).
        # 230 non-caregivers: 15 yes, 15 no, 200 did-not-need-care (needed_care=30).
        # n_valid=30 each keeps both above LOW_N_THRESHOLD (30) so the values
        # surface rather than being suppressed as low-n.
        # Wrong (ds.health-wide) base: 20/230=8.7% vs 15/230=6.5%.
        # Correct (needed-care-only) base: 20/30=66.7% vs 15/30=50%.
        values = (
            ["Yes"] * 20 + ["No"] * 10 + [HEALTHCARE_ACCESS_NA] * 200
            + ["Yes"] * 15 + ["No"] * 15 + [HEALTHCARE_ACCESS_NA] * 200
        )
        health_df = pd.DataFrame({"q_healthcare_access": values})
        ds = _FakeDataset(df=health_df.iloc[0:0], health=health_df)
        result = calculate(ds, _segment_masks(n_caregiver=230, n_non_caregiver=230))
        metric = result["caregiver_comparison"]["metrics"]["healthcare_access"]
        assert metric["caregiver"]["n_valid"] == 30
        assert metric["caregiver"]["value"] == pytest.approx(20 / 30)
        assert metric["non_caregiver"]["n_valid"] == 30
        assert metric["non_caregiver"]["value"] == pytest.approx(15 / 30)

    def test_matches_real_production_numbers(self):
        # Reproduces the exact real-data regression this bug was found in
        # (runs/lacro_final_check/): wrong 8.9%/8.6% vs correct 31.4%/46.7%.
        n_caregiver_yes, n_caregiver_no_care = 117, 940
        n_caregiver_needed = 373
        n_caregiver_total = n_caregiver_needed + n_caregiver_no_care
        caregiver_values = (
            ["Yes"] * n_caregiver_yes
            + ["No"] * (n_caregiver_needed - n_caregiver_yes)
            + [HEALTHCARE_ACCESS_NA] * n_caregiver_no_care
        )

        n_non_yes, n_non_no_care = 35, 333
        n_non_needed = 75
        non_caregiver_values = (
            ["Yes"] * n_non_yes
            + ["No"] * (n_non_needed - n_non_yes)
            + [HEALTHCARE_ACCESS_NA] * n_non_no_care
        )

        health_df = pd.DataFrame({
            "q_healthcare_access": caregiver_values + non_caregiver_values,
        })
        ds = _FakeDataset(df=health_df.iloc[0:0], health=health_df)
        result = calculate(
            ds,
            _segment_masks(
                n_caregiver=len(caregiver_values),
                n_non_caregiver=len(non_caregiver_values),
            ),
        )
        metric = result["caregiver_comparison"]["metrics"]["healthcare_access"]
        assert metric["caregiver"]["n_valid"] == n_caregiver_needed
        assert metric["caregiver"]["value"] == pytest.approx(n_caregiver_yes / n_caregiver_needed, abs=0.01)
        assert metric["non_caregiver"]["n_valid"] == n_non_needed
        assert metric["non_caregiver"]["value"] == pytest.approx(n_non_yes / n_non_needed, abs=0.01)
        assert metric["significance"]["p_value"] < 0.05

    def test_financial_stress_still_uses_full_sample(self):
        # financial_stress_high has no skip logic (see part_5.py's own
        # _CAREGIVER_COMPARISON_NOTE) -- R-007 only affects healthcare_access,
        # this must stay on ds.df unfiltered.
        df = pd.DataFrame({
            "q_financial_stress": [5] * 5 + [1] * 5 + [5] * 5 + [1] * 5,
        })
        ds = _FakeDataset(df=df, health=df.iloc[0:0])
        result = calculate(ds, _segment_masks(n_caregiver=10, n_non_caregiver=10))
        metric = result["caregiver_comparison"]["metrics"]["financial_stress_high"]
        assert metric["caregiver"]["n_valid"] == 10
        assert metric["non_caregiver"]["n_valid"] == 10
