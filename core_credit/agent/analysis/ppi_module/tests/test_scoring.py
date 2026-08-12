from ppi_module.reference_data import load_scorecard, load_lookup
from ppi_module.scoring import build_scorecard_index, find_ambiguous_options, score_client, score_to_likelihood


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


def test_kenya_q3_conflicting_option_labels_are_excluded_not_silently_merged(scorecard_path):
    # Kenya's scorecard mislabels option_order 9 ("Concrete or cement or terrazo") with prefix
    # "G", which option_order 7 ("Ceramic tiles", points=14) already uses; option_order 9's
    # points (10) differ. Without a guard, whichever loads last would silently win.
    ambiguous = find_ambiguous_options("KEN", "KEN2021", 2, scorecard_path)
    assert (3, "G") in ambiguous

    index = build_scorecard_index("KEN", "KEN2021", 2, scorecard_path)
    assert (3, "G") not in index  # dropped entirely, not resolved to either option's points


def test_zambia_q2_conflicting_option_labels_are_excluded(scorecard_path):
    # Zambia's scorecard mislabels option_order 4 ("Six or more") with prefix "C", which
    # option_order 3 ("Four or five") already uses, with different points.
    ambiguous = find_ambiguous_options("ZMB", "ZMB2017", 2, scorecard_path)
    assert (2, "C") in ambiguous


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
