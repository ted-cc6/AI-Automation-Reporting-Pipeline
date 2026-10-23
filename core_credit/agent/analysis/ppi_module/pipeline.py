"""Scores an entire analysis-ready dataframe, country by country.

Ties together reference_data (workbook parsing), scoring (score + lookup),
and country_policy (the exceptions the Impact team confirmed) into the
CountryPovertyResult list the Poverty Likelihood section schema expects.
"""

from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Optional

import pandas as pd

from schemas.common import SectionStatus
from schemas.poverty_likelihood import CountryPovertyResult

from .country_policy import TARGET_LINES, policy_for
from .reference_data import available_line_codes, guide_id_for_survey_version
from .scoring import (
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

    ambiguous = set(find_ambiguous_options(country_code, guide_id, survey_version, scorecard_path))

    values: dict = {}
    scored_per_line: dict = {}
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
        scored_per_line[line_code] = len(likelihoods)
    best_line = max(lines_to_score, key=lambda lc: scored_per_line[lc])
    max_scored = scored_per_line[best_line]

    # CC-069: the reason is computed per client from the data, on the line that scored the most
    # clients -- never assumed. The previous fixed "(incomplete PPI answers)" text, and CC-025's
    # label-conflict/incomplete split derived from it, misreported every unscored Kenya and
    # Zambia client: none had an incomplete answer, all had chosen a mislabeled scorecard option.
    unscored_reasons: Counter = Counter()
    for answers in all_answers:
        reason = unscored_reason(answers, scorecard_index, lookup_index, best_line, required_questions, ambiguous)
        if reason:
            unscored_reasons[reason] += 1

    status = SectionStatus.OK if max_scored == n_total else SectionStatus.PARTIAL
    status_reason = None
    if status == SectionStatus.PARTIAL:
        detail = ", ".join(f"{count} {reason}" for reason, count in unscored_reasons.most_common())
        status_reason = f"{n_total - max_scored} of {n_total} clients could not be scored: {detail}."

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
        unscored_reasons=dict(unscored_reasons),
    )


def unscored_reason(
    answers: dict,
    scorecard_index: dict,
    lookup_index: dict,
    line_code: str,
    required_questions: list,
    ambiguous: set = frozenset(),
) -> Optional[str]:
    """Why this one client gets no likelihood on `line_code`, phrased to follow a count in the
    coverage footnote ("3 left PPI question 1 unanswered"), or None when they score. Only the
    first failing question is named -- one reason per client, so the counts sum to the unscored
    total.
    """
    result = score_from_index(answers, scorecard_index, line_code, required_questions)
    if result.score is None:
        q = result.missing_questions[0]
        if q not in answers:
            return f"left PPI question {q} unanswered"
        if (q, answers[q]) in ambiguous:
            return f"chose an option on PPI question {q} that two scorecard options share"
        return f"gave an answer on PPI question {q} that is not on the scorecard"
    if likelihood_from_index(lookup_index, result.score, line_code) is None:
        return "had a score with no matching row in the PPI lookup table"
    return None


def score_dataframe(df: pd.DataFrame, scorecard_path: str, lookup_path: str) -> list:
    """One CountryPovertyResult per country present in `df`."""
    countries = df[COUNTRY_COL].astype(str).str.strip()
    results = []
    for country_code, country_df in df.groupby(countries):
        if not country_code:
            continue
        results.append(score_country(country_code, country_df, scorecard_path, lookup_path))
    return results
