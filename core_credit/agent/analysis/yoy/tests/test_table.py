"""CC-097: the year-over-year table, built in code."""

from yoy.table import build_yoy_section


def _c(a, b, sig, **kw):
    return {"value_2025": a, "value_2026": b, "change_pts": (b - a) * 100, "significant": sig, **kw}


def _metric(mid, sig, mix=False, gender=None, cycle=None, country=None, lower=False):
    return {
        "metric_id": mid, "label": mid.title(), "headline": True, "lower_is_better": lower, "population": "all clients",
        "portfolio": _c(0.4, 0.5 if sig else 0.41, sig, mix_flag=mix),
        "by_gender": gender or {}, "by_loan_cycle": cycle or {}, "by_country": country or {},
    }


DELTAS = {
    "waves": {"comparison": 2025, "report": 2026},
    "comparison_countries": ["KEN", "MNE"],
    "partial_countries": ["MLI"],
    "provisional": True,
    "metrics": [
        _metric("access", True, gender={"Female": _c(0.4, 0.5, True), "Male": _c(0.4, 0.41, False)},
                cycle={"Loan cycle 4": _c(0.3, 0.45, True)},
                country={"KEN": _c(0.4, 0.5, True, swing_flag=False), "MNE": _c(0.1, 0.6, True, swing_flag=True)}),
        _metric("respect", True, mix=True),
        _metric("food", False, lower=True),
        {**_metric("partial", True), "headline": False},
    ],
    "nps_score": {"portfolio": {"value_2025": 69.9, "value_2026": 71.9, "change_pts": 2.0, "significant": False},
                  "by_country": {"KEN": {"value_2025": 20.0, "value_2026": 60.0, "change_pts": 40.0, "significant": True, "swing_flag": True}}},
    "swing_review": [
        {"metric_id": "access", "label": "Access", "country": "MNE", "value_2025": 0.1, "value_2026": 0.6, "change_pts": 50.0},
        {"metric_id": "nps_score", "label": "Net Promoter Score", "country": "KEN", "value_2025": 20.0, "value_2026": 60.0, "change_pts": 40.0},
    ],
}
MANIFEST = {"excluded_countries": {"IND": "no rows in 2026"}}


def test_headline_rows_show_every_headline_metric_and_nps():
    s = build_yoy_section(DELTAS, MANIFEST)
    assert [r.label for r in s.headline_rows] == ["Access", "Respect", "Food", "Net Promoter Score"]
    access, respect, food, nps = s.headline_rows
    assert access.significant and not food.significant and food.note == "lower is better"
    assert not respect.significant and respect.note == "change reflects country mix"
    assert nps.is_score and not nps.significant


def test_appendix_rows_keep_only_significant_unflagged_changes():
    s = build_yoy_section(DELTAS, MANIFEST)
    assert [(r.label, r.group) for r in s.gender_rows] == [("Access", "women (all clients)")]
    assert [r.group for r in s.loan_cycle_rows] == ["Loan cycle 4 (all clients)"]
    assert [r.group for r in s.country_rows] == ["Kenya"]  # Montenegro and Kenya NPS are swing-flagged
    assert [(r.group, r.is_score) for r in s.review_rows] == [("Montenegro", False), ("Kenya", True)]


def test_note_names_the_set_the_exclusions_and_the_provisional_state():
    s = build_yoy_section(DELTAS, MANIFEST)
    assert s.comparison_countries == ["Kenya", "Montenegro"] and s.excluded_countries == {"India": "no rows in 2026"}
    assert "2 countries surveyed in both years" in s.note and "India (no rows in 2026)" in s.note
    assert "Mali is still being surveyed" in s.note and "provisional" in s.note
    assert "not the same clients" in s.note and "not why" in s.note
