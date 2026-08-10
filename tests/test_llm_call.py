"""
Unit tests for qualitative/llm_call.py — the single-country-vs-multi-country
system prompt variant. The core guarantee under test: a multi-country (or
country-indeterminate) payload must produce byte-identical output to the
original SYSTEM_PROMPT constant, so the global/multi-country report's prompt
never drifts as a side effect of adding single-country support.
Run: pytest tests/test_llm_call.py -v
"""
from __future__ import annotations

import json

import pytest

import qualitative.llm_call as llm_call
from qualitative.llm_call import (
    SYSTEM_PROMPT,
    _build_system_prompt,
    _distinct_payload_countries,
    call_gemini,
)


# ---------------------------------------------------------------------------
# _distinct_payload_countries
# ---------------------------------------------------------------------------

class TestDistinctPayloadCountries:
    def test_empty_payload_returns_empty_set(self):
        assert _distinct_payload_countries({}) == set()

    def test_all_groups_empty_returns_empty_set(self):
        payload = {"nps_promoters": [], "nps_detractors": []}
        assert _distinct_payload_countries(payload) == set()

    def test_null_country_values_are_ignored(self):
        payload = {"nps_promoters": [{"country": None}, {"country": ""}]}
        assert _distinct_payload_countries(payload) == set()

    def test_single_country_across_multiple_groups(self):
        payload = {
            "nps_promoters": [{"country": "Vietnam"}],
            "nps_detractors": [{"country": "Vietnam"}, {"country": "Vietnam"}],
        }
        assert _distinct_payload_countries(payload) == {"Vietnam"}

    def test_multiple_countries_across_groups(self):
        payload = {
            "nps_promoters": [{"country": "Kenya"}],
            "nps_detractors": [{"country": "Vietnam"}],
        }
        assert _distinct_payload_countries(payload) == {"Kenya", "Vietnam"}

    def test_non_list_values_are_skipped(self):
        # sparse_other-style groups are always lists in practice, but the
        # helper should not crash if a caller passes something else.
        payload = {"nps_promoters": [{"country": "Kenya"}], "meta": "not a list"}
        assert _distinct_payload_countries(payload) == {"Kenya"}


# ---------------------------------------------------------------------------
# _build_system_prompt
# ---------------------------------------------------------------------------

class TestBuildSystemPrompt:
    def test_multi_country_payload_returns_prompt_byte_identical_to_constant(self):
        payload = {"nps_promoters": [{"country": "Kenya"}, {"country": "Vietnam"}]}
        assert _build_system_prompt(payload) == SYSTEM_PROMPT

    def test_empty_payload_falls_back_to_multi_country_prompt(self):
        assert _build_system_prompt({}) == SYSTEM_PROMPT

    def test_all_null_country_payload_falls_back_to_multi_country_prompt(self):
        payload = {"nps_promoters": [{"country": None}]}
        assert _build_system_prompt(payload) == SYSTEM_PROMPT

    def test_single_country_payload_differs_from_constant(self):
        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        assert _build_system_prompt(payload) != SYSTEM_PROMPT

    def test_single_country_prompt_drops_country_diversity_language(self):
        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        prompt = _build_system_prompt(payload)
        assert "AND country" not in prompt
        assert "Do NOT nominate all 3 verbatims for a section from the same country" not in prompt
        assert "Country diversity is secondary" not in prompt
        assert "spans multiple country programmes" not in prompt

    def test_single_country_prompt_has_replacement_framing_and_diversity_line(self):
        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        prompt = _build_system_prompt(payload)
        assert "scoped to a single country programme" in prompt
        assert "Diverse: where possible, vary sex, is_claimant, and is_caregiver" in prompt

    def test_single_country_prompt_leaves_no_blank_line_artifact(self):
        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        prompt = _build_system_prompt(payload)
        assert "nominate best available\n\n**B. Produce a section insight**" in prompt

    def test_single_country_prompt_preserves_everything_else_unchanged(self):
        # Every other task/section/schema block must be untouched -- only the
        # two targeted regions differ between the two prompt variants.
        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        multi_lines = SYSTEM_PROMPT.splitlines()
        single_lines = _build_system_prompt(payload).splitlines()

        anchors = [
            "### TASK 1 — NPS Theme Tagging",
            "### TASK 6 — Protection Flags",
            "## THEME TAXONOMY (use ONLY these codes)",
            "## OUTPUT SCHEMA",
            '  "executive_summary": "3-5 sentences"',
        ]
        for anchor in anchors:
            assert anchor in multi_lines
            assert anchor in single_lines

        # The OUTPUT SCHEMA JSON block (the largest, most fragile chunk of
        # the prompt) must be byte-identical between both variants.
        schema_start_multi = SYSTEM_PROMPT.index("## OUTPUT SCHEMA")
        schema_start_single = _build_system_prompt(payload).index("## OUTPUT SCHEMA")
        assert SYSTEM_PROMPT[schema_start_multi:] == _build_system_prompt(payload)[schema_start_single:]


# ---------------------------------------------------------------------------
# call_gemini wiring -- confirms the right prompt variant actually reaches
# the LLM call, not just that the builder function works in isolation.
# ---------------------------------------------------------------------------

class TestCallGeminiPromptWiring:
    def test_multi_country_payload_sends_original_system_prompt(self, tmp_path, monkeypatch):
        captured = {}

        def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return json.dumps({"ok": True})

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)

        payload = {"nps_promoters": [{"country": "Kenya"}, {"country": "Vietnam"}]}
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        assert captured["system_prompt"] == SYSTEM_PROMPT

    def test_single_country_payload_sends_single_country_system_prompt(self, tmp_path, monkeypatch):
        captured = {}

        def fake_call_llm(**kwargs):
            captured.update(kwargs)
            return json.dumps({"ok": True})

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)

        payload = {"nps_promoters": [{"country": "Vietnam"}]}
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        assert captured["system_prompt"] != SYSTEM_PROMPT
        assert "scoped to a single country programme" in captured["system_prompt"]
