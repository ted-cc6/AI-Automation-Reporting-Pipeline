import pytest

from ppi_module.aggregate import aggregate_poverty_line_shares, country_to_region_map
from ppi_module.pipeline import COUNTRY_COL, score_dataframe
from schemas.common import SegmentAxis
from schemas.poverty_likelihood import CountryPovertyResult, SectionStatus

REGION_COL = "Introduction/Which region do you work in?"


def _result(country_code: str, values: dict, n_scored: int, status=SectionStatus.OK) -> CountryPovertyResult:
    return CountryPovertyResult(country_code=country_code, status=status, values=values, n_scored=n_scored, n_total=n_scored)


# --- country_to_region_map: real-data check --------------------------------------------


def test_country_to_region_map_matches_every_country_in_the_real_csv(analysis_ready_df):
    mapping = country_to_region_map(analysis_ready_df, COUNTRY_COL, REGION_COL)
    real_countries = set(analysis_ready_df[COUNTRY_COL].astype(str).str.strip()) - {""}
    assert real_countries.issubset(mapping.keys())
    assert mapping["ECU"] == "LACRO"
    assert mapping["GHA"] == "Africa"
    assert mapping["VNM"] == "Asia"


# --- aggregate_poverty_line_shares: synthetic, deterministic checks --------------------


def test_weights_the_overall_figure_by_each_countrys_n_scored():
    results = [
        _result("AAA", {"USD190day2011PPP": 10.0}, n_scored=100),
        _result("BBB", {"USD190day2011PPP": 30.0}, n_scored=300),
    ]
    metrics = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={})
    assert len(metrics) == 1
    m = metrics[0]
    assert m.metric_id == "poverty_likelihood_USD190day2011PPP"
    # (10*100 + 30*300) / 400 = 25.0 -> as a 0-1 share, 0.25
    assert m.overall.share == pytest.approx(0.25)
    assert m.overall.n == 400


def test_only_emits_lines_that_at_least_one_country_reports():
    results = [_result("AAA", {"USD190day2011PPP": 10.0}, n_scored=100)]
    metrics = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={})
    ids = {m.metric_id for m in metrics}
    assert ids == {"poverty_likelihood_USD190day2011PPP"}


def test_countries_missing_a_line_are_absent_from_its_by_segment_not_zero():
    results = [
        _result("AAA", {"USD190day2011PPP": 10.0}, n_scored=100),
        _result("BBB", {}, n_scored=50),  # e.g. NOT_AVAILABLE or no populated column for this line
    ]
    metrics = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={})
    m = metrics[0]
    country_labels = {seg.value_label for seg in m.by_segment if seg.axis == SegmentAxis.COUNTRY}
    assert country_labels == {"AAA"}


def test_uses_country_name_map_and_falls_back_to_code(analysis_ready_df):
    results = [_result("GHA", {"USD190day2011PPP": 8.0}, n_scored=50)]
    metrics = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={"GHA": "Ghana"})
    country_seg = next(seg for seg in metrics[0].by_segment if seg.axis == SegmentAxis.COUNTRY)
    assert country_seg.value_label == "Ghana"

    metrics_no_name_map = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={})
    country_seg = next(seg for seg in metrics_no_name_map[0].by_segment if seg.axis == SegmentAxis.COUNTRY)
    assert country_seg.value_label == "GHA"


def test_region_rows_are_weighted_across_their_member_countries():
    results = [
        _result("AAA", {"USD190day2011PPP": 10.0}, n_scored=100),
        _result("BBB", {"USD190day2011PPP": 30.0}, n_scored=100),
    ]
    metrics = aggregate_poverty_line_shares(
        results, country_to_region={"AAA": "RegionX", "BBB": "RegionX"}, country_to_name={}
    )
    region_seg = next(seg for seg in metrics[0].by_segment if seg.axis == SegmentAxis.REGION)
    assert region_seg.value_label == "RegionX"
    assert region_seg.share == pytest.approx(0.20)  # (10+30)/2 = 20.0 -> 0.20
    assert region_seg.n == 200


def test_no_benchmark_is_set_and_a_note_explains_why():
    results = [_result("AAA", {"USD190day2011PPP": 10.0}, n_scored=100)]
    metrics = aggregate_poverty_line_shares(results, country_to_region={}, country_to_name={})
    assert metrics[0].benchmark is None
    assert "no external mfi index benchmark" in metrics[0].notes.lower()


# --- real end-to-end sanity check, using the actual PPI pipeline output ----------------


def test_real_dataframe_produces_all_three_target_lines(analysis_ready_df, scorecard_path, lookup_path):
    country_results = score_dataframe(analysis_ready_df, scorecard_path, lookup_path)
    country_to_region = country_to_region_map(analysis_ready_df, COUNTRY_COL, REGION_COL)
    metrics = aggregate_poverty_line_shares(country_results, country_to_region, country_to_name={})

    ids = {m.metric_id for m in metrics}
    assert ids == {
        "poverty_likelihood_USD190day2011PPP",
        "poverty_likelihood_USD215day2017PPP",
        "poverty_likelihood_USD320day2011PPP",
    }
    for m in metrics:
        assert 0 <= m.overall.share <= 1
        assert m.overall.n > 0
        assert any(seg.axis == SegmentAxis.REGION for seg in m.by_segment)
