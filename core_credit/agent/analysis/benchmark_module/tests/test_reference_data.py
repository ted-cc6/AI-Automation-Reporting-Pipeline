import pytest

from benchmark_module.reference_data import load_mfi_index_sheet, load_national_poverty_rates


def _row(rows, indicator_name):
    return next(r for r in rows if r.indicator_name == indicator_name)


def test_first_access_row_parses_every_level(benchmarks_path):
    rows = load_mfi_index_sheet(benchmarks_path)
    row = _row(rows, "First Access")

    assert row.global_value == pytest.approx(0.57)
    assert row.global_year == 2025

    assert row.regional_values["Africa"] == (pytest.approx(0.66), 2025)
    assert row.regional_values["Asia"] == (pytest.approx(0.52), 2025)
    assert row.regional_values["LAC"] == (pytest.approx(0.52), 2025)

    assert row.country_values["Ghana"] == (pytest.approx(0.66), 2024)
    assert row.country_values["Kenya"] == (pytest.approx(0.69), 2024)
    assert row.country_values["Tanzania"] == (pytest.approx(0.74), 2024)
    assert row.country_values["India"] == (pytest.approx(0.49), 2025)  # India's column is the 2025-labeled one
    assert row.country_values["Ecuador"] == (pytest.approx(0.49), 2024)
    assert row.country_values["Mexico"] == (pytest.approx(0.44), 2024)


def test_nps_row_parses(benchmarks_path):
    rows = load_mfi_index_sheet(benchmarks_path)
    row = _row(rows, "NPS")
    assert row.global_value == pytest.approx(0.58)
    assert row.country_values["Philippines"] == (pytest.approx(0.86), 2024)


def test_blank_indicator_has_no_values_anywhere(benchmarks_path):
    rows = load_mfi_index_sheet(benchmarks_path)
    row = _row(rows, "Complaints Handling Mechanism")
    assert row.global_value is None
    assert row.regional_values == {}
    assert row.country_values == {}


def test_child_wellbeing_has_global_value_but_a_comment_flagging_it(benchmarks_path):
    rows = load_mfi_index_sheet(benchmarks_path)
    row = _row(rows, "Children's Wellbeing")
    assert row.global_value == pytest.approx(0.34)
    assert row.regional_values == {}
    assert "cannot be compared" in row.comment.lower()


def test_dimension_column_is_forward_filled(benchmarks_path):
    rows = load_mfi_index_sheet(benchmarks_path)
    # "Access to Alternatives" has no Dimension of its own in the sheet -- it should inherit
    # "Access" from the "First Access" row above it, the same way a merged cell reads visually.
    row = _row(rows, "Access to Alternatives")
    assert row.dimension is not None
    assert "access" in row.dimension.lower()


def test_national_poverty_rate_kenya(benchmarks_path):
    rows = load_national_poverty_rates(benchmarks_path)
    kenya = next(r for r in rows if r.country_name == "Kenya")
    assert kenya.source == "IPA"
    assert kenya.year == 2020
    # sheet has 0.3363 as a fraction -- converted to percentage points on load
    assert kenya.rates["USD190day2011PPP"] == pytest.approx(33.63, abs=0.01)


def test_national_poverty_rate_mali_has_no_values(benchmarks_path):
    rows = load_national_poverty_rates(benchmarks_path)
    mali = next(r for r in rows if r.country_name == "Mali")
    assert all(v is None for v in mali.rates.values())


def test_national_poverty_rate_region_forward_filled(benchmarks_path):
    rows = load_national_poverty_rates(benchmarks_path)
    # Kenya has no Region of its own in the sheet (it's under Ghana's "Africa" block)
    kenya = next(r for r in rows if r.country_name == "Kenya")
    assert kenya.region == "Africa"
