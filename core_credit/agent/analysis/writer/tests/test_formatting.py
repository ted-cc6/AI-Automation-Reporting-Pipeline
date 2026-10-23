from schemas.client_satisfaction import NPSResult
from schemas.common import BenchmarkComparison, MetricResult, RankedOption, RankedOptions, SegmentAxis, SegmentedValue
from schemas.poverty_likelihood import CountryVsNationalRate
from writer.formatting import format_metric_result, format_national_comparison, format_nps_result, format_ranked_options


def test_format_metric_result_includes_overall_and_segments():
    mr = MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.42, n=500),
        by_segment=[SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", share=0.50, n=300)],
    )
    text = format_metric_result(mr)
    assert "42.0%" in text
    assert "Female" in text
    assert "50.0%" in text


def test_format_metric_result_includes_benchmark_caveat():
    mr = MetricResult(
        metric_id="nps",
        label="NPS-adjacent metric",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.5, n=10),
        benchmark=BenchmarkComparison(external_mfi_index=0.4, external_mfi_index_year=2025, external_mfi_index_caveat="test caveat"),
    )
    text = format_metric_result(mr)
    assert "test caveat" in text


def test_format_metric_result_includes_benchmark_comparable_value_and_definition():
    mr = MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.915, n=5818),
        benchmark=BenchmarkComparison(
            external_mfi_index=0.23,
            external_mfi_index_year=2025,
            external_mfi_index_definition="% of Clients that say their business earnings have very much increased",
        ),
        benchmark_comparable_value=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.48, n=5818),
    )
    text = format_metric_result(mr)
    assert "91.5%" in text  # the overall top-2-box figure is still shown
    assert "23.0%" in text  # the benchmark itself
    assert "48.0%" in text  # the correctly-paired comparison figure
    assert "very much increased" in text  # verbatim source definition, so the writer sees the box type
    assert "SAME basis as that benchmark" in text


def test_format_metric_result_shows_comparable_value_without_a_benchmark():
    # CC-031 regression: benchmark_comparable_value is computed from our own survey data, not
    # from the benchmark workbook, so it must still be reported when no external benchmark
    # loaded this run -- previously it was nested inside `if benchmark exists`, so a degraded
    # (no-benchmark) run silently dropped it from the writer's data entirely.
    mr = MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.915, n=5818),
        benchmark=None,
        benchmark_comparable_value=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.48, n=5818),
    )
    text = format_metric_result(mr)
    assert "91.5%" in text
    assert "48.0%" in text
    assert "MFI Index benchmark:" not in text  # no benchmark data line -- none loaded
    assert "SAME basis as that benchmark" not in text  # must not claim a comparison that doesn't exist
    assert "stricter box definition" in text  # reported as our own standalone figure instead


def test_format_national_comparison_uses_percentage_points_not_fraction_scale():
    # portfolio_poverty_likelihood/national_poverty_rate are already percentage points
    # (21.6 means 21.6%), unlike SegmentedValue.share -- this must NOT go through ':.1%'
    # (which would read 21.6 as 2160%).
    rows = [
        CountryVsNationalRate(
            country_code="RWA", portfolio_poverty_likelihood=30.2, national_poverty_rate=38.2, poorer_than_national=False
        ),
        CountryVsNationalRate(
            country_code="ECU", portfolio_poverty_likelihood=3.8, national_poverty_rate=1.9, poorer_than_national=True
        ),
    ]
    text = format_national_comparison(rows)
    assert "30.2%" in text
    assert "2160" not in text  # would appear if ':.1%' were used by mistake
    assert "poverty likelihood is HIGHER than the national rate" in text
    assert "poverty likelihood is LOWER than the national rate" in text
    assert "targeting" not in text  # CC-081: the payload must not hand the writer "targeting"


def test_format_metric_result_labels_every_line_with_its_population():
    # CC-071 / HO52: a caregiver split of an all-client metric must say it covers all clients.
    mr = MetricResult(
        metric_id="household_influence_improved", label="Household influence improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.835, n=5818),
        by_segment=[
            SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", share=0.842, n=3825),
            SegmentedValue(axis=SegmentAxis.CAREGIVER, value_label="Caregiver", share=0.862, n=4851),
        ],
    )
    lines = format_metric_result(mr).splitlines()
    assert lines[1] == "  - Population: all clients"
    assert lines[2] == "  - all clients, split by gender: Female: 84.2% (n=3825)"
    assert lines[3] == "  - all clients, split by caregiver status: Caregiver: 86.2% (n=4851)"


def test_format_metric_result_shows_a_restricted_population():
    mr = MetricResult(
        metric_id="improved_child_wellbeing", label="Caregivers reporting improved child wellbeing",
        population="caregivers only",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.935, n=4851),
        by_segment=[SegmentedValue(axis=SegmentAxis.GENDER, value_label="Male", share=0.938, n=1000)],
    )
    text = format_metric_result(mr)
    assert "  - Population: caregivers only" in text
    assert "  - caregivers only, split by gender: Male: 93.8% (n=1000)" in text


def test_format_national_comparison_handles_missing_national_rate():
    rows = [CountryVsNationalRate(country_code="XYZ", portfolio_poverty_likelihood=12.0, poorer_than_national=None)]
    text = format_national_comparison(rows)
    assert "12.0%" in text
    assert "no national rate on file" in text


def test_format_ranked_options_lists_every_option_with_share_and_n():
    options = RankedOptions(
        base_n=100,
        options=[RankedOption(label="Female", share=0.6, n=60), RankedOption(label="Male", share=0.4, n=40)],
    )
    text = format_ranked_options("Gender split", options)
    assert "base n=100" in text
    assert "Female: 60.0% (n=60)" in text
    assert "Male: 40.0% (n=40)" in text


def test_format_nps_result():
    nps = NPSResult(score=58.0, promoter_share=0.6, passive_share=0.2, detractor_share=0.2, n=100)
    text = format_nps_result(nps)
    assert "58" in text
    assert "60.0%" in text
