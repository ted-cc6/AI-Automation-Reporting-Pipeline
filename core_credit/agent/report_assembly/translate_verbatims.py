"""Translates every non-English verbatim quote in an assembled report before it's rendered.

Runs once per report, after build_report() and before render_report() -- this is the one
point where every Verbatim that survived to the final report (across all 12 sections'
insight_verbatims, client_voices' green_lights/red_flags, and every theme's
representative_verbatims) is reachable in one place, so it's also the natural place to do
this rather than translating during theme-tagging (most theme-tagged responses never become
a representative_verbatim and would be wasted spend) or at render time (report_render has no
business making LLM calls).

Real incident this fixes: roughly half the quote blocks in a production report (21 of 44)
were left in their original language -- Spanish, Kinyarwanda, Vietnamese, Swahili -- with no
translation, gloss, or language label, while one writer call spontaneously and inconsistently
translated a Vietnamese quote inline in its own prose. The capability existed nowhere as a
rule; this makes it a deterministic step every quote goes through the same way.

Deliberately a plain module, not an agent: detect-language-and-translate is a mechanical,
per-quote task with no judgment call or tool use involved, the same reasoning that kept the
report assembler and renderer as plain modules rather than agents.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))

from pydantic import BaseModel, Field  # noqa: E402

from llm_client import build_chat_model, invoke_structured  # noqa: E402
from schemas.common import Verbatim  # noqa: E402

SYSTEM_PROMPT = """You identify the language a short client survey quote is written in and provide a \
natural, accurate English translation. Preserve the original meaning, tone, and register exactly -- \
do not soften, formalize, embellish, or correct grammar; a blunt, informal, or ungrammatical original \
should read as blunt, informal, or ungrammatical in English too, not polished up. If the quote is \
already in English, set language to "English" and repeat the quote unchanged as the gloss."""


class _Translation(BaseModel):
    language: str = Field(
        description="Full language name the quote is written in, e.g. 'English', 'Spanish', "
        "'Kinyarwanda', 'Vietnamese', 'Swahili' -- never a language code"
    )
    english_gloss: str = Field(
        description="English translation of the quote. If the quote is already in English, "
        "repeat it unchanged here."
    )


def translate_quote(quote: str) -> tuple[str, Optional[str]]:
    """Returns (language, english_gloss). english_gloss is None when language is English --
    nothing to gloss, and the renderer should show the quote as-is with no translation line.
    """
    llm = build_chat_model(use_thinking=False)
    result: _Translation = invoke_structured(llm, _Translation, [("system", SYSTEM_PROMPT), ("human", quote)])
    if result.language.strip().lower() == "english":
        return result.language, None
    return result.language, result.english_gloss


def _walk_verbatims(obj):
    """Yields every Verbatim instance found anywhere in a nested Pydantic model / list
    structure -- same recursive-walk shape as report_assembly.completeness._walk, generic over
    the report's structure rather than listing each of the ~15 fields a Verbatim can live in
    (insight_verbatims on 9 sections, representative_verbatims nested inside 5 sections'
    QualitativeSynthesis fields, client_voices' green_lights/red_flags) by name.
    """
    if isinstance(obj, Verbatim):
        yield obj
    elif isinstance(obj, BaseModel):
        for name in obj.__class__.model_fields:
            yield from _walk_verbatims(getattr(obj, name))
    elif isinstance(obj, list):
        for item in obj:
            yield from _walk_verbatims(item)


def _inline_gloss(v: Verbatim) -> str:
    return f'"{v.english_gloss}" (original {v.language}: "{v.quote}")'


def _apply_inline_translations(report) -> int:
    """Confirmed real: translating the Verbatim objects alone doesn't cover a quote the writer
    embedded directly in its own prose (per the system prompt's "quote it exactly as given,
    character for character" instruction) rather than only in the separate verbatim block
    below -- three insight paragraphs in a production report dropped foreign-language text mid
    sentence with no gloss anywhere nearby. This substitutes the gloss + original directly into
    every WrittenText.text wherever a now-translated verbatim's exact quote appears verbatim in
    it. Must run AFTER every Verbatim already has `.language`/`.english_gloss` set.

    Idempotent by construction, not just by convention: the substituted form still contains the
    original quote as a substring (so the original can't be told apart from "not yet
    substituted" by presence alone), so each check also confirms the gloss marker ISN'T already
    there before substituting -- safe to call twice on the same report.
    """
    from .completeness import _walk  # local import: avoids a module-load-order cycle with completeness.py

    non_english = [v for v in _walk_verbatims(report) if v.english_gloss]
    if not non_english:
        return 0

    substitutions = 0
    for _path, wt in _walk(report):
        if wt is None:
            continue
        new_text = wt.text
        for v in non_english:
            gloss_marker = f'"{v.english_gloss}"'
            if v.quote in new_text and gloss_marker not in new_text:
                new_text = new_text.replace(v.quote, _inline_gloss(v))
                substitutions += 1
        if new_text != wt.text:
            wt.text = new_text
    return substitutions


def translate_report_verbatims(report) -> int:
    """Mutates every Verbatim found anywhere in `report` in place, setting `.language` and
    `.english_gloss`, THEN substitutes the gloss inline everywhere a translated quote is also
    embedded directly in a WrittenText's own prose (see _apply_inline_translations). Returns
    how many verbatims were non-English (i.e. actually got a gloss), for logging. Safe to call
    more than once -- a Verbatim that already has `.language` set is skipped, and the inline
    substitution step is idempotent, so a second pass over the same report costs nothing.
    """
    translated = 0
    for v in _walk_verbatims(report):
        if v.language is not None:
            continue
        language, gloss = translate_quote(v.quote)
        v.language = language
        v.english_gloss = gloss
        if gloss is not None:
            translated += 1

    _apply_inline_translations(report)
    return translated
