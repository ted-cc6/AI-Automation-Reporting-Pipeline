"""CC-091: quotes survive whitespace differences, and insights must quote enough clients."""

from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim
from writer import chain
from writer.grounding import check_quote_grounding, quote_in_text
from writer.section_prompts import SubsectionPrompt

MULTILINE = "Vision Fund workers are sarcastic and do not have respect..\nThe branch alarms the community"
ONE_LINE = "Vision Fund workers are sarcastic and do not have respect.. The branch alarms the community"
SECOND = "The interest is too high and unaffordable for my small shop"
CFG = SubsectionPrompt(subsection_id="x-insight", title="Test", word_cap=60, instructions="Say it.")


def _pool(*quotes):
    return [Verbatim(quote=q, country="ZMB", source_field="f") for q in quotes]


def test_quote_with_a_line_break_is_not_fabricated_when_written_on_one_line():
    text = f'One client said "{ONE_LINE}".'
    assert check_quote_grounding(text, _pool(MULTILINE)) == []
    assert quote_in_text(MULTILINE, text)


def test_a_changed_word_is_still_fabricated():
    text = f'One client said "{ONE_LINE.replace("sarcastic", "rude")}".'
    assert check_quote_grounding(text, _pool(MULTILINE))


def test_quotes_used_and_required():
    pool = _pool(MULTILINE, SECOND, SECOND)
    assert chain.required_quotes(pool) == 2  # duplicates count once
    assert chain.required_quotes(_pool(SECOND)) == 1
    assert chain.required_quotes([]) == 0
    assert chain.quotes_used(f'"{ONE_LINE}" and "{SECOND}"', pool) == 2


def test_shortfall_is_a_violation_only_when_asked():
    pool = _pool(MULTILINE, SECOND)
    text = f'Clients report concerns. One said "{SECOND}".'
    assert not chain._writer_violations(text, 60, pool)
    v = chain._writer_violations(text, 60, pool, min_quotes=2)
    assert any("quotes 1 of the 2" in x for x in v)


def test_insight_rewrites_until_two_quotes_and_attaches_both(monkeypatch):
    qual = QualitativeSynthesis(
        source_field="f", base_n=2,
        themes=[ThemeFinding(theme="t", frequency=2, representative_verbatims=_pool(MULTILINE, SECOND))],
    )
    replies = [
        chain._NarrativeWithVerbatims(text=f'Clients report concerns. "{SECOND}"', used_verbatim_ids=[1]),
        chain._NarrativeWithVerbatims(text=f'Clients report concerns. "{ONE_LINE}" and "{SECOND}"', used_verbatim_ids=[0, 1]),
    ]
    prompts = []

    def fake(llm, schema, messages):
        prompts.append(messages[-1][1])
        return replies.pop(0)

    monkeypatch.setattr(chain, "build_chat_model", lambda **k: object())
    monkeypatch.setattr(chain, "invoke_structured", fake)
    written, used = chain.write_insight(CFG, "data", qual)
    assert len(prompts) == 2 and "quotes 1 of the 2" in prompts[1]
    assert [v.quote for v in used] == [MULTILINE, SECOND]  # the line-break quote is attached too
    assert written.word_count == 4  # "Clients report concerns." + "and"; quotes not counted


def test_shorten_keeps_quotes_but_is_not_asked_to_add_one(monkeypatch):
    # an insight left one quote short by the rewrite can still be shortened
    qual = QualitativeSynthesis(
        source_field="f", base_n=2,
        themes=[ThemeFinding(theme="t", frequency=2, representative_verbatims=_pool(MULTILINE, SECOND))],
    )
    long_text = " ".join(["word"] * 90) + f' "{SECOND}"'
    replies = [
        chain._NarrativeWithVerbatims(text=long_text, used_verbatim_ids=[1]),
        chain._NarrativeWithVerbatims(text=long_text, used_verbatim_ids=[1]),
        chain._NarrativeWithVerbatims(text=" ".join(["word"] * 50) + f' "{SECOND}"', used_verbatim_ids=[1]),
    ]
    monkeypatch.setattr(chain, "build_chat_model", lambda **k: object())
    monkeypatch.setattr(chain, "invoke_structured", lambda llm, schema, messages: replies.pop(0))
    written, used = chain.write_insight(CFG, "data", qual)
    assert written.word_count == 50 and written.within_cap
    assert [v.quote for v in used] == [SECOND]


def test_literal_backslash_n_is_cleaned_and_the_quote_matches(monkeypatch):
    # Test7: the model wrote a quote's line break as the two characters \\n
    multi = "PROCESSING FEE IS VERY HIGH KINDLY REDUCE\nINTEREST RATE IS VERY HIGH KINLDY REDUCE."
    qual = QualitativeSynthesis(
        source_field="f", base_n=1, themes=[ThemeFinding(theme="t", frequency=1, representative_verbatims=_pool(multi))]
    )
    written_by_model = 'A client wrote "PROCESSING FEE IS VERY HIGH KINDLY REDUCE\\nINTEREST RATE IS VERY HIGH KINLDY REDUCE."'
    monkeypatch.setattr(chain, "build_chat_model", lambda **k: object())
    monkeypatch.setattr(
        chain, "invoke_structured",
        lambda llm, schema, messages: chain._NarrativeWithVerbatims(text=written_by_model, used_verbatim_ids=[0]),
    )
    written, used = chain.write_insight(CFG, "data", qual)
    assert "\\n" not in written.text and "\n" not in written.text
    assert written.ungrounded_quotes == [] and [v.quote for v in used] == [multi]
