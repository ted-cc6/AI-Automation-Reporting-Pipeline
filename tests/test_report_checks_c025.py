"""
Unit tests for docs/report_checks.py's C-025 (R-035, session-11): the report
must describe correlations and group differences as associations, never as
one thing driving, causing, or determining another, since this is
cross-sectional survey data and the design does not support causal
inference. Verbatim client quotes are exempt -- a client's own words stand
as given.

This is the one check in report_checks.py complex enough (verbatim/bilingual
exclusion, per-term inflection matching, a deliberate exemption for
"improved" in its non-causal uses) to warrant a dedicated pytest file rather
than only manual verification against a real extraction -- a miss in the
quote-exclusion regex would produce false positives on every section that
quotes a client.

Run: pytest tests/test_report_checks_c025.py -v
"""
from __future__ import annotations

from docs.report_checks import no_causal_language_outside_verbatims as check


class TestRealTest11Sentences:
    """The 7 sentences Lorenz's colleague flagged in Test11 -- each must trip
    the check on its own, unmodified."""

    def test_drove(self):
        result = check("Analysis of 1,721 clients revealed that value perception drove satisfaction most strongly")
        assert result[0] is False

    def test_lever_and_improving(self):
        result = check("offers the strongest lever for improving client advocacy")
        assert result[0] is False

    def test_driver(self):
        result = check("Value perception was the central NPS driver")
        assert result[0] is False

    def test_underpins(self):
        result = check("This trust underpins the protective value of coverage")
        assert result[0] is False

    def test_eased(self):
        result = check("the health cover eased both access and cost pressures")
        assert result[0] is False

    def test_strengthens(self):
        result = check("direct experience filing a claim substantially strengthens process knowledge")
        assert result[0] is False

    def test_translating_into(self):
        # The most exposed case: asserts a mechanism behind a cross-sectional
        # group difference.
        result = check("caregivers face greater barriers translating cover into improved access")
        assert result[0] is False


class TestBannedTermCoverage:
    def test_cause_family(self):
        assert check("insurance causes better outcomes")[0] is False
        assert check("this caused the observed gap")[0] is False

    def test_determines_family(self):
        assert check("premium affordability determines renewal")[0] is False

    def test_reduces_family(self):
        assert check("coverage reduces financial stress")[0] is False

    def test_leads_to(self):
        assert check("higher understanding leads to renewal")[0] is False

    def test_impact_as_verb_is_banned(self):
        assert check("financial stress impacts satisfaction")[0] is False
        assert check("the change impacted outcomes")[0] is False

    def test_bare_impact_noun_is_not_banned(self):
        assert check("measuring the impact of the programme")[0] is True

    def test_report_title_is_never_flagged(self):
        assert check("VisionFund Insurance Impact Report, Q2 2026")[0] is True


class TestQuotedVerbatimExemption:
    def test_banned_term_inside_plain_quote_is_exempt(self):
        text = 'A client said "it drives me to trust them more" in their own words.'
        assert check(text)[0] is True

    def test_banned_term_outside_quote_still_flagged_in_same_sentence(self):
        text = 'This trust underpins everything, a client said "it drives me to trust them more."'
        result = check(text)
        assert result[0] is False
        assert "underpins" in result[1]
        assert "drives" not in result[1]

    def test_bilingual_gloss_and_original_both_exempt(self):
        # Real pattern from writer.py's own VOICE RULES example and this
        # codebase's actual rendered output: an English gloss in quotes,
        # immediately followed by the unquoted original-language text in
        # parentheses.
        text = (
            'One client praised that it was "very easy to schedule an appointment '
            'and the service" ("ES MUY FACIL AGENDER UNA CIATA Y LA ATENCION"), '
            'while another appreciated the "In-person service" ("Atencion presencial").'
        )
        assert check(text)[0] is True

    def test_real_test11_style_bilingual_quote_with_banned_word_inside(self):
        text = (
            'One client expressed frustration, stating "it drives me crazy that '
            'they never explain anything" ("me vuelve loca que nunca explican nada").'
        )
        assert check(text)[0] is True


class TestImprovedExemptions:
    def test_fixed_metric_labels_are_exempt(self):
        assert check("Healthcare Access Improved: 31.4% among caregivers, 46.7% among non-caregivers")[0] is True
        assert check("Children's Wellbeing Improved")[0] is True
        assert check("Child Wellbeing Improved")[0] is True

    def test_reported_improved_is_exempt(self):
        assert check("36.1% reported improved child wellbeing")[0] is True

    def test_intransitive_improved_at_clause_end_is_exempt(self):
        text = "Among clients who needed medical care, 33.9% reported that their access to healthcare services improved."
        assert check(text)[0] is True

    def test_recommended_caregiver_replacement_sentence_is_exempt(self):
        # The exact replacement wording proposed for Test11's most exposed
        # sentence (item 7) -- must not itself trip the check it exists to
        # satisfy.
        text = "caregivers reported improved access less often than non-caregivers (31.4% versus 46.7%)"
        assert check(text)[0] is True

    def test_unattributed_improved_with_an_object_is_still_banned(self):
        # A genuine causal claim ("the programme improved X") must not be
        # let through just because "improved" is on the exemption list --
        # only the specific safe surface patterns above are exempt.
        text = "the programme improved outcomes for many families"
        assert check(text)[0] is False

    def test_bare_improve_and_improving_are_always_banned(self):
        assert check("this improves client advocacy")[0] is False
        assert check("aimed at improving retention")[0] is False

    def test_reduced_as_a_noun_phrase_subject_is_exempt(self):
        # Real regenerated Part 4 text (session-11): a state description,
        # not a causal claim -- the same non-causal use "improved" has.
        text = "Reduced financial stress is also associated with higher satisfaction."
        assert check(text)[0] is True

    def test_reducing_with_a_named_agent_is_still_banned(self):
        # Real regenerated Part 5 text (session-11), caught by the check
        # exactly as intended: this asserts insurance causes the stress
        # reduction, which the correlation alone does not establish. The
        # gerund form (needs an agent to read naturally) has no exemption,
        # unlike the past-participle "reduced" above.
        text = "Better child wellbeing is also associated with insurance reducing financial stress (rho=-0.238)."
        result = check(text)
        assert result[0] is False
        assert "reducing" in result[1]


class TestRecommendedActionsExemption:
    """Confirmed with the user (session-11): the ban covers descriptions of
    findings/correlations, not the formal Recommended Actions section --
    narrower than "any forward-looking language anywhere.\""""

    def test_banned_term_inside_recommended_actions_is_exempt(self):
        # Real regenerated Recommended Action #3 (session-11).
        text = (
            "Top Findings\n"
            "1. A critical gap in product understanding is a major factor.\n"
            "Recommended Actions\n"
            "1. Develop a simple document for every client.\n"
            "2. Audit the claims process to simplify documentation.\n"
            "3. Review product coverage against common client health expenditures, "
            "particularly outpatient medication, to assess alignment with client needs "
            "and improve the value proposition.\n"
            "Data Availability\n"
            "This report's survey instrument does not collect the following."
        )
        assert check(text)[0] is True

    def test_banned_term_before_recommended_actions_still_flagged(self):
        # The heading itself does not blank out everything before it --
        # only the region from the heading up to the next section.
        text = (
            "A critical gap in product understanding is the single largest driver of "
            "client dissatisfaction.\n"
            "Recommended Actions\n"
            "1. Review coverage to improve the value proposition.\n"
            "Data Availability\n"
            "Nothing else to report."
        )
        result = check(text)
        assert result[0] is False
        assert "driver" in result[1]
        assert "improve" not in result[1]

    def test_forward_looking_aside_outside_recommended_actions_still_flagged(self):
        # Confirmed scope: a narrative aside elsewhere in the report ("this
        # gap highlights an opportunity to improve X") is NOT exempt just
        # because it is forward-looking -- only the formal section is.
        text = (
            "This gap highlights an opportunity to improve claims process awareness, "
            "especially for those who may need to use their insurance but hesitate to do so."
        )
        assert check(text)[0] is False

    def test_recommended_actions_region_does_not_swallow_the_next_section(self):
        # A banned term in "Data Availability" (or whatever follows) must
        # still be caught -- the exemption is bounded to Recommended
        # Actions' own region, not "everything after this heading."
        text = (
            "Recommended Actions\n"
            "1. Review coverage to improve the value proposition.\n"
            "Data Availability\n"
            "This section improves nothing and should still be flagged."
        )
        result = check(text)
        assert result[0] is False
        assert "improves" in result[1]


class TestNoTrackedTermsFound:
    def test_clean_narrative_passes(self):
        text = "Financial resilience remained broadly stable across the portfolio this wave."
        assert check(text) == (True, "")

    def test_association_language_passes(self):
        text = (
            "A negative correlation with the outcome variable therefore corresponds to a "
            "POSITIVE association in plain terms, not a negative one."
        )
        assert check(text)[0] is True

    def test_own_no_causation_disclaimer_does_not_trip_itself(self):
        # A real bug caught on the first end-to-end regeneration: the
        # association_note/appendix-intro text this requirement itself
        # renders under both correlation tables originally said "...do not
        # establish that one factor causes or determines another" -- which
        # tripped its own check. Reworded to "is responsible for another";
        # this locks in that the disclaimer never bans itself again.
        text = (
            "These are observed associations in cross-sectional survey data and do not "
            "establish that one factor is responsible for another."
        )
        assert check(text) == (True, "")

    def test_ease_of_use_noun_is_not_banned(self):
        # Real regenerated Part 2 text (session-11): "ease" as an ordinary
        # noun, not a causal claim -- only its inflected verb forms
        # (eases/eased/easing) are banned.
        text = 'Positive feedback highlighted ease of use, with one client stating, "it was quick."'
        assert check(text)[0] is True

    def test_eased_as_a_verb_is_still_banned(self):
        assert check("the health cover eased both access and cost pressures")[0] is False
