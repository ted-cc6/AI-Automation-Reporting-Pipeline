"""
Unit tests for generation/writer.py's scope-aware title/house-voice logic
(Phase 5). The core guarantee under test: an unscoped (global-portfolio) run
must produce byte-identical title/prompt text to what writer.py always
produced, so adding single-country support can't change the global report.
Run: pytest tests/test_writer.py -v
"""
from __future__ import annotations

import json

import pytest

import generation.writer as writer
from generation.writer import (
    _build_scorecard_text,
    _build_sections_text,
    _house_voice,
    _house_voice_text,
    _is_larco_rollup,
    _is_single_country,
    _lacro_scoped,
    _load_analysis_meta,
    _report_title,
    write_part,
)


# ---------------------------------------------------------------------------
# _load_analysis_meta
# ---------------------------------------------------------------------------

class TestLoadAnalysisMeta:
    def test_missing_run_dir_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(writer, "ROOT", tmp_path)
        assert _load_analysis_meta("no_such_run") == {}

    def test_malformed_json_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(writer, "ROOT", tmp_path)
        run_dir = tmp_path / "runs" / "bad_run"
        run_dir.mkdir(parents=True)
        (run_dir / "analysis_results.json").write_text("{not valid json", encoding="utf-8")
        assert _load_analysis_meta("bad_run") == {}

    def test_valid_file_returns_meta_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr(writer, "ROOT", tmp_path)
        run_dir = tmp_path / "runs" / "good_run"
        run_dir.mkdir(parents=True)
        (run_dir / "analysis_results.json").write_text(
            json.dumps({"meta": {"country": "vietnam", "n_total": 154}}), encoding="utf-8"
        )
        assert _load_analysis_meta("good_run") == {"country": "vietnam", "n_total": 154}


# ---------------------------------------------------------------------------
# _is_single_country
# ---------------------------------------------------------------------------

class TestIsSingleCountry:
    def test_empty_meta_is_not_single_country(self):
        assert _is_single_country({}) is False

    def test_default_sentinel_is_not_single_country(self):
        assert _is_single_country({"country": "default"}) is False

    def test_null_country_is_not_single_country(self):
        assert _is_single_country({"country": None}) is False

    def test_real_country_is_single_country(self):
        assert _is_single_country({"country": "vietnam"}) is True


# ---------------------------------------------------------------------------
# _report_title
# ---------------------------------------------------------------------------

class TestReportTitle:
    def test_no_meta_matches_original_hardcoded_global_title(self):
        period = writer.format_period_label("2026_Q2")
        expected = f"VisionFund International Insurance Impact Report: Global Portfolio, {period}"
        assert _report_title("2026_Q2") == expected
        assert _report_title("2026_Q2", None) == expected
        assert _report_title("2026_Q2", {}) == expected

    def test_default_country_meta_matches_global_title(self):
        period = writer.format_period_label("2026_Q2")
        expected = f"VisionFund International Insurance Impact Report: Global Portfolio, {period}"
        assert _report_title("2026_Q2", {"country": "default", "country_label": "Default"}) == expected

    def test_scoped_country_uses_country_label(self):
        title = _report_title("2026_Q2", {"country": "vietnam", "country_label": "Vietnam"})
        assert title == f"VisionFund International Insurance Impact Report: Vietnam, {writer.format_period_label('2026_Q2')}"

    def test_scoped_country_without_label_falls_back_to_titlecase(self):
        title = _report_title("2026_Q2", {"country": "kenya"})
        assert "Kenya" in title

    def test_larco_rollup_uses_lacro_regional_title_not_global(self):
        title = _report_title("2026_Q2", {"country": "default", "dataset_schema": "larco"})
        assert "LACRO Regional Portfolio" in title
        assert "Global Portfolio" not in title
        # The internal dataset_schema value is spelled "larco" (this
        # codebase's file/variable naming convention), but nothing
        # reader-facing may say "LARCO" -- see report_scopes.py's
        # LACRO_SHORT_LABEL docstring for why this distinction matters.
        assert "LARCO" not in title

    def test_larco_single_country_still_uses_country_label(self):
        title = _report_title(
            "2026_Q2", {"country": "ecuador", "country_label": "Ecuador", "dataset_schema": "larco"}
        )
        assert title == f"VisionFund International Insurance Impact Report: Ecuador, {writer.format_period_label('2026_Q2')}"
        assert "LACRO" not in title
        assert "LARCO" not in title

    def test_missing_dataset_schema_key_defaults_to_global(self):
        # analysis_results.json files written before dataset_schema was added
        # to meta must still resolve to the original global-portfolio title.
        title = _report_title("2026_Q2", {"country": "default"})
        assert "Global Portfolio" in title

    def test_report_scope_lacro_uses_lacro_regional_title_not_global(self):
        # The real bug this guards against: a report_scope=="lacro" run on
        # the unified schema (country="default", dataset_schema=
        # "africa_vietnam") previously fell through to "Global Portfolio"
        # since only the legacy dataset_schema=="larco" path was checked.
        title = _report_title("2026_Q2", {
            "country": "default", "dataset_schema": "africa_vietnam",
            "report_scope": "lacro",
            "report_scope_label": "LACRO (Latin America and Caribbean Regional Office)",
        })
        assert "LACRO Regional Portfolio" in title
        assert "Global Portfolio" not in title
        # A separate, later bug (round 3): this branch hardcoded "LARCO"
        # (the internal naming convention) directly into the title instead
        # of the correct reader-facing "LACRO" spelling, even after the
        # scope-vs-global bug above was fixed.
        assert "LARCO" not in title

    def test_report_scope_africa_uses_its_own_label(self):
        title = _report_title("2026_Q2", {
            "country": "default", "dataset_schema": "africa_vietnam",
            "report_scope": "africa", "report_scope_label": "Africa and Asia",
        })
        assert title == (
            f"VisionFund International Insurance Impact Report: Africa and Asia Portfolio, "
            f"{writer.format_period_label('2026_Q2')}"
        )
        assert "Global Portfolio" not in title

    def test_report_scope_without_label_falls_back_to_raw_scope_key(self):
        title = _report_title("2026_Q2", {
            "country": "default", "dataset_schema": "africa_vietnam", "report_scope": "africa",
        })
        assert "africa Portfolio" in title

    def test_single_country_wins_over_report_scope(self):
        # Defensive ordering: if a caller somehow sets both country and
        # report_scope, the more specific single-country title wins (the
        # frontend never sends both, but the API model doesn't forbid it --
        # see StartRunRequest.report_scope's docstring).
        title = _report_title("2026_Q2", {
            "country": "ecuador", "country_label": "Ecuador",
            "dataset_schema": "africa_vietnam", "report_scope": "lacro",
        })
        assert title == f"VisionFund International Insurance Impact Report: Ecuador, {writer.format_period_label('2026_Q2')}"
        assert "LARCO" not in title


# ---------------------------------------------------------------------------
# _is_larco_rollup / _lacro_scoped
# ---------------------------------------------------------------------------

class TestLacroScoped:
    def test_legacy_larco_schema_rollup_is_scoped(self):
        assert _lacro_scoped({"country": "default", "dataset_schema": "larco"}) is True

    def test_report_scope_lacro_is_scoped(self):
        assert _lacro_scoped({"country": "default", "dataset_schema": "africa_vietnam", "report_scope": "lacro"}) is True

    def test_report_scope_africa_is_not_lacro_scoped(self):
        assert _lacro_scoped({"country": "default", "dataset_schema": "africa_vietnam", "report_scope": "africa"}) is False

    def test_no_scope_at_all_is_not_lacro_scoped(self):
        assert _lacro_scoped({"country": "default", "dataset_schema": "africa_vietnam"}) is False

    def test_single_country_larco_schema_is_not_a_rollup(self):
        assert _lacro_scoped({"country": "ecuador", "dataset_schema": "larco"}) is False


class TestIsLarcoRollup:
    def test_empty_meta_is_not_larco_rollup(self):
        assert _is_larco_rollup({}) is False

    def test_africa_vietnam_schema_is_not_larco_rollup(self):
        assert _is_larco_rollup({"country": "default", "dataset_schema": "africa_vietnam"}) is False

    def test_larco_schema_with_default_country_is_rollup(self):
        assert _is_larco_rollup({"country": "default", "dataset_schema": "larco"}) is True

    def test_larco_schema_with_single_country_is_not_rollup(self):
        assert _is_larco_rollup({"country": "ecuador", "dataset_schema": "larco"}) is False


# ---------------------------------------------------------------------------
# _house_voice
# ---------------------------------------------------------------------------

class TestHouseVoice:
    def test_default_matches_unmodified_base_text(self):
        assert _house_voice("TITLE") == _house_voice_text("TITLE")

    def test_single_country_false_is_byte_identical_to_base_text(self):
        assert _house_voice("TITLE", single_country=False) == _house_voice_text("TITLE")

    def test_single_country_true_differs_from_multi_country(self):
        assert _house_voice("TITLE", single_country=True) != _house_voice("TITLE", single_country=False)

    def test_single_country_drops_multi_country_scope_language(self):
        prompt = _house_voice("TITLE", single_country=True)
        assert "across MULTIPLE" not in prompt
        assert "it is not a single-country report" not in prompt
        assert "among Vietnam's crop-insurance clients" not in prompt

    def test_single_country_still_carries_population_guidance(self):
        # Simplified, but the core "check each metric's population before
        # connecting it to another" guidance must survive -- still needed
        # within a single country (e.g. health vs credit-life product mix).
        prompt = _house_voice("TITLE", single_country=True)
        assert "population" in prompt
        assert "before connecting it to another" in prompt

    def test_single_country_preserves_everything_outside_scope_paragraph(self):
        multi = _house_voice("TITLE", single_country=False)
        single = _house_voice("TITLE", single_country=True)
        for anchor in ("SCALE DIRECTION:", "VOICE RULES:", "WORD LIMITS", "OUTPUT FORMAT:"):
            assert anchor in multi
            assert anchor in single
        # Everything from SCALE DIRECTION onward is untouched by the swap.
        assert multi[multi.index("SCALE DIRECTION"):] == single[single.index("SCALE DIRECTION"):]

    def test_instructs_against_em_and_en_dash(self):
        prompt = _house_voice("TITLE")
        assert "em dash" in prompt
        assert "en dash" in prompt

    def test_instructs_against_out_of_scope_country_recommendations(self):
        multi = " ".join(_house_voice("TITLE", single_country=False).split())
        single = " ".join(_house_voice("TITLE", single_country=True).split())
        assert "does not cover" in multi
        assert "never recommend an action for any other country" in single

    def test_own_prose_contains_no_em_or_en_dash_outside_the_instruction_itself(self):
        # The prompt is the model's own style example -- if HOUSE_VOICE's own
        # prose used the dash it's telling the model to avoid, the model
        # would imitate the example over the instruction. The single
        # permitted appearance is the instruction line itself, which quotes
        # the banned characters literally so the model knows what to avoid.
        prompt = _house_voice("TITLE")
        offending = [
            line for line in prompt.splitlines()
            if ("—" in line or "–" in line) and "em dash" not in line
        ]
        assert offending == []


# ---------------------------------------------------------------------------
# write_part wiring -- confirms the right prompt variant actually reaches
# the LLM call, not just that the builder functions work in isolation.
# ---------------------------------------------------------------------------

class TestWritePartWiring:
    _PACKAGE = {"part": "part_1", "title": "Client Understanding", "sections": {}}

    def test_default_single_country_arg_uses_multi_country_prompt(self, monkeypatch):
        captured = {}

        def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return json.dumps({"s1_1": "ok"})

        monkeypatch.setattr(writer, "call_llm", fake_call_llm)
        write_part(self._PACKAGE, "part_1", "gemini", "fake-key", None, "Some Title")
        assert captured["system_prompt"] == _house_voice("Some Title")

    def test_single_country_true_uses_single_country_prompt(self, monkeypatch):
        captured = {}

        def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return json.dumps({"s1_1": "ok"})

        monkeypatch.setattr(writer, "call_llm", fake_call_llm)
        write_part(self._PACKAGE, "part_1", "gemini", "fake-key", None, "Some Title", single_country=True)
        assert captured["system_prompt"] == _house_voice("Some Title", single_country=True)
        assert captured["system_prompt"] != _house_voice("Some Title", single_country=False)


# ---------------------------------------------------------------------------
# _build_sections_text -- the drivers-table not_applicable marker (the gap
# picked up after Phase 5: a population-exclusive driver like renewal_intent
# must read "NOT APPLICABLE" in the prompt text, not "SUPPRESSED").
# ---------------------------------------------------------------------------

class TestBuildSectionsTextDrivers:
    def _package(self, driver_row: dict) -> dict:
        return {"sections": {"s4_3": {
            "label": "Drivers", "word_limit": 90, "metrics": {}, "distributions": {},
            "qualitative": {}, "note": "",
            "drivers_data": [driver_row],
        }}}

    def test_not_applicable_driver_renders_marker_not_suppressed(self):
        pkg = self._package({
            "label": "Renewal Intent", "rho": None, "p_value": None, "n_valid": None,
            "suppressed": True, "not_applicable": True,
        })
        text = _build_sections_text(pkg)
        assert "Renewal Intent: rho=NOT APPLICABLE" in text
        assert "Renewal Intent: rho=SUPPRESSED" not in text

    def test_ordinary_suppressed_driver_unaffected(self):
        pkg = self._package({
            "label": "Coverage Understanding", "rho": None, "p_value": None, "n_valid": None,
            "suppressed": True, "not_applicable": False,
        })
        text = _build_sections_text(pkg)
        assert "Coverage Understanding: rho=SUPPRESSED" in text

    def test_normal_driver_unaffected(self):
        pkg = self._package({
            "label": "Confidence in Payout", "rho": 0.312, "p_value": 0.001, "n_valid": 1200,
            "suppressed": False, "not_applicable": False,
        })
        text = _build_sections_text(pkg)
        assert "Confidence in Payout: rho=+0.312, p=0.0010, n=1200" in text


# ---------------------------------------------------------------------------
# _build_sections_text -- the "_n"-suffix metric-key collision (a standalone
# metric whose OWN name happens to end in "_n" is invisible to the model
# entirely, since that suffix means "the n-count for the metric named before
# it" everywhere else in this format -- e.g. healthcare_access paired with
# healthcare_access_n). Caught for real on Part 10's report_spec.yaml
# metric, once named "new_country_n": rebuilding the actual prompt against
# real data showed the model was never shown its value at all, which is why
# it echoed the literal key name into prose instead of a real number.
# ---------------------------------------------------------------------------

class TestBuildSectionsTextMetrics:
    def _package(self, metrics: dict) -> dict:
        return {"sections": {"s1_1": {
            "label": "Section", "word_limit": 90, "metrics": metrics,
            "distributions": {}, "qualitative": {}, "note": "",
        }}}

    def test_standalone_metric_ending_in_n_is_dropped(self):
        # Documents the actual (surprising) behavior rather than asserting
        # it's correct -- any report_spec.yaml metric key must avoid an "_n"
        # suffix unless it's genuinely the n-count companion to another
        # metric of the same name minus "_n".
        pkg = self._package({"new_country_n": 270})
        text = _build_sections_text(pkg)
        assert "270" not in text
        assert "new_country_n" not in text

    def test_metric_key_avoiding_n_suffix_is_shown(self):
        pkg = self._package({"new_country_count": 270})
        text = _build_sections_text(pkg)
        assert "new_country_count: 270" in text

    def test_n_suffix_still_works_as_a_companion_count(self):
        # The intended use of the "_n" convention: metrics.get(m_key + "_n")
        # attaches as "(n=...)" to the metric it's named after, rather than
        # appearing as its own line.
        pkg = self._package({"healthcare_access": 0.339, "healthcare_access_n": 448})
        text = _build_sections_text(pkg)
        assert "healthcare_access: 0.339  (n=448)" in text
        assert "healthcare_access_n:" not in text


# ---------------------------------------------------------------------------
# Part 10's "no prior wave" hardening -- a real generated report once called
# the current wave a "founding baseline" and claimed product understanding
# "was not asked of this population" despite the prompt already forbidding
# both (see docs/maintenance/known-issues-log.md). These tests cover the
# code-level guard added on top of the prompt instruction: detection,
# corrective retry, and the fixed fallback sentence.
# ---------------------------------------------------------------------------

class TestPart10TrendAvailable:
    def test_true_when_any_row_has_a_real_prior_value(self):
        package = {"scorecard": [
            {"group_b_value": "N/A (no prior wave)"},
            {"group_b_value": "73.6%"},
        ]}
        assert writer._part10_trend_available(package) is True

    def test_false_when_every_row_has_no_prior_wave(self):
        package = {"scorecard": [
            {"group_b_value": "N/A (no prior wave)"},
            {"group_b_value": "N/A (no prior wave)"},
        ]}
        assert writer._part10_trend_available(package) is False

    def test_false_when_scorecard_is_empty_or_missing(self):
        assert writer._part10_trend_available({"scorecard": []}) is False
        assert writer._part10_trend_available({}) is False


class TestPart10NarrativeViolations:
    def test_clean_narrative_has_no_violations(self):
        text = writer._PART10_NO_PRIOR_WAVE_FALLBACK
        assert writer._part10_narrative_violations(text) == []

    def test_founding_baseline_is_flagged(self):
        text = ("This wave establishes the founding baseline for VisionFund's global "
                "insurance portfolio.")
        violations = writer._part10_narrative_violations(text)
        assert any("founding baseline" in v for v in violations)

    def test_founding_wave_is_flagged(self):
        violations = writer._part10_narrative_violations("This is the founding wave for the dataset.")
        assert any("founding wave" in v for v in violations)

    def test_not_asked_of_population_is_flagged(self):
        violations = writer._part10_narrative_violations(
            "Product understanding was not asked of this population."
        )
        assert any("not asked of this population" in v for v in violations)

    def test_comparative_verb_despite_no_trend_is_flagged(self):
        violations = writer._part10_narrative_violations(
            "Client satisfaction improved since last year despite no prior wave being loaded."
        )
        assert any("comparative language" in v for v in violations)

    def test_non_string_or_empty_returns_no_violations(self):
        assert writer._part10_narrative_violations(None) == []
        assert writer._part10_narrative_violations("") == []


class TestWriteAllPartsPart10Hardening:
    _PACKAGE_NO_PRIOR = {
        "part": "part_10", "title": "Trend Comparison",
        "scorecard": [{"label": "First-Time Access", "group_a_value": "77.2%",
                       "group_b_value": "N/A (no prior wave)", "significant": False, "sig_p": None}],
        "sections": {"narrative": {"note": ""}, "insight": {"word_limit": 120, "verbatims": []}},
    }

    def _init_run_dir(self, tmp_path, monkeypatch, run_id: str):
        monkeypatch.setattr(writer, "ROOT", tmp_path)
        run_dir = tmp_path / "runs" / run_id
        run_dir.mkdir(parents=True)
        (run_dir / "analysis_results.json").write_text(json.dumps({"meta": {}}), encoding="utf-8")
        return run_dir

    def test_retries_once_and_accepts_a_clean_second_attempt(self, tmp_path, monkeypatch):
        self._init_run_dir(tmp_path, monkeypatch, "run_a")
        calls = []

        def fake_call_llm(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                narrative = "This is the founding baseline for VisionFund's global insurance portfolio."
            else:
                narrative = writer._PART10_NO_PRIOR_WAVE_FALLBACK
            return json.dumps({"narrative": narrative, "insight": "ok"})

        monkeypatch.setattr(writer, "call_llm", fake_call_llm)
        texts = writer.write_all_parts([self._PACKAGE_NO_PRIOR], "run_a", model=None,
                                       provider="gemini", api_key="fake-key",
                                       max_retries=2, retry_delay=0)

        assert len(calls) == 2
        assert "CORRECTION REQUIRED" in calls[1]["user_content"]
        assert "founding baseline" not in texts["part_10"]["narrative"]
        assert texts["part_10"].get("_generation_failed") is None

    def test_falls_back_to_fixed_sentence_after_exhausting_retries(self, tmp_path, monkeypatch):
        self._init_run_dir(tmp_path, monkeypatch, "run_b")
        calls = []

        def fake_call_llm(**kwargs):
            calls.append(kwargs)
            return json.dumps({"narrative": "This wave is the founding baseline.", "insight": "ok"})

        monkeypatch.setattr(writer, "call_llm", fake_call_llm)
        texts = writer.write_all_parts([self._PACKAGE_NO_PRIOR], "run_b", model=None,
                                       provider="gemini", api_key="fake-key",
                                       max_retries=1, retry_delay=0)

        assert len(calls) == 2  # max_retries=1 -> initial attempt + one retry, both bad
        assert texts["part_10"]["narrative"] == writer._PART10_NO_PRIOR_WAVE_FALLBACK
        # Guaranteed by substitution, not marked as a failed generation --
        # the assembler must render this part normally, not as a manual
        # write-up placeholder.
        assert texts["part_10"].get("_generation_failed") is None

    def test_no_check_at_all_when_a_real_trend_is_available(self, tmp_path, monkeypatch):
        self._init_run_dir(tmp_path, monkeypatch, "run_c")
        package = dict(self._PACKAGE_NO_PRIOR)
        package["scorecard"] = [{"label": "First-Time Access", "group_a_value": "77.2%",
                                 "group_b_value": "73.6%", "significant": False, "sig_p": None}]
        calls = []

        def fake_call_llm(**kwargs):
            calls.append(kwargs)
            # Deliberately uses banned phrasing to prove the check is SKIPPED
            # (not just passed) once a real trend exists.
            return json.dumps({"narrative": "This wave is the founding baseline.", "insight": "ok"})

        monkeypatch.setattr(writer, "call_llm", fake_call_llm)
        texts = writer.write_all_parts([package], "run_c", model=None,
                                       provider="gemini", api_key="fake-key",
                                       max_retries=2, retry_delay=0)

        assert len(calls) == 1
        assert texts["part_10"]["narrative"] == "This wave is the founding baseline."


# ---------------------------------------------------------------------------
# _fmt_insight_summary's tiny-sentiment-base handling -- percentages on a
# base of 3 read as findings ("100%!"); below the threshold, instruct
# counts-only instead (see also generation/validate_output.py's
# _check_tiny_sentiment_base_percentages(), the advisory second line of
# defense for this same rule).
# ---------------------------------------------------------------------------

def _split(positive, negative, neutral, selection_rule="base description"):
    """R-006a's deterministic split shape for one group."""
    return {
        "positive": positive, "negative": negative, "neutral": neutral,
        "base_n": positive + negative + neutral,
        "source_pool_n": positive + negative + neutral,
        "selection_rule": selection_rule,
    }


class TestFmtInsightSummaryTinySentimentBase:
    """sentiment_split is always {group_label: split} (session-8) -- a
    single-group section nests under "all"."""

    def test_small_base_instructs_counts_only(self):
        summary = {"sentiment_split": {"all": _split(2, 1, 0)}}
        text = writer._fmt_insight_summary(summary)
        assert "n=3, too small to state as percentages" in text
        assert "do NOT" in text

    def test_large_base_permits_percentages(self):
        summary = {"sentiment_split": {"all": _split(18, 9, 3)}}
        text = writer._fmt_insight_summary(summary)
        assert "too small" not in text
        assert "SENTIMENT SPLIT:" in text

    def test_threshold_boundary_does_not_trigger_tiny_base_wording(self):
        summary = {"sentiment_split": {"all": _split(10, 0, 0)}}
        text = writer._fmt_insight_summary(summary)
        assert "too small" not in text

    def test_no_sentiment_split_omits_the_line_entirely(self):
        assert "SENTIMENT SPLIT" not in writer._fmt_insight_summary({"theme_summary": "x"})

    def test_selection_rule_is_surfaced_to_the_prompt(self):
        summary = {"sentiment_split": {"all": _split(18, 9, 3, selection_rule="53 of 55 claimants qualify.")}}
        text = writer._fmt_insight_summary(summary)
        assert "53 of 55 claimants qualify." in text


class TestFmtInsightSummaryMultiGroup:
    """Part 7's female/male split (session-8) -- more than one group must
    produce a comparison instruction, not two isolated statements."""

    def test_single_group_gets_no_comparison_instruction(self):
        summary = {"sentiment_split": {"all": _split(18, 9, 3)}}
        text = writer._fmt_insight_summary(summary)
        assert "compare these groups" not in text
        assert "SENTIMENT SPLIT BY GROUP" not in text

    def test_multi_group_gets_a_comparison_instruction(self):
        summary = {"sentiment_split": {
            "female": _split(428, 396, 260, selection_rule="1084 of 1196 women qualify."),
            "male": _split(180, 150, 90, selection_rule="420 of 478 men qualify."),
        }}
        text = writer._fmt_insight_summary(summary)
        assert "SENTIMENT SPLIT BY GROUP" in text
        assert "compare these groups explicitly" in text
        assert "FEMALE" in text and "MALE" in text
        assert "1084 of 1196 women qualify." in text
        assert "420 of 478 men qualify." in text

    def test_each_group_gets_its_own_percentage_eligibility(self):
        # One group above the threshold, one below -- each must be judged
        # independently, not by a combined/summed total across groups.
        summary = {"sentiment_split": {
            "female": _split(18, 9, 3),   # base_n=30, percentage-eligible
            "male": _split(2, 1, 0),      # base_n=3, too small
        }}
        text = writer._fmt_insight_summary(summary)
        female_line = next(l for l in text.splitlines() if l.strip().startswith("FEMALE"))
        male_line = next(l for l in text.splitlines() if l.strip().startswith("MALE"))
        assert "too small" not in female_line
        assert "too small to state as percentages" in male_line


# ---------------------------------------------------------------------------
# _build_scorecard_text -- R-009 (session-4): Part 10's own p-value leak
# doesn't live here (this function is shared by Parts 6, 7, and 10, and is
# not touched this session) -- it lives in orchestrator.py's
# _build_trend_data() no longer populating sig_p/significant for Part 10's
# rows at all. This is the actual proof of that fix: rows shaped exactly as
# orchestrator.py now produces them, fed into this real, unmodified
# function, must reach the LLM prompt with no "(p=...)" text -- not just an
# assertion on the row dict in isolation, and not the rendered docx table
# (which never showed a raw p-value to begin with; the leak was always in
# the prompt, not the render). Parts 6/7's own rows (sig_p populated) must
# keep citing a p-value exactly as before -- this function itself is
# unchanged, only what Part 10 now passes into it.
# ---------------------------------------------------------------------------

class TestBuildScorecardTextPart10NoPValueLeak:
    def _trend_row(self, **overrides) -> dict:
        row = {
            "label": "First-Time Access to Insurance",
            "group_a_value": "76.7%", "group_b_value": "73.6%",
            "sig_p": None, "significant": False,
            "population": None,
            "sig_test_note": "Identical question wording and options in both waves.",
        }
        row.update(overrides)
        return row

    def test_part10_shaped_row_with_sig_p_none_produces_no_p_note(self):
        text = _build_scorecard_text([self._trend_row()], "Current Wave", "Prior Wave")
        assert "(p=" not in text
        assert "p=" not in text

    def test_part10_shaped_row_never_shows_a_significance_asterisk(self):
        # significant is always False for Part 10 (orchestrator.py never
        # sets it True), so the asterisk this function would otherwise
        # print (sig_mark = "*" if row["significant"] else "") must never
        # appear on this row's own line.
        text = _build_scorecard_text([self._trend_row()], "Current Wave", "Prior Wave")
        row_line = next(l for l in text.splitlines() if "First-Time Access" in l)
        assert "*" not in row_line

    def test_reason_still_reaches_the_prompt_as_a_note(self):
        # The comparability reason (R-004) still needs to reach the model,
        # via the same sig_test_note field Parts 6/7's real significance
        # notes already use -- renaming that field would have silently cut
        # this off, which is exactly why orchestrator.py keeps the name.
        text = _build_scorecard_text([self._trend_row()], "Current Wave", "Prior Wave")
        assert "Identical question wording and options in both waves." in text

    def test_part6_shaped_row_with_real_sig_p_still_cites_it(self):
        # Confirms the fix is scoped to Part 10's own data, not a change to
        # this shared function -- a Part 6/7-style row with a real p-value
        # must keep citing it exactly as before.
        row = self._trend_row(sig_p=0.0234, significant=True)
        text = _build_scorecard_text([row], "Claimant", "Non-Claimant")
        assert "(p=" in text
