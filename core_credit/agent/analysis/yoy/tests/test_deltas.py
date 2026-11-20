"""CC-094: year-over-year changes, significance levels, NPS variance, the country-mix check."""

import pandas as pd
import pytest

from yoy import deltas as d
from yoy.waves import COUNTRY_COL

ANSWER = "q"
SPEC = d.MetricSpec("m", "Metric", "s", lambda df: df[ANSWER].map({"yes": True, "no": False}))


def _wave(counts):
    """counts: {country: (yes, no)} -> one row per answer."""
    rows = [(c, "yes") for c, (y, n) in counts.items() for _ in range(y)]
    rows += [(c, "no") for c, (y, n) in counts.items() for _ in range(n)]
    return pd.DataFrame(rows, columns=[COUNTRY_COL, ANSWER])


def _change(a, b, alpha=d.PORTFOLIO_ALPHA, min_n=1):
    ma, ea = d._answered(SPEC, a)
    mb, eb = d._answered(SPEC, b)
    return d.share_change(ma, ea, mb, eb, alpha, min_n)


def test_change_in_points_and_significance():
    c = _change(_wave({"KEN": (400, 600)}), _wave({"KEN": (500, 500)}))
    assert c.value_2025 == 0.4 and c.value_2026 == 0.5 and c.change_pts == pytest.approx(10.0)
    assert c.tested and c.significant and c.p_value < 0.001


def test_small_change_is_not_significant():
    c = _change(_wave({"KEN": (100, 170)}), _wave({"KEN": (108, 162)}))
    assert c.change_pts == pytest.approx(2.96, abs=0.01) and not c.significant


def test_the_stricter_level_can_reject_what_95_accepts():
    a, b = _wave({"KEN": (120, 150)}), _wave({"KEN": (145, 125)})  # p about 0.03
    assert _change(a, b, 0.05).significant and not _change(a, b, 0.01).significant


def test_cells_below_the_floor_are_reported_but_not_tested():
    c = _change(_wave({"KEN": (5, 5)}), _wave({"KEN": (9, 1)}), min_n=d.MIN_CELL_N)
    assert c.change_pts == pytest.approx(40.0) and not c.tested and not c.significant


def test_blank_answers_are_outside_the_base():
    a = pd.DataFrame({COUNTRY_COL: ["KEN"] * 4, ANSWER: ["yes", "no", None, None]})
    ma, ea = d._answered(SPEC, a)
    assert int(ea.sum()) == 2


def test_nps_change_and_its_variance():
    scores_a = pd.Series([10] * 50 + [8] * 30 + [3] * 20)  # NPS 30
    scores_b = pd.Series([10] * 60 + [8] * 30 + [3] * 10)  # NPS 50
    c = d.nps_change(scores_a, scores_b)
    assert c.value_2025 == pytest.approx(30) and c.value_2026 == pytest.approx(50) and c.change_pts == pytest.approx(20)
    # var per answer: 0.7 - 0.09 = 0.61 and 0.7 - 0.25 = 0.45; se = 100 * sqrt(0.0106) = 10.3
    assert c.p_value == pytest.approx(0.052, abs=0.003) and not c.significant


def test_nps_ignores_non_numeric_answers():
    c = d.nps_change(pd.Series(["10", "", "x", "3"]), pd.Series(["9", "9"]))
    assert c.n_2025 == 2 and c.value_2025 == pytest.approx(0)


def test_mix_flag_when_the_change_is_only_country_mix():
    # within each country nothing changes; 2026 just surveyed more of the high-scoring country
    a = _wave({"AAA": (80, 20), "BBB": (20, 80)})
    b = _wave({"AAA": (160, 40), "BBB": (10, 40)})
    raw = _change(a, b)
    assert raw.significant and raw.change_pts > 10
    mix = d._mix_check(SPEC, a, b, raw)
    assert mix["standardised_change_pts"] == pytest.approx(0, abs=1e-9) and mix["mix_flag"]


def test_no_mix_flag_when_the_change_holds_within_countries():
    a = _wave({"AAA": (50, 50), "BBB": (50, 50)})
    b = _wave({"AAA": (70, 30), "BBB": (70, 30)})
    raw = _change(a, b)
    mix = d._mix_check(SPEC, a, b, raw)
    assert mix["standardised_change_pts"] == pytest.approx(20) and not mix["mix_flag"]


def test_segment_changes_cover_every_value_with_the_given_level():
    a, b = _wave({"AAA": (50, 50), "BBB": (30, 70)}), _wave({"AAA": (70, 30), "BBB": (30, 70)})
    seg = lambda df: df[COUNTRY_COL]
    out = d._segment_changes(SPEC, a, b, seg, d.SUBGROUP_ALPHA)
    assert set(out) == {"AAA", "BBB"}
    assert out["AAA"]["alpha"] == 0.01 and out["AAA"]["significant"] and out["BBB"]["change_pts"] == pytest.approx(0)


def test_rows_outside_the_comparison_set_are_dropped():
    df = _wave({"KEN": (1, 1), "IND": (1, 1)})
    assert set(d._in_set(df, ["KEN"])[COUNTRY_COL]) == {"KEN"}


def test_metric_inventory_reuses_report_definitions():
    specs = d.metric_specs()
    ids = [s.metric_id for s in specs]
    assert len(ids) == len(set(ids))
    assert sum(s.headline for s in specs) == 15  # the gender scorecard's 15 rows
    assert {"first_time_access", "nps_promoter", "cut_food_to_repay", "savings_increased"} <= set(ids)
    assert next(s for s in specs if s.metric_id == "cut_food_to_repay").lower_is_better


def test_swing_screen_flags_moves_over_30_points_only():
    assert d._screen({"change_pts": 30.0, "tested": True})["swing_flag"] is False
    assert d._screen({"change_pts": -30.1, "tested": True})["swing_flag"] is True
    assert d._screen({"change_pts": None, "tested": False})["swing_flag"] is False
    assert d._screen({"change_pts": 100.0, "tested": False})["swing_flag"] is False  # too small to test


def test_swing_review_lists_metric_and_nps_cells_largest_first():
    cell = lambda ch, flag: {"value_2025": 0.5, "value_2026": 0.5, "change_pts": ch, "n_2025": 100, "n_2026": 100, "swing_flag": flag}
    metrics = [{"metric_id": "m", "label": "M", "by_country": {"KEN": cell(-40.0, True), "UGA": cell(10.0, False)}}]
    nps = {"by_country": {"ZMB": cell(55.0, True)}}
    rows = d.swing_review(metrics, nps)
    assert [(r["metric_id"], r["country"]) for r in rows] == [("nps_score", "ZMB"), ("m", "KEN")]
