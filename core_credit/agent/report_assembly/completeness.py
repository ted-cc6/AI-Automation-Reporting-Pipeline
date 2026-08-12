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
        if value.orphan_markers:
            issues.append(f"{path}: orphan citation markers left in text {value.orphan_markers}")
        if value.banned_punctuation:
            issues.append(f"{path}: banned punctuation survived the rewrite retry {value.banned_punctuation}")
        if value.misattributed_quotes:
            issues.append(f"{path}: real quote(s) with a wrong profile attribution {value.misattributed_quotes}")
    return issues


# Substrings that only ever show up in finished prose when the model narrated its own drafting
# or self-correction into the deliverable, instead of just not including a quote it couldn't
# support -- confirmed real: "A female client from Ghana said \"[quote placeholder removed]\"
# -- actually omitting fabricated text" shipped straight into a production report. Case-
# insensitive substring match on purpose: this is meant to be a blunt, hard-to-defeat backstop
# behind the writer's own retry logic (writer.chain._writer_violations), not a subtle one --
# any of these appearing in finished prose is itself a bug worth stopping the build for, not a
# judgment call.
META_TEXT_LEAK_PATTERNS = ("placeholder", "fabricat", "omitting", "as tagged")


class MetaTextLeakError(Exception):
    """Raised when finished prose contains a substring that can only mean the model narrated
    its own drafting process into the deliverable -- see META_TEXT_LEAK_PATTERNS.
    """


def find_meta_text_leaks(report) -> list[str]:
    """One entry per (path, matched pattern) where finished prose leaked meta-commentary about
    its own generation. Empty list means the report is clean.
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
    not just get logged alongside softer completeness issues a human might skim past.
    """
    leaks = find_meta_text_leaks(report)
    if leaks:
        raise MetaTextLeakError(
            f"{len(leaks)} section(s) leaked meta-commentary about their own drafting into finished "
            f"prose -- this must never reach a reader:\n" + "\n".join(leaks)
        )
