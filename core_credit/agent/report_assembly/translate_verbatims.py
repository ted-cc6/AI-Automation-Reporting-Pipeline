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

import re
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
from writer.grounding import _MIN_QUOTE_LEN  # noqa: E402

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


def _inline_gloss(v: Verbatim, *, omit_leading_quote: bool = False) -> str:
    opening = "" if omit_leading_quote else '"'
    return f'{opening}{v.english_gloss}" (original {v.language}: "{v.quote}")'


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

    A third rule (CC-064) fixes a real, repeatedly-deferred defect: the writer sometimes wraps
    the original-language text in its own quote marks before this substitution ever runs (e.g.
    `cited "EXCELENTE ATENCION..."`), and since the gloss's own opening quote lands immediately
    after the writer's, the result doubles it (`cited ""EXCELLENT SERVICE...`). When the matched
    span is immediately preceded by a `"` already in the text, the substitution's own opening
    quote is omitted -- the writer's own mark serves as the opening instead. Checked against the
    ORIGINAL text at each match's own position, so it's correct regardless of how many other
    substitutions land before or after it in the same pass.

    A fourth rule (CC-065) fixes a worse, independent defect: a plain `str.find` matches a
    quote as a raw substring wherever it occurs, including inside an unrelated English word. A
    real 2-character verbatim, "da" ("yes" in Montenegrin, mistagged as Indonesian), matched
    inside "Secondary", "standardised", "Uganda", "Rwanda", and "adaptation" 13 times across 9
    blocks, including the executive summary. `grounding.py` solved exactly this problem under
    CC-006 for its own quote-matching (`(?<!\\w)...(?!\\w)` plus `_MIN_QUOTE_LEN`) -- reused
    directly here rather than inventing a second mechanism: word-boundary lookarounds around
    the escaped quote, and any verbatim shorter than `_MIN_QUOTE_LEN` is never matched at all
    (word boundaries alone don't help a short quote that legitimately IS a whole word --
    "da" bounded by spaces would still wrongly gloss every "da" a respondent typed as a
    stand-alone answer to an unrelated question).

    Idempotent: a verbatim whose gloss marker is already present in `text` (an earlier pipeline
    pass) is skipped entirely.
    """
    pending = [
        v for v in non_english
        if len(v.quote) >= _MIN_QUOTE_LEN and f'"{v.english_gloss}"' not in text
    ]
    pending.sort(key=lambda v: len(v.quote), reverse=True)

    matches: list = []   # (start, end, verbatim), non-overlapping, in original-text coordinates
    occupied: list = []  # (start, end) already claimed
    for v in pending:
        pattern = re.compile(r"(?<!\w)" + re.escape(v.quote) + r"(?!\w)")
        for m in pattern.finditer(text):
            i, j = m.start(), m.end()
            if not any(s < j and i < e for s, e in occupied):
                matches.append((i, j, v))
                occupied.append((i, j))
    if not matches:
        return text, 0

    matches.sort(key=lambda m: m[0])
    out: list = []
    cursor = 0
    for i, j, v in matches:
        out.append(text[cursor:i])
        preceded_by_quote = i > 0 and text[i - 1] == '"'
        out.append(_inline_gloss(v, omit_leading_quote=preceded_by_quote))
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


def _dedup_key(v: Verbatim):
    return v.client_id or v.quote.strip()


def _suppress_duplicate_theme_verbatims(qs, rank_key) -> int:
    """CC-020 (originally client-protection-only), generalized under CC-037 to any
    QualitativeSynthesis that gets rendered as an independent per-theme verbatim bank
    (report_render.section_layout.add_theme_list / add_protection_signals): both render each
    theme's own representative_verbatims slice with zero visibility into what an earlier theme
    in the same list already showed, so the same client response can legitimately be a
    representative pick for two different (often near-duplicate) themes and appear twice, back
    to back, in the rendered document -- read by a reviewer as an error, not a feature. Keeps
    each verbatim once, on the theme `rank_key` ranks highest, and drops it from every lower-
    ranked theme it also appears on. A cross-reference ("also cited under ...") was the
    alternative considered for the original protection-signals case -- see
    docs/core_credit_report_spec.md CC-020 / CC-037.

    Mutates `qs.themes[*].representative_verbatims` in place (a theme can end up with fewer
    than its usual 2-3 after a duplicate is dropped from it -- no backfill, matching CC-020's
    existing behavior). Returns how many were removed.
    """
    if qs is None or not getattr(qs, "themes", None):
        return 0

    removed = 0
    seen: set = set()
    for theme in sorted(qs.themes, key=rank_key, reverse=True):  # highest-ranked theme first
        kept = []
        for v in theme.representative_verbatims:
            k = _dedup_key(v)
            if k in seen:
                removed += 1
                continue
            seen.add(k)
            kept.append(v)
        theme.representative_verbatims = kept
    return removed


def _suppress_duplicate_protection_verbatims(report) -> int:
    """The client-protection free-text pass legitimately attaches one verbatim to a theme in
    two severity tiers when it describes both (the Zambia KASAMA quote -- coercive collection
    AND rude conduct -- is the case this exists for). Kept on its highest-severity theme; see
    _suppress_duplicate_theme_verbatims for the general mechanism (CC-020).

    Runs here because report_assembly is already the one place every surviving Verbatim is
    walked and mutated in place; nothing else in the report changes.
    """
    cp = getattr(report, "client_protection", None)
    qs = getattr(cp, "protection_signals", None) if cp is not None else None
    return _suppress_duplicate_theme_verbatims(qs, rank_key=lambda t: _PROTECTION_SEVERITY_RANK.get(t.severity, 0))


def _suppress_insight_verbatims_already_in_protection_signals(report) -> int:
    """CC-058: client_protection.insight_verbatims is picked by the writer from the same
    protection_signals pool render_client_protection already renders as its own theme-list bank
    earlier in the same Part (add_protection_signals runs first, the Insight's own verbatim
    callout comes later) -- with no awareness of what that bank already showed. Confirmed real:
    "Vision Fund female workers lack good customer service and respect" appeared in both.
    Removes the overlap from insight_verbatims, not from protection_signals -- the theme list
    renders first and is the section's own established evidence bank; the insight callout is
    the one duplicating it, not the other way around. Runs after
    _suppress_duplicate_protection_verbatims so it checks against protection_signals' own
    final, already-deduped state.
    """
    cp = getattr(report, "client_protection", None)
    if cp is None or not cp.insight_verbatims:
        return 0
    qs = getattr(cp, "protection_signals", None)
    if qs is None:
        return 0
    shown = {_dedup_key(v) for theme in qs.themes for v in theme.representative_verbatims}
    kept = [v for v in cp.insight_verbatims if _dedup_key(v) not in shown]
    removed = len(cp.insight_verbatims) - len(kept)
    cp.insight_verbatims = kept
    return removed


def _suppress_duplicate_qol_driver_verbatims(report) -> int:
    """CC-037: qol_drivers (3.3, business_household_impact) has the exact exposure
    protection_signals had before CC-020 -- confirmed live, the Hugging Face run's rendered
    "Increased income/earnings (general)" and "...business profit growth" themes carried the
    identical two verbatims back to back. qol_drivers has no severity concept, so themes are
    kept on whichever ranks higher by frequency -- already the section's own natural ranking
    (theme_tag_batch / merge_batches both sort themes by frequency descending, and
    render_child... add_theme_list renders in that same order), so this doesn't change which
    theme a reader sees a duplicate survive on relative to what they'd expect from the table.
    """
    bh = getattr(report, "business_household_impact", None)
    qs = getattr(bh, "qol_drivers", None) if bh is not None else None
    return _suppress_duplicate_theme_verbatims(qs, rank_key=lambda t: t.frequency)


def _suppress_duplicate_nps_verbatims(report) -> int:
    """CC-048: nps_followup_themes (client_satisfaction) never got the CC-020/037 treatment --
    confirmed live, the Zambia "wonderful services" quote sat in two different promoter-band
    themes' representative_verbatims at once. representative_verbatims here is never rendered
    to a reader directly (client_satisfaction only renders insight_verbatims -- see
    report_render.section_layout.render_client_satisfaction), so this isn't a direct duplicate-
    on-the-page fix; it removes a candidate that was counted twice from the pool write_insight()
    and build_client_voices.pick_diverse_verbatims both draw from, which is what let the same
    quote pull disproportionate weight across three independent, unrelated selection steps in
    the first place. Same mechanism as qol_drivers: no severity concept here either, so themes
    are kept on whichever ranks higher by frequency. Applied to all three bands (promoters,
    passives, detractors) independently -- a verbatim never legitimately spans two bands, so
    there is no case for deduping across them.
    """
    cs = getattr(report, "client_satisfaction", None)
    bands = getattr(cs, "nps_followup_themes", None) if cs is not None else None
    return sum(_suppress_duplicate_theme_verbatims(qs, rank_key=lambda t: t.frequency) for qs in (bands or []))


def translate_report_verbatims(report) -> int:
    """Mutates every Verbatim found anywhere in `report` in place, setting `.language` and
    `.english_gloss`, THEN substitutes the gloss inline everywhere a translated quote is also
    embedded directly in a WrittenText's own prose (see _apply_inline_translations). Returns
    how many verbatims were non-English (i.e. actually got a gloss), for logging. Safe to call
    more than once -- a Verbatim that already has `.language` set is skipped, and the inline
    substitution step is idempotent, so a second pass over the same report costs nothing.

    First suppresses any verbatim duplicated across two themes in the same theme list -- client
    protection's severity tiers (CC-020), business & household impact's qol_drivers (CC-037),
    and client satisfaction's nps_followup_themes bands (CC-048) -- plus client protection's own
    insight_verbatims duplicating its own protection_signals bank (CC-058) -- so a dropped copy
    is never translated.
    """
    _suppress_duplicate_protection_verbatims(report)
    _suppress_insight_verbatims_already_in_protection_signals(report)
    _suppress_duplicate_qol_driver_verbatims(report)
    _suppress_duplicate_nps_verbatims(report)

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
