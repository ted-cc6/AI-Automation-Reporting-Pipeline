from typing import Optional
from unittest.mock import patch

from pydantic import BaseModel, Field

from report_assembly.translate_verbatims import (
    _apply_inline_translations,
    _suppress_duplicate_nps_verbatims,
    _suppress_duplicate_protection_verbatims,
    _suppress_duplicate_qol_driver_verbatims,
    _suppress_duplicate_theme_verbatims,
    _suppress_insight_verbatims_already_in_protection_signals,
    _walk_verbatims,
    translate_report_verbatims,
)
from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim, WrittenText


def _verbatim(quote: str, language: Optional[str] = None, english_gloss: Optional[str] = None) -> Verbatim:
    return Verbatim(quote=quote, source_field="test_field", language=language, english_gloss=english_gloss)


def _wt(text: str) -> WrittenText:
    return WrittenText(subsection_id="1", text=text, word_count=len(text.split()), within_cap=True)


class _Sub(BaseModel):
    v: Optional[Verbatim] = None


class _Fake(BaseModel):
    direct: Optional[Verbatim] = None
    nested: Optional[_Sub] = None
    listed: list[Verbatim] = Field(default_factory=list)
    qualitative: Optional[QualitativeSynthesis] = None
    insight_text: Optional[WrittenText] = None


def test_walk_verbatims_finds_direct_nested_and_listed():
    report = _Fake(
        direct=_verbatim("a"),
        nested=_Sub(v=_verbatim("b")),
        listed=[_verbatim("c"), _verbatim("d")],
    )
    found = {v.quote for v in _walk_verbatims(report)}
    assert found == {"a", "b", "c", "d"}


def test_walk_verbatims_finds_representative_verbatims_inside_theme_findings():
    # The real shape this exists for: representative_verbatims nested two levels down inside
    # a QualitativeSynthesis, not just direct insight_verbatims fields.
    report = _Fake(
        qualitative=QualitativeSynthesis(
            source_field="test",
            base_n=10,
            themes=[ThemeFinding(theme="t", frequency=2, representative_verbatims=[_verbatim("e")])],
        )
    )
    found = {v.quote for v in _walk_verbatims(report)}
    assert found == {"e"}


def test_translate_report_verbatims_mutates_in_place_and_counts_non_english():
    report = _Fake(
        direct=_verbatim("Hola, gracias por el prestamo"),
        listed=[_verbatim("Thank you for the loan")],
    )

    def fake_translate(quote: str):
        if quote.startswith("Hola"):
            return "Spanish", "Hello, thank you for the loan"
        return "English", None

    with patch("report_assembly.translate_verbatims.translate_quote", side_effect=fake_translate):
        n = translate_report_verbatims(report)

    assert n == 1
    assert report.direct.language == "Spanish"
    assert report.direct.english_gloss == "Hello, thank you for the loan"
    assert report.listed[0].language == "English"
    assert report.listed[0].english_gloss is None


def test_translate_report_verbatims_skips_already_translated():
    # Idempotent: a second pass over the same report (e.g. a resumed orchestrator run) should
    # not re-spend on verbatims that already have a language set.
    report = _Fake(direct=_verbatim("already done", language="French"))

    with patch("report_assembly.translate_verbatims.translate_quote") as mock_translate:
        n = translate_report_verbatims(report)

    mock_translate.assert_not_called()
    assert n == 0
    assert report.direct.language == "French"


def test_apply_inline_translations_substitutes_quote_embedded_in_prose():
    # Regression test for a real gap: translating the separate Verbatim block never touched a
    # copy of the same quote the writer embedded directly in its own prose, so three insight
    # paragraphs in a production report dropped foreign-language text mid sentence with no
    # gloss anywhere nearby.
    report = _Fake(
        direct=_verbatim("Aujourd'hui j'ai plus de quatre têtes de bœuf", language="French", english_gloss="Today I have more than four head of cattle"),
        insight_text=_wt('A client said, "Aujourd\'hui j\'ai plus de quatre têtes de bœuf" describing asset growth.'),
    )
    n = _apply_inline_translations(report)
    assert n == 1
    assert '"Today I have more than four head of cattle" (original French: "Aujourd\'hui j\'ai plus de quatre têtes de bœuf")' in report.insight_text.text


def test_apply_inline_translations_ignores_english_verbatims():
    report = _Fake(
        direct=_verbatim("Thank you for the loan", language="English", english_gloss=None),
        insight_text=_wt('A client said, "Thank you for the loan" plainly.'),
    )
    original_text = report.insight_text.text
    n = _apply_inline_translations(report)
    assert n == 0
    assert report.insight_text.text == original_text


def test_apply_inline_translations_is_idempotent():
    report = _Fake(
        direct=_verbatim("bonjour a tout le monde entier", language="French", english_gloss="hello to the whole world"),
        insight_text=_wt('A client said, "bonjour a tout le monde entier" warmly.'),
    )
    _apply_inline_translations(report)
    once = report.insight_text.text
    n_second_pass = _apply_inline_translations(report)
    assert n_second_pass == 0
    assert report.insight_text.text == once


def test_translate_report_verbatims_applies_inline_substitution_end_to_end():
    report = _Fake(
        direct=_verbatim("hola mundo entero de verdad"),
        insight_text=_wt('A client said, "hola mundo entero de verdad" happily.'),
    )

    def fake_translate(quote: str):
        return "Spanish", "hello whole real world"

    with patch("report_assembly.translate_verbatims.translate_quote", side_effect=fake_translate):
        translate_report_verbatims(report)

    assert '"hello whole real world" (original Spanish: "hola mundo entero de verdad")' in report.insight_text.text


def test_apply_inline_translations_does_not_re_gloss_a_substring_of_a_longer_verbatim():
    # CC-017: the Test5 Part 8 insight rendered as
    #   ""KINDNESS ..." (original Spanish: "AMABILIDAD POCOS REQUISITOS "EXCELLENT"
    #     (original Spanish: "EXCELENTE") ATENCION")."
    # -- the short verbatim was glossed a second time inside the longer verbatim's own inline
    # gloss. The longer quote must be resolved first and the shorter one skipped wherever it
    # falls inside it (raw text or the gloss's parenthetical). Both quotes here are kept at or
    # above _MIN_QUOTE_LEN (CC-065) so this test still exercises the occupied-span mechanism
    # itself, not the length filter standing in for it.
    long_v = _verbatim(
        "AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION",
        language="Spanish", english_gloss="KINDNESS FEW REQUIREMENTS EXCELLENT SERVICE",
    )
    short_v = _verbatim("POCOS REQUISITOS EXCELENTE", language="Spanish", english_gloss="FEW REQUIREMENTS EXCELLENT")
    report = _Fake(
        direct=long_v,
        listed=[short_v],
        insight_text=_wt('A promoter said "AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION" plainly.'),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    # the longer verbatim is glossed exactly once...
    assert (
        '"KINDNESS FEW REQUIREMENTS EXCELLENT SERVICE" '
        '(original Spanish: "AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION")'
    ) in t
    # ...and the shorter one is NOT glossed again inside it (the Test5 bug)
    assert '"FEW REQUIREMENTS EXCELLENT" (original Spanish: "POCOS REQUISITOS EXCELENTE")' not in t
    assert t.count("(original Spanish:") == 1


def test_apply_inline_translations_still_glosses_a_short_verbatim_outside_the_longer_one():
    long_v = _verbatim(
        "AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION",
        language="Spanish", english_gloss="KINDNESS FEW REQUIREMENTS EXCELLENT SERVICE",
    )
    short_v = _verbatim("POCOS REQUISITOS EXCELENTE", language="Spanish", english_gloss="FEW REQUIREMENTS EXCELLENT")
    report = _Fake(
        direct=long_v,
        listed=[short_v],
        insight_text=_wt(
            'She rated it "POCOS REQUISITOS EXCELENTE" on its own, then praised '
            '"AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION" overall.'
        ),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    assert '"FEW REQUIREMENTS EXCELLENT" (original Spanish: "POCOS REQUISITOS EXCELENTE")' in t  # the standalone one is still glossed
    assert (
        '"KINDNESS FEW REQUIREMENTS EXCELLENT SERVICE" '
        '(original Spanish: "AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION")'
    ) in t
    assert t.count("(original Spanish:") == 2


# CC-064: the writer sometimes wraps the original-language text in its own quote marks before
# this substitution runs, and the gloss's own opening quote then lands right next to the
# writer's, doubling it. Present in every report to date, deferred three times as cosmetic --
# fixed by omitting the substitution's own opening quote when one is already there.

def test_apply_inline_translations_does_not_double_a_quote_the_writer_already_supplied():
    # The exact real incident, local-cc061 Part 8.2.
    v = _verbatim(
        "EXCELENTE ATENCION, EDUCACION CRISTIANA LA TASA DE INTERES",
        language="Spanish", english_gloss="EXCELLENT SERVICE, CHRISTIAN EDUCATION THE INTEREST RATE",
    )
    report = _Fake(
        direct=v,
        insight_text=_wt(
            'A female client in Honduras, non-caregiver, cited '
            '"EXCELENTE ATENCION, EDUCACION CRISTIANA LA TASA DE INTERES."'
        ),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    assert '""' not in t
    assert (
        'cited "EXCELLENT SERVICE, CHRISTIAN EDUCATION THE INTEREST RATE" '
        '(original Spanish: "EXCELENTE ATENCION, EDUCACION CRISTIANA LA TASA DE INTERES")'
    ) in t


def test_apply_inline_translations_does_not_double_a_quote_a_second_real_incident():
    # local-cc061 Part 8-insight -- same defect, different introducing verb, confirms the fix
    # isn't specific to "cited".
    v = _verbatim("BUEN TRATO Y EXCELENTE SERVICIO", language="Spanish", english_gloss="GOOD TREATMENT AND EXCELLENT SERVICE")
    report = _Fake(
        direct=v,
        insight_text=_wt('A client captured this directly, saying "BUEN TRATO Y EXCELENTE SERVICIO."'),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    assert '""' not in t
    assert 'saying "GOOD TREATMENT AND EXCELLENT SERVICE" (original Spanish: "BUEN TRATO Y EXCELENTE SERVICIO")' in t


def test_apply_inline_translations_still_adds_its_own_quote_when_the_writer_did_not_supply_one():
    # The ordinary, far more common case -- unaffected: no preceding quote mark in the text, so
    # the substitution's own opening quote is exactly as needed.
    v = _verbatim("hola mundo entero de verdad", language="Spanish", english_gloss="hello whole real world")
    report = _Fake(
        direct=v,
        insight_text=_wt("A client mentioned hola mundo entero de verdad as her reason."),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    assert '"hello whole real world" (original Spanish: "hola mundo entero de verdad")' in t
    assert '""' not in t


def test_apply_inline_translations_handles_both_orderings_of_a_preceded_and_unpreceded_match_together():
    # Two substitutions in the same text -- one immediately preceded by a writer's quote, one
    # not -- each checked against its own position in the ORIGINAL text, regardless of order.
    preceded = _verbatim("EXCELENTE ATENCION AL CLIENTE", language="Spanish", english_gloss="EXCELLENT CUSTOMER SERVICE")
    unpreceded = _verbatim("muy bueno el servicio recibido", language="Spanish", english_gloss="very good the service received")
    report = _Fake(
        direct=preceded,
        listed=[unpreceded],
        insight_text=_wt(
            'One client said "EXCELENTE ATENCION AL CLIENTE" plainly, another simply called it '
            "muy bueno el servicio recibido overall."
        ),
    )
    _apply_inline_translations(report)
    t = report.insight_text.text
    assert '""' not in t
    assert 'said "EXCELLENT CUSTOMER SERVICE" (original Spanish: "EXCELENTE ATENCION AL CLIENTE")' in t
    assert 'called it "very good the service received" (original Spanish: "muy bueno el servicio recibido")' in t


# CC-065: a plain str.find matched a verbatim's quote as a raw substring anywhere it occurred,
# including inside an unrelated English word. A real 2-character verbatim, "da" ("yes" in
# Montenegrin, mistagged as Indonesian), matched inside "Secondary", "standardised", "Uganda",
# "Rwanda", and "adaptation" 13 times across 9 blocks in a real run, including the executive
# summary. Fixed by reusing grounding.py's own CC-006 word-boundary approach directly
# ((?<!\w)...(?!\w) plus _MIN_QUOTE_LEN) rather than inventing a second mechanism.

def test_apply_inline_translations_does_not_match_a_short_quote_inside_an_unrelated_word():
    # The exact real incident: "da" must not match inside "standardised".
    v = _verbatim("da", language="Montenegrin", english_gloss="yes")
    original = "Once the gaps are standardised across countries, most of the difference disappears."
    report = _Fake(direct=v, insight_text=_wt(original))
    n = _apply_inline_translations(report)
    assert n == 0
    assert report.insight_text.text == original


def test_apply_inline_translations_never_attempts_a_verbatim_shorter_than_min_quote_len():
    # Even standing alone, bounded by spaces on both sides, a verbatim this short is never
    # trusted as a real client quote for substitution -- word boundaries alone don't help a
    # short quote that legitimately IS a whole word ("da" as a stand-alone answer to an
    # unrelated question must not get glossed into every other stand-alone "da" in the report).
    v = _verbatim("da", language="Montenegrin", english_gloss="yes")
    report = _Fake(
        direct=v,
        insight_text=_wt("The client simply answered da when asked if the loan helped."),
    )
    n = _apply_inline_translations(report)
    assert n == 0
    assert report.insight_text.text == "The client simply answered da when asked if the loan helped."


def test_apply_inline_translations_still_matches_a_short_quote_with_word_boundaries_once_long_enough():
    # Confirms the boundary fix doesn't just suppress short quotes outright -- a quote at or
    # above _MIN_QUOTE_LEN with genuine word-boundary risk (a substring of a longer real phrase
    # elsewhere in the text) still matches correctly when it stands alone, bounded by
    # non-word characters.
    v = _verbatim("da igual si tengo poco dinero", language="Spanish", english_gloss="it's the same if I have little money")
    report = _Fake(
        direct=v,
        insight_text=_wt('A client said "da igual si tengo poco dinero" about her situation.'),
    )
    n = _apply_inline_translations(report)
    assert n == 1
    assert '"it\'s the same if I have little money" (original Spanish: "da igual si tengo poco dinero")' in report.insight_text.text


class _CP(BaseModel):
    protection_signals: Optional[QualitativeSynthesis] = None
    insight_verbatims: list[Verbatim] = Field(default_factory=list)


class _FakeWithCP(BaseModel):
    client_protection: Optional[_CP] = None


def test_suppress_duplicate_protection_verbatims_keeps_only_highest_severity():
    # CC-020: the Zambia KASAMA quote genuinely fits both High (coercive collection) and
    # Medium (rude conduct). Keep it once, on High; drop the Medium copy.
    q = "Vision Fund workers are sarcastic and do not have a heart of understanding"
    qs = QualitativeSynthesis(
        source_field="protection_signals",
        base_n=5,
        themes=[
            ThemeFinding(theme="Rude staff conduct", frequency=18, severity="medium",
                         representative_verbatims=[Verbatim(quote=q, source_field="f"),
                                                   Verbatim(quote="only here", source_field="f")]),
            ThemeFinding(theme="Coercive collection", frequency=9, severity="high",
                         representative_verbatims=[Verbatim(quote=q, source_field="f")]),
        ],
    )
    report = _FakeWithCP(client_protection=_CP(protection_signals=qs))
    removed = _suppress_duplicate_protection_verbatims(report)

    assert removed == 1
    assert [v.quote for v in qs.themes[1].representative_verbatims] == [q]          # High keeps it
    assert [v.quote for v in qs.themes[0].representative_verbatims] == ["only here"]  # Medium drops it


def test_suppress_duplicate_protection_verbatims_noop_without_client_protection():
    assert _suppress_duplicate_protection_verbatims(_Fake()) == 0


def test_suppress_insight_verbatims_already_in_protection_signals_removes_the_overlap():
    # CC-058 regression: the real incident -- "Vision Fund female workers lack good customer
    # service and respect" appeared in both client_protection.insight_verbatims and its own
    # protection_signals theme list. Removed from insight_verbatims, not protection_signals --
    # the theme list is the section's established bank and renders first.
    shared = "Vision Fund female workers lack good customer service and respect"
    qs = _qs_for_cp(shared)
    cp = _CP(protection_signals=qs, insight_verbatims=[Verbatim(quote=shared, source_field="f"), Verbatim(quote="unique", source_field="f")])
    report = _FakeWithCP(client_protection=cp)

    removed = _suppress_insight_verbatims_already_in_protection_signals(report)

    assert removed == 1
    assert [v.quote for v in cp.insight_verbatims] == ["unique"]
    # protection_signals itself is untouched -- it's the established bank, not the duplicate.
    assert [v.quote for v in qs.themes[0].representative_verbatims] == [shared]


def test_suppress_insight_verbatims_already_in_protection_signals_noop_when_no_overlap():
    qs = _qs_for_cp("something in the theme list")
    cp = _CP(protection_signals=qs, insight_verbatims=[Verbatim(quote="a different quote entirely", source_field="f")])
    report = _FakeWithCP(client_protection=cp)

    removed = _suppress_insight_verbatims_already_in_protection_signals(report)

    assert removed == 0
    assert len(cp.insight_verbatims) == 1


def test_suppress_insight_verbatims_already_in_protection_signals_noop_without_client_protection():
    assert _suppress_insight_verbatims_already_in_protection_signals(_Fake()) == 0


def _qs_for_cp(quote: str) -> QualitativeSynthesis:
    return QualitativeSynthesis(
        source_field="protection_signals", base_n=5,
        themes=[ThemeFinding(theme="Rude staff conduct", frequency=1, representative_verbatims=[Verbatim(quote=quote, source_field="f")])],
    )


class _BH(BaseModel):
    qol_drivers: Optional[QualitativeSynthesis] = None


class _FakeWithBH(BaseModel):
    business_household_impact: Optional[_BH] = None


def test_suppress_duplicate_qol_driver_verbatims_keeps_only_the_higher_frequency_theme():
    # CC-037 regression: the exact incident -- "Increased income/earnings (general)" (n=577)
    # and "...business profit growth" (n=473) rendered the identical two verbatims back to
    # back in a real Hugging Face run. qol_drivers has no severity concept, so rank by
    # frequency, same order the table already renders in.
    shared = "I have more income"
    qs = QualitativeSynthesis(
        source_field="qol_drivers",
        base_n=5000,
        themes=[
            ThemeFinding(theme="Increased income/earnings (general) - business profit growth", frequency=473,
                         representative_verbatims=[Verbatim(quote=shared, source_field="f"),
                                                    Verbatim(quote="Income sources increased", source_field="f")]),
            ThemeFinding(theme="Increased income/earnings (general)", frequency=577,
                         representative_verbatims=[Verbatim(quote=shared, source_field="f"),
                                                    Verbatim(quote="Income sources increased", source_field="f")]),
        ],
    )
    report = _FakeWithBH(business_household_impact=_BH(qol_drivers=qs))
    removed = _suppress_duplicate_qol_driver_verbatims(report)

    assert removed == 2  # both shared verbatims dropped from the lower-frequency theme
    higher = next(t for t in qs.themes if t.frequency == 577)
    lower = next(t for t in qs.themes if t.frequency == 473)
    assert [v.quote for v in higher.representative_verbatims] == [shared, "Income sources increased"]
    assert lower.representative_verbatims == []


def test_suppress_duplicate_qol_driver_verbatims_noop_without_business_household_impact():
    assert _suppress_duplicate_qol_driver_verbatims(_Fake()) == 0


class _CS(BaseModel):
    nps_followup_themes: list = Field(default_factory=list)


class _FakeWithCS(BaseModel):
    client_satisfaction: Optional[_CS] = None


def test_suppress_duplicate_nps_verbatims_keeps_only_the_higher_frequency_theme():
    # CC-048 regression: the real incident -- the Zambia "wonderful services" quote sat in two
    # different promoter-band themes at once, then got independently re-selected by
    # write_insight, gender_scorecard's pooled write_insight, and client_voices'
    # pick_diverse_verbatims, landing in the rendered document three times over. No severity
    # concept here either, so rank by frequency, same as qol_drivers (CC-037).
    zambia = "Vision Fund has got wonderful services and gives enough time to clients when it comes to paying back money"
    promoters = QualitativeSynthesis(
        source_field="promoters", base_n=500,
        themes=[
            ThemeFinding(theme="Affordable / fair rates", frequency=12,
                         representative_verbatims=[Verbatim(quote=zambia, client_id="ZMB_77828", source_field="f")]),
            ThemeFinding(theme="Good service / staff conduct", frequency=90,
                         representative_verbatims=[Verbatim(quote=zambia, client_id="ZMB_77828", source_field="f"),
                                                    Verbatim(quote="Fast disbursement", source_field="f")]),
        ],
    )
    passives = QualitativeSynthesis(source_field="passives", base_n=10, themes=[])
    detractors = QualitativeSynthesis(source_field="detractors", base_n=10, themes=[])
    report = _FakeWithCS(client_satisfaction=_CS(nps_followup_themes=[promoters, passives, detractors]))

    removed = _suppress_duplicate_nps_verbatims(report)

    assert removed == 1
    higher = next(t for t in promoters.themes if t.frequency == 90)
    lower = next(t for t in promoters.themes if t.frequency == 12)
    assert [v.client_id for v in higher.representative_verbatims] == ["ZMB_77828", None]
    assert lower.representative_verbatims == []


def test_suppress_duplicate_nps_verbatims_noop_without_client_satisfaction():
    assert _suppress_duplicate_nps_verbatims(_Fake()) == 0


def test_suppress_duplicate_theme_verbatims_matches_by_client_id_over_quote_text():
    # Two different clients who happened to type the identical short phrase must NOT be
    # treated as the same duplicate -- client_id is the real identity when present.
    qs = QualitativeSynthesis(
        source_field="x", base_n=10,
        themes=[
            ThemeFinding(theme="A", frequency=2, representative_verbatims=[Verbatim(quote="good", client_id="c1", source_field="f")]),
            ThemeFinding(theme="B", frequency=1, representative_verbatims=[Verbatim(quote="good", client_id="c2", source_field="f")]),
        ],
    )
    removed = _suppress_duplicate_theme_verbatims(qs, rank_key=lambda t: t.frequency)
    assert removed == 0
    assert all(t.representative_verbatims for t in qs.themes)
