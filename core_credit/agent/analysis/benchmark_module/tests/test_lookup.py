import pytest

from benchmark_module.lookup import build_national_comparison, get_mfi_index_benchmark, get_national_poverty_rate
from schemas.common import SectionStatus
from schemas.poverty_likelihood import CountryPovertyResult


def test_global_only_when_no_country_or_region_given(benchmarks_path):
    result = get_mfi_index_benchmark("first_time_access", benchmarks_path)
    assert result.external_mfi_index == pytest.approx(0.57)
    assert result.external_mfi_index_year == 2025
    assert result.not_available_reason is None


def test_country_level_preferred_over_region_and_global(benchmarks_path):
    result = get_mfi_index_benchmark("first_time_access", benchmarks_path, country="GHA", region="Africa")
    assert result.external_mfi_index == pytest.approx(0.66)
    assert result.external_mfi_index_year == 2024


def test_region_used_when_country_has_no_peer_value(benchmarks_path):
    # Rwanda has no country-level column in the sheet at all -- should fall back to its region.
    result = get_mfi_index_benchmark("first_time_access", benchmarks_path, country="RWA", region="Africa")
    assert result.external_mfi_index == pytest.approx(0.66)  # Africa regional value
    assert result.external_mfi_index_year == 2025


def test_meer_region_falls_back_to_global(benchmarks_path):
    # No MEER column exists in the sheet at all -- OUR_REGION_TO_SHEET_REGION maps it to None.
    result = get_mfi_index_benchmark("first_time_access", benchmarks_path, region="MEER")
    assert result.external_mfi_index == pytest.approx(0.57)  # global


def test_nps_is_scaled_by_100_and_has_no_caveat_scale_is_confirmed(benchmarks_path):
    # Confirmed by Lorenz (2026-08-05 email): 0.58 in the sheet means NPS 58, not "58% promoters".
    result = get_mfi_index_benchmark("nps", benchmarks_path)
    assert result.external_mfi_index == pytest.approx(58.0)
    assert result.external_mfi_index_caveat is None


def test_loan_terms_clear_has_no_caveat_box_type_is_confirmed(benchmarks_path):
    # Confirmed by Lorenz (2026-08-05 email): compares against "strongly agree" only.
    result = get_mfi_index_benchmark("loan_terms_clear", benchmarks_path)
    assert result.external_mfi_index is not None
    assert result.external_mfi_index_caveat is None


def test_reduced_food_intake_has_no_caveat_direction_is_confirmed(benchmarks_path):
    result = get_mfi_index_benchmark("did_not_reduce_food", benchmarks_path)
    assert result.external_mfi_index is not None
    assert result.external_mfi_index_caveat is None


def test_child_wellbeing_is_deliberately_excluded_despite_having_a_value(benchmarks_path):
    result = get_mfi_index_benchmark("improved_child_wellbeing", benchmarks_path)
    assert result.external_mfi_index is None
    assert "not comparable" in result.not_available_reason.lower() or "isn't comparable" in result.not_available_reason.lower()


def test_household_influence_is_deliberately_excluded(benchmarks_path):
    result = get_mfi_index_benchmark("household_influence_improved", benchmarks_path)
    assert result.external_mfi_index is None
    assert result.not_available_reason is not None


def test_complaints_mechanism_is_not_available_but_not_a_policy_exclusion(benchmarks_path):
    # Distinguish "we chose to exclude this" from "the data just isn't there this wave":
    # complaints mechanism isn't on the template's exclusion list, it's just blank in the sheet.
    result = get_mfi_index_benchmark("complaints_mechanism_trusted", benchmarks_path)
    assert result.external_mfi_index is None
    assert "no 60 decibels value found" in result.not_available_reason.lower()


def test_unmapped_metric_id_returns_not_available(benchmarks_path):
    result = get_mfi_index_benchmark("some_metric_with_no_60db_indicator", benchmarks_path)
    assert result.external_mfi_index is None
    assert result.not_available_reason is not None


def test_get_national_poverty_rate_kenya(benchmarks_path):
    result = get_national_poverty_rate("KEN", "USD190day2011PPP", benchmarks_path)
    assert result is not None
    assert result.rate == pytest.approx(33.63, abs=0.01)
    assert result.source == "IPA"
    assert result.year == 2020


def test_get_national_poverty_rate_missing_country_returns_none(benchmarks_path):
    assert get_national_poverty_rate("KOS", "USD190day2011PPP", benchmarks_path) is None


def test_build_national_comparison_uses_first_available_line_and_flags_targeting(benchmarks_path):
    # Mirrors the real Ghana PPI result: scored OK on USD190day2011PPP=8.3, USD320day2011PPP=24.6.
    # Ghana's national USD190 rate is ~21.37 -- so VisionFund's Ghana clients are LESS poor than
    # the national average on this measure, i.e. not poorer-than-national.
    ghana = CountryPovertyResult(
        country_code="GHA",
        status=SectionStatus.OK,
        values={"USD190day2011PPP": 8.3, "USD320day2011PPP": 24.6},
        n_scored=288,
        n_total=288,
    )
    excluded = CountryPovertyResult(country_code="IND", status=SectionStatus.NOT_AVAILABLE, n_total=285)

    comparisons = build_national_comparison([ghana, excluded], benchmarks_path)

    assert len(comparisons) == 1
    result = comparisons[0]
    assert result.country_code == "GHA"
    assert result.portfolio_poverty_likelihood == pytest.approx(8.3)
    assert result.national_poverty_rate == pytest.approx(21.37, abs=0.01)
    assert result.poorer_than_national is False
