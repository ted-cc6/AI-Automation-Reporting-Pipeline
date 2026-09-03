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


def _inline_glossed_text(text: str, non_english: list) -> tuple[str, int]:
    """Substitute `"<gloss>" (original <lang>: "<quote>")` for every occurrence of a
    non-English verbatim's exact quote in `text`, and return (new_text, occurrences_substituted).

    Two rules keep this from re-entering its own output (the Test5 bug -- see CC-017):
      - longest quote first, so a verbatim whose quote CONTAINS a shorter verbatim's quote is
        resolved first;
      - every substituted span is recorded as occupied, and no later verbatim may match inside
        an occupied span. So the short "EXCELENTE" is never glossed a second time inside the
        already-glossed "AMABILIDAD ... EXCELENTE ... ATENCION" (nor inside that verbatim's
        original text, which the gloss keeps verbatim in its parenthetical).

    Idempotent: a verbatim whose gloss marker is already present in `text` (an earlier pipeline
    pass) is skipped entirely.
    """
    pending = [v for v in non_english if f'"{v.english_gloss}"' not in text]
    pending.sort(key=lambda v: len(v.quote), reverse=True)

    matches: list = []   # (start, end, verbatim), non-overlapping, in original-text coordinates
    occupied: list = []  # (start, end) already claimed
    for v in pending:
        pos = 0
        while True:
            i = text.find(v.quote, pos)
            if i == -1:
                break
            j = i + len(v.quote)
            if not any(s < j and i < e for s, e in occupied):
                matches.append((i, j, v))
                occupied.append((i, j))
            pos = j
    if not matches:
        return text, 0

    matches.sort(key=lambda m: m[0])
    out: list = []
    cursor = 0
    for i, j, v in matches:
        out.append(text[cursor:i])
        out.append(_inline_gloss(v))
        cursor = j
    out.append(text[cursor:])
    return "".join(out), len(matches)


def _apply_inline_translations(report) -> int:
    """Confirmed real: translating the Verbatim objects alone doesn't cover a quote the writer
    embedded directly in its own prose (per the system prompt's "quote it exactly as given,
    character for character" instruction) rather than only in the separate verbatim block
    below -- three insight paragraphs in a production report dropped foreign-language text mid
    sentence with no gloss anywhere nearby. This substitutes the gloss + original directly into
    every WrittenText.text wherever a now-translated verbatim's exact quote appears verbatim in
    it. Must run AFTER every Verbatim already has `.language`/`.english_gloss` set.

    See _inline_glossed_text for the substring/re-entry handling.
    """
    from .completeness import _walk  # local import: avoids a module-load-order cycle with completeness.py

    non_english = [v for v in _walk_verbatims(report) if v.english_gloss]
    if not non_english:
        return 0

    substitutions = 0
    for _path, wt in _walk(report):
        if wt is None:
            continue
        new_text, n = _inline_glossed_text(wt.text, non_english)
        if n:
            wt.text = new_text
            substitutions += n
    return substitutions


_PROTECTION_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _suppress_duplicate_protection_verbatims(report) -> int:
    """The client-protection free-text pass legitimately attaches one verbatim to a theme in
    two severity tiers when it describes both (the Zambia KASAMA quote -- coercive collection
    AND rude conduct -- is the case this exists for). A reader seeing the same quote twice reads
    it as an error, so keep each verbatim once, on its highest-severity theme, and drop the
    lower-tier copies. A cross-reference ("also cited under Medium severity") was the
    alternative -- see docs/core_credit_report_spec.md CC-020.

    Runs here because report_assembly is already the one place every surviving Verbatim is
    walked and mutated in place; nothing else in the report changes. Client Protection only.
    """
    cp = getattr(report, "client_protection", None)
    qs = getattr(cp, "protection_signals", None) if cp is not None else None
    if qs is None or not getattr(qs, "themes", None):
        return 0

    def _key(v: Verbatim):
        return v.client_id or v.quote.strip()

    def _rank(theme) -> int:
        return _PROTECTION_SEVERITY_RANK.get(theme.severity, 0)

    removed = 0
    seen: set = set()
    for theme in sorted(qs.themes, key=_rank, reverse=True):  # highest severity first
        kept = []
        for v in theme.representative_verbatims:
            k = _key(v)
            if k in seen:
                removed += 1
                continue
            seen.add(k)
            kept.append(v)
        theme.representative_verbatims = kept
    return removed


def translate_report_verbatims(report) -> int:
    """Mutates every Verbatim found anywhere in `report` in place, setting `.language` and
    `.english_gloss`, THEN substitutes the gloss inline everywhere a translated quote is also
    embedded directly in a WrittenText's own prose (see _apply_inline_translations). Returns
    how many verbatims were non-English (i.e. actually got a gloss), for logging. Safe to call
    more than once -- a Verbatim that already has `.language` set is skipped, and the inline
    substitution step is idempotent, so a second pass over the same report costs nothing.

    First suppresses any client-protection verbatim that appears under more than one severity
    tier (CC-020), so a dropped copy is never translated.
    """
    _suppress_duplicate_protection_verbatims(report)

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
