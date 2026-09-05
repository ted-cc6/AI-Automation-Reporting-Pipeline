from typing import Optional
from unittest.mock import patch

from pydantic import BaseModel, Field

from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim
from synthesis.build_gender_scorecard import VERBATIM_SOURCE_SECTIONS, _verbatim_pool


def _verbatim(quote: str, client_id: str) -> Verbatim:
    return Verbatim(quote=quote, client_id=client_id, country="KEN", source_field="test_field")


def _qs(themes: list) -> QualitativeSynthesis:
    return QualitativeSynthesis(source_field="test", base_n=100, themes=themes)


class _FakeBH(BaseModel):
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
    qol_drivers: Optional[QualitativeSynthesis] = None


class _FakeResilience(BaseModel):
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
    other_coping_qualitative: Optional[QualitativeSynthesis] = None


class _FakeChildWellbeing(BaseModel):
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
    other_improvements_qualitative: Optional[QualitativeSynthesis] = None


class _FakeClientSatisfaction(BaseModel):
    insight_verbatims: list[Verbatim] = Field(default_factory=list)
    nps_followup_themes: list[QualitativeSynthesis] = Field(default_factory=list)


def _fake_sections(
    bh_insight=None, bh_pool=None,
    resilience_insight=None, resilience_pool=None,
    cw_insight=None, cw_pool=None,
    cs_insight=None, cs_pool=None,
):
    return {
        "business_household_impact": _FakeBH(
            insight_verbatims=bh_insight or [],
            qol_drivers=_qs([ThemeFinding(theme="t", frequency=len(bh_pool or []), representative_verbatims=bh_pool or [])]),
        ),
        "resilience": _FakeResilience(
            insight_verbatims=resilience_insight or [],
            other_coping_qualitative=_qs([ThemeFinding(theme="t", frequency=len(resilience_pool or []), representative_verbatims=resilience_pool or [])]),
        ),
        "child_wellbeing": _FakeChildWellbeing(
            insight_verbatims=cw_insight or [],
            other_improvements_qualitative=_qs([ThemeFinding(theme="t", frequency=len(cw_pool or []), representative_verbatims=cw_pool or [])]),
        ),
        "client_satisfaction": _FakeClientSatisfaction(
            insight_verbatims=cs_insight or [],
            nps_followup_themes=[_qs([ThemeFinding(theme="t", frequency=len(cs_pool or []), representative_verbatims=cs_pool or [])])],
        ),
    }


def test_verbatim_source_sections_unchanged():
    assert VERBATIM_SOURCE_SECTIONS == ["business_household_impact", "resilience", "child_wellbeing", "client_satisfaction"]


def test_pool_prefers_candidates_not_already_cited_by_their_own_source_section():
    # CC-058 regression: business_household_impact's own insight already spotlighted "already
    # used" -- the pool must not offer that one when a real, unused alternative exists.
    already_used = _verbatim("Already used by its own section", "BH_1")
    unused = _verbatim("Never cited anywhere yet", "BH_2")
    sections = _fake_sections(bh_insight=[already_used], bh_pool=[already_used, unused])
    pool = _verbatim_pool(sections=sections)
    quotes = {v.quote for v in pool.themes[0].representative_verbatims}
    assert "Never cited anywhere yet" in quotes
    assert "Already used by its own section" not in quotes


def test_pool_draws_from_the_deeper_qualitative_pool_not_just_insight_verbatims():
    # The old pool was ONLY each source's insight_verbatims (1-3 items each, always already
    # cited by construction) -- confirm the new pool reaches into the fuller candidate set.
    only_already_cited = _verbatim("The only thing this section ever cited", "CW_1")
    deeper_candidate = _verbatim("A different real response from the same theme pass", "CW_2")
    sections = _fake_sections(cw_insight=[only_already_cited], cw_pool=[only_already_cited, deeper_candidate])
    pool = _verbatim_pool(sections=sections)
    quotes = {v.quote for v in pool.themes[0].representative_verbatims}
    assert "A different real response from the same theme pass" in quotes


def test_pool_falls_back_to_reuse_only_when_the_unused_pool_is_completely_empty():
    # CC-058: "falling back to reuse only when the pool is exhausted" -- if the ENTIRE deeper
    # pool across all four sources is already cited by its own section, the writer must still
    # get something rather than an empty pool.
    only_candidate = _verbatim("The one and only candidate anywhere", "BH_1")
    sections = _fake_sections(bh_insight=[only_candidate], bh_pool=[only_candidate])
    pool = _verbatim_pool(sections=sections)
    quotes = {v.quote for v in pool.themes[0].representative_verbatims}
    assert "The one and only candidate anywhere" in quotes


def test_pool_dedupes_across_the_four_sources():
    same = _verbatim("Same client cited twice in the raw pool", "X_1")
    sections = _fake_sections(bh_pool=[same], resilience_pool=[same])
    pool = _verbatim_pool(sections=sections)
    matches = [v for v in pool.themes[0].representative_verbatims if v.client_id == "X_1"]
    assert len(matches) == 1


def test_accepts_an_in_memory_sections_map_instead_of_reading_from_disk():
    sections = _fake_sections(bh_pool=[_verbatim("q", "c1")])
    with patch("synthesis.build_gender_scorecard.load_section") as mock_load:
        _verbatim_pool(sections=sections)
    mock_load.assert_not_called()
