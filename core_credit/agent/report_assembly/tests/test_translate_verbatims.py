from typing import Optional
from unittest.mock import patch

from pydantic import BaseModel, Field

from report_assembly.translate_verbatims import _apply_inline_translations, _walk_verbatims, translate_report_verbatims
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
        direct=_verbatim("bonjour le monde entier", language="French", english_gloss="hello whole world"),
        insight_text=_wt('A client said, "bonjour le monde entier" warmly.'),
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
