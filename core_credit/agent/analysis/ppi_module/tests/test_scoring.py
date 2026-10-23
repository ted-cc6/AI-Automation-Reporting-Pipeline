import warnings

import pytest

from ppi_module.reference_data import ScorecardOption, load_lookup, load_scorecard
from ppi_module.scoring import (
    ScorecardLabelWarning,
    build_scorecard_index,
    find_ambiguous_options,
    find_label_order_mismatches,
    index_options,
    score_client,
    score_to_likelihood,
)


def _first_option_per_question(country: str, guide_id: str, survey_version: int, scorecard_path: str) -> dict:
    """Picks the option_order==1 answer for every question in one guide+version -- a synthetic
    'client' whose expected score we can compute independently by hand-summing points.

    Must be scoped to survey_version, not just guide_id: Ecuador's guide_id "ECU2022" is shared
    by two survey versions whose scorecards assign different points to the same options.
    """
    options = [
        o
        for o in load_scorecard(country, scorecard_path)
        if o.guide_id == guide_id and o.survey_version == survey_version
    ]
    by_question: dict = {}
    for o in options:
        if o.question not in by_question and o.option_order == 1:
            by_question[o.question] = o
    return by_question


def test_score_client_matches_hand_summed_points_for_ecuador(scorecard_path):
    line_code = "USD190day2011PPP"
    chosen = _first_option_per_question("ECU", "ECU2022", 3, scorecard_path)
    assert len(chosen) == 10  # Ecuador's guide asks 10 questions

    answers = {q: opt.option_prefix for q, opt in chosen.items()}
    expected_total = sum(opt.points[line_code] for opt in chosen.values())

    result = score_client(answers, "ECU", 3, line_code, scorecard_path)

    assert result.guide_id == "ECU2022"
    assert result.missing_questions == tuple()
    assert result.score == round(expected_total)


def test_score_client_uses_the_survey_version_specific_points_not_a_sibling_version(scorecard_path):
    # Survey versions 2 and 3 both carry guide_id "ECU2022" but score the same
    # question/option differently -- scoring under v3 must not silently pick up v2's points.
    line_code = "USD190day2011PPP"
    chosen_v3 = _first_option_per_question("ECU", "ECU2022", 3, scorecard_path)
    chosen_v2 = _first_option_per_question("ECU", "ECU2022", 2, scorecard_path)
    assert any(chosen_v3[q].points[line_code] != chosen_v2[q].points[line_code] for q in chosen_v3)

    answers = {q: opt.option_prefix for q, opt in chosen_v3.items()}
    result_v3 = score_client(answers, "ECU", 3, line_code, scorecard_path)
    expected_v3_total = sum(opt.points[line_code] for opt in chosen_v3.values())
    assert result_v3.score == round(expected_v3_total)


def test_score_client_incomplete_answers_returns_none_score(scorecard_path):
    chosen = _first_option_per_question("ECU", "ECU2022", 3, scorecard_path)
    answers = {q: opt.option_prefix for q, opt in chosen.items()}
    del answers[1]  # drop one required question

    result = score_client(answers, "ECU", 3, "USD190day2011PPP", scorecard_path)

    assert result.score is None
    assert 1 in result.missing_questions


def test_score_client_unknown_letter_counts_as_missing(scorecard_path):
    chosen = _first_option_per_question("ECU", "ECU2022", 3, scorecard_path)
    answers = {q: opt.option_prefix for q, opt in chosen.items()}
    answers[1] = "ZZ_NOT_A_REAL_OPTION"

    result = score_client(answers, "ECU", 3, "USD190day2011PPP", scorecard_path)

    assert result.score is None
    assert 1 in result.missing_questions


def test_rwanda_district_30_scores_via_doubled_letter_not_padded_id(scorecard_path):
    # This is the concrete regression test for the padding bug: district 30 ("dd) Bugesera")
    # must resolve correctly even though the scorecard's own Answer_Option ID for it
    # (ppi01-RWA-v1-R-0030) uses inconsistent padding we deliberately never touch.
    options = [
        o for o in load_scorecard("RWA", scorecard_path) if o.guide_id == "RWA2019" and o.question == 1
    ]
    district_30 = next(o for o in options if o.option_order == 30)
    assert district_30.option_prefix == "DD"

    chosen = _first_option_per_question("RWA", "RWA2019", 1, scorecard_path)
    answers = {q: opt.option_prefix for q, opt in chosen.items()}
    answers[1] = "DD"  # override question 1 with district 30 specifically

    line_code = "USD190day2011PPP"
    expected_total = sum(
        (district_30.points[line_code] if q == 1 else opt.points[line_code]) for q, opt in chosen.items()
    )

    result = score_client(answers, "RWA", 1, line_code, scorecard_path)
    assert result.score == round(expected_total)


def _opt(question, order, label, points):
    from ppi_module.reference_data import parse_option_prefix

    return ScorecardOption(
        guide_id="TEST", survey_version=1, question=question, option_order=order,
        option_prefix=parse_option_prefix(label), option_label=label, points={"L": points},
    )


def test_two_options_sharing_a_label_are_keyed_by_position_not_dropped():
    # CC-068, the Kenya Q3 shape on synthetic options: the 9th option's label wrongly reuses
    # the 7th option's letter. Each must keep its own points, under its own position letter.
    options = [_opt(3, 7, "G. Ceramic tiles", 14), _opt(3, 8, "H. Carpet", 12), _opt(3, 9, "G. Concrete", 10)]
    index, ambiguous, mismatches = index_options(options)
    assert index[(3, "G")] == {"L": 14}
    assert index[(3, "I")] == {"L": 10}
    assert ambiguous == set()
    assert [(m.question, m.option_order, m.label_prefix, m.keyed_as) for m in mismatches] == [(3, 9, "G", "I")]


def test_wrong_letter_without_a_collision_is_also_corrected():
    # The Zambia Q4 shape: "A. Yes" / "C. No" -- no duplicate, but the survey records B for "No".
    index, _, mismatches = index_options([_opt(4, 1, "A. Yes", 0), _opt(4, 2, "C. No", 5)])
    assert set(index) == {(4, "A"), (4, "B")}
    assert len(mismatches) == 1


def test_double_letter_positions_keep_their_label_prefix():
    # Past 26 the guides' own conventions differ (Rwanda "bb)" at 28), so the label wins there.
    index, _, mismatches = index_options([_opt(1, 28, "bb) Kirehe", 3), _opt(1, 29, "cc) Ngoma", 4)])
    assert set(index) == {(1, "BB"), (1, "CC")}
    assert mismatches == []


def test_a_collision_the_position_cannot_explain_is_still_dropped():
    # Safety net: two options at the SAME position with different points stay ambiguous.
    index, ambiguous, _ = index_options([_opt(2, 1, "A. One", 1), _opt(2, 1, "A. Uno", 2)])
    assert (2, "A") in ambiguous


def test_real_workbook_mislabels_are_exactly_the_known_three(scorecard_path):
    ken = find_label_order_mismatches("KEN", "KEN2021", 2, scorecard_path)
    zmb = find_label_order_mismatches("ZMB", "ZMB2017", 2, scorecard_path)
    assert [(m.question, m.option_order, m.label_prefix, m.keyed_as) for m in ken] == [(3, 9, "G", "I")]
    assert sorted((m.question, m.option_order, m.label_prefix, m.keyed_as) for m in zmb) == [(2, 4, "C", "D"), (4, 2, "C", "B")]
    assert find_ambiguous_options("KEN", "KEN2021", 2, scorecard_path) == []
    assert find_ambiguous_options("ZMB", "ZMB2017", 2, scorecard_path) == []


@pytest.mark.parametrize(
    "country, guide, question, letter, order",
    [("KEN", "KEN2021", 3, "G", 7), ("KEN", "KEN2021", 3, "I", 9), ("ZMB", "ZMB2017", 2, "D", 4), ("ZMB", "ZMB2017", 4, "B", 2)],
)
def test_real_mislabeled_options_score_with_their_own_points(scorecard_path, country, guide, question, letter, order):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ScorecardLabelWarning)
        index = build_scorecard_index(country, guide, 2, scorecard_path)
    expected = next(
        o for o in load_scorecard(country, scorecard_path)
        if o.guide_id == guide and o.survey_version == 2 and o.question == question and o.option_order == order
    )
    assert index[(question, letter)] == expected.points


def test_score_to_likelihood_resolves_duplicate_rows_by_most_recent_modification(scorecard_path, lookup_path):
    # Ecuador's lookup sheet carries two conflicting tables under guide_id "ECU2022" for the
    # same score, with no version column to disambiguate -- only a modification date. Confirm
    # score_to_likelihood picks the more recently modified one, via an independent raw scan.
    line_code = "USD190day2011PPP"
    guide_id = "ECU2022"
    target_score = 50

    rows = load_lookup("ECU", lookup_path)
    matching = [r for r in rows if r.guide_id == guide_id and r.score == target_score]
    assert len(matching) > 1, "expected Ecuador to still carry the duplicate-row situation this test guards"

    most_recent = max(matching, key=lambda r: r.record_modified_date or r.record_created_date)
    expected = most_recent.likelihoods[line_code]

    result = score_to_likelihood("ECU", guide_id, target_score, line_code, lookup_path)
    assert result == expected
