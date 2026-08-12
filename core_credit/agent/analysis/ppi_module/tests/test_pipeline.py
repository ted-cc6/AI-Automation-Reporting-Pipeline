import pytest

from ppi_module.pipeline import COUNTRY_COL, score_dataframe
from schemas.common import SectionStatus


def _subset(df, codes):
    mask = df[COUNTRY_COL].astype(str).str.strip().isin(codes)
    return df[mask]


def test_ecuador_matches_the_verified_email_figure(analysis_ready_df, scorecard_path, lookup_path):
    # Lorenz and Binjie independently hand-recomputed Ecuador at 3.8% on the $1.90/day
    # line (see the project email thread) after the dashboard showed a stale 1.2%/2.5%.
    # This is the strongest ground truth available for this pipeline.
    df = _subset(analysis_ready_df, ["ECU"])
    results = score_dataframe(df, scorecard_path, lookup_path)
    assert len(results) == 1
    ecu = results[0]

    assert ecu.status in (SectionStatus.OK, SectionStatus.PARTIAL)
    assert ecu.guide_id == "ECU2022"
    assert ecu.values["USD190day2011PPP"] == pytest.approx(3.8, abs=1.5)


def test_rwanda_matches_the_verified_email_figure(analysis_ready_df, scorecard_path, lookup_path):
    # Lorenz's manual recount: Rwanda averages 30.2% on the $1.90/day line once the
    # district-code padding mismatch is corrected. Our matching never depends on that
    # padding at all (see test_reference_data / test_scoring), so this should land close.
    df = _subset(analysis_ready_df, ["RWA"])
    results = score_dataframe(df, scorecard_path, lookup_path)
    rwa = results[0]

    assert rwa.status in (SectionStatus.OK, SectionStatus.PARTIAL)
    assert rwa.guide_id == "RWA2019"
    assert rwa.values["USD190day2011PPP"] == pytest.approx(30.2, abs=3.0)
    # every one of Rwanda's 30 districts must be reachable, not just districts 1-9
    assert rwa.n_scored > 250


def test_india_is_excluded_by_policy(analysis_ready_df, scorecard_path, lookup_path):
    df = _subset(analysis_ready_df, ["IND"])
    results = score_dataframe(df, scorecard_path, lookup_path)
    ind = results[0]
    assert ind.status == SectionStatus.NOT_AVAILABLE
    assert "policy" in ind.status_reason.lower()
    assert ind.n_total == len(df)


@pytest.mark.parametrize("country_code", ["KOS", "MLI", "MNE", "MNG"])
def test_na_countries_are_flagged_not_available(analysis_ready_df, scorecard_path, lookup_path, country_code):
    df = _subset(analysis_ready_df, [country_code])
    results = score_dataframe(df, scorecard_path, lookup_path)
    result = results[0]
    assert result.status == SectionStatus.NOT_AVAILABLE
    assert result.status_reason


def test_vietnam_scores_on_percentiles(analysis_ready_df, scorecard_path, lookup_path):
    df = _subset(analysis_ready_df, ["VNM"])
    results = score_dataframe(df, scorecard_path, lookup_path)
    vnm = results[0]

    assert vnm.metric_type == "percentile"
    assert vnm.status in (SectionStatus.OK, SectionStatus.PARTIAL)
    assert set(vnm.values.keys()) == {
        "Bottom20thPercentile",
        "Bottom40thPercentile",
        "Bottom60thPercentile",
        "Bottom80thPercentile",
    }
    assert all(0 <= v <= 100 for v in vnm.values.values() if v is not None)


def test_kenya_and_zambia_flag_the_scorecard_label_conflict(analysis_ready_df, scorecard_path, lookup_path):
    # Both countries have a genuine data-quality issue in the source scorecard (two options
    # sharing one label prefix) that suppresses some clients from being scored -- this should
    # come through as PARTIAL with a reason mentioning the affected question, not silently OK.
    df = _subset(analysis_ready_df, ["KEN", "ZMB"])
    results = {r.country_code: r for r in score_dataframe(df, scorecard_path, lookup_path)}

    for code in ("KEN", "ZMB"):
        result = results[code]
        assert result.status == SectionStatus.PARTIAL
        assert "conflicting option labels" in result.status_reason


def test_dominican_republic_and_mexico_only_report_lines_they_have(analysis_ready_df, scorecard_path, lookup_path):
    df = _subset(analysis_ready_df, ["DOM", "MEX"])
    results = {r.country_code: r for r in score_dataframe(df, scorecard_path, lookup_path)}

    for code in ("DOM", "MEX"):
        result = results[code]
        assert "USD190day2011PPP" not in result.values
        assert "USD215day2017PPP" not in result.values
        assert "USD320day2011PPP" not in result.values
