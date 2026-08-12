"""Checks that every percentage -- and every quote -- a written subsection states actually
traces back to the structured data it was given: the safety net against a hallucinated
headline number or an invented client quote.

Percentage checks are deliberately scoped to percentage-style claims ("42%", "42 percent")
rather than every digit in the text: loan cycles, counts of themes, and similar small
integers show up in prose for structural reasons that have nothing to do with a statistic,
and flagging those would just be noise. A wrong percentage is the actual risk this guards
against.

Quote checks exist because the "grounding by construction" ID-selection mechanism
(used_verbatim_ids) only resolves and verifies the quotes the model SAYS it used -- it does
not stop the model from writing an additional, un-tracked quoted span directly into `text`,
complete with an invented profile attribution ("female, Ghana"). Confirmed for real: two of
three quotes flagged in a production report had no match anywhere in the source data, with
fluent, typo-free English unlike every genuine verbatim elsewhere. check_quote_grounding()
closes that gap the same way check_grounding() already closes it for percentages.
"""

from __future__ import annotations

import re

from schemas.client_satisfaction import NPSResult
from schemas.common import GapComparison, MetricResult, QualitativeSynthesis, RankedOptions, Verbatim
from schemas.poverty_likelihood import CountryVsNationalRate

_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)\s?(?:%|percent)")

_TOLERANCE = 0.6  # allows the writer to round 42.3% to "42 percent" without a false flag

# Matches "..." spans of meaningful length -- a floor of 25 characters skips short quoted
# survey-option labels ("a. Very difficult", "b. Slightly difficult") and single-word
# emphasis that were never meant to represent a client's own words, while still catching the
# real fabricated quotes seen in production (all 40+ characters -- full sentences).
_QUOTED_SPAN_RE = re.compile(r'"([^"]{25,})"')

# Matches a literal citation-style marker like "[3]" left in prose -- these come from the
# numbered verbatim pool the writer is shown, but nothing in the final document prints that
# pool alongside the text, so any marker that survives resolves to nothing for a reader.
_ORPHAN_MARKER_RE = re.compile(r"\[\d+\]")

_EM_DASH = "—"


def _add_both_roundings(acceptable: set, value: float) -> None:
    acceptable.add(round(value))
    acceptable.add(round(value, 1))


def collect_acceptable_percentages(*sources) -> set:
    """Walks any mix of MetricResult / NPSResult / QualitativeSynthesis objects and collects
    every percentage that could legitimately appear in prose describing them: overall, every
    segment cut, any benchmark value, and (for qualitative themes) each theme's share of
    respondents -- e.g. "40% of quoted clients raised X" is a real, grounded number when it
    matches a ThemeFinding.share_of_respondents, not a hallucination.
    """
    acceptable: set = set()
    for source in sources:
        if source is None:
            continue
        if isinstance(source, MetricResult):
            if source.overall.share is not None:
                _add_both_roundings(acceptable, source.overall.share * 100)
            for seg in source.by_segment:
                if seg.share is not None:
                    _add_both_roundings(acceptable, seg.share * 100)
            if source.benchmark and source.benchmark.external_mfi_index is not None:
                _add_both_roundings(acceptable, source.benchmark.external_mfi_index * 100)
            if source.benchmark_comparable_value is not None and source.benchmark_comparable_value.share is not None:
                _add_both_roundings(acceptable, source.benchmark_comparable_value.share * 100)
        elif isinstance(source, NPSResult):
            _add_both_roundings(acceptable, source.score)  # already on a -100..100 scale
            for share in (source.promoter_share, source.passive_share, source.detractor_share):
                _add_both_roundings(acceptable, share * 100)
            for seg in source.by_segment:
                if seg.mean is not None:
                    _add_both_roundings(acceptable, seg.mean)  # per-segment NPS score, -100..100 scale
            if source.benchmark and source.benchmark.external_mfi_index is not None:
                _add_both_roundings(acceptable, source.benchmark.external_mfi_index)  # already NPS-scale
        elif isinstance(source, QualitativeSynthesis):
            for theme in source.themes:
                if theme.share_of_respondents is not None:
                    _add_both_roundings(acceptable, theme.share_of_respondents * 100)
        elif isinstance(source, CountryVsNationalRate):
            if source.portfolio_poverty_likelihood is not None:
                _add_both_roundings(acceptable, source.portfolio_poverty_likelihood)
            if source.national_poverty_rate is not None:
                _add_both_roundings(acceptable, source.national_poverty_rate)
        elif isinstance(source, RankedOptions):
            for opt in source.options:
                _add_both_roundings(acceptable, opt.share * 100)
        elif isinstance(source, GapComparison):
            if source.group_a_share is not None:
                _add_both_roundings(acceptable, source.group_a_share * 100)
            if source.group_b_share is not None:
                _add_both_roundings(acceptable, source.group_b_share * 100)
            if source.gap is not None:
                _add_both_roundings(acceptable, abs(source.gap) * 100)
    return acceptable


def check_grounding(text: str, acceptable: set) -> list:
    """Every percentage mentioned in `text` that doesn't match (within rounding) a number in
    `acceptable`. Empty list means every percentage claim traces back to real data.
    """
    flagged = []
    for match in _PERCENT_RE.finditer(text):
        value = float(match.group(1))
        if not any(abs(value - a) < _TOLERANCE for a in acceptable):
            flagged.append(match.group(0))
    return flagged


_QUOTE_MARK_TRANSLATION = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"'})


def _normalize_quote_marks(s: str) -> str:
    """Curly and straight quote marks are the same character to a human but not to `==` --
    confirmed a real false positive from this: a genuine pool verbatim used a curly apostrophe
    ("j’ai"), the model's reproduction came back with a straight one ("j'ai"), and the exact
    match in check_quote_grounding flagged a real quote as fabricated.
    """
    return s.translate(_QUOTE_MARK_TRANSLATION)


def check_quote_grounding(text: str, pool: list[Verbatim]) -> list:
    """Every quoted span (25+ characters) in `text` that doesn't match a real Verbatim's quote
    in `pool`. Matching is exact after whitespace-trimming and quote-mark normalization -- the
    system prompt requires the model to reproduce a real quote character-for-character, so a
    genuine quote from the pool will match exactly; anything that doesn't match was either
    invented outright or altered enough that it's no longer the client's real words. Empty list
    means every quoted span traces back to a real client record.
    """
    real_quotes = {_normalize_quote_marks(v.quote.strip()) for v in pool}
    flagged = []
    for match in _QUOTED_SPAN_RE.finditer(text):
        candidate = match.group(1).strip()
        if _normalize_quote_marks(candidate) not in real_quotes:
            flagged.append(candidate)
    return flagged


def check_profile_grounding(text: str, pool: list[Verbatim]) -> list:
    """For every real, pool-matched quote found in `text`, checks that no country OTHER than
    the quote's own real country is mentioned near it. Catches a failure check_quote_grounding
    can't see: a genuine quote, reproduced correctly, wrapped in an invented attribution.
    Confirmed for real: a production report quoted a real Malawi client's real words as "a
    female Ugandan caregiver from a PWD household in Malawi" -- the quote text matched the pool
    exactly, "Ugandan" did not match anything about that client at all.
    """
    from benchmark_module.mapping import COUNTRY_CODE_TO_NAME, COUNTRY_NAME_TO_CODE

    all_country_names = set(COUNTRY_NAME_TO_CODE.keys())
    flagged = []
    for v in pool:
        if not v.country:
            continue
        idx = text.find(v.quote)
        if idx == -1:
            continue
        window = text[max(0, idx - 200) : idx]
        correct_name = COUNTRY_CODE_TO_NAME.get(v.country, v.country)
        wrong = {name for name in all_country_names if name in window} - {correct_name}
        if wrong:
            flagged.append(f"quote attributed near {sorted(wrong)} but the real record is {correct_name!r}")
    return flagged


def check_orphan_markers(text: str) -> list:
    """Every literal '[N]' citation-style marker left in `text`. Empty list means none survived
    into the final prose.
    """
    return _ORPHAN_MARKER_RE.findall(text)


def check_banned_punctuation(text: str) -> list:
    """Every em dash and semicolon in `text` -- the template's house style bans both in favor
    of plain sentences (period, comma, "and"/"but"). Returns one entry per occurrence so the
    count itself is visible in a completeness report, not just whether any exist.
    """
    return [_EM_DASH for _ in range(text.count(_EM_DASH))] + [";" for _ in range(text.count(";"))]
