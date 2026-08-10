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
    _is_single_country,
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
        expected = f"VisionFund International Insurance Impact Report — Global Portfolio, {period}"
        assert _report_title("2026_Q2") == expected
        assert _report_title("2026_Q2", None) == expected
        assert _report_title("2026_Q2", {}) == expected

    def test_default_country_meta_matches_global_title(self):
        period = writer.format_period_label("2026_Q2")
        expected = f"VisionFund International Insurance Impact Report — Global Portfolio, {period}"
        assert _report_title("2026_Q2", {"country": "default", "country_label": "Default"}) == expected

    def test_scoped_country_uses_country_label(self):
        title = _report_title("2026_Q2", {"country": "vietnam", "country_label": "Vietnam"})
        assert title == f"VisionFund International Insurance Impact Report — Vietnam, {writer.format_period_label('2026_Q2')}"

    def test_scoped_country_without_label_falls_back_to_titlecase(self):
        title = _report_title("2026_Q2", {"country": "kenya"})
        assert "Kenya" in title


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
