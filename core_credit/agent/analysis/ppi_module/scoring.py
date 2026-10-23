"""Turns a client's raw PPI answers into a score, and a score into a poverty likelihood.

`build_scorecard_index` / `build_lookup_index` do the expensive parsing work
once per (country, guide); `score_from_index` / `likelihood_from_index` are
the cheap per-client lookups meant to run in a loop over thousands of rows.
`score_client` / `score_to_likelihood` are the simple single-call versions,
useful for tests and one-off checks.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Iterable, Optional

from .reference_data import ScorecardOption, guide_id_for_survey_version, load_lookup, load_scorecard


@dataclass(frozen=True)
class ClientScoreResult:
    score: Optional[int]
    missing_questions: tuple
    guide_id: Optional[str]


@dataclass(frozen=True)
class LabelOrderMismatch:
    """One scorecard option whose label letter disagrees with its position in the question."""

    question: int
    option_order: int
    option_label: str
    label_prefix: str
    keyed_as: str


class ScorecardLabelWarning(UserWarning):
    """A PPI_scorecards.xlsx label carries the wrong letter -- scored correctly here (CC-068),
    but the workbook itself still needs correcting upstream."""


_WARNED_GUIDES: set = set()


def _order_letter(option_order: int) -> str:
    """1 -> 'A', 9 -> 'I', 26 -> 'Z'. Only used for single-letter positions (see _option_key)."""
    return chr(ord("A") + option_order - 1)


def _option_key(opt: ScorecardOption) -> tuple[Optional[str], Optional[LabelOrderMismatch]]:
    """The answer letter a client's `resp_value` carries for this option, and the mismatch record
    when the label's own letter disagrees with it.

    CC-068: the survey's resp_value is the option's position letter (1st option = A, 9th = I) --
    with this correction every client in every scored country this wave matches the scorecard
    except three who left a question blank -- but a handful of OptionValues labels carry the
    wrong letter. Kenya Q3 option 9 reads "G. Concrete..."
    (should be I, while option 7 really is G), Zambia Q2 option 4 reads "C. Six or more" (should
    be D) and Zambia Q4 option 2 reads "C. No" (should be B). Keyed on the label, those clients
    either matched nothing or collided with another option and were dropped -- every unscored
    Kenya and Zambia client this wave, reported for months as "incomplete answers".

    So for positions 1-26 with a single-letter label, the position letter wins. Positions past 26
    keep the label prefix: guides genuinely disagree on double-letter conventions (Rwanda's 28th
    district is "bb)", Mexico v2 uses "AC"), and the survey follows each guide's own label there.
    """
    prefix = opt.option_prefix
    if prefix is None:
        return None, None
    if opt.option_order <= 26 and len(prefix) == 1:
        expected = _order_letter(opt.option_order)
        if prefix != expected:
            return expected, LabelOrderMismatch(opt.question, opt.option_order, opt.option_label, prefix, expected)
    return prefix, None


def index_options(options: Iterable[ScorecardOption]) -> tuple[dict, set, list]:
    """(question, letter) -> points for one guide+version's options, plus any key two options
    still claim with different points after _option_key's correction (dropped from the index by
    build_scorecard_index rather than silently kept as whichever loaded last), plus every label
    the correction overrode. Pure -- no workbook access -- so it is unit-testable on synthetic
    options.
    """
    seen: dict = {}
    ambiguous: set = set()
    mismatches: list = []
    for opt in options:
        letter, mismatch = _option_key(opt)
        if letter is None:
            continue
        if mismatch:
            mismatches.append(mismatch)
        key = (opt.question, letter)
        if key in seen and seen[key] != opt.points:
            ambiguous.add(key)
        seen[key] = opt.points
    return seen, ambiguous, mismatches


def _guide_options(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> list:
    return [
        o for o in load_scorecard(country_code, scorecard_path)
        if o.guide_id == guide_id and o.survey_version == survey_version
    ]


def build_scorecard_index(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> dict:
    """(question, answer letter) -> {line_code: points}, restricted to one guide AND survey version.

    Filtering by guide_id alone is not enough: confirmed on Ecuador, a single
    guide_id ("ECU2022") is shared by two survey versions whose scorecards
    assign genuinely different points to the same question/option -- an
    artifact of the guide being re-released with a new translation/option
    layout without a new guide_id. survey_version is what the client's own
    answers are actually tagged with, so it's the correct join key.

    Mislabeled options are keyed on their position letter (see _option_key) and reported once
    per guide as a ScorecardLabelWarning. Any key still claimed by two options with different
    points is dropped entirely -- a safe, visible "missing" rather than a client scored against
    the wrong option's points. Use find_ambiguous_options to report those.
    """
    seen, ambiguous, mismatches = index_options(_guide_options(country_code, guide_id, survey_version, scorecard_path))
    guide = (country_code, guide_id, survey_version)
    if mismatches and guide not in _WARNED_GUIDES:
        _WARNED_GUIDES.add(guide)
        detail = ", ".join(f"Q{m.question} option {m.option_order} {m.option_label.strip()!r} keyed as {m.keyed_as}" for m in mismatches)
        warnings.warn(
            f"PPI_scorecards.xlsx {country_code} {guide_id} v{survey_version}: label letter disagrees with "
            f"option position -- {detail}. Scored on the position letter; correct the workbook upstream.",
            ScorecardLabelWarning,
            stacklevel=2,
        )
    return {key: points for key, points in seen.items() if key not in ambiguous}


def find_label_order_mismatches(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> list:
    """Every option in one guide+version whose label letter was overridden by its position."""
    return index_options(_guide_options(country_code, guide_id, survey_version, scorecard_path))[2]


def find_ambiguous_options(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> list:
    """(question, letter) pairs two options still share with different points after the
    position-letter correction -- a data-quality issue worth flagging back to whoever maintains
    PPI_scorecards.xlsx, not something build_scorecard_index guesses a fix for. Empty for every
    guide in the workbook as of CC-068.
    """
    return sorted(index_options(_guide_options(country_code, guide_id, survey_version, scorecard_path))[1])


def required_questions_for_guide(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> list:
    """Which PPI question numbers this guide+version actually asks (10 for most countries, 12 for Mongolia)."""
    return sorted(
        {
            opt.question
            for opt in load_scorecard(country_code, scorecard_path)
            if opt.guide_id == guide_id and opt.survey_version == survey_version
        }
    )


def build_lookup_index(country_code: str, guide_id: str, lookup_path: str) -> dict:
    """score (0-100) -> {line_code: likelihood %}, restricted to one guide.

    When a guide_id has more than one likelihood row for the same score
    (confirmed on Ecuador -- see load_lookup's docstring), the lookup sheet
    itself has no survey-version column to disambiguate, so the most
    recently modified row wins. Rows without a date are treated as oldest.
    """
    best_row_for_score: dict = {}
    for row in load_lookup(country_code, lookup_path):
        if row.guide_id != guide_id:
            continue
        existing = best_row_for_score.get(row.score)
        if existing is None or _is_more_recent(row, existing):
            best_row_for_score[row.score] = row
    return {score: row.likelihoods for score, row in best_row_for_score.items()}


def _is_more_recent(candidate, existing) -> bool:
    candidate_date = candidate.record_modified_date or candidate.record_created_date
    existing_date = existing.record_modified_date or existing.record_created_date
    if candidate_date is None:
        return False
    if existing_date is None:
        return True
    return candidate_date > existing_date


def score_from_index(
    answers: dict,
    scorecard_index: dict,
    line_code: str,
    required_questions: list,
) -> ClientScoreResult:
    """`answers`: {question_number: answer_letter_code_or_None}. The letter code must already be the
    survey's own resp_value field (e.g. 'A', 'AA', 'J') -- uppercase, never a hand-built ID string.
    """
    total = 0.0
    missing = []
    for q in required_questions:
        letter = answers.get(q)
        points = None
        if letter:
            points_for_option = scorecard_index.get((q, letter.upper()))
            if points_for_option is not None:
                points = points_for_option.get(line_code)
        if points is None:
            missing.append(q)
            continue
        total += float(points)

    if missing:
        return ClientScoreResult(score=None, missing_questions=tuple(missing), guide_id=None)
    return ClientScoreResult(score=round(total), missing_questions=tuple(), guide_id=None)


def likelihood_from_index(lookup_index: dict, score: int, line_code: str) -> Optional[float]:
    likelihoods = lookup_index.get(score)
    if likelihoods is None:
        return None
    value = likelihoods.get(line_code)
    return float(value) if value is not None else None


def score_client(
    answers: dict,
    country_code: str,
    survey_version: int,
    line_code: str,
    scorecard_path: str,
    required_questions: Optional[list] = None,
) -> ClientScoreResult:
    """Convenience single-client scorer. For scoring a whole dataframe, build the indexes once with
    build_scorecard_index/required_questions_for_guide and call score_from_index in a loop instead --
    this re-parses the scorecard sheet on every call (cheap thanks to lru_cache, but still avoid it
    in a hot loop).
    """
    guide_id = guide_id_for_survey_version(country_code, survey_version, scorecard_path)
    if guide_id is None:
        return ClientScoreResult(score=None, missing_questions=tuple(sorted(answers)), guide_id=None)

    index = build_scorecard_index(country_code, guide_id, survey_version, scorecard_path)
    if required_questions is None:
        required_questions = required_questions_for_guide(country_code, guide_id, survey_version, scorecard_path)

    result = score_from_index(answers, index, line_code, required_questions)
    return ClientScoreResult(score=result.score, missing_questions=result.missing_questions, guide_id=guide_id)


def score_to_likelihood(
    country_code: str, guide_id: str, score: int, line_code: str, lookup_path: str
) -> Optional[float]:
    """Convenience single-lookup version; see build_lookup_index for the bulk path."""
    index = build_lookup_index(country_code, guide_id, lookup_path)
    return likelihood_from_index(index, score, line_code)
