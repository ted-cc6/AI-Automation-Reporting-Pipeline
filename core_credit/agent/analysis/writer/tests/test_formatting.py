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
    assert "POORER than the national rate" in text
    assert "LESS poor than the national rate" in text


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
