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

# Every "..." pair in the text, matched left to right so a closing quote mark can never be
# read as the opening of the next span. The length filter is applied to the matched spans
# afterward (see _MIN_QUOTE_LEN), NOT baked into the pattern: an earlier version required 25+
# characters *inside* the quotes for the pattern to match at all, so a short quoted string (a
# metric box label like "very much improved", 18 chars) was skipped entirely and re.finditer
# then paired ITS closing quote with the opening quote of the next real verbatim, swallowing
# 300-640 characters of ordinary prose as one bogus span. Found during CC-001 verification
# (docs/core_credit_report_spec.md CC-005): it fired on 8 of 8 runs of one insight.
_QUOTED_SPAN_RE = re.compile(r'"([^"]*)"')

# A quoted span (or a pool verbatim) shorter than this is not treated as a client's own words:
# it is a survey-option label ("a. Very difficult"), a quoted metric term ("very much
# improved"), or single-word emphasis. Real fabricated verbatims seen in production are all
# full sentences, 40+ characters. Gates both check_quote_grounding (which spans to test) and
# check_profile_grounding (which pool verbatims are searchable), so the two stay consistent.
_MIN_QUOTE_LEN = 25

# The start of a quote's own attribution clause, scanning back from the quote: everything up to
# and including a sentence terminator (with any trailing closing bracket/quote and whitespace)
# or a hard line break belongs to an earlier sentence. check_profile_grounding also cuts at the
# previous quoted span's closing quote mark, whichever is later.
_CLAUSE_BOUNDARY_RE = re.compile(r'[.!?]["\')\]]*\s+|\n')

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


# Terminal punctuation stripped before the exact-match test. A sentence period placed inside
# the closing quote mark ("...loan amount.") is correct English typography, not a different
# quote from "...loan amount", so a trailing run of these is normalised away on BOTH the
# candidate span and the pool verbatim. Only the trailing run -- internal punctuation is left
# intact, so a verbatim with a word (and its comma) dropped from the middle still fails to
# match and reads as fabrication, not a partial quote.
_TERMINAL_PUNCT = " .,;:!?…"


def _match_core(s: str) -> str:
    return _normalize_quote_marks(s).strip().rstrip(_TERMINAL_PUNCT)


def _classify_quoted_spans(text: str, pool: list[Verbatim]) -> tuple[list, list]:
    """(ungrounded, partial) for every quoted span of real-sentence length in `text`.

      ungrounded -- traces to no real client record, whole or in part: fabrication.
      partial    -- an exact contiguous substring of a real pool verbatim: the client's real
                    words, but only a fragment of them.

    A span that reproduces a pool verbatim exactly (modulo quote-mark style and a moved
    terminal period, see _match_core) is neither -- it is clean.
    """
    normalized_text = _normalize_quote_marks(text)
    pool_norm = [_normalize_quote_marks(v.quote.strip()) for v in pool]
    exact = {_match_core(p) for p in pool_norm}
    ungrounded: list = []
    partial: list = []
    for match in _QUOTED_SPAN_RE.finditer(normalized_text):
        span = match.group(1).strip()
        if len(span) < _MIN_QUOTE_LEN:
            continue
        core = _match_core(span)
        if core in exact:
            continue
        if core and any(core in whole for whole in pool_norm):
            partial.append(span)
        else:
            ungrounded.append(span)
    return ungrounded, partial


def check_quote_grounding(text: str, pool: list[Verbatim]) -> list:
    """Every quoted span of real-sentence length (>= _MIN_QUOTE_LEN) in `text` that traces to
    NO real client verbatim, whole or in part -- i.e. fabrication. The system prompt requires
    the model to reproduce a real quote character-for-character; a span that does (allowing for
    quote-mark style and a moved terminal period) is clean, and a span that is an exact
    contiguous FRAGMENT of a real verbatim is a partial quote (check_partial_quotes), not an
    ungrounded one. Empty list means nothing in `text` was invented.

    Spans are paired first (every "..." pair, left to right) and only then filtered by length,
    so a short quoted term earlier in the text cannot desync the pairing for the spans that
    follow it -- see _QUOTED_SPAN_RE.
    """
    return _classify_quoted_spans(text, pool)[0]


def check_partial_quotes(text: str, pool: list[Verbatim]) -> list:
    """Every quoted span in `text` that is an EXACT CONTIGUOUS substring of a real pool verbatim
    but not the whole of one -- the client's real words, quoted only in fragment. This is not
    fabrication (check_quote_grounding) and not a house-style violation: it never feeds
    _writer_violations, because the corrective rewrite replaces quotes rather than restoring
    dropped context and would likely make a truncation worse. It is surfaced for a human
    reviewer, because a fragment can change what a client said -- "the money I was waiting for"
    lifted out of a longer complaint about a broken promise reads very differently from the
    whole. Every fragment is flagged regardless of how much of the source it covers: meaning
    distortion does not scale with length, so there is no coverage threshold to gate on.
    """
    return _classify_quoted_spans(text, pool)[1]


def check_profile_grounding(text: str, pool: list[Verbatim]) -> list:
    """For every real, pool-matched quote found in `text`, checks that no country OTHER than
    the quote's own real country is mentioned in the attribution clause that introduces it.
    Catches a failure check_quote_grounding can't see: a genuine quote, reproduced correctly,
    wrapped in an invented attribution. Confirmed for real: a production report quoted a real
    Malawi client's real words as "a female Ugandan caregiver from a PWD household in Malawi" --
    the quote text matched the pool exactly, "Ugandan" did not match anything about that client.

    Two guards added after CC-001 verification found this check unusable at a 3/8 false-positive
    rate (docs/core_credit_report_spec.md CC-005):
      - Only pool verbatims of real-sentence length (>= _MIN_QUOTE_LEN) are searched, and the
        match must be word-bounded. A one-letter junk verbatim (a real client answer of just
        "B") was matching inside "BUSINESS" in an unrelated, correctly-attributed quote.
      - The country scan is scoped to this quote's own attribution clause -- from the previous
        quoted span's closing quote mark, or the last sentence boundary, up to this quote --
        not a flat 200-character lookback, which bled a neighbouring (also correct) quote's
        country in.
    """
    from benchmark_module.mapping import COUNTRY_CODE_TO_NAME, COUNTRY_NAME_TO_CODE

    all_country_names = set(COUNTRY_NAME_TO_CODE.keys())
    normalized = _normalize_quote_marks(text)
    flagged = []
    for v in pool:
        quote = _normalize_quote_marks(v.quote.strip())
        if not v.country or len(quote) < _MIN_QUOTE_LEN:
            continue
        m = re.search(r"(?<!\w)" + re.escape(quote) + r"(?!\w)", normalized)
        if m is None:
            continue
        idx = m.start()
        lookback = normalized[max(0, idx - 200) : idx]
        intro = lookback[:-1] if lookback.endswith('"') else lookback  # drop this quote's own opening mark
        clause_start = intro.rfind('"') + 1  # after the previous quoted span, or 0 if none
        for boundary in _CLAUSE_BOUNDARY_RE.finditer(intro):
            clause_start = max(clause_start, boundary.end())
        window = intro[clause_start:]
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
