"""CC-096: year-over-year FACT lines given to the writer."""

import json

import pytest

from writer import chain, yoy_facts
from writer.grounding import check_grounding, check_population_mismatch


def _cell(a, b, sig, **kw):
    return {"value_2025": a, "value_2026": b, "change_pts": (b - a) * 100, "significant": sig, "n_2025": 500, "n_2026": 500, **kw}


DELTAS = {
    "comparison_countries": ["KEN", "MLI"],
    "partial_countries": ["MLI"],
    "provisional": True,
    "metrics": [
        {"metric_id": "first_time_access", "label": "First-time access", "headline": True, "population": "all clients",
         "portfolio": _cell(0.436, 0.463, True, mix_flag=False),
         "by_gender": {"Female": _cell(0.40, 0.45, True), "Male": _cell(0.5, 0.51, False)}},
        {"metric_id": "alternative_lender_hard_to_find", "label": "Hard to find another lender", "headline": True, "population": "all clients",
         "portfolio": _cell(0.46, 0.39, True, mix_flag=True), "by_gender": {}},
    ],
    "nps_score": {"portfolio": {"value_2025": 69.9, "value_2026": 71.9, "change_pts": 2.0, "significant": False}},
}


@pytest.fixture
def active(tmp_path, monkeypatch):
    path = tmp_path / "d.json"
    path.write_text(json.dumps(DELTAS), encoding="utf-8")
    monkeypatch.setenv(yoy_facts.ENV, str(path))
    yoy_facts._load.cache_clear()
    yield
    yoy_facts._load.cache_clear()


def test_nothing_without_a_deltas_file(monkeypatch):
    monkeypatch.delenv(yoy_facts.ENV, raising=False)
    assert yoy_facts.facts_for("1.1") == ("", set())


def test_analysis_block_gets_portfolio_and_significant_gender_changes(active):
    text, accepted = yoy_facts.facts_for("1.1")
    assert "First-time access (all clients): 46.3% in 2026 compared with 43.6% in 2025, +2.7 points" in text
    assert "split by gender: Female): 45.0% in 2026" in text and "Male" not in text
    assert "Mali" in text and "provisional" in text and "Never give a reason" in text
    assert {46.3, 43.6, 2.7, 45.0, 40.0} <= accepted


def test_mix_flagged_change_is_listed_as_similar(active):
    text, _ = yoy_facts.facts_for("1.2")
    assert "YOY FACT" not in text and "Similar to 2025 (no significant change): Hard to find another lender" in text


def test_insight_gets_no_gender_lines(active):
    text, _ = yoy_facts.facts_for("1-insight")
    assert "First-time access (all clients)" in text and "split by gender" not in text


def test_executive_summary_gets_headline_metrics_and_nps(active):
    text, _ = yoy_facts.facts_for("executive-summary")
    assert "First-time access" in text and "Net Promoter Score" in text.split("Similar to 2025")[1]


def test_block_with_no_metrics_gets_nothing(active):
    assert yoy_facts.facts_for("2.1") == ("", set())


def test_yoy_figures_pass_grounding_and_the_population_check(active):
    summary, accepted = chain._with_yoy("1.1", "First-time access: overall 46.3% (n=5000)", {46.3})
    sentence = "Among women, 45.0% of clients surveyed in 2026 were first-time borrowers, compared with 40.0% in 2025."
    assert check_grounding(sentence, accepted) == []
    assert check_population_mismatch(sentence, summary) == []


def test_rules_ban_trend_verbs_and_joined_sentences():
    assert "rose, fell" in yoy_facts.RULES and "its own sentence" in yoy_facts.RULES


def test_trend_wording_in_a_yoy_sentence_drives_the_rewrite(active):
    bad = "Overall, 95.7% trust the mechanism, up from 93.9% in 2025."
    good = "Overall, 95.7% of clients surveyed in 2026 trust the mechanism, compared with 93.9% in 2025."
    assert yoy_facts.wording_violations(bad) == [bad]
    assert yoy_facts.wording_violations(good) == []
    assert yoy_facts.wording_violations('Savings rose for many. A client said "my sales fell in 2025".') == []
    assert any("trend wording" in v for v in chain._writer_violations(bad, 100, []))


def test_trend_check_is_off_without_a_deltas_file(monkeypatch):
    monkeypatch.delenv(yoy_facts.ENV, raising=False)
    assert yoy_facts.wording_violations("It rose from 40% in 2025.") == []


def test_closed_collection_drops_provisional_and_partial_wording(tmp_path, monkeypatch):
    path = tmp_path / "d.json"
    path.write_text(json.dumps({**DELTAS, "provisional": False}), encoding="utf-8")
    monkeypatch.setenv(yoy_facts.ENV, str(path))
    yoy_facts._load.cache_clear()
    text, _ = yoy_facts.facts_for("1.1")
    assert "provisional" not in text and "partial" not in text
    yoy_facts._load.cache_clear()


def test_up_from_and_down_from_are_rewritten_in_code():
    assert chain._clean_output("Business income improved for 93.5%, up from 92.0% in 2025.") == (
        "Business income improved for 93.5%, compared with 92.0% in 2025."
    )
    assert chain._clean_output("Wellbeing is 92.9%, down from 94.7% in 2025.").endswith("compared with 94.7% in 2025.")
