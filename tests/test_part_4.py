"""
Unit tests for analysis_engine/sections/part_4.py -- focused on the
healthcare_access base bug: "did not need care" is a real, common response
value (not blank/NaN), and must be excluded from the share's denominator the
same way medical_cost_change's own sibling NA value already is, or the
headline share is computed against a base ~4x too large. A real generated
report showed "Among clients who needed care, 8.8%..." (152/1,721, the wrong
base) when the correct figure is 33.9% (152/448, clients who actually
needed care).
Run: pytest tests/test_part_4.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis_engine.sections.part_4 import _HEALTHCARE_ACCESS_NA, calculate


class _FakeDataset:
    def __init__(self, health: pd.DataFrame):
        self.df = health
        self.health = health
        self.child_wellbeing_base = health.iloc[0:0]  # empty -- not under test here


def _health_df(n_yes: int, n_no: int, n_not_applicable: int) -> pd.DataFrame:
    values = (
        ["Yes"] * n_yes
        + ["No"] * n_no
        + [_HEALTHCARE_ACCESS_NA] * n_not_applicable
    )
    return pd.DataFrame({"q_healthcare_access": values})


class TestHealthcareAccessBase:
    def test_not_applicable_excluded_from_base(self):
        # 152 yes, 296 no, 1,273 "did not need care" -- matches the real
        # production numbers cited in the bug report. Correct share is
        # 152/448 = 33.9%, not 152/1721 = 8.8%.
        ds = _FakeDataset(_health_df(n_yes=152, n_no=296, n_not_applicable=1273))
        result = calculate(ds, segment_masks={})
        headline = result["healthcare_access"]["headline"]
        assert headline["n_valid"] == 448
        assert headline["n_total"] == 448
        assert headline["value"] == pytest.approx(152 / 448)

    def test_full_raw_distribution_still_includes_not_applicable(self):
        # ha_dist is a diagnostic field, not the headline share -- it should
        # still show the true 3-category split, including how many clients
        # never needed care at all.
        ds = _FakeDataset(_health_df(n_yes=15, n_no=25, n_not_applicable=100))
        result = calculate(ds, segment_masks={})
        dist_values = {row["value"] for row in result["healthcare_access"]["distribution"]}
        assert _HEALTHCARE_ACCESS_NA in dist_values

    def test_no_not_applicable_values_behaves_like_before(self):
        ds = _FakeDataset(_health_df(n_yes=20, n_no=20, n_not_applicable=0))
        result = calculate(ds, segment_masks={})
        headline = result["healthcare_access"]["headline"]
        assert headline["n_valid"] == 40
        assert headline["value"] == pytest.approx(0.5)

    def test_all_not_applicable_suppresses_as_missing_not_a_zero(self):
        ds = _FakeDataset(_health_df(n_yes=0, n_no=0, n_not_applicable=50))
        result = calculate(ds, segment_masks={})
        headline = result["healthcare_access"]["headline"]
        assert headline["value"] is None
        assert headline.get("suppress_reason") == "no matching values found"

    def test_missing_column_degrades_gracefully(self):
        ds = _FakeDataset(pd.DataFrame({"other_col": [1, 2, 3]}))
        result = calculate(ds, segment_masks={})
        assert result["healthcare_access"]["headline"]["value"] is None
        assert result["healthcare_access"]["distribution"] == []
