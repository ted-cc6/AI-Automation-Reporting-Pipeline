"""
Unit tests for analysis_engine/sections/about_survey.py -- the deterministic
"About This Survey" respondent-composition summary (Phase D). The core
guarantee under test: product-mix must never render from a schema where
enrollment isn't a reliable single field (LARCO's is_health/is_crop/
is_credit_life only cover ~11% of respondents, derived from a claim-history
question, not enrollment) -- it must be omitted, not shown as mostly
unclassified.
Run: pytest tests/test_about_survey.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from analysis_engine.sections.about_survey import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame):
        self.df = df


def _base_df(**overrides) -> pd.DataFrame:
    n = overrides.pop("_n", 4)
    base = {
        "country": ["Kenya", "Kenya", "Ghana", "Ghana"],
        "is_health": [True, True, False, False],
        "is_crop": [False, False, True, False],
        "is_credit_life": [False, False, False, True],
        "q_client_age": pd.array([25, 40, 55, 30], dtype="Int16"),
        "q_sex": pd.Categorical(["Female", "Male", "Female", "Female"]),
        "interview_start": [
            "2026-01-01T08:00:00+00:00", "2026-01-15T08:00:00+00:00",
            "2026-02-01T08:00:00+00:00", "2026-02-15T08:00:00+00:00",
        ],
    }
    base.update(overrides)
    return pd.DataFrame(base)


class TestByCountry:
    def test_counts_and_percentages(self):
        result = calculate(_FakeDataset(_base_df()), {})
        by_country = {row["country"]: row for row in result["by_country"]}
        assert by_country["Kenya"]["n"] == 2
        assert by_country["Kenya"]["pct"] == pytest.approx(0.5)
        assert by_country["Ghana"]["n"] == 2

    def test_missing_column_returns_empty_list(self):
        df = _base_df().drop(columns=["country"])
        result = calculate(_FakeDataset(df), {})
        assert result["by_country"] == []


class TestProductMix:
    def test_high_coverage_schema_shows_product_mix(self):
        # All 4 rows classified (100% coverage) -- well above the threshold.
        result = calculate(_FakeDataset(_base_df()), {})
        pm = result["product_mix"]
        assert pm["available"] is True
        assert pm["coverage"] == pytest.approx(1.0)
        products = {row["product"]: row["n"] for row in pm["distribution"]}
        assert products["health"] == 2
        assert products["crop"] == 1
        assert products["credit_life"] == 1

    def test_larco_like_low_coverage_omits_product_mix(self):
        # Only 1 of 10 respondents classified (~11%, matching LARCO's real
        # coverage) -- must be omitted, not shown as 90% "unclassified".
        n = 10
        df = _base_df(
            _n=n,
            country=["Ecuador"] * n,
            is_health=[True] + [False] * (n - 1),
            is_crop=[False] * n,
            is_credit_life=[False] * n,
            q_client_age=pd.array([30] * n, dtype="Int16"),
            q_sex=pd.Categorical(["Female"] * n),
            interview_start=["2026-01-01T08:00:00+00:00"] * n,
        )
        result = calculate(_FakeDataset(df), {})
        pm = result["product_mix"]
        assert pm["available"] is False
        assert pm["distribution"] == []
        assert pm["coverage"] == pytest.approx(0.1)
        assert "not captured" in pm["reason"] or "unclassified" in pm["reason"]

    def test_missing_columns_marked_unavailable(self):
        df = _base_df().drop(columns=["is_health", "is_crop", "is_credit_life"])
        result = calculate(_FakeDataset(df), {})
        assert result["product_mix"]["available"] is False


class TestAgeSummary:
    def test_mean_median_min_max(self):
        result = calculate(_FakeDataset(_base_df()), {})
        age = result["age"]
        assert age["n_valid"] == 4
        assert age["mean"] == pytest.approx((25 + 40 + 55 + 30) / 4)
        assert age["min"] == 25
        assert age["max"] == 55

    def test_missing_column_degrades_gracefully(self):
        df = _base_df().drop(columns=["q_client_age"])
        result = calculate(_FakeDataset(df), {})
        assert result["age"]["n_valid"] == 0
        assert result["age"]["mean"] is None


class TestBySex:
    def test_counts_and_percentages(self):
        result = calculate(_FakeDataset(_base_df()), {})
        by_sex = {row["sex"]: row for row in result["by_sex"]}
        assert by_sex["Female"]["n"] == 3
        assert by_sex["Male"]["n"] == 1
        assert by_sex["Female"]["pct"] == pytest.approx(0.75)


class TestFieldworkWindow:
    def test_start_and_end_dates(self):
        result = calculate(_FakeDataset(_base_df()), {})
        fw = result["fieldwork"]
        assert fw["available"] is True
        assert fw["start_date"] == "2026-01-01"
        assert fw["end_date"] == "2026-02-15"

    def test_missing_column_marked_unavailable(self):
        df = _base_df().drop(columns=["interview_start"])
        result = calculate(_FakeDataset(df), {})
        assert result["fieldwork"]["available"] is False


class TestCalculateShape:
    def test_n_total_matches_dataframe_length(self):
        result = calculate(_FakeDataset(_base_df()), {})
        assert result["n_total"] == 4
