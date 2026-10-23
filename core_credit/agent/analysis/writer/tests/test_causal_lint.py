import pytest

from writer.causal_lint import HARD_TERMS, lint_text


def _hard_terms(text):
    return [h.term for h in lint_text(text) if h.tier == "hard"]


# One real Test5 sentence per rule Henry's comments map to (CC-076 to CC-083), with the term
# the lint must report for it.
@pytest.mark.parametrize(
    "sentence, term",
    [
        ("Our Net Promoter Score of 69 outpaces the MFI Index's 58, on the -100 to 100 scale.", "outpaces"),  # HO16
        ("Client satisfaction leads the story.", "leads the story"),
        ("Overall Net Promoter Score stands at a strong 69, comfortably ahead of the MFI Index benchmark of 58.", "comfortably ahead"),
        ("Nearly half of clients would find it hard to replace VisionFund, signaling a strong competitive moat and retention lever.", "moat"),  # HO17
        ("Senegal and Honduras exceed their national poverty rates, suggesting genuinely pro-poor targeting there.", "pro-poor targeting"),  # HO26
        ("The loan-cycle gradient doesn't run cleanly upward as expected, since cycle 4 dips slightly.", "as expected"),  # HO27
        ("91.5% report improved business income, confirming that credit access is translating into tangible household gains at scale.", "translating into"),  # HO31
        ("Clients receiving other services consistently outperform loan-only clients, pointing to bundled services as a lever worth expanding.", "lever"),  # HO32
        ("Equipment purchases repeatedly surface as the concrete mechanism behind these gains.", "mechanism"),  # HO33
        ("Prioritizing bundled services in weaker markets should raise both metrics further.", "should raise"),  # HO34
        ("The pattern suggests loans first ease household food security, which frees resources toward schooling.", "which frees"),  # HO35
        ("Gaps favor caregivers, suggesting the loan's social payoff for caregivers runs deeper than the metric captures.", "payoff"),  # HO41
        ("Clarity dips notably in India, signaling misselling and over-indebtedness risk there.", "misselling"),  # HO42
        ("Women report improved household influence at 84.2%, a sign this credit program is genuinely shifting decision-making power.", "a sign this"),  # HO51
        ("Promoters cite good staff service most, showing that service quality and speed drive loyalty as much as pricing.", "drive"),  # HO54
        ("Revisiting interest rate structure carries the most leverage for lifting detractor scores.", "leverage"),  # HO55
        ("57.4% said VisionFund services reduced its severity, a genuine resilience dividend from access.", "dividend"),
        ("Receiving other services lifts household influence to 89.2%.", "lifts"),
        ("Women are converting loan capital into stronger household decision-making power.", "converting"),
        ("This can be read as realized preparedness among those who actually faced a shock.", "can be read as"),  # cc066 7.4
        ("Our 70.1% figure is far above the MFI Index benchmark of 32.0%.", "far above the mfi index"),  # cc066 6.1
        ("Stronger-than-national poverty targeting appears in Honduras (11.8% vs. 9.2%).", "poverty targeting"),  # cc066 2.2
    ],
)
def test_real_violations_are_hard_hits(sentence, term):
    assert term in _hard_terms(sentence)


@pytest.mark.parametrize(
    "sentence",
    [
        # Known false positives from local-cc066 -- a plain noun, and a negated claim.
        "95.4% of clients report no unfair treatment, and 92.4% trust the complaints mechanism.",
        "Notably, 10.4% had no access to any coping mechanism at all.",
        "These figures should not be read as evidence of a broader social benefit of caregiving.",
        # Henry's own approved replacements must pass the hard tier.
        "Our Net Promoter Score of 69 is higher than the MFI Index's 58.",
        "45.0% would find it hard to find another lender, suggesting limited perceived alternatives.",
        "Clients' poverty likelihood is higher than the national rate, consistent with relatively pro-poor client reach.",
        "Women report high levels of improved household influence.",
        "Good, respectful staff service and fast disbursement are commonly cited reasons for recommendation.",
        "Revisiting the interest rate structure may be a priority area to investigate.",
    ],
)
def test_allowed_and_approved_wording_has_no_hard_hit(sentence):
    assert _hard_terms(sentence) == []


def test_negated_as_expected_is_still_a_hit():
    # A negation does not rescue "as expected" -- HO27's sentence is itself negated.
    assert _hard_terms("The gradient doesn't run upward as expected.") == ["as expected"]


def test_quoted_client_words_are_not_scanned():
    text = 'A client said "the loan drives my business forward" when asked.'
    assert lint_text(text) == []


def test_review_term_inside_hard_phrase_is_not_double_counted():
    hits = lint_text("Senegal shows strong pro-poor targeting.")
    assert [(h.term, h.tier) for h in hits] == [("pro-poor targeting", "hard")]


def test_review_tier_reports_interpretive_framing():
    hits = lint_text("Women face an easier alternative-lender landscape.")
    assert [(h.term, h.tier) for h in hits] == [("landscape", "review")]
    assert lint_text("Women face an easier alternative-lender landscape.", include_review=False) == []


def test_vs_abbreviation_does_not_split_the_sentence():
    hits = lint_text("Stronger-than-national poverty targeting appears in Honduras (11.8% vs. 9.2%) and Senegal.")
    assert hits[0].sentence.endswith("and Senegal.")


def test_word_boundaries_hold():
    # "drivers" must not also report "drive"; "leverage" must not also report "lever".
    assert _hard_terms("Cost is one of the drivers.") == ["drivers"]
    assert _hard_terms("This carries the most leverage.") == ["leverage"]


def test_hard_terms_are_lowercase_and_unique():
    assert all(t == t.lower() for t in HARD_TERMS)
    assert len(HARD_TERMS) == len(set(HARD_TERMS))
