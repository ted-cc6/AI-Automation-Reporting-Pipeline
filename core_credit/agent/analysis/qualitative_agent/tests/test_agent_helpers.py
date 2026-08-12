from qualitative_agent.agent import _highest_severity, pick_diverse_verbatims as _pick_diverse_verbatims
from schemas.common import Verbatim


def _v(country: str, quote: str = "quote") -> Verbatim:
    return Verbatim(quote=quote, country=country, source_field="test_field")


def test_pick_diverse_verbatims_prefers_distinct_countries():
    verbatims = [_v("ECU", "a"), _v("ECU", "b"), _v("RWA", "c"), _v("KEN", "d")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    countries = {v.country for v in picked}
    assert countries == {"ECU", "RWA", "KEN"}
    assert len(picked) == 3


def test_pick_diverse_verbatims_fills_remaining_slots_if_not_enough_countries():
    verbatims = [_v("ECU", "a"), _v("ECU", "b"), _v("RWA", "c")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert len(picked) == 3  # falls back to filling from remaining pool


def test_pick_diverse_verbatims_handles_fewer_than_k():
    verbatims = [_v("ECU", "a")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert len(picked) == 1


def test_pick_diverse_verbatims_empty_pool():
    assert _pick_diverse_verbatims([], k=3) == []


def test_highest_severity_picks_the_worst():
    assert _highest_severity(["low", "high", "medium"]) == "high"
    assert _highest_severity(["low", None, "medium"]) == "medium"


def test_highest_severity_all_none_returns_none():
    assert _highest_severity([None, None]) is None


def test_highest_severity_empty_list_returns_none():
    assert _highest_severity([]) is None


def test_highest_severity_ignores_unrecognized_values():
    assert _highest_severity(["not_a_real_severity", "low"]) == "low"
