"""
Unit tests for generation/validate_output.py -- the advisory post-generation
validation pass (Step 8's "suggested validation pass": reject row_id
patterns, snake_case theme keys, out-of-scope country names, comparative
verbs on non-comparable indicators; flag unstated bases and unverified
numerals/quotes).
Run: pytest tests/test_validate_output.py -v
"""
from __future__ import annotations

import json

from generation.validate_output import (
    ALL_KNOWN_COUNTRIES,
    _INTERNAL_KEYS,
    load_in_scope_countries,
    load_product_mix,
    validate_report,
)


def _package(part="part_1", numeric_leaves=None, verbatims=None, scorecard=None,
             sentiment_split=None):
    pkg = {"part": part, "title": "Test Part", "sections": {}}
    if numeric_leaves is not None:
        pkg["sections"]["s1_1"] = {"metrics": numeric_leaves}
    if verbatims is not None:
        pkg["sections"].setdefault("insight", {})["verbatims"] = verbatims
    if sentiment_split is not None:
        pkg["sections"].setdefault("insight", {})["insight_summary"] = {
            "sentiment_split": sentiment_split
        }
    if scorecard is not None:
        pkg["scorecard"] = scorecard
    return pkg


class TestInternalKeysExtraction:
    def test_only_underscore_joined_codes_are_kept(self):
        # The PROTECTION FLAG TAXONOMY block's SEVERITY RUBRIC has "high:",
        # "medium:", "low:" sub-headings, and one real flag_type ("coercion")
        # has no underscore -- none of these are snake_case identifiers, and
        # all are ordinary English words that appear in legitimate prose
        # constantly, so none should be in the banned-key set.
        assert "high" not in _INTERNAL_KEYS
        assert "medium" not in _INTERNAL_KEYS
        assert "low" not in _INTERNAL_KEYS
        assert "coercion" not in _INTERNAL_KEYS

    def test_real_theme_and_flag_codes_are_present(self):
        assert "staff_service" in _INTERNAL_KEYS
        assert "mis_selling" in _INTERNAL_KEYS
        assert "unfair_claim_denial" in _INTERNAL_KEYS


class TestRowIdLeak:
    def test_row_id_in_prose_is_rejected(self):
        texts = {"part_1": {"s1_1": "This is illustrated by row_0042 among others."}}
        findings = validate_report(texts, [_package()], set())
        assert any(f["category"] == "row_id_leak" for f in findings)

    def test_no_row_id_produces_no_finding(self):
        texts = {"part_1": {"s1_1": "Clients reported strong satisfaction overall."}}
        findings = validate_report(texts, [_package()], set())
        assert not any(f["category"] == "row_id_leak" for f in findings)


class TestThemeKeyLeak:
    def test_internal_code_in_prose_is_rejected(self):
        texts = {"part_1": {"s1_1": "Clients cited staff_service as a key driver."}}
        findings = validate_report(texts, [_package()], set())
        assert any(f["category"] == "theme_key_leak" for f in findings)

    def test_natural_language_phrase_is_not_flagged(self):
        # "staff service" (space, not underscore) is exactly the natural
        # phrasing the taxonomy code is a stand-in for -- must not fire.
        texts = {"part_1": {"s1_1": "Clients cited staff service quality as a key driver."}}
        findings = validate_report(texts, [_package()], set())
        assert not any(f["category"] == "theme_key_leak" for f in findings)


class TestOutOfScopeCountry:
    def test_country_outside_scope_is_rejected(self):
        texts = {"part_1": {"s1_1": "Clients in Kenya reported high satisfaction."}}
        in_scope = {"Bolivia", "Ecuador"}
        findings = validate_report(texts, [_package()], in_scope)
        matches = [f for f in findings if f["category"] == "out_of_scope_country"]
        assert len(matches) == 1
        assert "Kenya" in matches[0]["detail"]

    def test_in_scope_country_is_not_flagged(self):
        texts = {"part_1": {"s1_1": "Clients in Bolivia reported high satisfaction."}}
        in_scope = {"Bolivia", "Ecuador"}
        findings = validate_report(texts, [_package()], in_scope)
        assert not any(f["category"] == "out_of_scope_country" for f in findings)

    def test_all_known_countries_includes_both_schemas(self):
        # A sample from each dataset schema -- verified against real
        # production data (see the module's ALL_KNOWN_COUNTRIES docstring).
        for country in ("Bolivia", "Dominican Republic", "Kenya", "Vietnam"):
            assert country in ALL_KNOWN_COUNTRIES


# ---------------------------------------------------------------------------
# Product claims -- a real generated report characterized a verbatim as
# describing a Credit Life death benefit in a report whose product-mix table
# showed zero Credit Life respondents (see qualitative/prepare_payload.py's
# record schema, which carries no product-type field at all -- nothing
# grounds this claim in the data, so the LLM inferred it purely from a
# quote's content).
# ---------------------------------------------------------------------------

class TestProductClaims:
    def test_product_named_with_zero_respondents_is_flagged(self):
        texts = {"part_7": {"insight": "This describes a Credit Life benefit paid on death."}}
        findings = validate_report(texts, [_package()], set(), product_mix={"Credit Life": 0, "Health": 1721})
        matches = [f for f in findings if f["category"] == "product_claim_on_zero_mix"]
        assert len(matches) == 1
        assert matches[0]["severity"] == "warn"
        assert "Credit Life" in matches[0]["detail"]

    def test_product_named_with_real_respondents_is_not_flagged(self):
        texts = {"part_11": {"s11_1": "Credit Life clients reported their loan balance was cleared."}}
        findings = validate_report(texts, [_package()], set(), product_mix={"Credit Life": 14, "Health": 1721})
        assert not any(f["category"] == "product_claim_on_zero_mix" for f in findings)

    def test_no_product_mix_supplied_skips_the_check(self):
        texts = {"part_7": {"insight": "This describes a Credit Life benefit paid on death."}}
        findings = validate_report(texts, [_package()], set())
        assert not any(f["category"] == "product_claim_on_zero_mix" for f in findings)

    def test_empty_product_mix_dict_skips_the_check(self):
        texts = {"part_7": {"insight": "This describes a Credit Life benefit paid on death."}}
        findings = validate_report(texts, [_package()], set(), product_mix={})
        assert not any(f["category"] == "product_claim_on_zero_mix" for f in findings)

    def test_text_not_naming_any_product_is_not_flagged(self):
        texts = {"part_7": {"insight": "Gendered experiences varied across the portfolio."}}
        findings = validate_report(texts, [_package()], set(), product_mix={"Credit Life": 0, "Crop": 0})
        assert not any(f["category"] == "product_claim_on_zero_mix" for f in findings)


class TestLoadProductMix:
    def test_reads_distribution_from_analysis_results(self, tmp_path):
        run_dir = tmp_path / "test_run"
        run_dir.mkdir()
        analysis = {"parts": {"about_survey": {"product_mix": {"distribution": [
            {"product": "health", "n": 1721}, {"product": "credit_life", "n": 0},
            {"product": "crop", "n": 0},
        ]}}}}
        (run_dir / "analysis_results.json").write_text(json.dumps(analysis), encoding="utf-8")
        mix = load_product_mix("test_run", runs_dir=tmp_path)
        assert mix == {"Health": 1721, "Credit Life": 0, "Crop": 0}

    def test_missing_file_returns_empty_dict(self, tmp_path):
        assert load_product_mix("nonexistent_run", runs_dir=tmp_path) == {}

    def test_unavailable_product_mix_returns_empty_dict(self, tmp_path):
        # about_survey.py's _product_mix() returns distribution: [] when
        # coverage is too low to trust (_PRODUCT_MIX_MIN_COVERAGE) -- the
        # check should simply have nothing to verify against, not error.
        run_dir = tmp_path / "low_coverage_run"
        run_dir.mkdir()
        analysis = {"parts": {"about_survey": {"product_mix": {
            "available": False, "distribution": [],
        }}}}
        (run_dir / "analysis_results.json").write_text(json.dumps(analysis), encoding="utf-8")
        assert load_product_mix("low_coverage_run", runs_dir=tmp_path) == {}


class TestComparativeVerbOnNonComparable:
    # session-5 (R-004/R-005/R-009, per Lorenz/LM3): a non-"clean" row now
    # shows a real prior-wave value (48.9%) rather than the literal string
    # "NOT COMPARABLE" -- _non_comparable_labels() was updated in the same
    # session to key off `comparability` instead, so this fixture carries
    # that field explicitly rather than relying on group_b_value's text.
    _SCORECARD = [
        {"label": "Access to Alternatives (Difficult)", "group_a_value": "44.5%",
         "group_b_value": "48.9%", "comparability": "indicative"},
        {"label": "First-Time Access to Insurance", "group_a_value": "77.2%",
         "group_b_value": "73.6%", "comparability": "clean"},
    ]

    def test_comparative_verb_on_non_comparable_indicator_is_rejected(self):
        texts = {"part_10": {"narrative": "Access to Alternatives (Difficult) increased this wave."}}
        pkg = _package(part="part_10", scorecard=self._SCORECARD)
        findings = validate_report(texts, [pkg], set())
        matches = [f for f in findings if f["category"] == "comparative_verb_on_non_comparable"]
        assert len(matches) == 1

    def test_comparative_verb_on_comparable_indicator_is_not_flagged(self):
        # First-Time Access IS comparable (has a real prior-wave value in
        # the scorecard) -- comparative language about it is correct, not a
        # defect.
        texts = {"part_10": {"narrative": "First-Time Access to Insurance rose this wave."}}
        pkg = _package(part="part_10", scorecard=self._SCORECARD)
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "comparative_verb_on_non_comparable" for f in findings)

    def test_mentioning_the_indicator_without_a_comparative_verb_is_fine(self):
        texts = {"part_10": {"narrative": "Access to Alternatives (Difficult) stood at 44.5% this wave."}}
        pkg = _package(part="part_10", scorecard=self._SCORECARD)
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "comparative_verb_on_non_comparable" for f in findings)

    def test_check_is_scoped_to_part_10_only(self):
        # A part that isn't part_10 has no non_comparable_labels at all, so
        # comparative language elsewhere in the report is never flagged by
        # this check (it isn't a trend-comparison section).
        texts = {"part_1": {"s1_1": "Access to Alternatives (Difficult) increased sharply."}}
        pkg = _package(part="part_1")
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "comparative_verb_on_non_comparable" for f in findings)


class TestUnverifiedQuote:
    def test_quote_not_in_pool_is_rejected(self):
        texts = {"part_1": {"insight": 'One client said "this exact sentence was never provided".'}}
        pkg = _package(verbatims=[{"id": "row_0001", "text": "a completely different quote"}])
        findings = validate_report(texts, [pkg], set())
        assert any(f["category"] == "unverified_quote" for f in findings)

    def test_quote_matching_pool_is_not_flagged(self):
        quote = "the process was very slow and confusing for me"
        texts = {"part_1": {"insight": f'One client said "{quote}".'}}
        pkg = _package(verbatims=[{"id": "row_0001", "text": quote}])
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_quote" for f in findings)

    def test_short_quoted_fragments_are_ignored(self):
        # Under the 15-char minimum -- avoids flagging short parenthetical
        # quoted single words as if they were verbatim citations.
        texts = {"part_1": {"insight": 'The client described it as "good".'}}
        pkg = _package(verbatims=[])
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_quote" for f in findings)

    def test_only_checked_on_insight_text_key(self):
        # A quote-shaped string in a non-insight section (which never
        # carries a verbatim pool) should not be checked against it.
        texts = {"part_1": {"s1_1": '"an arbitrary quoted phrase of some length"'}}
        pkg = _package(verbatims=[])
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_quote" for f in findings)


class TestUnverifiedNumeral:
    def test_numeral_matching_data_package_is_not_flagged(self):
        pkg = _package(numeric_leaves={"share": {"value": 0.772, "n_valid": 1721}})
        texts = {"part_1": {"s1_1": "First-time access reached 77.2% of respondents."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_numeral" for f in findings)

    def test_fabricated_numeral_is_flagged_as_warn(self):
        pkg = _package(numeric_leaves={"share": {"value": 0.772, "n_valid": 1721}})
        texts = {"part_1": {"s1_1": "First-time access reached 91.4% of respondents."}}
        findings = validate_report(texts, [pkg], set())
        matches = [f for f in findings if f["category"] == "unverified_numeral"]
        assert len(matches) == 1
        assert matches[0]["severity"] == "warn"

    def test_bare_small_integers_are_not_flagged(self):
        # "Part 4", "top 3" -- narrative digits, not cited statistics.
        pkg = _package()
        texts = {"part_1": {"s1_1": "See Part 4 for the top 3 drivers."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_numeral" for f in findings)

    def test_years_are_not_flagged(self):
        pkg = _package()
        texts = {"part_1": {"s1_1": "The 2026 wave expanded coverage."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_numeral" for f in findings)

    def test_large_integer_with_comma_matches_comma_formatted_n(self):
        pkg = _package(numeric_leaves={"n": {"n_total": 1721}})
        texts = {"part_1": {"s1_1": "The sample includes 1,721 respondents."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unverified_numeral" for f in findings)


class TestUnstatedBase:
    def test_bare_percentage_with_no_base_language_is_flagged(self):
        pkg = _package()
        texts = {"part_1": {"s1_1": "Overall satisfaction was 77%."}}
        findings = validate_report(texts, [pkg], set())
        matches = [f for f in findings if f["category"] == "unstated_base"]
        assert len(matches) == 1
        assert matches[0]["severity"] == "warn"

    def test_percentage_with_population_language_is_not_flagged(self):
        pkg = _package()
        texts = {"part_1": {"s1_1": "Among health and credit-life clients, 92.3% reported awareness."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unstated_base" for f in findings)

    def test_percentage_with_explicit_fraction_is_not_flagged(self):
        pkg = _package()
        texts = {"part_1": {"s1_1": "481 of 3,669 respondents (13.1%) experienced an insured event."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "unstated_base" for f in findings)


def _grp(positive, negative, neutral):
    """R-006a's deterministic split shape for one group (test helper)."""
    return {"positive": positive, "negative": negative, "neutral": neutral,
            "base_n": positive + negative + neutral, "source_pool_n": positive + negative + neutral}


class TestTinySentimentBasePercentage:
    # Mirrors generation/writer.py's _SENTIMENT_SPLIT_MIN_BASE_FOR_PCT
    # instruction (counts-only below the threshold) -- this is the advisory
    # second line of defense: writer.py shapes the prompt so the model
    # shouldn't state a percentage at all below the threshold, and this
    # check flags it if one shows up anyway. sentiment_split is R-006a's
    # uniform nested shape (session-8): {group_label: split}, a
    # single-group section under "all".
    def test_percentage_on_tiny_base_is_flagged(self):
        pkg = _package(sentiment_split={"all": _grp(2, 1, 0)})
        texts = {"part_1": {"insight": "Sentiment was strongly positive (67%) among relevant responses."}}
        findings = validate_report(texts, [pkg], set())
        matches = [f for f in findings if f["category"] == "percentage_on_tiny_sentiment_base"]
        assert len(matches) == 1
        assert matches[0]["severity"] == "warn"

    def test_counts_only_phrasing_on_tiny_base_is_not_flagged(self):
        pkg = _package(sentiment_split={"all": _grp(2, 1, 0)})
        texts = {"part_1": {"insight": "2 clients were positive and 1 was negative."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "percentage_on_tiny_sentiment_base" for f in findings)

    def test_percentage_on_large_base_is_not_flagged(self):
        pkg = _package(sentiment_split={"all": _grp(18, 9, 3)})
        texts = {"part_1": {"insight": "Sentiment was mostly positive (60%) among relevant responses."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "percentage_on_tiny_sentiment_base" for f in findings)

    def test_no_sentiment_split_is_never_flagged(self):
        pkg = _package()
        texts = {"part_1": {"insight": "Some findings mention 67% for an unrelated reason."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "percentage_on_tiny_sentiment_base" for f in findings)

    def test_only_checked_on_insight_text_key(self):
        pkg = _package(sentiment_split={"all": _grp(2, 1, 0)})
        texts = {"part_1": {"s1_1": "An unrelated metric reads 67% here."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "percentage_on_tiny_sentiment_base" for f in findings)

    def test_small_group_flagged_even_when_another_group_is_large(self):
        # session-8, per instruction: summing groups back into one total
        # would hide a small group's problem behind a large one's size --
        # each group must be judged on its own base_n.
        pkg = _package(sentiment_split={
            "female": _grp(200, 150, 78),  # base_n=428, percentage-eligible
            "male": _grp(2, 1, 0),         # base_n=3, tiny
        })
        texts = {"part_1": {"insight": "Sentiment was positive (47%) among women and men alike."}}
        findings = validate_report(texts, [pkg], set())
        matches = [f for f in findings if f["category"] == "percentage_on_tiny_sentiment_base"]
        assert len(matches) == 1
        assert "male" in matches[0]["detail"]

    def test_both_groups_large_is_not_flagged(self):
        pkg = _package(sentiment_split={
            "female": _grp(200, 150, 78),
            "male": _grp(80, 60, 30),
        })
        texts = {"part_1": {"insight": "Sentiment was positive (47%) among women and (46%) among men."}}
        findings = validate_report(texts, [pkg], set())
        assert not any(f["category"] == "percentage_on_tiny_sentiment_base" for f in findings)


class TestLoadInScopeCountries:
    def test_reads_by_country_from_analysis_results(self, tmp_path):
        run_dir = tmp_path / "test_run"
        run_dir.mkdir()
        analysis = {
            "parts": {"about_survey": {"by_country": [
                {"country": "Bolivia", "n": 100}, {"country": "Ecuador", "n": 50},
            ]}}
        }
        (run_dir / "analysis_results.json").write_text(json.dumps(analysis), encoding="utf-8")
        countries = load_in_scope_countries("test_run", runs_dir=tmp_path)
        assert countries == {"Bolivia", "Ecuador"}

    def test_missing_file_returns_empty_set(self, tmp_path):
        assert load_in_scope_countries("nonexistent_run", runs_dir=tmp_path) == set()


class TestValidateReportSkipsFailedGeneration:
    def test_generation_failed_part_is_skipped(self):
        texts = {"part_1": {"_generation_failed": True, "_error": "timeout"}}
        findings = validate_report(texts, [_package()], set())
        assert findings == []
