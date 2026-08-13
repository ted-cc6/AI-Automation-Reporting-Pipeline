"""
Unit tests for analysis_engine/sections/part_12.py -- the Crop Module
(africa report_scope only). Every metric here is Vietnam crop clients
only -- the population note must say so explicitly.
Run: pytest tests/test_part_12.py -v
"""
from __future__ import annotations

import pandas as pd

from analysis_engine.sections.part_12 import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame):
        self.crop = df


class TestCropModule:
    def test_recovery_speed_counts_fastest_two_of_three_options(self):
        # n=40, kept >= LOW_N_THRESHOLD (30) so the result isn't suppressed --
        # 30 fast (10 immediate + 20 within 1-3 months), 10 slow.
        df = pd.DataFrame({
            "q_crop_recovery_speed": (
                ["Immediately or within 1 month"] * 10
                + ["After 1–3 months"] * 20
                + ["After more than 3 months"] * 10
            ),
            "q_crop_farming_change": ["No change"] * 40,
        })
        ds = _FakeDataset(df)
        result = calculate(ds, {})
        assert result["recovery_speed"]["n_valid"] == 40
        assert result["recovery_speed"]["suppressed"] is False
        assert result["recovery_speed"]["value"] == 30 / 40

    def test_farming_change_counts_top_two_of_four_options(self):
        # n=40, kept >= LOW_N_THRESHOLD (30) -- 25 improved (15 very much +
        # 10 slightly), 15 not.
        df = pd.DataFrame({
            "q_crop_recovery_speed": ["After 1–3 months"] * 40,
            "q_crop_farming_change": (
                ["Very much improved"] * 15
                + ["Slightly improved"] * 10
                + ["No change"] * 10
                + ["Got slightly worse"] * 5
            ),
        })
        ds = _FakeDataset(df)
        result = calculate(ds, {})
        assert result["farming_change"]["n_valid"] == 40
        assert result["farming_change"]["suppressed"] is False
        assert result["farming_change"]["value"] == 25 / 40

    def test_population_note_states_vietnam_crop_only(self):
        ds = _FakeDataset(pd.DataFrame({
            "q_crop_recovery_speed": [], "q_crop_farming_change": [],
        }))
        result = calculate(ds, {})
        assert "Vietnam" in result["population"]
        assert "crop" in result["population"].lower()

    def test_missing_columns_degrade_to_not_applicable(self):
        ds = _FakeDataset(pd.DataFrame({"unrelated": [1, 2, 3]}))
        result = calculate(ds, {})
        assert result["recovery_speed"]["not_applicable"] is True
        assert result["farming_change"]["not_applicable"] is True
