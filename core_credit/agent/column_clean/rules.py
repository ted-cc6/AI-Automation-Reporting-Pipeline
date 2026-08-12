"""
Column classification engine for Column Cleaner.

This is the deterministic, rule-based half of the agent. It knows the shape
of a KoboToolbox/ODK-style survey export -- one export column per
(section, question-code, field) triple, e.g.:

    Financial Access/ACCESS01_desc
    Financial Access/ACCESS01_resp_value
    Resilience/RESILIENCE03_resp_1_en

-- and classifies every column as KEEP or DROP without ever looking at the
question codes themselves. That's the point: a future quarter's export can
add, remove, or rename question codes and this still works, because the
rules key off the *suffix* (``_resp_value``, ``_desc``, ...), not the code.

Nothing in here calls the LLM. The agent (run_agent.py) hands the LLM only
the columns this module can't confidently classify.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional


# --------------------------------------------------------------------------
# Naming-convention patterns
# --------------------------------------------------------------------------

# "Section/CODE_suffix" -- the standard single-answer question block.
CODE_SUFFIX_RE = re.compile(
    r"^(?P<section>[^/]+)/(?P<code>.+?)_"
    r"(?P<suffix>desc|question_id|question_loc|question_en|resp_id|resp_loc|resp_en|resp_value)$"
)

# "Section/CODE_exists" -- per-country applicability flag (e.g. PPI scorecard items).
EXISTS_RE = re.compile(r"^(?P<section>[^/]+)/(?P<code>.+?)_exists$")

# "Section/CODE_resp_<N>_<id|loc|en>[.1]" -- one column per option of a
# multi-select ("select multiple") question.
MULTISELECT_RE = re.compile(
    r"^(?P<section>[^/]+)/(?P<code>.+?)_resp_(?P<optnum>\d+)_(?P<subtype>id|loc|en)(?P<dup>\.1)?$"
)

# "Section/${CODE_question_loc}" -- Kobo's dynamic-label re-reference to a
# sibling column's *_question_loc value. Always a duplicate of question_id
# metadata, never real respondent data. Note this is narrower than "contains
# '${' " -- a column like "Introduction/${Country_question}" does NOT match
# (it ends in "_question}", not "_question_loc}") and is deliberately left
# for the unmatched/default-keep path below, because in some survey designs
# a ${...} reference holds a real answer, not just a metadata echo.
DYNAMIC_LABEL_METADATA_RE = re.compile(r"/\$\{[^}]*_question_loc\}$")

# Suffixes from CODE_SUFFIX_RE that are always static question/answer-label
# metadata -- identical across every row for a given question, so they add
# nothing per respondent. Kept once in a data dictionary instead, never in
# the trimmed file.
STATIC_METADATA_SUFFIXES = {
    "desc",
    "question_id",
    "question_loc",
    "question_en",
    "resp_id",
    "resp_loc",
}

# Suffixes that carry the respondent's actual answer -- tentatively kept,
# subject to the empty-column check below.
RESPONDENT_DATA_SUFFIXES = {"resp_en", "resp_value"}


@dataclass
class ColumnRecord:
    index: int
    name: str
    section: Optional[str]
    suffix: Optional[str]
    null_pct: float
    cardinality: int
    cardinality_capped: bool
    samples: list = field(default_factory=list)
    action: str = "keep"  # "keep" | "drop"
    reason: str = ""
    confidence: str = "rule"  # "rule" | "review"


def _section_of(name: str) -> Optional[str]:
    return name.split("/", 1)[0] if "/" in name else None


def classify_column(
    name: str,
    null_pct: float,
    config: dict,
) -> tuple[str, str, str]:
    """Classify one column. Returns (action, reason, confidence).

    action:      "keep" | "drop"
    confidence:  "rule" (the pattern rules are confident) or
                 "review" (unrecognized shape -- defaults to keep, but the
                 agent should have an LLM look at it)
    """
    excluded_sections = {s.lower() for s in config.get("excluded_sections", [])}
    always_drop = set(config.get("always_drop_column_names", []))
    always_keep = set(config.get("always_keep_column_names", []))

    section = _section_of(name)

    # 1. Whole-section exclusion (e.g. the Voluntary Savings module) wins
    #    over everything else, regardless of the column's own suffix.
    if section and section.lower() in excluded_sections:
        return "drop", f"excluded section: {section}", "rule"

    # 2. Explicit boilerplate columns.
    if name in always_drop:
        return "drop", "configured always-drop (survey-tool boilerplate)", "rule"

    # 3. Explicit structural/audit columns -- never dropped by the null
    #    check below, since an empty _id or _uuid means something is wrong
    #    with the export, not that the column is safe to discard.
    if name in always_keep:
        return "keep", "system/audit identifier (always kept)", "rule"

    # 4. Dynamic-label metadata duplicate.
    if DYNAMIC_LABEL_METADATA_RE.search(name):
        return "drop", "duplicate of question_id (dynamic label reference)", "rule"

    # 5. Multi-select option column.
    m = MULTISELECT_RE.match(name)
    if m:
        subtype = m.group("subtype")
        if subtype in ("id", "loc"):
            return "drop", "multiselect option id/local-language duplicate", "rule"
        # subtype == "en" -- the human-readable selected option.
        if null_pct >= 100.0:
            return "drop", "empty - no data in this file", "rule"
        return "keep", "multiselect option (English label) - respondent data", "rule"

    # 6. Per-country applicability flag.
    m = EXISTS_RE.match(name)
    if m:
        if null_pct >= 100.0:
            return "drop", "empty - no data in this file", "rule"
        return "keep", "scorecard applicability flag", "rule"

    # 7. Standard single-answer question block.
    m = CODE_SUFFIX_RE.match(name)
    if m:
        suffix = m.group("suffix")
        if suffix in STATIC_METADATA_SUFFIXES:
            return "drop", f"static question/answer metadata ({suffix})", "rule"
        # suffix in RESPONDENT_DATA_SUFFIXES
        if null_pct >= 100.0:
            return "drop", "empty - no data in this file", "rule"
        return "keep", f"respondent answer ({suffix})", "rule"

    # 8. Anything else: unrecognized shape. Safe default is to keep it and
    #    flag it for review -- we'd rather over-keep than silently lose a
    #    column a future report needs. A genuinely empty unmatched column
    #    is still auto-dropped, since "empty" is unambiguous regardless of
    #    naming convention.
    if null_pct >= 100.0:
        return "drop", "empty - no data in this file", "rule"
    return "keep", "unrecognized naming pattern - needs review", "review"


def detect_delimiter(sample_line: str, candidates: str = ";,|\t") -> str:
    """Pick the delimiter that splits the header line into the most fields.

    Works on a single raw text line (the file's first line) so it doesn't
    require loading anything. Falls back to comma if nothing else looks
    plausible.
    """
    best_delim, best_count = ",", 1
    for delim in candidates:
        count = sample_line.count(delim)
        if count > best_count:
            best_delim, best_count = delim, count
    return best_delim
