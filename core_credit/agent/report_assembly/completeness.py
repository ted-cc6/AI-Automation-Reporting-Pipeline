"""Walks an assembled CoreCreditImpactReport for real, already-known-to-matter issues --
not a new check invented for this step, just aggregating signals every WrittenText already
carries (word_count/within_cap, ungrounded_percentages, ungrounded_quotes, orphan_markers)
into one punch list a human reviewer can work from, instead of digging through 12 separate
section outputs by hand.

Pydantic's own validation already guarantees the report is structurally complete (a missing
required section, or a field of the wrong type, fails at construction time, before this module
ever runs) -- what this adds is a review pass over the two things Pydantic can't check on its
own: whether an optional WrittenText field that SHOULD have been filled in was left None, and
which of the ones that were filled in are worth a second look before publishing.
"""

from __future__ import annotations

import re
from typing import get_args

from pydantic import BaseModel

from schemas.common import WrittenText


def _is_written_text_field(annotation) -> bool:
    return annotation is WrittenText or WrittenText in get_args(annotation)


def _walk(obj, path: str = ""):
    """Yields (path, value) for every field found while recursing through a Pydantic model /
    list structure -- value is a WrittenText instance, or None where one was expected but
    missing.
    """
    if isinstance(obj, BaseModel):
        for name, field in obj.__class__.model_fields.items():
            value = getattr(obj, name)
            full_path = f"{path}.{name}" if path else name
            if _is_written_text_field(field.annotation):
                yield full_path, value
            elif isinstance(value, (BaseModel, list)):
                yield from _walk(value, full_path)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _walk(item, f"{path}[{i}]")


def completeness_report(report) -> list[str]:
    """One line per real issue: a WrittenText field left unwritten, over its template word
    cap, or carrying a percentage that didn't trace back to the data it was given. Empty list
    means every subsection in the whole report is complete and clean.
    """
    issues = []
    for path, value in _walk(report):
        if value is None:
            issues.append(f"{path}: MISSING -- expected a WrittenText, found none")
            continue
        if not value.within_cap:
            issues.append(f"{path}: {value.word_count} words, over the template's target cap")
        if value.ungrounded_percentages:
            issues.append(f"{path}: ungrounded percentages {value.ungrounded_percentages}")
        if value.ungrounded_quotes:
            issues.append(f"{path}: ungrounded quotes (not found in the source verbatim pool) {value.ungrounded_quotes}")
        if value.partial_quotes:
            issues.append(f"{path}: partial quote(s) -- a real verbatim quoted only in fragment, for a reviewer to check {value.partial_quotes}")
        if value.orphan_markers:
            issues.append(f"{path}: orphan citation markers left in text {value.orphan_markers}")
        if value.banned_punctuation:
            issues.append(f"{path}: banned punctuation survived the rewrite retry {value.banned_punctuation}")
        if value.misattributed_quotes:
            issues.append(f"{path}: real quote(s) with a wrong profile attribution {value.misattributed_quotes}")
    issues.extend(find_dangling_attributions(report))  # CC-058: soft, see its own docstring
    return issues


# Substrings that only ever show up in finished prose when the model narrated its own drafting
# or self-correction into the deliverable, instead of just not including a quote it couldn't
# support -- confirmed real: "A female client from Ghana said \"[quote placeholder removed]\"
# -- actually omitting fabricated text" shipped straight into a production report. Case-
# insensitive substring match on purpose: this is meant to be a blunt, hard-to-defeat backstop
# behind the writer's own retry logic (writer.chain._writer_violations), not a subtle one --
# any of these appearing in finished prose is itself a bug worth stopping the build for, not a
# judgment call.
#
# CC-044: this phrase list is inherently reactive -- each entry is a wording caught after the
# fact, and a differently-worded instance of the same defect sails straight through. A second,
# real incident proved it: "though the exact phrasing should be drawn from the verbatim pool
# rather than summarized here without quotation" is the model addressing itself in fluent,
# unbracketed prose -- none of the four original patterns match a single word of it. The five
# entries below close that specific gap (still just wording, so still reactive by nature).
# CC-044 originally paired this with a structural check for the same class of defect; CC-058
# redesigned and downgraded that check (find_dangling_attributions, further down) after live
# false positives showed "no quote nearby" wasn't the right signal -- see its own docstring.
META_TEXT_LEAK_PATTERNS = (
    "placeholder", "fabricat", "omitting", "as tagged",
    "should be drawn from", "rather than summarized here", "verbatim pool",
    "without quotation", "should be quoted",
)


_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


class MetaTextLeakError(Exception):
    """Raised when finished prose contains a substring that can only mean the model narrated
    its own drafting process into the deliverable -- see META_TEXT_LEAK_PATTERNS.
    """


def find_meta_text_leaks(report) -> list[str]:
    """One entry per (path, pattern) where finished prose contains a literal phrase from
    META_TEXT_LEAK_PATTERNS. Empty list means the report is clean. Phrase-only on purpose --
    see CC-058 on why the structural companion this used to carry (find_dangling_attributions,
    below) was split out into a soft completeness issue instead of living here.
    """
    leaks = []
    for path, value in _walk(report):
        if value is None:
            continue
        lowered = value.text.lower()
        for pattern in META_TEXT_LEAK_PATTERNS:
            if pattern in lowered:
                leaks.append(f"{path}: contains {pattern!r} -- {value.text!r}")
    return leaks


def raise_on_meta_text_leaks(report) -> None:
    """Hard gate: raises MetaTextLeakError if any finished prose leaked meta-commentary about
    its own generation. Meant to be called right after assembly, before anything downstream
    (translation, render) touches the report -- this class of defect should stop the build,
    not just get logged alongside softer completeness issues a human might skim past. Kept
    hard specifically because a phrase-list hit is unambiguous drafting commentary, not a
    judgment call -- unlike find_dangling_attributions below, which is a prose-quality signal,
    not a fabrication/leak one, and is deliberately not wired into this gate.
    """
    leaks = find_meta_text_leaks(report)
    if leaks:
        raise MetaTextLeakError(
            f"{len(leaks)} section(s) leaked meta-commentary about their own drafting into finished "
            f"prose -- this must never reach a reader:\n" + "\n".join(leaks)
        )


# CC-058: redesigned from CC-044/051's "no quote in the next N sentences," which keyed on the
# wrong signal and cost more than it caught. Live evidence from two real regenerations: Rwanda
# -- "A male client in Rwanda, Climate-shock-affected, reported selling land as a coping
# route..." -- has no quote at all and is completely legitimate (a real, specific, sanctioned
# paraphrase); Guatemala -- "A female client in Guatemala described this directly." -- also has
# no quote, but is a genuine defect: there is nothing here, no predicate content beyond the
# reporting verb itself. The real signal was never "no quote nearby," it was always "named a
# client, then said nothing about them" -- a dangling attribution, not a missing citation. This
# version checks a single sentence's own grammar instead of scanning a multi-sentence window:
# a reporting verb whose only object is a bare demonstrative pronoun, with at most two trailing
# words before the sentence ends. Real content of any kind -- a quote, a gerund-headed action
# ("selling land"), a specific noun -- means it isn't dangling, however short the sentence.
_REPORTING_VERBS = r"described|reported|said|explained|shared|noted|stated|mentioned|recounted|valued|indicated"
_DANGLING_ATTRIBUTION_RE = re.compile(
    r"\b(?:" + _REPORTING_VERBS + r")\s+(?:this|that|it)\b(?:\s+\w+){0,2}\s*[.!?]"
)

# Still the anchor for "this sentence is citing a named client" -- unchanged from CC-044/051.
# See its own history there for why it's scoped to "client"/"in" specifically.
_CLIENT_ATTRIBUTION_RE = re.compile(
    r"\b(?:[Aa]|[Oo]ne)\s+(?:female|male)\s+client\b[^.!?\"]{0,60}?\bin\s+([A-Z][A-Za-z]+)"
)


def find_dangling_attributions(report) -> list[str]:
    """One entry per sentence that names a client by country (_CLIENT_ATTRIBUTION_RE) and, in
    that same sentence, reports on them with nothing but a bare demonstrative pronoun as the
    object -- the writer named who, never said what. A soft completeness issue (see
    completeness_report), not a hard gate: this is a prose-quality judgment call, not the
    unambiguous fabrication/leak class raise_on_meta_text_leaks exists for, and a hard gate
    that kills a completed run and forces downstream regeneration over a phrasing judgment
    costs more than the defect it prevents.
    """
    issues = []
    for path, value in _walk(report):
        if value is None:
            continue
        for sent in _SENTENCE_SPLIT_RE.split(value.text):
            if _CLIENT_ATTRIBUTION_RE.search(sent) and _DANGLING_ATTRIBUTION_RE.search(sent):
                issues.append(f"{path}: names a client with a dangling attribution -- {sent!r}")
    return issues


# CC-044: the eight theme names are a fixed, known set -- the executive summary narrative
# should only ever reference them verbatim. Confirmed real: "Client Wellbeing outcomes anchor
# this year's results" opened a production executive summary; there is no "Client Wellbeing"
# theme, only "Child Wellbeing". Each anchor word below is meaningless in this report's
# vocabulary except as the tail of its one real theme name, so a capitalized occurrence with
# any other qualifier is a garbled or fabricated theme reference. "Financial Access",
# "Business & Household Impact", "Agency", and "Resilience" have no distinctive single-word
# tail that could plausibly be confused with another theme's name, so they're not checked here.
EXECUTIVE_SUMMARY_THEME_NAMES = (
    "Financial Access", "Poverty Likelihood", "Business & Household Impact",
    "Child Wellbeing", "Client Protection", "Agency", "Resilience", "Client Satisfaction",
)

_THEME_NAME_ANCHORS = {
    "Wellbeing": "Child Wellbeing",
    "Likelihood": "Poverty Likelihood",
    "Satisfaction": "Client Satisfaction",
}


class UnknownThemeNameError(Exception):
    """Raised when the executive summary narrative names a theme-like phrase that isn't one of
    the eight real theme names -- see EXECUTIVE_SUMMARY_THEME_NAMES.
    """


def find_unknown_theme_references(report) -> list[str]:
    """Scans the executive summary's analysis_text for a capitalized theme-name anchor word
    (Wellbeing, Likelihood, Satisfaction) not immediately preceded by its one real qualifier.
    Empty list means every theme reference in the narrative names a real theme.
    """
    es = getattr(report, "executive_summary", None)
    text_obj = getattr(es, "analysis_text", None) if es is not None else None
    if text_obj is None:
        return []

    issues = []
    for anchor, real_name in _THEME_NAME_ANCHORS.items():
        for match in re.finditer(r"\b([A-Z][A-Za-z]*)\s+" + anchor + r"\b", text_obj.text):
            phrase = f"{match.group(1)} {anchor}"
            if phrase != real_name:
                issues.append(
                    f"executive_summary.analysis_text: {phrase!r} is not a real theme name -- "
                    f"the real theme is {real_name!r}"
                )
    return issues


def raise_on_unknown_theme_references(report) -> None:
    """Hard gate: raises UnknownThemeNameError if the executive summary narrative names a theme
    that doesn't exist. Meant to be called alongside raise_on_meta_text_leaks, before anything
    downstream touches the report.
    """
    issues = find_unknown_theme_references(report)
    if issues:
        raise UnknownThemeNameError(
            f"{len(issues)} fabricated theme reference(s) in the executive summary narrative:\n"
            + "\n".join(issues)
        )


# CC-053: Child Wellbeing is the one theme in the executive summary's data-at-a-glance whose
# headline_value is scored among caregivers only -- every other theme's figure covers the whole
# client base (see build_executive_summary.py's own theme_scores construction). Confirmed real:
# a production executive summary stated "Child Wellbeing is strong at 93.5%" with no scope,
# sitting next to six genuinely all-client figures with nothing to distinguish it -- exactly the
# CC-004 violation ("every figure that describes a subgroup must name the subgroup it
# describes"), just never checked here before. A gate is feasible specifically because this is
# narrow: one known theme, one known subsection, one known qualifier word to look for -- CC-004
# in general (any subgroup figure anywhere in the report) has no comparable gate and this isn't
# proposed as one; it only covers this one instance.
class MissingCaregiverScopeError(Exception):
    """Raised when the executive summary states the Child Wellbeing figure without noting it is
    scoped to caregivers -- see find_missing_caregiver_scope.
    """


def find_missing_caregiver_scope(report) -> list[str]:
    """Scans the executive summary's analysis_text: any sentence naming the Child Wellbeing
    theme must also say "caregiver" somewhere in that same sentence. Empty list means the scope
    was stated wherever the theme was.
    """
    es = getattr(report, "executive_summary", None)
    text_obj = getattr(es, "analysis_text", None) if es is not None else None
    if text_obj is None:
        return []

    issues = []
    for sent in _SENTENCE_SPLIT_RE.split(text_obj.text):
        if "Child Wellbeing" in sent and "caregiver" not in sent.lower():
            issues.append(
                f"executive_summary.analysis_text: states Child Wellbeing with no caregiver "
                f"scope -- {sent!r}"
            )
    return issues


def raise_on_missing_caregiver_scope(report) -> None:
    """Hard gate: raises MissingCaregiverScopeError if the executive summary states Child
    Wellbeing's figure without its caregiver scope. Meant to be called alongside
    raise_on_meta_text_leaks / raise_on_unknown_theme_references.
    """
    issues = find_missing_caregiver_scope(report)
    if issues:
        raise MissingCaregiverScopeError(
            f"{len(issues)} Child Wellbeing reference(s) in the executive summary missing "
            f"their caregiver scope:\n" + "\n".join(issues)
        )
