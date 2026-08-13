"""
Unit tests for qualitative/llm_call.py -- the batched NPS-tagging +
synthesis pipeline (see that module's docstring for the full rationale:
the original single-call design doesn't scale to the 2026 unified dataset's
payload size). Core guarantees under test:
  - NPS responses get split into the right number of batches and every
    batch's tagging output gets merged back correctly.
  - Protection flags / verbatim candidates / not-worth-it candidates get
    enriched with the original record (text, profile) when pooled, not just
    echoed back as bare ids.
  - The single-country-vs-multi-country prompt variant still applies
    correctly to both the batch and synthesis prompts.
  - The final merged dict has exactly parse_results.REQUIRED_TOP_KEYS, so
    parse_results.py needs no changes.
  - Partial batch failure degrades gracefully; total batch failure raises.
Run: pytest tests/test_llm_call.py -v
"""
from __future__ import annotations

import json

import pytest

import qualitative.llm_call as llm_call
from qualitative.llm_call import (
    _NPS_BATCH_SIZE,
    _build_batch_prompt,
    _build_synthesis_prompt,
    _chunk,
    _distinct_payload_countries,
    _is_single_country_payload,
    call_gemini,
)
from qualitative.parse_results import REQUIRED_TOP_KEYS


def _nps_record(idx: int, group: str, country: str = "Kenya", not_worth_it: bool = False) -> dict:
    return {
        "id": f"row_{idx:04d}", "text": f"response text {idx}", "sex": "Female",
        "client_age": 30, "branch": "Branch A", "country": country,
        "is_claimant": False, "is_caregiver": True, "is_female": True,
        "nps_group": group, "nps_score": 9, "worth_premium_value": 5 if not_worth_it else 1,
        "not_worth_it": not_worth_it,
    }


# ---------------------------------------------------------------------------
# _distinct_payload_countries / _is_single_country_payload
# ---------------------------------------------------------------------------

class TestDistinctPayloadCountries:
    def test_empty_payload_returns_empty_set(self):
        assert _distinct_payload_countries({}) == set()

    def test_null_country_values_are_ignored(self):
        payload = {"nps_promoters": [{"country": None}, {"country": ""}]}
        assert _distinct_payload_countries(payload) == set()

    def test_multiple_countries_across_groups(self):
        payload = {
            "nps_promoters": [{"country": "Kenya"}],
            "nps_detractors": [{"country": "Vietnam"}],
        }
        assert _distinct_payload_countries(payload) == {"Kenya", "Vietnam"}


class TestIsSingleCountryPayload:
    def test_single_country_is_true(self):
        assert _is_single_country_payload({"nps_promoters": [{"country": "Vietnam"}]}) is True

    def test_multi_country_is_false(self):
        payload = {"nps_promoters": [{"country": "Kenya"}, {"country": "Vietnam"}]}
        assert _is_single_country_payload(payload) is False

    def test_empty_payload_is_false(self):
        # Falls back to the multi-country prompt variant, the safer default
        # when scope can't be confirmed.
        assert _is_single_country_payload({}) is False


# ---------------------------------------------------------------------------
# _chunk
# ---------------------------------------------------------------------------

class TestChunk:
    def test_splits_into_even_batches(self):
        assert _chunk(list(range(10)), 5) == [[0, 1, 2, 3, 4], [5, 6, 7, 8, 9]]

    def test_final_batch_is_a_remainder(self):
        chunks = _chunk(list(range(11)), 5)
        assert len(chunks) == 3
        assert chunks[-1] == [10]

    def test_empty_list_produces_no_batches(self):
        assert _chunk([], 5) == []

    def test_fewer_items_than_batch_size_is_one_batch(self):
        assert _chunk([1, 2], 5) == [[1, 2]]


# ---------------------------------------------------------------------------
# Prompt variants
# ---------------------------------------------------------------------------

class TestPromptVariants:
    def test_batch_prompt_multi_country_has_country_diversity_language(self):
        prompt = _build_batch_prompt(is_single_country=False)
        assert "AND country" in prompt
        assert "spans multiple country programmes" in prompt

    def test_batch_prompt_single_country_drops_country_diversity_language(self):
        prompt = _build_batch_prompt(is_single_country=True)
        assert "AND country" not in prompt
        assert "scoped to a single country programme" in prompt

    def test_synthesis_prompt_multi_country_has_country_diversity_language(self):
        prompt = _build_synthesis_prompt(is_single_country=False)
        assert "AND country" in prompt
        assert "spans multiple country programmes" in prompt

    def test_synthesis_prompt_single_country_drops_country_diversity_language(self):
        prompt = _build_synthesis_prompt(is_single_country=True)
        assert "AND country" not in prompt
        assert "scoped to a single country programme" in prompt

    def test_batch_and_synthesis_prompts_share_identical_taxonomy_text(self):
        # Both prompts embed the same _THEME_TAXONOMY_BLOCK/_PROTECTION_FLAG_
        # TAXONOMY_BLOCK constants -- tagging must never drift depending on
        # which call (batch vs synthesis) produced it.
        batch = _build_batch_prompt(is_single_country=False)
        synthesis = _build_synthesis_prompt(is_single_country=False)
        assert llm_call._THEME_TAXONOMY_BLOCK in batch
        assert llm_call._THEME_TAXONOMY_BLOCK in synthesis
        assert llm_call._PROTECTION_FLAG_TAXONOMY_BLOCK in batch
        assert llm_call._PROTECTION_FLAG_TAXONOMY_BLOCK in synthesis


# ---------------------------------------------------------------------------
# call_gemini orchestration
# ---------------------------------------------------------------------------

def _fake_batch_response(batch_records: list) -> str:
    """A minimal-but-valid batch response tagging every record it was given."""
    tags = {"promoters": [], "passives": [], "detractors": []}
    for rec in batch_records:
        grp = rec["nps_group"] + "s"
        tags[grp].append([rec["id"], ["staff_service"]])
    candidates = {f"part{i}": [] for i in range(1, 8)}
    if batch_records:
        candidates["part4"] = [{"id": batch_records[0]["id"], "note": "good quote"}]
    not_worth_it = [
        {"id": r["id"], "type_guess": "pricing", "one_line_reason": "too expensive"}
        for r in batch_records if r.get("not_worth_it")
    ]
    protection_flags = []
    if len(batch_records) > 1:
        protection_flags = [{"id": batch_records[1]["id"], "flag_type": "staff_misconduct",
                              "severity": "low", "reason": "minor friction"}]
    return json.dumps({
        "nps_tags": tags, "protection_flags": protection_flags,
        "verbatim_candidates": candidates, "not_worth_it_candidates": not_worth_it,
    })


def _fake_synthesis_response() -> str:
    return json.dumps({
        "claims_other_tagged": {"claim_no_reason_other": [], "claim_challenges_other_support": []},
        "not_worth_it_themes": [],
        "other_subthemes": {"claim_no_reason_other": [], "claim_challenges_other_support": []},
        "section_verbatims": {f"part{i}": [] for i in range(1, 8)},
        "section_insights": {},
        "protection_flags": [],
        "executive_summary": "summary",
        "top_findings": ["a", "b", "c"],
        "top_actions": ["x", "y", "z"],
    })


class TestCallGeminiOrchestration:
    def _install_fake_call_llm(self, monkeypatch, captured_calls):
        def fake_call_llm(**kwargs):
            captured_calls.append(kwargs)
            # Batch calls send {"nps_responses": [...]}; the synthesis call
            # sends a dict with "verbatim_candidates" as one of its keys --
            # distinguish on that rather than call order, so this stays
            # correct regardless of how many batches run.
            body = json.loads(kwargs["user_content"])
            if "nps_responses" in body:
                return _fake_batch_response(body["nps_responses"])
            return _fake_synthesis_response()

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)

    def test_small_payload_is_a_single_batch_plus_synthesis(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter")],
            "nps_passives": [_nps_record(2, "passive")],
            "nps_detractors": [_nps_record(3, "detractor")],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        # 1 NPS batch (3 records, well under _NPS_BATCH_SIZE) + 1 synthesis call.
        assert len(captured) == 2

    def test_large_nps_group_splits_into_multiple_batches(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        n = _NPS_BATCH_SIZE + 50
        payload = {
            "nps_promoters": [_nps_record(i, "promoter") for i in range(n)],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        # ceil(n / _NPS_BATCH_SIZE) == 2 batches + 1 synthesis call.
        assert len(captured) == 3

    def test_final_result_has_exactly_required_top_keys(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter")],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        # section_insights is intentionally additive/optional in the original
        # schema (parse_results.py's _check_section_insights only warns, never
        # requires it) -- the merged result carries it too, so this checks a
        # superset rather than exact equality.
        assert REQUIRED_TOP_KEYS <= set(result.keys())

    def test_nps_tags_merge_across_batches(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        n = _NPS_BATCH_SIZE + 10
        payload = {
            "nps_promoters": [_nps_record(i, "promoter") for i in range(n)],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        assert len(result["nps_tags"]["promoters"]) == n

    def test_protection_flag_enriched_with_column_from_nps_group(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [], "nps_passives": [],
            "nps_detractors": [_nps_record(1, "detractor"), _nps_record(2, "detractor")],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        # _fake_batch_response() flags the batch's 2nd record when >1 present.
        assert len(result["protection_flags"]) == 1
        assert result["protection_flags"][0]["column"] == "nps_detractors"
        assert result["protection_flags"][0]["id"] == "row_0002"

    def test_verbatim_candidate_enriched_with_original_record_fields(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [], "nps_passives": [], "nps_detractors": [_nps_record(1, "detractor")],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        synth_input = json.loads(synthesis_call["user_content"])
        cand = synth_input["verbatim_candidates"]["part4"][0]
        assert cand["id"] == "row_0001"
        assert cand["text"] == "response text 1"
        assert cand["note"] == "good quote"

    def test_not_worth_it_candidate_pooled_with_text(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter", not_worth_it=True)],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        synth_input = json.loads(synthesis_call["user_content"])
        assert len(synth_input["not_worth_it_candidates"]) == 1
        cand = synth_input["not_worth_it_candidates"][0]
        assert cand["id"] == "row_0001"
        assert cand["text"] == "response text 1"
        assert cand["type_guess"] == "pricing"

    def test_raw_response_files_written_for_each_call(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter")], "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        raw_path = tmp_path / "raw.json"
        call_gemini(payload, raw_path, provider="gemini", api_key="fake-key")

        assert raw_path.exists()
        assert (tmp_path / "raw.batch_0.json").exists()
        assert (tmp_path / "raw.synthesis.json").exists()

    def test_single_country_payload_uses_single_country_prompts(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter", country="Vietnam")],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        for call in captured:
            assert "scoped to a single country programme" in call["system_prompt"]

    def test_all_batches_failing_raises(self, tmp_path, monkeypatch):
        def always_fails(**kwargs):
            raise RuntimeError("simulated provider failure")

        monkeypatch.setattr(llm_call, "call_llm", always_fails)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter")], "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        with pytest.raises(RuntimeError):
            call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                        max_retries=0, retry_delay_seconds=0)

    def test_partial_batch_failure_still_produces_a_result(self, tmp_path, monkeypatch):
        call_count = {"n": 0}

        def flaky_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" in body:
                call_count["n"] += 1
                if call_count["n"] == 1:
                    raise RuntimeError("simulated failure on first batch")
                return _fake_batch_response(body["nps_responses"])
            return _fake_synthesis_response()

        monkeypatch.setattr(llm_call, "call_llm", flaky_call_llm)

        n = _NPS_BATCH_SIZE + 10  # 2 batches
        payload = {
            "nps_promoters": [_nps_record(i, "promoter") for i in range(n)],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                              max_retries=0, retry_delay_seconds=0)

        # Only the 2nd batch's records made it into the merged tags.
        assert len(result["nps_tags"]["promoters"]) == 10
