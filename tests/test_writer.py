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

    def test_larco_rollup_uses_larco_regional_title_not_global(self):
        title = _report_title("2026_Q2", {"country": "default", "dataset_schema": "larco"})
        assert "LARCO Regional Portfolio" in title
        assert "Global Portfolio" not in title

    def test_larco_single_country_still_uses_country_label(self):
        title = _report_title(
            "2026_Q2", {"country": "ecuador", "country_label": "Ecuador", "dataset_schema": "larco"}
        )
        assert title == f"VisionFund International Insurance Impact Report: Ecuador, {writer.format_period_label('2026_Q2')}"
        assert "LARCO" not in title

    def test_missing_dataset_schema_key_defaults_to_global(self):
        # analysis_results.json files written before dataset_schema was added
        # to meta must still resolve to the original global-portfolio title.
        title = _report_title("2026_Q2", {"country": "default"})
        assert "Global Portfolio" in title

    def test_report_scope_lacro_uses_larco_regional_title_not_global(self):
        # The real bug this guards against: a report_scope=="lacro" run on
        # the unified schema (country="default", dataset_schema=
        # "africa_vietnam") previously fell through to "Global Portfolio"
        # since only the legacy dataset_schema=="larco" path was checked.
        title = _report_title("2026_Q2", {
            "country": "default", "dataset_schema": "africa_vietnam",
            "report_scope": "lacro", "report_scope_label": "LACRO (Latin America and Caribbean)",
        })
        assert "LARCO Regional Portfolio" in title
        assert "Global Portfolio" not in title

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
