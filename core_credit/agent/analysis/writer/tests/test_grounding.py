from schemas.client_satisfaction import NPSResult
from schemas.common import (
    BenchmarkComparison,
    GapComparison,
    MetricResult,
    QualitativeSynthesis,
    RankedOption,
    RankedOptions,
    SegmentAxis,
    SegmentedValue,
    ThemeFinding,
    Verbatim,
)
from schemas.poverty_likelihood import CountryVsNationalRate
from writer.grounding import (
    check_grounding,
    check_orphan_markers,
    check_partial_quotes,
    check_profile_grounding,
    check_quote_grounding,
    collect_acceptable_percentages,
)


def _metric_result() -> MetricResult:
    return MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.42, n=500),
        by_segment=[
            SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", share=0.50, n=300),
            SegmentedValue(axis=SegmentAxis.GENDER, value_label="Male", share=0.35, n=200),
        ],
        benchmark=BenchmarkComparison(external_mfi_index=0.23, external_mfi_index_year=2025),
    )


def test_collect_acceptable_percentages_includes_benchmark_comparable_value():
    # Regression test: this field was added after collect_acceptable_percentages was first
    # written, and it was initially forgotten -- a real writer run correctly cited a
    # benchmark-comparable "very much only" figure and the checker flagged it as hallucinated.
    mr = MetricResult(
        metric_id="business_income_change",
        label="Business income improved",
        overall=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.915, n=5818),
        benchmark=BenchmarkComparison(external_mfi_index=0.23, external_mfi_index_year=2025),
        benchmark_comparable_value=SegmentedValue(axis=SegmentAxis.OVERALL, value_label="Overall", share=0.458, n=5818),
    )
    acceptable = collect_acceptable_percentages(mr)
    flagged = check_grounding("Our own figure on the same basis is 45.8%, well above the 23% benchmark.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_includes_theme_share_of_respondents():
    # Regression test: a real writer run cited "40% of quoted clients raised X" where 40%
    # was a real ThemeFinding.share_of_respondents, and the checker flagged it as hallucinated
    # because collect_acceptable_percentages didn't know QualitativeSynthesis existed yet.
    qual = QualitativeSynthesis(
        source_field="test",
        base_n=100,
        themes=[ThemeFinding(theme="School fees", frequency=40, share_of_respondents=0.4)],
    )
    acceptable = collect_acceptable_percentages(qual)
    flagged = check_grounding("40% of quoted clients raised school fees as the main benefit.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_from_metric_result():
    acceptable = collect_acceptable_percentages(_metric_result())
    assert 42 in acceptable
    assert 50 in acceptable
    assert 35 in acceptable
    assert 23 in acceptable


def test_check_grounding_flags_number_not_in_data():
    acceptable = collect_acceptable_percentages(_metric_result())
    flagged = check_grounding("A striking 99% of clients said their business improved.", acceptable)
    assert flagged == ["99%"]


def test_check_grounding_accepts_matching_percent_word_variant():
    acceptable = collect_acceptable_percentages(_metric_result())
    flagged = check_grounding("Around 42 percent of clients reported higher income.", acceptable)
    assert flagged == []


def test_check_grounding_allows_small_rounding_tolerance():
    acceptable = collect_acceptable_percentages(_metric_result())
    # 42.3% rounds to 42% in prose -- should not be flagged given the 0.6 tolerance
    flagged = check_grounding("42% of clients said their income improved.", acceptable)
    assert flagged == []


def test_check_grounding_no_percentages_in_text_is_clean():
    assert check_grounding("Clients reported higher income overall.", set()) == []


def _nps_result() -> NPSResult:
    return NPSResult(
        score=58.0,
        promoter_share=0.6,
        passive_share=0.2,
        detractor_share=0.2,
        n=100,
        benchmark=BenchmarkComparison(external_mfi_index=58.0, external_mfi_index_year=2025),
    )


def test_collect_acceptable_percentages_from_nps_result_uses_score_scale_not_fraction():
    acceptable = collect_acceptable_percentages(_nps_result())
    assert 58 in acceptable  # the NPS score itself, not score/100
    assert 60 in acceptable  # promoter_share * 100
    assert 20 in acceptable  # passive/detractor share * 100


def test_collect_acceptable_percentages_includes_nps_by_segment():
    # Regression: NPSResult.by_segment was never read by collect_acceptable_percentages --
    # only overall score/shares -- so a real per-country or per-gender NPS figure in prose
    # would have been falsely flagged as ungrounded the first time by_segment was populated.
    nps_result = NPSResult(
        score=58.0,
        promoter_share=0.6,
        passive_share=0.2,
        detractor_share=0.2,
        n=100,
        by_segment=[SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", mean=72.0, n=50)],
    )
    acceptable = collect_acceptable_percentages(nps_result)
    flagged = check_grounding("Women score VisionFund at 72 on NPS.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_handles_multiple_sources_together():
    acceptable = collect_acceptable_percentages(_metric_result(), _nps_result())
    assert 42 in acceptable
    assert 58 in acceptable


def test_collect_acceptable_percentages_from_country_vs_national_rate_uses_percentage_point_scale():
    # portfolio_poverty_likelihood/national_poverty_rate are already percentage points (30.2
    # means 30.2%), unlike MetricResult.share -- must be added as-is, not multiplied by 100.
    row = CountryVsNationalRate(country_code="RWA", portfolio_poverty_likelihood=30.2, national_poverty_rate=38.2)
    acceptable = collect_acceptable_percentages(row)
    flagged = check_grounding("Rwanda's portfolio sits at 30% against a national rate of 38%.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_from_multiple_country_vs_national_rates():
    rows = [
        CountryVsNationalRate(country_code="RWA", portfolio_poverty_likelihood=30.2, national_poverty_rate=38.2),
        CountryVsNationalRate(country_code="ECU", portfolio_poverty_likelihood=3.8, national_poverty_rate=1.9),
    ]
    acceptable = collect_acceptable_percentages(*rows)
    flagged = check_grounding("Rwanda is at 30%, Ecuador at 4%.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_from_gap_comparison():
    gap = GapComparison(group_a_label="Caregiver", group_a_share=0.62, group_a_n=100, group_b_label="Non-caregiver", group_b_share=0.48, group_b_n=200, gap=0.14)
    acceptable = collect_acceptable_percentages(gap)
    flagged = check_grounding("Caregivers are at 62% against 48% for non-caregivers, a 14-point gap.", acceptable)
    assert flagged == []


def test_collect_acceptable_percentages_from_ranked_options():
    options = RankedOptions(
        base_n=100,
        options=[RankedOption(label="Female", share=0.62, n=62), RankedOption(label="Male", share=0.38, n=38)],
    )
    acceptable = collect_acceptable_percentages(options)
    flagged = check_grounding("62% of clients are female, 38% male.", acceptable)
    assert flagged == []


def _verbatim(quote: str) -> Verbatim:
    return Verbatim(quote=quote, gender="Female", country="Kenya", source_field="test_field")


def test_check_quote_grounding_passes_a_real_quote_from_the_pool():
    pool = [_verbatim("I am able to educate my children because of the loan amount")]
    text = 'She said, "I am able to educate my children because of the loan amount", a common theme.'
    assert check_quote_grounding(text, pool) == []


def test_check_quote_grounding_flags_a_fabricated_quote():
    # Regression test for a real incident: two quotes in a production report ("for the first
    # time, my opinion is respected during family decisions" / "people in my village now ask
    # for my advice") traced to no real respondent anywhere in the source data -- fluent,
    # typo-free illustrative quotes the model composed itself rather than selected from the
    # pool. used_verbatim_ids only checks IDs the model claims it used, so this is the only
    # check that catches an UNCLAIMED invented quote sitting in the free-form prose.
    pool = [_verbatim("I am able to educate my children because of the loan amount")]
    text = 'For the first time, "my opinion is respected during family decisions" (female, Ghana).'
    flagged = check_quote_grounding(text, pool)
    assert flagged == ["my opinion is respected during family decisions"]


def test_check_quote_grounding_ignores_short_quoted_phrases():
    # A floor on quote length skips short quoted survey-option labels / emphasis that were
    # never meant to represent a client's own words.
    pool: list[Verbatim] = []
    text = 'The response was "a. Very difficult" for most clients.'
    assert check_quote_grounding(text, pool) == []


def test_check_quote_grounding_empty_pool_flags_any_real_length_quote():
    # A subsection given no qualitative material at all has no valid source for any quote --
    # anything quoted should be flagged, not silently passed because the pool is empty.
    text = 'One client noted, "this loan changed how my whole family makes decisions together."'
    assert check_quote_grounding(text, []) == ["this loan changed how my whole family makes decisions together."]


def test_check_orphan_markers_flags_bracket_citations():
    text = "Clients reported improved wellbeing [0], though some faced setbacks [9]."
    assert check_orphan_markers(text) == ["[0]", "[9]"]


def test_check_orphan_markers_clean_text_returns_empty():
    assert check_orphan_markers("Clients reported improved wellbeing across the portfolio.") == []


def test_check_quote_grounding_accepts_a_moved_terminal_period():
    # CC-006: the writer reproduced a real verbatim exactly but placed the sentence-ending
    # period inside the closing quote mark. Correct typography, not a grounding failure.
    pool = [_verbatim("I am able to educate my children because of the loan amount")]
    text = 'A client said, "I am able to educate my children because of the loan amount."'
    assert check_quote_grounding(text, pool) == []
    assert check_partial_quotes(text, pool) == []


def test_check_partial_quotes_flags_a_contiguous_fragment():
    # CC-006: a real, correctly-sourced verbatim quoted only in fragment -- not fabrication,
    # but a reviewer should see it, because the fragment can change the meaning.
    pool = [_verbatim("they promised me the money I was waiting for but the payout never came")]
    text = 'One client recalled "the money I was waiting for" while describing the delay.'
    assert check_quote_grounding(text, pool) == []
    assert check_partial_quotes(text, pool) == ["the money I was waiting for"]


def test_check_partial_quotes_ignores_an_exact_full_quote():
    pool = [_verbatim("the money I was waiting for never actually arrived at the branch")]
    text = 'One client said, "the money I was waiting for never actually arrived at the branch."'
    assert check_quote_grounding(text, pool) == []
    assert check_partial_quotes(text, pool) == []


def test_internal_deletion_is_ungrounded_not_partial():
    # CC-006 edge case: a real verbatim with a word removed from the MIDDLE is no longer the
    # client's contiguous words -- it must read as fabrication, never a partial quote.
    pool = [_verbatim("I am able to educate my children because of the loan amount")]
    text = 'A client said, "I am able to educate children because of the loan amount."'
    assert check_partial_quotes(text, pool) == []
    assert check_quote_grounding(text, pool) == ["I am able to educate children because of the loan amount."]


def test_check_partial_quotes_leaves_a_true_fabrication_in_ungrounded():
    pool = [_verbatim("I am able to educate my children because of the loan amount")]
    text = 'A client said, "this loan let me hire two people and open a second market stall."'
    assert check_partial_quotes(text, pool) == []
    assert check_quote_grounding(text, pool) == ["this loan let me hire two people and open a second market stall."]


def test_check_quote_grounding_treats_curly_and_straight_apostrophes_as_equal():
    # Regression test for a real false positive: the pool verbatim used a curly apostrophe
    # ("j’ai"), the model's reproduction in prose came back with a straight one ("j'ai"),
    # and an exact-string match flagged a genuine, correctly-reproduced quote as fabricated.
    pool = [_verbatim("C'est très facile d'avoir le prêt et j’ai remarqué la transparence.")]
    text = 'Un client a dit, "C’est très facile d’avoir le prêt et j\'ai remarqué la transparence."'
    assert check_quote_grounding(text, pool) == []


def test_check_profile_grounding_passes_correctly_attributed_real_quote():
    v = Verbatim(quote="I would not recommend them because rates are too high for my needs.", country="MWI", source_field="f")
    text = 'A female client in Malawi said, "I would not recommend them because rates are too high for my needs."'
    assert check_profile_grounding(text, [v]) == []


def test_check_profile_grounding_flags_a_real_quote_wrapped_in_the_wrong_country():
    # Regression test for a real incident: a genuinely real Malawi client's quote was
    # introduced in a production report as "A female Ugandan caregiver from a PWD household in
    # Malawi said..." -- the quote text matched the pool exactly, so check_quote_grounding
    # correctly passed it, but "Ugandan" doesn't match anything about that client at all.
    v = Verbatim(quote="I would not recommend them because rates are too high for my needs.", country="MWI", source_field="f")
    text = 'A female Ugandan caregiver in Malawi said, "I would not recommend them because rates are too high for my needs."'
    flagged = check_profile_grounding(text, [v])
    assert len(flagged) == 1
    assert "Uganda" in flagged[0]


def test_check_profile_grounding_ignores_quotes_not_present_in_text():
    v = Verbatim(quote="A quote that was never actually used.", country="KEN", source_field="f")
    assert check_profile_grounding("Some unrelated analytical prose.", [v]) == []
