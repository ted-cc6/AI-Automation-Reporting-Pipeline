"""Scores an entire analysis-ready dataframe, country by country.

Ties together reference_data (workbook parsing), scoring (score + lookup),
and country_policy (the exceptions the Impact team confirmed) into the
CountryPovertyResult list the Poverty Likelihood section schema expects.
"""

from __future__ import annotations

from statistics import mean
from typing import Optional

import pandas as pd

from schemas.common import SectionStatus
from schemas.poverty_likelihood import CountryPovertyResult

from .country_policy import TARGET_LINES, policy_for
from .reference_data import available_line_codes, guide_id_for_survey_version
from .scoring import (
    _scorecard_index_and_ambiguous,
    build_lookup_index,
    build_scorecard_index,
    find_ambiguous_options,
    likelihood_from_index,
    required_questions_for_guide,
    score_from_index,
)

COUNTRY_COL = "Introduction/${Country_question}"
SURVEY_VERSION_COL = "Introduction/SurveyVersion"
PPI_QUESTION_COLS = {q: f"Poverty Likelihood/PPI{q:02d}_resp_value" for q in range(1, 13)}


def client_answers(row: pd.Series) -> dict:
    """Pulls this client's raw PPI answer letters into {question_number: letter_code}."""
    answers = {}
    for q, col in PPI_QUESTION_COLS.items():
        if col not in row.index:
            continue
        v = row[col]
        if v is None or (isinstance(v, float) and pd.isna(v)):
            continue
        s = str(v).strip()
        if s and s.lower() != "nan":
            answers[q] = s.upper()
    return answers


def _dominant_survey_version(country_df: pd.DataFrame) -> Optional[int]:
    versions = country_df[SURVEY_VERSION_COL].dropna().astype(str).str.strip()
    versions = versions[versions != ""]
    if versions.empty:
        return None
    # In every country observed this wave, all clients share one survey version;
    # take the most common one defensively rather than assuming that always holds.
    return int(float(versions.mode().iloc[0]))


def score_country(
    country_code: str,
    country_df: pd.DataFrame,
    scorecard_path: str,
    lookup_path: str,
) -> CountryPovertyResult:
    n_total = len(country_df)
    policy = policy_for(country_code)

    if policy.status == "not_available":
        return CountryPovertyResult(
            country_code=country_code,
            status=SectionStatus.NOT_AVAILABLE,
            status_reason=policy.reason,
            n_total=n_total,
        )

    survey_version = _dominant_survey_version(country_df)
    guide_id = None if survey_version is None else guide_id_for_survey_version(country_code, survey_version, scorecard_path)
    if guide_id is None:
        return CountryPovertyResult(
            country_code=country_code,
            status=SectionStatus.NOT_AVAILABLE,
            status_reason=f"No matching scorecard for survey version {survey_version!r}.",
            n_total=n_total,
        )

    if policy.lines:
        lines_to_score = list(policy.lines)
    else:
        available = available_line_codes(country_code, guide_id, survey_version, scorecard_path)
        lines_to_score = [line for line in TARGET_LINES if line in available]

    if not lines_to_score:
        return CountryPovertyResult(
            country_code=country_code,
            status=SectionStatus.NOT_AVAILABLE,
            status_reason="Scorecard has no populated poverty-line columns for this guide.",
            guide_id=guide_id,
            survey_version=str(survey_version),
            n_total=n_total,
        )

    scorecard_index = build_scorecard_index(country_code, guide_id, survey_version, scorecard_path)
    required_questions = required_questions_for_guide(country_code, guide_id, survey_version, scorecard_path)
    lookup_index = build_lookup_index(country_code, guide_id, lookup_path)

    all_answers = [client_answers(row) for _, row in country_df.iterrows()]

    values: dict = {}
    max_scored = 0
    for line_code in lines_to_score:
        likelihoods = []
        for answers in all_answers:
            result = score_from_index(answers, scorecard_index, line_code, required_questions)
            if result.score is None:
                continue
            pct = likelihood_from_index(lookup_index, result.score, line_code)
            if pct is not None:
                likelihoods.append(pct)
        values[line_code] = mean(likelihoods) if likelihoods else None
        max_scored = max(max_scored, len(likelihoods))

    status = SectionStatus.OK if max_scored == n_total else SectionStatus.PARTIAL
    status_reason = None
    if status == SectionStatus.PARTIAL:
        status_reason = f"{n_total - max_scored} of {n_total} clients could not be scored (incomplete PPI answers)."

    ambiguous = find_ambiguous_options(country_code, guide_id, survey_version, scorecard_path)
    n_unscored_label_conflict = 0
    n_unscored_incomplete = 0
    if ambiguous:
        questions = sorted({q for q, _ in ambiguous})
        question_label = "question" if len(questions) == 1 else "questions"
        has_have = "has" if len(questions) == 1 else "have"
        it_them = "it" if len(questions) == 1 else "them"
        questions_str = ", ".join(str(q) for q in questions)
        ambiguous_note = (
            f"{question_label.capitalize()} {questions_str} of the PPI scorecard {has_have} conflicting "
            f"option labels (two answer options share the same label with different point values), so "
            f"responses to {it_them} could not be scored reliably and were excluded."
        )
        status_reason = f"{status_reason} {ambiguous_note}" if status_reason else ambiguous_note
        status = SectionStatus.PARTIAL

        # CC-025: split the unscored count into the two unrelated causes -- clients unscored
        # PURELY because the ambiguous (question, letter) key was dropped (they would score if
        # it were kept, last-write-wins), vs. everyone else, who fails on some other missing
        # answer. The former is fixable upstream in PPI_scorecards.xlsx; the latter is a
        # data-collection gap. Measured on the poverty line that scored the most clients.
        seen_full, _ = _scorecard_index_and_ambiguous(country_code, guide_id, survey_version, scorecard_path)
        best_line = max(
            lines_to_score,
            key=lambda lc: sum(
                1 for a in all_answers if score_from_index(a, scorecard_index, lc, required_questions).score is not None
            ),
        )
        scored_now = sum(
            1 for a in all_answers if score_from_index(a, scorecard_index, best_line, required_questions).score is not None
        )
        scored_if_typo_fixed = sum(
            1 for a in all_answers if score_from_index(a, seen_full, best_line, required_questions).score is not None
        )
        total_unscored = n_total - max_scored
        n_unscored_label_conflict = max(0, min(scored_if_typo_fixed - scored_now, total_unscored))
        n_unscored_incomplete = total_unscored - n_unscored_label_conflict

    return CountryPovertyResult(
        country_code=country_code,
        status=status,
        status_reason=status_reason,
        metric_type=policy.metric_type,
        guide_id=guide_id,
        survey_version=str(survey_version),
        values=values,
        n_scored=max_scored,
        n_total=n_total,
        n_unscored_label_conflict=n_unscored_label_conflict,
        n_unscored_incomplete=n_unscored_incomplete,
    )


def score_dataframe(df: pd.DataFrame, scorecard_path: str, lookup_path: str) -> list:
    """One CountryPovertyResult per country present in `df`."""
    countries = df[COUNTRY_COL].astype(str).str.strip()
    results = []
    for country_code, country_df in df.groupby(countries):
        if not country_code:
            continue
        results.append(score_country(country_code, country_df, scorecard_path, lookup_path))
    return results
