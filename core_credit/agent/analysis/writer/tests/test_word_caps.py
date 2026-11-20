"""CC-090: quote-free word counts, the 10% tolerance, and the length-only shorten pass."""

import pytest

from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim
from writer import chain
from writer.section_prompts import SubsectionPrompt

CFG = SubsectionPrompt(subsection_id="x-insight", title="Test", word_cap=20, instructions="Say it.")
QUOTE = "The loan helped me buy a second sewing machine for my shop"


def _words(n: int) -> str:
    return " ".join(["word"] * n) + "."


class _FakeLLM:
    """Returns the queued replies in order and records every prompt it was sent."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def invoke(self, messages):
        self.prompts.append(messages[-1][1])
        return self.replies.pop(0)


@pytest.fixture
def fake(monkeypatch):
    holder = {}

    def install(replies):
        llm = _FakeLLM(replies)
        holder["llm"] = llm
        monkeypatch.setattr(chain, "build_chat_model", lambda **k: llm)
        monkeypatch.setattr(chain, "extract_text", lambda r: r)
        return llm

    return install


def test_quotes_are_not_counted():
    pool = [Verbatim(quote=QUOTE, source_field="f")]
    text = f'Clients report gains. One said "{QUOTE}".'
    assert chain.narrative_word_count(text, pool) == 5
    assert chain.narrative_word_count(text) == len(text.split())


def test_short_strings_in_the_pool_are_not_stripped():
    pool = [Verbatim(quote="good", source_field="f")]
    assert chain.narrative_word_count("good results were good", pool) == 4


@pytest.mark.parametrize("n,ok", [(20, True), (22, True), (23, False)])
def test_tolerance_is_ten_percent(n, ok):
    assert chain.within_tolerance(n, 20) is ok


def test_length_violation_names_the_cut():
    v = chain._writer_violations(_words(30), 20, [])
    assert v and "cut at least 10 words" in v[0]
    assert chain._writer_violations(_words(30), 20, [], include_length=False) == []


def test_within_cap_draft_makes_one_call(fake):
    llm = fake([_words(18)])
    out = chain.write_subsection(CFG, "data")
    assert len(llm.prompts) == 1 and out.within_cap


def test_rewrite_that_lands_in_tolerance_skips_shorten(fake):
    llm = fake([_words(40), _words(21)])
    out = chain.write_subsection(CFG, "data")
    assert len(llm.prompts) == 2
    assert out.word_count == 21 and out.within_cap


def test_shorten_pass_runs_when_still_over_tolerance(fake):
    llm = fake([_words(40), _words(30), _words(19)])
    out = chain.write_subsection(CFG, "data")
    assert len(llm.prompts) == 3
    assert "cut at least 10 words" in llm.prompts[2]
    assert "Say it." in llm.prompts[2]  # the subsection instructions travel with it
    assert out.word_count == 19 and out.within_cap


def test_shorten_that_breaks_a_rule_is_discarded(fake):
    # the shorter draft adds a semicolon (banned punctuation): keep the longer, clean one
    llm = fake([_words(40), _words(30), "word word; word."])
    out = chain.write_subsection(CFG, "data")
    assert out.word_count == 30 and not out.within_cap


def test_shorten_that_is_not_shorter_is_discarded(fake):
    llm = fake([_words(40), _words(30), _words(35)])
    out = chain.write_subsection(CFG, "data")
    assert out.word_count == 30


def test_rewrite_instruction_allows_dropping_content():
    text = chain._revise_instruction("draft", ["30 words"], 20)
    assert "drop the least important" in text
    assert "Keep every fact, number" not in text


def test_insight_shorten_keeps_verbatim_ids(monkeypatch):
    pool_theme = ThemeFinding(theme="t", frequency=1, representative_verbatims=[Verbatim(quote=QUOTE, source_field="f")])
    qual = QualitativeSynthesis(source_field="f", base_n=1, themes=[pool_theme])
    replies = [
        chain._NarrativeWithVerbatims(text=_words(40) + f' "{QUOTE}"', used_verbatim_ids=[0]),
        chain._NarrativeWithVerbatims(text=_words(30) + f' "{QUOTE}"', used_verbatim_ids=[0]),
        chain._NarrativeWithVerbatims(text=_words(18) + f' "{QUOTE}"', used_verbatim_ids=[0]),
    ]
    calls = []

    def fake_structured(llm, schema, messages):
        calls.append(messages[-1][1])
        return replies.pop(0)

    monkeypatch.setattr(chain, "build_chat_model", lambda **k: object())
    monkeypatch.setattr(chain, "invoke_structured", fake_structured)
    written, used = chain.write_insight(CFG, "data", qual)
    assert len(calls) == 3
    assert written.word_count == 18 and written.within_cap
    assert [v.quote for v in used] == [QUOTE]
