from qualitative_agent.agent import (
    _dedup_frequency,
    _highest_severity,
    _response_key,
    pick_diverse_verbatims as _pick_diverse_verbatims,
)
from qualitative_agent.data_prep import FreeTextResponse
from schemas.common import ThemeFinding, Verbatim


def _v(country: str, quote: str = "a real quote here") -> Verbatim:
    return Verbatim(quote=quote, country=country, source_field="test_field")


def _theme(keys: list, frequency: int = None) -> ThemeFinding:
    return ThemeFinding(theme="t", frequency=frequency if frequency is not None else len(keys), response_keys=keys)


def _response(client_id, source_field="f") -> FreeTextResponse:
    return FreeTextResponse(client_id=client_id, text="x", source_field=source_field, gender=None, age=None, branch=None, country=None, loan_cycle=None)


def test_pick_diverse_verbatims_prefers_distinct_countries():
    verbatims = [_v("ECU", "response number one"), _v("ECU", "response number two"), _v("RWA", "response number three"), _v("KEN", "response number four")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    countries = {v.country for v in picked}
    assert countries == {"ECU", "RWA", "KEN"}
    assert len(picked) == 3


def test_pick_diverse_verbatims_fills_remaining_slots_if_not_enough_countries():
    verbatims = [_v("ECU", "response number one"), _v("ECU", "response number two"), _v("RWA", "response number three")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert len(picked) == 3  # falls back to filling from remaining pool


def test_pick_diverse_verbatims_handles_fewer_than_k():
    verbatims = [_v("ECU", "response number one")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert len(picked) == 1


def test_pick_diverse_verbatims_empty_pool():
    assert _pick_diverse_verbatims([], k=3) == []


# CC-065: a minimum length for verbatim selection -- see _MIN_VERBATIM_SELECTION_LEN's own
# docstring in agent.py for the evidence behind the chosen floor (10 characters).

def test_pick_diverse_verbatims_excludes_the_real_da_incident():
    verbatims = [_v("MNE", "da"), _v("KEN", "a genuinely usable response")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert "da" not in [v.quote for v in picked]
    assert "a genuinely usable response" in [v.quote for v in picked]


def test_pick_diverse_verbatims_excludes_anything_below_the_floor_even_with_no_alternative():
    # No usable fallback either -- the pool must come back empty rather than citing noise
    # just because it's all that's available.
    verbatims = [_v("ECU", "B"), _v("KEN", "L"), _v("RWA", "sfs")]
    assert _pick_diverse_verbatims(verbatims, k=3) == []


def test_pick_diverse_verbatims_keeps_a_short_but_complete_real_sentiment():
    # "Interest is too high" (21 chars) is a real production verbatim -- above the chosen
    # floor (10) even though well below grounding.py's own _MIN_QUOTE_LEN (25).
    verbatims = [_v("KEN", "Interest is too high")]
    picked = _pick_diverse_verbatims(verbatims, k=3)
    assert picked == verbatims


def test_highest_severity_picks_the_worst():
    assert _highest_severity(["low", "high", "medium"]) == "high"
    assert _highest_severity(["low", None, "medium"]) == "medium"


def test_highest_severity_all_none_returns_none():
    assert _highest_severity([None, None]) is None


def test_highest_severity_empty_list_returns_none():
    assert _highest_severity([]) is None


def test_highest_severity_ignores_unrecognized_values():
    assert _highest_severity(["not_a_real_severity", "low"]) == "low"


def test_response_key_uses_client_id_when_present():
    assert _response_key(_response("c1"), fallback_local_index=5) == "client:c1"


def test_response_key_falls_back_to_a_collision_free_key_when_client_id_is_blank():
    a = _response_key(_response(None, source_field="fieldA"), fallback_local_index=3)
    b = _response_key(_response(None, source_field="fieldB"), fallback_local_index=3)
    assert a != b  # different source fields must not collide even at the same local index
    assert "client:" not in a  # never mistakable for a real client_id


def test_dedup_frequency_does_not_double_count_a_response_shared_by_two_merged_themes():
    # CC-037 regression: this is the exact incident -- one response tagged into two of a
    # batch's own themes (allowed by theme_tag_batch's own SYSTEM_PROMPT), both of which the
    # merge step decides belong to the same canonical theme. Summing frequency directly would
    # give 3 + 2 = 5 over a 4-response universe -- share_of_respondents > 1.0, the real bug.
    theme_a = _theme(["client:1", "client:2", "client:3"])  # frequency 3
    theme_b = _theme(["client:3", "client:4"])  # frequency 2, client:3 shared with theme_a
    frequency, keys = _dedup_frequency([theme_a, theme_b])
    assert frequency == 4  # union, not 3 + 2 = 5
    assert keys == ["client:1", "client:2", "client:3", "client:4"]


def test_dedup_frequency_matches_sum_when_themes_share_no_responses():
    theme_a = _theme(["client:1", "client:2"])
    theme_b = _theme(["client:3"])
    frequency, keys = _dedup_frequency([theme_a, theme_b])
    assert frequency == 3
    assert keys == ["client:1", "client:2", "client:3"]


def test_dedup_frequency_empty_input():
    assert _dedup_frequency([]) == (0, [])
