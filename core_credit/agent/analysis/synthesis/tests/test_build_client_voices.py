from unittest.mock import patch

from schemas.client_satisfaction import ClientSatisfactionSection, NPSResult
from schemas.common import QualitativeSynthesis, RankedOptions, SegmentAxis, SegmentedValue, ThemeFinding, Verbatim
from synthesis.build_client_voices import build_section


def _verbatim(quote: str, country: str, client_id: str = None) -> Verbatim:
    return Verbatim(quote=quote, country=country, client_id=client_id, source_field="test_field")


def _fake_client_satisfaction(insight_verbatims: list = None) -> ClientSatisfactionSection:
    promoters = QualitativeSynthesis(
        source_field="promoters",
        base_n=100,
        themes=[
            ThemeFinding(theme="Great staff", frequency=50, representative_verbatims=[_verbatim("Great staff!", "KEN", client_id="KEN_1")]),
            ThemeFinding(theme="Fast service", frequency=30, representative_verbatims=[_verbatim("Very fast service", "GHA")]),
            ThemeFinding(theme="Low rates", frequency=5, representative_verbatims=[_verbatim("Very affordable", "TZA")]),
        ],
    )
    passives = QualitativeSynthesis(source_field="passives", base_n=10, themes=[])
    detractors = QualitativeSynthesis(
        source_field="detractors",
        base_n=50,
        themes=[
            ThemeFinding(
                theme="High interest", frequency=40, severity=None,
                representative_verbatims=[_verbatim("Too expensive", "RWA")],
            ),
            ThemeFinding(
                theme="Harassment by staff", frequency=3, severity="high",
                representative_verbatims=[_verbatim("Staff threatened me", "UGA")],
            ),
        ],
    )
    return ClientSatisfactionSection(
        nps=NPSResult(
            score=50, promoter_share=0.6, passive_share=0.2, detractor_share=0.2, n=100,
            by_segment=[SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", mean=50, n=50)],
        ),
        promoter_drivers=RankedOptions(base_n=100, options=[]),
        detractor_pain_points=RankedOptions(base_n=50, options=[]),
        nps_followup_themes=[promoters, passives, detractors],
        insight_verbatims=insight_verbatims or [],
    )


def test_green_lights_come_from_the_most_frequent_promoter_themes():
    with patch("synthesis.build_client_voices.load_section", return_value=_fake_client_satisfaction()):
        section = build_section()
    quotes = {v.quote for v in section.green_lights}
    assert "Great staff!" in quotes
    assert "Very fast service" in quotes
    assert "Very affordable" not in quotes  # 3rd-ranked theme, outside TOP_N_THEMES=2


def test_red_flags_prioritize_severity_over_frequency():
    # "Harassment by staff" has far lower frequency (3 vs 40) but severity=high -- it must still
    # surface, which is the entire reason red flags aren't just sorted by frequency.
    with patch("synthesis.build_client_voices.load_section", return_value=_fake_client_satisfaction()):
        section = build_section()
    quotes = {v.quote for v in section.red_flags}
    assert "Staff threatened me" in quotes
    assert "Too expensive" in quotes


def test_accepts_an_in_memory_sections_map_instead_of_reading_from_disk():
    # The orchestrator's graph state, not synthesis.loader -- load_section must never be
    # called when sections is provided explicitly.
    with patch("synthesis.build_client_voices.load_section") as mock_load:
        section = build_section(sections={"client_satisfaction": _fake_client_satisfaction()})
    mock_load.assert_not_called()
    assert len(section.green_lights) <= 3


def test_result_is_a_valid_client_voices_section():
    with patch("synthesis.build_client_voices.load_section", return_value=_fake_client_satisfaction()):
        section = build_section()
    assert len(section.green_lights) <= 3
    assert len(section.red_flags) <= 3


def test_excludes_a_quote_already_cited_in_client_satisfactions_own_insight():
    # CC-048 regression: client_satisfaction's own Insight (Part 8) already rendered this
    # client's quote -- Client Voices must not independently re-pick it a section later, even
    # though it's still sitting in the top-ranked promoter theme's representative_verbatims.
    already_cited = _verbatim("Great staff!", "KEN", client_id="KEN_1")
    cs = _fake_client_satisfaction(insight_verbatims=[already_cited])
    with patch("synthesis.build_client_voices.load_section", return_value=cs):
        section = build_section()
    quotes = {v.quote for v in section.green_lights}
    assert "Great staff!" not in quotes
    assert "Very fast service" in quotes  # falls back to the next-ranked theme's candidate instead


def test_excludes_by_client_id_even_if_quote_text_differs():
    # The exclusion is keyed the same way _dedup_key is everywhere else in this pipeline --
    # client_id first, so a client already cited elsewhere is skipped even if the two quotes
    # (different free-text questions) don't share a single word.
    already_cited = Verbatim(quote="A completely different sentence", country="KEN", client_id="KEN_1", source_field="test_field")
    cs = _fake_client_satisfaction(insight_verbatims=[already_cited])
    with patch("synthesis.build_client_voices.load_section", return_value=cs):
        section = build_section()
    quotes = {v.quote for v in section.green_lights}
    assert "Great staff!" not in quotes
