import pytest

from ppi_module.pipeline import COUNTRY_COL, score_dataframe, unscored_reason
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


@pytest.mark.filterwarnings("ignore::ppi_module.scoring.ScorecardLabelWarning")
def test_kenya_and_zambia_score_every_client(analysis_ready_df, scorecard_path, lookup_path):
    # CC-068: every Kenya and Zambia client answered all ten questions; before the fix 181 and
    # 249 of them were dropped over mislabeled scorecard options and reported as "incomplete".
    df = _subset(analysis_ready_df, ["KEN", "ZMB"])
    results = {r.country_code: r for r in score_dataframe(df, scorecard_path, lookup_path)}

    for code in ("KEN", "ZMB"):
        result = results[code]
        assert result.status == SectionStatus.OK
        assert result.n_scored == result.n_total
        assert result.status_reason is None
        assert result.unscored_reasons == {}


def test_partial_country_states_the_real_per_client_reason(analysis_ready_df, scorecard_path, lookup_path):
    # CC-069: Myanmar's three unscored clients left question 1 blank -- the reason must say so,
    # computed from the data, and the counts must sum to the unscored total.
    df = _subset(analysis_ready_df, ["MMR"])
    mmr = score_dataframe(df, scorecard_path, lookup_path)[0]
    assert mmr.status == SectionStatus.PARTIAL
    assert sum(mmr.unscored_reasons.values()) == mmr.n_total - mmr.n_scored
    assert mmr.unscored_reasons == {"left PPI question 1 unanswered": 3}
    assert mmr.status_reason == f"3 of {mmr.n_total} clients could not be scored: 3 left PPI question 1 unanswered."
    assert "incomplete" not in mmr.status_reason


def test_unscored_reason_classifies_each_failure():
    index = {(1, "A"): {"L": 10}, (2, "A"): {"L": 20}}
    lookup = {30: {"L": 12.5}}
    assert unscored_reason({1: "A", 2: "A"}, index, lookup, "L", [1, 2]) is None
    assert unscored_reason({1: "A"}, index, lookup, "L", [1, 2]) == "left PPI question 2 unanswered"
    assert unscored_reason({1: "A", 2: "Z"}, index, lookup, "L", [1, 2]) == "gave an answer on PPI question 2 that is not on the scorecard"
    assert unscored_reason({1: "A", 2: "Z"}, index, lookup, "L", [1, 2], ambiguous={(2, "Z")}) == (
        "chose an option on PPI question 2 that two scorecard options share"
    )
    assert unscored_reason({1: "A", 2: "A"}, index, {}, "L", [1, 2]) == "had a score with no matching row in the PPI lookup table"


def test_dominican_republic_and_mexico_only_report_lines_they_have(analysis_ready_df, scorecard_path, lookup_path):
    df = _subset(analysis_ready_df, ["DOM", "MEX"])
    results = {r.country_code: r for r in score_dataframe(df, scorecard_path, lookup_path)}

    for code in ("DOM", "MEX"):
        result = results[code]
        assert "USD190day2011PPP" not in result.values
        assert "USD215day2017PPP" not in result.values
        assert "USD320day2011PPP" not in result.values
