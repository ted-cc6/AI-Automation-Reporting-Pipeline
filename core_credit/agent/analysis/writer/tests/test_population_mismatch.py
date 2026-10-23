from schemas.common import MetricResult, SegmentAxis, SegmentedValue
from writer.chain import _writer_violations
from writer.formatting import format_metric_result
from writer.grounding import check_population_mismatch


def _metric(metric_id, label, overall, segments):
    return MetricResult(
        metric_id=metric_id,
        label=label,
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=overall, n=5818),
        by_segment=[SegmentedValue(axis=axis, value_label=v, share=s, n=100) for axis, v, s in segments],
    )


# The real Test5/local-cc066 figures for the Part 6 metrics, as formatting.py hands them to the writer.
HOUSEHOLD_INFLUENCE = _metric(
    "household_influence_improved", "Household influence improved", 0.835,
    [
        (SegmentAxis.GENDER, "Female", 0.842), (SegmentAxis.GENDER, "Male", 0.822),
        (SegmentAxis.CAREGIVER, "Caregiver", 0.862), (SegmentAxis.CAREGIVER, "Non-caregiver", 0.699),
        (SegmentAxis.FIRST_TIME_ACCESS, "First-time access", 0.867), (SegmentAxis.FIRST_TIME_ACCESS, "Prior access", 0.811),
        (SegmentAxis.OTHER_SERVICES, "Receives other services", 0.892), (SegmentAxis.OTHER_SERVICES, "Loan only", 0.794),
    ],
)
LOAN_PURPOSE_FULLY = _metric(
    "loan_purpose_achieved_fully", "Fully achieved the loan's purpose", 0.701,
    [
        (SegmentAxis.GENDER, "Female", 0.726), (SegmentAxis.GENDER, "Male", 0.652),
        (SegmentAxis.FIRST_TIME_ACCESS, "First-time access", 0.667), (SegmentAxis.FIRST_TIME_ACCESS, "Prior access", 0.726),
        (SegmentAxis.OTHER_SERVICES, "Receives other services", 0.738), (SegmentAxis.OTHER_SERVICES, "Loan only", 0.673),
    ],
)
COMMUNITY_RESPECT = _metric(
    "community_respect_improved", "Community respect improved", 0.740,
    [
        (SegmentAxis.GENDER, "Female", 0.739), (SegmentAxis.GENDER, "Male", 0.742),
        (SegmentAxis.CAREGIVER, "Caregiver", 0.772), (SegmentAxis.CAREGIVER, "Non-caregiver", 0.579),
        (SegmentAxis.OTHER_SERVICES, "Receives other services", 0.827), (SegmentAxis.OTHER_SERVICES, "Loan only", 0.676),
    ],
)
PAYLOAD_6_2 = format_metric_result(HOUSEHOLD_INFLUENCE)
PAYLOAD_6_INSIGHT = "\n".join(format_metric_result(m) for m in (LOAN_PURPOSE_FULLY, HOUSEHOLD_INFLUENCE, COMMUNITY_RESPECT))

# Test5 section 6.2, verbatim -- HO52.
TEST5_6_2 = (
    "Women report improved household influence at 84.2%, edging out men's 82.2%, a sign this credit program "
    "is genuinely shifting decision-making power toward female borrowers rather than just adding income. The "
    "gain is strongest among caregivers (86.2% versus 69.9% for non-caregivers) and those with prior access to "
    "credit reporting slightly less improvement (81.1%) than first-timers (86.7%), suggesting influence gains "
    "build steadily as women gain both program experience and caregiving responsibility within the household."
)

# local-cc066, where CC-004's rule held: the same figures with their base restated.
CC066_6_2 = (
    "Among all clients, 83.5% reported improved influence over household resource decisions, with women "
    "reporting this slightly more often at 84.2% compared with 82.2% of men. Among clients who reported "
    "improved influence, the most frequently cited way this showed up was making more decisions jointly with "
    "a spouse, at 44.2%."
)
CC066_6_INSIGHT = (
    "Women report fully achieving their loan's purpose at 72.6% compared with 65.2% of men, and women also "
    "report improved household influence at a slightly higher rate, 84.2% versus 82.2% for men, suggesting the "
    "goal-achievement gap by gender is the more pronounced pattern to track. Prior access to loans is associated "
    "with higher full achievement, 72.6%, than first-time access at 66.7%, while first-time clients report higher "
    "household influence gains, 86.7% versus 81.1% for prior-access clients. Caregivers report notably higher "
    "household influence improvement, 86.2%, than non-caregivers, 69.9%, and a similar gap appears in community "
    "respect, 77.2% for caregivers versus 57.9% for non-caregivers."
)


def test_ho52_sentence_is_flagged():
    flagged = check_population_mismatch(TEST5_6_2, PAYLOAD_6_2)
    assert len(flagged) == 1  # only the second sentence -- the first cites real gender figures
    for figure in ("86.2%", "69.9%", "81.1%", "86.7%"):
        assert figure in flagged[0]
    assert "as women gain" in flagged[0]


def test_cc066_part_6_text_passes():
    assert check_population_mismatch(CC066_6_2, PAYLOAD_6_2) == []
    assert check_population_mismatch(CC066_6_INSIGHT, PAYLOAD_6_INSIGHT) == []


def test_restating_all_clients_clears_the_flag():
    text = "Among all clients, household influence improved for 86.2% of caregivers, with women at 84.2%."
    assert check_population_mismatch(text, PAYLOAD_6_2) == []


def test_gender_scorecard_rows_count_as_gender_figures():
    payload = "  - Loan purpose fully achieved: Female 72.6% vs. Male 65.2% (gap +7.4%)\nOverall 70.1%"
    assert check_population_mismatch("Women fully achieved their loan purpose at 72.6% versus 65.2% for men.", payload) == []


def test_gender_figures_alongside_another_named_subgroup_pass():
    # The six false positives the first version of this check raised on Test5/local-cc066.
    payload = PAYLOAD_6_INSIGHT
    texts = [
        "Full achievement is higher among women (72.6%) than men (65.2%), and among clients with prior access (72.6%) versus first-time access (66.7%).",
        "Women report 84.2% against 82.2% for men, while caregivers report 86.2% and non-caregivers 69.9%.",
    ]
    for text in texts:
        assert check_population_mismatch(text, payload) == []


def test_quoted_client_words_are_ignored():
    text = 'A woman said "86.2% of my neighbours borrow" and men agreed.'
    assert check_population_mismatch(text, PAYLOAD_6_2) == []


def test_mismatch_triggers_the_writer_rewrite():
    violations = _writer_violations(TEST5_6_2, word_cap=200, pool=[], data_summary=PAYLOAD_6_2)
    # The same paragraph also trips CC-086's causal check ("a sign this", "genuinely shifting").
    population = [v for v in violations if "restate the base" in v]
    assert len(population) == 1
    assert _writer_violations(CC066_6_2, word_cap=200, pool=[], data_summary=PAYLOAD_6_2) == []
