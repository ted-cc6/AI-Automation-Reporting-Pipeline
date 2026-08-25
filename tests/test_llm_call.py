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
import qualitative.tag_cache as tag_cache
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


@pytest.fixture(autouse=True)
def _isolated_tag_cache(tmp_path, monkeypatch):
    """Every test in this file gets its own empty, throwaway tag cache file
    instead of touching the real qualitative/cache/tag_cache.json -- without
    this, every call_gemini() test would read/write a real file in the repo
    (see qualitative/tag_cache.py's load()/save(), which resolve
    DEFAULT_CACHE_PATH fresh from the module namespace on each call
    specifically so this monkeypatch works)."""
    monkeypatch.setattr(tag_cache, "DEFAULT_CACHE_PATH", tmp_path / "tag_cache.json")


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
# _dedupe_protection_flags
# ---------------------------------------------------------------------------

class TestDedupeProtectionFlags:
    def test_no_duplicates_passes_through_unchanged(self):
        flags = [
            {"id": "row_0001", "flag_type": "staff_misconduct", "severity": "medium"},
            {"id": "row_0002", "flag_type": "coercion", "severity": "high"},
        ]
        assert llm_call._dedupe_protection_flags(flags) == flags

    def test_same_id_and_flag_type_collapses_to_one(self):
        # The synthesis call was handed nps_protection_flags_found as context
        # and can re-emit the same case in its own protection_flags list --
        # this is the real bug the user cited (refs #12/#18/#600/#806
        # appearing twice, inflating the total).
        flags = [
            {"id": "row_0012", "flag_type": "staff_misconduct", "severity": "medium", "reason": "batch phase"},
            {"id": "row_0012", "flag_type": "staff_misconduct", "severity": "medium", "reason": "synthesis"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert len(result) == 1
        assert result[0]["reason"] == "batch phase"  # first occurrence wins on a tie

    def test_higher_severity_copy_wins(self):
        # Same underlying case flagged at different severities by the two
        # phases (the user's cited "#1678 appeared in two tiers") -- keep
        # the more severe one rather than picking arbitrarily.
        flags = [
            {"id": "row_1678", "flag_type": "coercion", "severity": "low"},
            {"id": "row_1678", "flag_type": "coercion", "severity": "high"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert len(result) == 1
        assert result[0]["severity"] == "high"

    def test_same_id_different_flag_type_both_kept(self):
        # A genuinely distinct second concern about the same respondent is
        # not a duplicate -- only the same (id, flag_type) pair collapses.
        flags = [
            {"id": "row_0042", "flag_type": "staff_misconduct", "severity": "medium"},
            {"id": "row_0042", "flag_type": "data_privacy", "severity": "low"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert len(result) == 2

    def test_preserves_first_seen_order(self):
        flags = [
            {"id": "row_0003", "flag_type": "coercion", "severity": "low"},
            {"id": "row_0001", "flag_type": "coercion", "severity": "low"},
            {"id": "row_0003", "flag_type": "coercion", "severity": "high"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert [f["id"] for f in result] == ["row_0003", "row_0001"]

    def test_same_id_and_flag_type_different_column_both_kept(self):
        # R-018 (docs/report_spec.md, session-9): row_id is one-per-
        # RESPONDENT, not one-per-(respondent, column) -- a respondent
        # with a concern in two different source columns, tagged with the
        # SAME flag_type, must not collapse to one. Modelled on the real
        # row_1015 case: an NPS-phase complaint and a claims-other-phase
        # complaint naming a second affected person (the client's
        # daughter), both unfair_claim_denial.
        flags = [
            {"id": "row_1015", "column": "nps_detractors", "flag_type": "unfair_claim_denial",
             "severity": "high", "reason": "could never use the insurance"},
            {"id": "row_1015", "column": "claim_challenges_other_support", "flag_type": "unfair_claim_denial",
             "severity": "high", "reason": "claim was not valid for both themself and their daughter"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert len(result) == 2
        reasons = {f["reason"] for f in result}
        assert "claim was not valid for both themself and their daughter" in reasons

    def test_same_id_column_and_flag_type_still_collapses(self):
        # The genuine duplicate case (same case, same column, re-emitted)
        # must still collapse -- column joining the key narrows what
        # counts as "the same case", it doesn't turn off dedup entirely.
        flags = [
            {"id": "row_0012", "column": "nps_promoters", "flag_type": "staff_misconduct",
             "severity": "medium", "reason": "batch phase"},
            {"id": "row_0012", "column": "nps_promoters", "flag_type": "staff_misconduct",
             "severity": "medium", "reason": "synthesis"},
        ]
        result = llm_call._dedupe_protection_flags(flags)
        assert len(result) == 1
        assert result[0]["reason"] == "batch phase"


class TestRecordColumn:
    """_record_column() resolves the payload GROUP name (the vocabulary
    protection flags' own "column" field uses -- confirmed against real
    model output: {"column": "claim_challenges_other_support"}), NOT the
    raw dataframe column a record's source_column carries. Conflating the
    two was a real bug caught before this shipped -- see the function's
    own docstring."""

    def test_nps_record_resolves_via_nps_group(self):
        assert llm_call._record_column({"nps_group": "detractor"}) == "nps_detractors"
        assert llm_call._record_column({"nps_group": "promoter"}) == "nps_promoters"

    def test_non_nps_record_translates_raw_source_column_to_group_name(self):
        # "q_no_claim_reason__other_text" is the RAW dataframe column
        # (prepare_payload.py's own source_column value) -- must resolve
        # to the payload GROUP name a protection flag's "column" field
        # actually contains, not pass the raw column through unchanged.
        rec = {"source_column": "q_no_claim_reason__other_text"}
        assert llm_call._record_column(rec) == "claim_no_reason_other"

    def test_both_claim_challenges_columns_map_to_the_same_group(self):
        # q_claim_challenges__other_text and q_claim_challenges__support_text
        # both feed the single claim_challenges_other_support payload group
        # (prepare_payload.py's build_payload()) -- must agree here too.
        assert llm_call._record_column({"source_column": "q_claim_challenges__other_text"}) \
            == "claim_challenges_other_support"
        assert llm_call._record_column({"source_column": "q_claim_challenges__support_text"}) \
            == "claim_challenges_other_support"

    def test_sparse_other_column_resolves_to_sparse_other_group(self):
        rec = {"source_column": "q_income_sources__other_text"}
        assert llm_call._record_column(rec) == "sparse_other"

    def test_unmapped_source_column_falls_back_to_itself_not_a_crash(self):
        # Defensive only -- every real column is in _SOURCE_COLUMN_TO_GROUP;
        # an unmapped one (e.g. a future column added to config.yaml but
        # not here yet) should degrade to "fails to match", not raise.
        rec = {"source_column": "q_some_future_column__other_text"}
        assert llm_call._record_column(rec) == "q_some_future_column__other_text"

    def test_source_column_takes_precedence_when_both_present(self):
        # Shouldn't happen in real data (a record is either NPS or not),
        # but source_column is the more specific signal if both are set.
        rec = {"source_column": "q_income_sources__other_text", "nps_group": "promoter"}
        assert llm_call._record_column(rec) == "sparse_other"

    def test_neither_present_returns_none(self):
        assert llm_call._record_column({}) is None
        assert llm_call._record_column({"nps_group": "unknown_value"}) is None


class TestApplyProtectionFlagCache:
    def test_same_id_two_columns_one_flag_attributed_once_not_twice(self):
        # R-029 (docs/report_spec.md, session-9): a respondent can appear
        # twice in scanned_records (once per column with qualifying text)
        # sharing one id -- found_by_id used to key on id alone, handing
        # BOTH instances the same flag regardless of which one it came
        # from. Modelled on the real row_0841/row_1015 duplicates observed
        # in this run's own saved output before this fix.
        cache = {}
        scanned_records = [
            {"id": "row_0841", "nps_group": "promoter", "text": "nps text"},
            {"id": "row_0841", "source_column": "q_vf_services_received__other_text", "text": "sparse text"},
        ]
        found_flags = [
            {"id": "row_0841", "column": "nps_promoters", "flag_type": "staff_misconduct",
             "severity": "medium", "reason": "unresponsive after two months"},
        ]
        result = llm_call._apply_protection_flag_cache(scanned_records, found_flags, cache)
        assert len(result) == 1
        assert result[0]["reason"] == "unresponsive after two months"

    def test_two_columns_two_distinct_flags_both_attributed_correctly(self):
        cache = {}
        scanned_records = [
            {"id": "row_1015", "nps_group": "detractor", "text": "nps text"},
            {"id": "row_1015", "source_column": "q_claim_challenges__other_text", "text": "claims text"},
        ]
        found_flags = [
            {"id": "row_1015", "column": "nps_detractors", "flag_type": "unfair_claim_denial",
             "severity": "high", "reason": "could never use the insurance"},
            # "claim_challenges_other_support" -- the payload GROUP name,
            # matching what the model actually puts in "column" (confirmed
            # against real output), not the raw "q_claim_challenges__other_text".
            {"id": "row_1015", "column": "claim_challenges_other_support", "flag_type": "unfair_claim_denial",
             "severity": "high", "reason": "claim was not valid for both themself and their daughter"},
        ]
        result = llm_call._apply_protection_flag_cache(scanned_records, found_flags, cache)
        assert len(result) == 2
        reasons = {f["reason"] for f in result}
        assert reasons == {
            "could never use the insurance",
            "claim was not valid for both themself and their daughter",
        }

    def test_unflagged_scanned_record_stays_unflagged(self):
        cache = {}
        scanned_records = [{"id": "row_0001", "nps_group": "passive", "text": "nothing wrong here"}]
        result = llm_call._apply_protection_flag_cache(scanned_records, [], cache)
        assert result == []


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

    def test_synthesis_prompt_instructs_against_out_of_scope_country_recommendations(self):
        # top_actions is where the model writes recommendations -- a
        # region-scoped report (e.g. LACRO) must never recommend an action
        # for a country outside its own scope (e.g. Kenya).
        prompt = _build_synthesis_prompt(is_single_country=False)
        assert "does not cover" in prompt

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

    def test_no_prompt_text_itself_contains_an_em_or_en_dash(self):
        # The prompt is the model's own style example -- if the instruction
        # text uses the dash it's telling the model to avoid, the model will
        # imitate the example over the instruction (see writer.py's
        # _house_voice_text() for the same principle applied to report prose).
        for prompt in (
            _build_batch_prompt(is_single_country=False),
            _build_batch_prompt(is_single_country=True),
            _build_synthesis_prompt(is_single_country=False),
            _build_synthesis_prompt(is_single_country=True),
        ):
            assert "—" not in prompt
            assert "–" not in prompt

    def test_both_prompts_instruct_against_em_and_en_dash(self):
        batch = _build_batch_prompt(is_single_country=False)
        synthesis = _build_synthesis_prompt(is_single_country=False)
        assert "em dash" in batch and "en dash" in batch
        assert "em dash" in synthesis and "en dash" in synthesis

    def test_batch_prompt_task1_requires_sentiment_not_derived_from_nps_group(self):
        # R-006a Stage 1 (docs/report_spec.md): sentiment must be judged
        # from the response text, not shortcut from promoter/passive/
        # detractor -- otherwise it just reproduces the NPS score band and
        # adds no signal.
        prompt = _build_batch_prompt(is_single_country=False)
        assert '"positive", "negative", or "neutral"' in prompt
        assert "NOT a shortcut from" in prompt
        assert '["row_id", ["theme1", "theme2"], "sentiment"]' in prompt


# ---------------------------------------------------------------------------
# _apply_theme_tag_cache
# ---------------------------------------------------------------------------

class TestApplyThemeTagCache:
    def test_fresh_entry_is_cached_and_returned_unchanged(self):
        cache = {}
        by_id = {"row_0001": {"text": "hello"}}
        entries = [["row_0001", ["staff_service"], "positive"]]
        out = llm_call._apply_theme_tag_cache(entries, by_id, cache)
        assert out == [["row_0001", ["staff_service"], "positive"]]
        assert len(cache) == 1

    def test_cached_entry_overrides_fresh_themes_and_sentiment(self):
        cache = {}
        by_id = {"row_0001": {"text": "hello"}}
        llm_call._apply_theme_tag_cache(
            [["row_0001", ["staff_service"], "negative"]], by_id, cache
        )
        # Same id/text, different fresh output -- cached decision wins on both fields.
        out = llm_call._apply_theme_tag_cache(
            [["row_0001", ["product_value"], "positive"]], by_id, cache
        )
        assert out == [["row_0001", ["staff_service"], "negative"]]

    def test_two_element_entry_passes_through_unchanged_and_uncached(self):
        # No sentiment to cache or restore -- see the function's own docstring.
        cache = {}
        by_id = {"row_0001": {"text": "hello"}}
        entries = [["row_0001", ["staff_service"]]]
        out = llm_call._apply_theme_tag_cache(entries, by_id, cache)
        assert out == [["row_0001", ["staff_service"]]]
        assert cache == {}

    def test_different_text_is_a_fresh_cache_miss(self):
        cache = {}
        llm_call._apply_theme_tag_cache(
            [["row_0001", ["staff_service"], "negative"]],
            {"row_0001": {"text": "original text"}}, cache,
        )
        out = llm_call._apply_theme_tag_cache(
            [["row_0001", ["product_value"], "positive"]],
            {"row_0001": {"text": "a different response entirely"}}, cache,
        )
        assert out == [["row_0001", ["product_value"], "positive"]]


# ---------------------------------------------------------------------------
# call_gemini orchestration
# ---------------------------------------------------------------------------

def _fake_batch_response(batch_records: list) -> str:
    """A minimal-but-valid batch response tagging every record it was given."""
    tags = {"promoters": [], "passives": [], "detractors": []}
    for rec in batch_records:
        grp = rec["nps_group"] + "s"
        tags[grp].append([rec["id"], ["staff_service"], "positive"])
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

    def test_synthesis_re_flagging_a_batch_flagged_case_is_deduped(self, tmp_path, monkeypatch):
        # Synthesis is handed nps_protection_flags_found as context (see
        # llm_call.py's synthesis_input) and can re-emit the same case in its
        # own protection_flags output, sometimes at a different severity --
        # the merged result must collapse that to one entry, not double-count
        # the same client. R-018 (session-9): this is only the SAME case if
        # it also carries the same "column" -- the model is shown each
        # context flag's own column and re-flagging genuinely the same case
        # would carry it forward, so the fake synthesis response sets it
        # here too (matching the batch phase's "nps_detractors", the same
        # column _nps_record(2, "detractor") resolves to).
        captured = []

        def fake_call_llm(**kwargs):
            captured.append(kwargs)
            body = json.loads(kwargs["user_content"])
            if "nps_responses" in body:
                return _fake_batch_response(body["nps_responses"])
            synth = json.loads(_fake_synthesis_response())
            synth["protection_flags"] = [
                {"id": "row_0002", "column": "nps_detractors", "flag_type": "staff_misconduct",
                 "severity": "high", "reason": "escalated on full-payload review"},
            ]
            return json.dumps(synth)

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)

        payload = {
            "nps_promoters": [], "nps_passives": [],
            "nps_detractors": [_nps_record(1, "detractor"), _nps_record(2, "detractor")],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        matching = [f for f in result["protection_flags"] if f["id"] == "row_0002"]
        assert len(matching) == 1
        # The higher-severity copy (synthesis's "high") wins over the batch
        # phase's "low".
        assert matching[0]["severity"] == "high"

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


# ---------------------------------------------------------------------------
# Per-record classification stability across regenerations (qualitative/
# tag_cache.py). Three consecutive runs on identical data were observed to
# disagree on theme rankings and protection-flag counts/severities with no
# data change -- these tests simulate two consecutive call_gemini() runs
# against the SAME cache (the autouse _isolated_tag_cache fixture points
# DEFAULT_CACHE_PATH at one shared tmp_path file for the whole test, so two
# calls within one test share a cache exactly like two regenerations in the
# same container session would) and confirm the second run's result matches
# the first run's cached decision, not whatever the second run's own fresh
# (deliberately different) mock LLM output says.
# ---------------------------------------------------------------------------

class TestQualitativeTagCacheStability:
    def _payload(self, records: list) -> dict:
        return {
            "nps_promoters": [], "nps_passives": [], "nps_detractors": records,
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }

    def test_theme_tags_stable_across_two_runs_with_different_fresh_output(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" not in body:
                return _fake_synthesis_response()
            calls["n"] += 1
            # Deliberately different theme each call, to prove the SECOND
            # run's result is the cache's value, not this fresh one.
            theme = "product_value" if calls["n"] == 1 else "staff_service"
            return json.dumps({
                "nps_tags": {"promoters": [], "passives": [], "detractors": [["row_0001", [theme], "negative"]]},
                "protection_flags": [], "verbatim_candidates": {f"part{i}": [] for i in range(1, 8)},
                "not_worth_it_candidates": [],
            })

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)
        payload = self._payload([_nps_record(1, "detractor")])

        first = call_gemini(payload, tmp_path / "raw1.json", provider="gemini", api_key="fake-key")
        second = call_gemini(payload, tmp_path / "raw2.json", provider="gemini", api_key="fake-key")

        assert first["nps_tags"]["detractors"] == [["row_0001", ["product_value"], "negative"]]
        # Same result on rerun -- NOT ["staff_service"], which is what this
        # run's own fresh mock call actually returned.
        assert second["nps_tags"]["detractors"] == [["row_0001", ["product_value"], "negative"]]

    def test_sentiment_stable_across_two_runs_with_different_fresh_output(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" not in body:
                return _fake_synthesis_response()
            calls["n"] += 1
            # Same theme both calls, deliberately different SENTIMENT --
            # proves sentiment is cached/restored the same way themes are,
            # not just passed through as an untracked extra element.
            sentiment = "negative" if calls["n"] == 1 else "positive"
            return json.dumps({
                "nps_tags": {"promoters": [], "passives": [],
                             "detractors": [["row_0001", ["staff_service"], sentiment]]},
                "protection_flags": [], "verbatim_candidates": {f"part{i}": [] for i in range(1, 8)},
                "not_worth_it_candidates": [],
            })

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)
        payload = self._payload([_nps_record(1, "detractor")])

        first = call_gemini(payload, tmp_path / "raw1.json", provider="gemini", api_key="fake-key")
        second = call_gemini(payload, tmp_path / "raw2.json", provider="gemini", api_key="fake-key")

        assert first["nps_tags"]["detractors"][0][2] == "negative"
        # Same result on rerun -- NOT "positive", which is what this run's
        # own fresh mock call actually returned.
        assert second["nps_tags"]["detractors"][0][2] == "negative"

    def test_protection_flag_severity_stable_across_two_runs(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" not in body:
                return _fake_synthesis_response()
            calls["n"] += 1
            severity = "low" if calls["n"] == 1 else "high"
            return json.dumps({
                "nps_tags": {"promoters": [], "passives": [], "detractors": [["row_0001", ["staff_service"]]]},
                "protection_flags": [
                    {"id": "row_0001", "flag_type": "staff_misconduct", "severity": severity, "reason": "r"}
                ],
                "verbatim_candidates": {f"part{i}": [] for i in range(1, 8)},
                "not_worth_it_candidates": [],
            })

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)
        payload = self._payload([_nps_record(1, "detractor")])

        first = call_gemini(payload, tmp_path / "raw1.json", provider="gemini", api_key="fake-key")
        second = call_gemini(payload, tmp_path / "raw2.json", provider="gemini", api_key="fake-key")

        assert first["protection_flags"][0]["severity"] == "low"
        # Cached decision from the first run wins, not this run's "high".
        assert second["protection_flags"][0]["severity"] == "low"

    def test_unflagged_record_stays_unflagged_even_if_a_later_run_would_flag_it(self, tmp_path, monkeypatch):
        calls = {"n": 0}

        def fake_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" not in body:
                return _fake_synthesis_response()
            calls["n"] += 1
            flags = [] if calls["n"] == 1 else [
                {"id": "row_0001", "flag_type": "staff_misconduct", "severity": "medium", "reason": "r"}
            ]
            return json.dumps({
                "nps_tags": {"promoters": [], "passives": [], "detractors": [["row_0001", ["staff_service"]]]},
                "protection_flags": flags,
                "verbatim_candidates": {f"part{i}": [] for i in range(1, 8)},
                "not_worth_it_candidates": [],
            })

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)
        payload = self._payload([_nps_record(1, "detractor")])

        first = call_gemini(payload, tmp_path / "raw1.json", provider="gemini", api_key="fake-key")
        second = call_gemini(payload, tmp_path / "raw2.json", provider="gemini", api_key="fake-key")

        assert first["protection_flags"] == []
        # The first run's "checked, not flagged" decision is itself cached
        # and stable -- a record cannot gain a flag on a later run just
        # because that run's fresh LLM call happened to produce one.
        assert second["protection_flags"] == []

    def test_a_genuinely_new_record_is_still_tagged_fresh(self, tmp_path, monkeypatch):
        # Confirms the cache doesn't just freeze the FIRST run's entire
        # output wholesale -- a record with no prior cache entry (here,
        # different text under the same id, so a different content hash)
        # still gets tagged normally.
        def fake_call_llm(**kwargs):
            body = json.loads(kwargs["user_content"])
            if "nps_responses" not in body:
                return _fake_synthesis_response()
            records = body["nps_responses"]
            tags = [[r["id"], ["product_value"]] for r in records]
            return json.dumps({
                "nps_tags": {"promoters": [], "passives": [], "detractors": tags},
                "protection_flags": [], "verbatim_candidates": {f"part{i}": [] for i in range(1, 8)},
                "not_worth_it_candidates": [],
            })

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)
        first_payload = self._payload([_nps_record(1, "detractor")])
        call_gemini(first_payload, tmp_path / "raw1.json", provider="gemini", api_key="fake-key")

        rec2 = _nps_record(1, "detractor")
        rec2["text"] = "a completely different response, never seen before"
        second_payload = self._payload([rec2])
        second = call_gemini(second_payload, tmp_path / "raw2.json", provider="gemini", api_key="fake-key")

        assert second["nps_tags"]["detractors"] == [["row_0001", ["product_value"]]]


# ---------------------------------------------------------------------------
# excluded_countries -- data_quality_flags.py's exclusion mechanism (see
# that module's docstring). Flagged countries stay in nps_tags/theme counts
# (aggregate figures are unaffected) but must never appear as a verbatim
# candidate or not-worth-it representative -- and the synthesis prompt must
# carry an explicit instruction not to cite them as headline evidence.
# ---------------------------------------------------------------------------

class TestExcludedCountries:
    def _install_fake_call_llm(self, monkeypatch, captured_calls):
        def fake_call_llm(**kwargs):
            captured_calls.append(kwargs)
            body = json.loads(kwargs["user_content"])
            if "nps_responses" in body:
                tags = {"promoters": [], "passives": [], "detractors": []}
                candidates = {f"part{i}": [] for i in range(1, 8)}
                not_worth_it = []
                for rec in body["nps_responses"]:
                    tags[rec["nps_group"] + "s"].append([rec["id"], ["staff_service"]])
                    candidates["part4"].append({"id": rec["id"], "note": "candidate"})
                    if rec.get("not_worth_it"):
                        not_worth_it.append({"id": rec["id"], "type_guess": "pricing", "one_line_reason": "x"})
                return json.dumps({
                    "nps_tags": tags, "protection_flags": [],
                    "verbatim_candidates": candidates, "not_worth_it_candidates": not_worth_it,
                })
            return _fake_synthesis_response()

        monkeypatch.setattr(llm_call, "call_llm", fake_call_llm)

    def test_flagged_country_excluded_from_verbatim_candidates(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [
                _nps_record(1, "promoter", country="Bolivia"),
                _nps_record(2, "promoter", country="Ecuador"),
            ],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                     excluded_countries=["Bolivia"])

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        synth_input = json.loads(synthesis_call["user_content"])
        candidate_ids = [c["id"] for c in synth_input["verbatim_candidates"]["part4"]]
        assert candidate_ids == ["row_0002"]  # Bolivia's row_0001 excluded

    def test_flagged_country_still_tagged_in_nps_tags(self, tmp_path, monkeypatch):
        # Aggregate figures (nps_tags, and therefore theme_counts) are
        # unaffected by the exclusion -- only quote/example eligibility is.
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter", country="Bolivia")],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        result = call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                              excluded_countries=["Bolivia"])

        assert len(result["nps_tags"]["promoters"]) == 1
        assert result["nps_tags"]["promoters"][0][0] == "row_0001"

    def test_flagged_country_excluded_from_not_worth_it_candidates(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [
                _nps_record(1, "promoter", country="Bolivia", not_worth_it=True),
                _nps_record(2, "promoter", country="Ecuador", not_worth_it=True),
            ],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                     excluded_countries=["Bolivia"])

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        synth_input = json.loads(synthesis_call["user_content"])
        ids = [c["id"] for c in synth_input["not_worth_it_candidates"]]
        assert ids == ["row_0002"]

    def test_synthesis_prompt_carries_flag_instruction_when_excluded(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter", country="Bolivia")],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key",
                     excluded_countries=["Bolivia"])

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        assert "DATA QUALITY FLAG" in synthesis_call["system_prompt"]
        assert "Bolivia" in synthesis_call["system_prompt"]

    def test_no_excluded_countries_leaves_prompt_unchanged(self, tmp_path, monkeypatch):
        captured = []
        self._install_fake_call_llm(monkeypatch, captured)

        payload = {
            "nps_promoters": [_nps_record(1, "promoter")],
            "nps_passives": [], "nps_detractors": [],
            "claim_no_reason_other": [], "claim_challenges_other_support": [], "sparse_other": [],
        }
        call_gemini(payload, tmp_path / "raw.json", provider="gemini", api_key="fake-key")

        synthesis_call = next(c for c in captured if "nps_responses" not in json.loads(c["user_content"]))
        assert "DATA QUALITY FLAG" not in synthesis_call["system_prompt"]
