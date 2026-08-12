"""Turns a client's raw PPI answers into a score, and a score into a poverty likelihood.

`build_scorecard_index` / `build_lookup_index` do the expensive parsing work
once per (country, guide); `score_from_index` / `likelihood_from_index` are
the cheap per-client lookups meant to run in a loop over thousands of rows.
`score_client` / `score_to_likelihood` are the simple single-call versions,
useful for tests and one-off checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from .reference_data import guide_id_for_survey_version, load_lookup, load_scorecard


@dataclass(frozen=True)
class ClientScoreResult:
    score: Optional[int]
    missing_questions: tuple
    guide_id: Optional[str]


def _scorecard_index_and_ambiguous(country_code: str, guide_id: str, survey_version: int, scorecard_path: str):
    """Builds the (question, prefix) -> points map and separately tracks any key that two
    different options both claim with different points -- confirmed on Kenya's Q3
    (options 7 and 9 are both mislabeled "G") and Zambia's Q2 (options 3 and 4 are both
    mislabeled "C"). Those are typos in the source scorecard, not something this code
    should guess a fix for.
    """
    seen: dict = {}
    ambiguous: set = set()
    for opt in load_scorecard(country_code, scorecard_path):
        if opt.guide_id != guide_id or opt.survey_version != survey_version or opt.option_prefix is None:
            continue
        key = (opt.question, opt.option_prefix)
        if key in seen and seen[key] != opt.points:
            ambiguous.add(key)
        seen[key] = opt.points
    return seen, ambiguous


def build_scorecard_index(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> dict:
    """(question, option_prefix) -> {line_code: points}, restricted to one guide AND survey version.

    Filtering by guide_id alone is not enough: confirmed on Ecuador, a single
    guide_id ("ECU2022") is shared by two survey versions whose scorecards
    assign genuinely different points to the same question/option -- an
    artifact of the guide being re-released with a new translation/option
    layout without a new guide_id. survey_version is what the client's own
    answers are actually tagged with, so it's the correct join key.

    Any (question, prefix) key claimed by more than one option with
    different points (see _scorecard_index_and_ambiguous) is dropped
    entirely rather than silently kept as whichever option loaded last --
    that turns a risk of scoring a client against the wrong option's points
    into a safe, visible "missing" instead. Use find_ambiguous_options to
    report which keys were affected.
    """
    seen, ambiguous = _scorecard_index_and_ambiguous(country_code, guide_id, survey_version, scorecard_path)
    return {key: points for key, points in seen.items() if key not in ambiguous}


def find_ambiguous_options(country_code: str, guide_id: str, survey_version: int, scorecard_path: str) -> list:
    """(question, option_prefix) pairs where two options in the source scorecard share the same
    label prefix with different points -- a data-quality issue worth flagging back to whoever
    maintains PPI_scorecards.xlsx, not something build_scorecard_index guesses a fix for.
    """
    _, ambiguous = _scorecard_index_and_ambiguous(country_code, guide_id, survey_version, scorecard_path)
    return sorted(ambiguous)


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
