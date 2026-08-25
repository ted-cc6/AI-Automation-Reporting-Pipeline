"""
Unit tests for qualitative/parse_results.py -- focused on the executive-summary
extension (Phase D): top_findings/top_actions are now required keys alongside
the pre-existing executive_summary, threaded straight into the saved
qualitative_results.json for generation/assembler.py's executive-summary
section to render.
Run: pytest tests/test_parse_results.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from qualitative.parse_results import (
    REQUIRED_TOP_KEYS,
    _count_themes,
    _dedupe_protection_flags_by_client,
    _humanize_top_drivers,
    _load_theme_section_map,
    _lookup_profile,
    _normalise_reason,
    _validate,
    compute_part7_sentiment_splits,
    compute_stage1_sentiment_splits,
    compute_stage2_sentiment_splits,
    parse_and_save,
)


def _base_raw(**overrides) -> dict:
    base = {
        "nps_tags": {"promoters": [], "passives": [], "detractors": []},
        "claims_other_tagged": {},
        "not_worth_it_themes": [],
        "other_subthemes": {},
        "section_verbatims": {
            "part1": ["row_0001"], "part2": ["row_0001"], "part3": ["row_0001"],
            "part4": ["row_0001"], "part5": ["row_0001"], "part6": ["row_0001"],
            "part7": ["row_0001"],
        },
        "protection_flags": [],
        "executive_summary": "Some summary.",
        "top_findings": ["Finding 1", "Finding 2", "Finding 3"],
        "top_actions": ["Action 1", "Action 2", "Action 3"],
    }
    base.update(overrides)
    return base


class TestRequiredTopKeys:
    def test_top_findings_and_top_actions_are_required(self):
        assert "top_findings" in REQUIRED_TOP_KEYS
        assert "top_actions" in REQUIRED_TOP_KEYS


class TestValidate:
    def test_complete_payload_passes(self):
        _validate(_base_raw())  # must not raise

    def test_missing_top_findings_raises(self):
        raw = _base_raw()
        del raw["top_findings"]
        with pytest.raises(ValueError, match="top_findings"):
            _validate(raw)

    def test_missing_top_actions_raises(self):
        raw = _base_raw()
        del raw["top_actions"]
        with pytest.raises(ValueError, match="top_actions"):
            _validate(raw)


class TestLookupProfile:
    def _df(self):
        return pd.DataFrame({
            "client_id": ["CI-00042"],
            "q_sex": ["Female"],
            "q_client_age": [34],
            "branch": ["Branch A"],
            "country": ["Bolivia"],
            "q_claim_submitted": [True],
            "flag_paid_claimant": [False],
            "flag_child_wellbeing_denominator": [True],
        }, index=[42])

    def test_is_claimant_uses_canonical_q_claim_submitted_not_flag_paid_claimant(self):
        # R-006a Stage 1 (docs/report_spec.md): flag_paid_claimant is
        # narrower (claim approved AND paid) than the canonical "claimant"
        # segment (q_claim_submitted) used everywhere else in the report
        # (analysis_engine/segments.py, Part 6's own scorecard). This
        # respondent submitted a claim that was not (yet) paid -- must
        # still count as a claimant here, not silently excluded.
        profile = _lookup_profile("row_0042", self._df())
        assert profile["is_claimant"] is True

    def test_profile_carries_client_id_for_traceable_appendix_refs(self):
        # generation/assembler.py's _protection_flag_ref() needs client_id
        # (plus branch) to render a reference the client protection team can
        # actually look up -- a row_id/row-index number means nothing to them
        # and doesn't survive a re-run of the pipeline.
        profile = _lookup_profile("row_0042", self._df())
        assert profile["client_id"] == "CI-00042"
        assert profile["branch"] == "Branch A"

    def test_missing_client_id_column_returns_none(self):
        df = self._df().drop(columns=["client_id"])
        profile = _lookup_profile("row_0042", df)
        assert profile["client_id"] is None

    def test_unresolvable_row_id_returns_empty_profile(self):
        profile = _lookup_profile("row_9999", self._df())
        assert profile == {}


# ---------------------------------------------------------------------------
# Theme code humanization -- a real generated report shipped with the raw
# taxonomy code "claims_process" sitting unlabeled in reader-facing prose
# (the synthesis prompt allows it as a top_drivers value). Both theme_counts
# and top_drivers must never expose a raw snake_case code to a reader.
# ---------------------------------------------------------------------------

class TestCountThemes:
    def test_theme_counts_keys_are_human_readable_not_raw_codes(self):
        nps_tags = {
            "promoters": [["row_0001", ["product_value"]], ["row_0002", ["product_value"]]],
            "passives": [["row_0003", ["claims_process"]]],
            "detractors": [],
        }
        counts = _count_themes(nps_tags)
        assert counts["promoters"] == {"product value for money": 2}
        assert counts["passives"] == {"the claims process": 1}
        assert "product_value" not in counts["promoters"]
        assert "claims_process" not in counts["passives"]

    def test_counting_happens_before_relabeling_so_synonyms_dont_fragment(self):
        # Both entries are the same raw code; must still collapse into one
        # counted, humanized key -- not two separate near-duplicate keys.
        nps_tags = {
            "promoters": [["row_0001", ["staff_service"]], ["row_0002", ["staff_service"]]],
            "passives": [], "detractors": [],
        }
        counts = _count_themes(nps_tags)
        assert counts["promoters"] == {"staff service": 2}

    def test_empty_tags_produce_empty_counts(self):
        counts = _count_themes({"promoters": [], "passives": [], "detractors": []})
        assert counts == {"promoters": {}, "passives": {}, "detractors": {}}


# ---------------------------------------------------------------------------
# R-006a Stage 1: deterministic sentiment_split for part5 (caregivers) and
# part6 (claimants). Every section's sentiment_split is nested by group
# (session-8, per instruction: one uniform shape everywhere, no Part-7-only
# special case) -- a single-group section uses the key "all".
# ---------------------------------------------------------------------------

class TestComputeStage1SentimentSplits:
    def _df(self):
        # index 0..5; caregivers = {0, 1, 4}; claimants (q_claim_submitted) = {0, 2}
        return pd.DataFrame({
            "flag_child_wellbeing_denominator": [True, True, False, False, True, False],
            "q_claim_submitted": [True, False, True, False, False, False],
        }, index=range(6))

    def _tags(self, entries):
        return {"promoters": entries, "passives": [], "detractors": []}

    def test_only_parts_5_and_6_are_returned(self):
        # Part 7 has its own function (compute_part7_sentiment_splits) --
        # this one covers exactly the two segment-defined sections.
        result = compute_stage1_sentiment_splits(self._tags([]), self._df())
        assert set(result.keys()) == {"part5", "part6"}

    def test_single_group_section_is_nested_under_all(self):
        result = compute_stage1_sentiment_splits(self._tags([]), self._df())
        assert set(result["part5"].keys()) == {"all"}
        assert set(result["part6"].keys()) == {"all"}

    def test_part5_base_and_source_pool_from_caregiver_flag(self):
        tags = self._tags([
            ["row_0000", ["staff_service"], "positive"],
            ["row_0004", ["staff_service"], "negative"],
            ["row_0002", ["staff_service"], "neutral"],  # not a caregiver -- excluded
        ])
        part5 = compute_stage1_sentiment_splits(tags, self._df())["part5"]["all"]
        assert part5["source_pool_n"] == 3  # caregivers: rows 0, 1, 4
        assert part5["base_n"] == 2
        assert part5["positive"] == 1
        assert part5["negative"] == 1
        assert part5["neutral"] == 0
        # Describes the derivation (min_text_length), not "left a response"
        # -- the NPS follow-up is filled by every respondent; the gap is
        # the text-length threshold, not missing responses.
        assert "excluding responses under 10 characters" in part5["selection_rule"]
        assert "2 of 3 caregivers qualify" in part5["selection_rule"]

    def test_part6_uses_q_claim_submitted_not_flag_paid_claimant(self):
        tags = self._tags([
            ["row_0000", ["claims_process"], "positive"],
            ["row_0002", ["claims_process"], "negative"],
        ])
        part6 = compute_stage1_sentiment_splits(tags, self._df())["part6"]["all"]
        assert part6["source_pool_n"] == 2  # claimants: rows 0, 2
        assert part6["base_n"] == 2
        assert "excluding responses under 10 characters" in part6["selection_rule"]
        assert "2 of 2 claimants qualify" in part6["selection_rule"]

    def test_counts_always_sum_to_base_n(self):
        tags = self._tags([
            ["row_0000", ["staff_service"], "positive"],
            ["row_0004", ["staff_service"], "negative"],
        ])
        result = compute_stage1_sentiment_splits(tags, self._df())
        for section in ("part5", "part6"):
            entry = result[section]["all"]
            assert entry["positive"] + entry["negative"] + entry["neutral"] == entry["base_n"]

    def test_two_element_entry_without_sentiment_is_not_counted(self):
        tags = self._tags([["row_0000", ["staff_service"]]])  # no sentiment
        part5 = compute_stage1_sentiment_splits(tags, self._df())["part5"]["all"]
        assert part5["base_n"] == 0

    def test_untagged_in_segment_respondent_widens_the_gap_visibly(self):
        # A caregiver never tagged (e.g. a failed batch) shows up as
        # source_pool_n > base_n, not silently absorbed into either number.
        tags = self._tags([["row_0000", ["staff_service"], "positive"]])  # rows 1, 4 untagged
        part5 = compute_stage1_sentiment_splits(tags, self._df())["part5"]["all"]
        assert part5["source_pool_n"] == 3
        assert part5["base_n"] == 1
        assert part5["source_pool_n"] > part5["base_n"]


class TestStage1SyntheticSplitGuard:
    """R-006a's hard guard (per explicit instruction): a synthetic or
    placeholder sentiment split (e.g. a round-robin demo) must never
    silently reach a rendered report -- an exact 3-way tie at a base_n
    where that is not a plausible real coincidence raises instead."""

    def _df(self, n):
        return pd.DataFrame({
            "flag_child_wellbeing_denominator": [True] * n,
            "q_claim_submitted": [False] * n,
        }, index=range(n))

    def _tags(self, n, sentiments):
        return {
            "promoters": [[f"row_{i:04d}", ["staff_service"], sentiments[i]] for i in range(n)],
            "passives": [], "detractors": [],
        }

    def test_exact_tie_at_or_above_threshold_raises(self):
        # base_n=15, 5/5/5 -- exactly the round-robin signature.
        n = 15
        sentiments = (["positive", "negative", "neutral"] * (n // 3))
        with pytest.raises(ValueError, match="synthetic or placeholder"):
            compute_stage1_sentiment_splits(self._tags(n, sentiments), self._df(n))

    def test_exact_tie_below_threshold_does_not_raise(self):
        # base_n=9, 3/3/3 -- small enough that a genuine tie is plausible.
        n = 9
        sentiments = (["positive", "negative", "neutral"] * (n // 3))
        result = compute_stage1_sentiment_splits(self._tags(n, sentiments), self._df(n))
        assert result["part5"]["all"]["base_n"] == 9

    def test_uneven_real_looking_distribution_does_not_raise(self):
        n = 30
        sentiments = (["positive"] * 12) + (["negative"] * 11) + (["neutral"] * 7)
        result = compute_stage1_sentiment_splits(self._tags(n, sentiments), self._df(n))
        assert result["part5"]["all"]["base_n"] == 30


# ---------------------------------------------------------------------------
# R-006a Part 7: Gender needs two groups, not one -- female and male, each
# with its own base_n/source_pool_n/selection_rule, same uniform nested
# shape every other section uses (session-8).
# ---------------------------------------------------------------------------

class TestComputePart7SentimentSplits:
    def _df(self):
        # index 0..3: 2 female (0, 1), 2 male (2, 3)
        return pd.DataFrame({"q_sex": ["Female", "Female", "Male", "Male"]}, index=range(4))

    def _tags(self, entries):
        return {"promoters": entries, "passives": [], "detractors": []}

    def test_returns_female_and_male_groups(self):
        result = compute_part7_sentiment_splits(self._tags([]), self._df())
        assert set(result["part7"].keys()) == {"female", "male"}

    def test_each_group_scoped_to_its_own_sex(self):
        tags = self._tags([
            ["row_0000", ["staff_service"], "positive"],  # female
            ["row_0002", ["staff_service"], "negative"],  # male
        ])
        part7 = compute_part7_sentiment_splits(tags, self._df())["part7"]
        assert part7["female"]["source_pool_n"] == 2
        assert part7["female"]["base_n"] == 1
        assert part7["female"]["positive"] == 1
        assert part7["male"]["source_pool_n"] == 2
        assert part7["male"]["base_n"] == 1
        assert part7["male"]["negative"] == 1

    def test_selection_rule_names_the_group(self):
        result = compute_part7_sentiment_splits(self._tags([]), self._df())
        assert "women" in result["part7"]["female"]["selection_rule"]
        assert "men" in result["part7"]["male"]["selection_rule"]
        assert "excluding responses under 10 characters" in result["part7"]["female"]["selection_rule"]

    def test_synthetic_guard_applies_per_group(self):
        n = 30
        sentiments = ["positive", "negative", "neutral"] * (n // 3)
        df = pd.DataFrame({"q_sex": ["Female"] * n}, index=range(n))
        tags = {
            "promoters": [[f"row_{i:04d}", ["staff_service"], sentiments[i]] for i in range(n)],
            "passives": [], "detractors": [],
        }
        with pytest.raises(ValueError, match="synthetic or placeholder"):
            compute_part7_sentiment_splits(tags, df)


# ---------------------------------------------------------------------------
# R-006a Stage 2: deterministic sentiment_split for Parts 1-4 via
# config.yaml's theme_codes mapping (Lorenz-approved, session-7). Real
# config.yaml is used deliberately (not a stub) -- this is exactly the
# mapping a live run reads, and a config edit that breaks the mapping
# should break these tests too.
# ---------------------------------------------------------------------------

class TestLoadThemeSectionMap:
    def test_matches_approved_single_mapping(self):
        # payout_adequacy -> part2 only, staff_service -> part4 only
        # (session-7: single-map, not dual-map -- co-tagging handles
        # cross-cutting cases instead).
        mapping = _load_theme_section_map()
        assert mapping["part1"] == {"product_understanding"}
        assert mapping["part2"] == {"claims_speed", "claims_process", "payout_adequacy"}
        assert mapping["part3"] == {"access_inclusion", "financial_relief"}
        assert mapping["part4"] == {
            "product_value", "staff_service", "general_satisfaction",
            "improvement_suggestion", "complaint_grievance",
        }

    def test_part5_6_7_have_no_theme_mapping(self):
        mapping = _load_theme_section_map()
        assert "part5" not in mapping
        assert "part6" not in mapping
        assert "part7" not in mapping

    def test_child_family_and_crop_agricultural_are_unmapped(self):
        # Approved as unmapped: they match part5's / Vietnam's own
        # constructs, not any of Parts 1-4's topics.
        mapping = _load_theme_section_map()
        all_mapped_codes = set().union(*mapping.values())
        assert "child_family" not in all_mapped_codes
        assert "crop_agricultural" not in all_mapped_codes

    def test_no_theme_code_is_dual_mapped(self):
        # session-7 principle: each theme maps to exactly one primary
        # section; cross-cutting cases are handled by co-tagging, not by
        # listing the same code under two sections.
        mapping = _load_theme_section_map()
        seen = {}
        for section, codes in mapping.items():
            for code in codes:
                assert code not in seen, (
                    f"{code} is mapped to both {seen.get(code)} and {section} -- "
                    "the approved principle is single-mapping, not dual-mapping"
                )
                seen[code] = section


class TestComputeStage2SentimentSplits:
    def _tags(self, entries):
        return {"promoters": entries, "passives": [], "detractors": []}

    def test_only_parts_1_through_4_are_returned(self):
        result = compute_stage2_sentiment_splits(self._tags([]))
        assert set(result.keys()) == {"part1", "part2", "part3", "part4"}

    def test_single_group_section_is_nested_under_all(self):
        result = compute_stage2_sentiment_splits(self._tags([]))
        for section in result.values():
            assert set(section.keys()) == {"all"}

    def test_record_routes_to_its_mapped_section_only(self):
        tags = self._tags([
            ["row_0000", ["product_understanding"], "positive"],  # part1 only
        ])
        result = compute_stage2_sentiment_splits(tags)
        assert result["part1"]["all"]["base_n"] == 1
        assert result["part2"]["all"]["base_n"] == 0
        assert result["part3"]["all"]["base_n"] == 0
        assert result["part4"]["all"]["base_n"] == 0

    def test_co_tagged_record_reaches_both_sections_not_one(self):
        # session-7 principle in action: a staff complaint during a claim
        # carries BOTH staff_service (part4) and claims_process (part2)
        # and reaches both -- this is co-tagging, not dual-mapping, and
        # is exactly why payout_adequacy/staff_service were single-mapped.
        tags = self._tags([
            ["row_0000", ["staff_service", "claims_process"], "negative"],
        ])
        result = compute_stage2_sentiment_splits(tags)
        assert result["part2"]["all"]["base_n"] == 1
        assert result["part4"]["all"]["base_n"] == 1
        # Not double counted within a single section, and unrelated
        # sections stay at zero.
        assert result["part1"]["all"]["base_n"] == 0
        assert result["part3"]["all"]["base_n"] == 0

    def test_unmapped_theme_contributes_to_no_section(self):
        # Expected, not a defect (session-6/7 design constraint).
        tags = self._tags([["row_0000", ["child_family"], "positive"]])
        result = compute_stage2_sentiment_splits(tags)
        assert all(result[s]["all"]["base_n"] == 0 for s in result)

    def test_source_pool_n_is_the_full_tagged_pool_same_across_sections(self):
        tags = self._tags([
            ["row_0000", ["product_understanding"], "positive"],
            ["row_0001", ["child_family"], "neutral"],  # unmapped, still tagged
        ])
        result = compute_stage2_sentiment_splits(tags)
        for section in ("part1", "part2", "part3", "part4"):
            assert result[section]["all"]["source_pool_n"] == 2

    def test_selection_rule_names_the_mapped_theme_codes(self):
        result = compute_stage2_sentiment_splits(self._tags([]))
        assert "product_understanding" in result["part1"]["all"]["selection_rule"]
        assert "excluding responses under 10 characters" in result["part1"]["all"]["selection_rule"]

    def test_counts_always_sum_to_base_n(self):
        tags = self._tags([
            ["row_0000", ["product_understanding"], "positive"],
            ["row_0001", ["claims_speed"], "negative"],
        ])
        result = compute_stage2_sentiment_splits(tags)
        for section in result.values():
            entry = section["all"]
            assert entry["positive"] + entry["negative"] + entry["neutral"] == entry["base_n"]


def _flag(client_id, flag_type, severity, reason, id_="row_0001", branch="Branch A"):
    return {
        "id": id_, "flag_type": flag_type, "severity": severity, "reason": reason,
        "profile": {"client_id": client_id, "branch": branch},
    }


class TestNormaliseReason:
    def test_collapses_whitespace_and_lowercases(self):
        assert _normalise_reason("  Claim   was\ndenied.  ") == "claim was denied."

    def test_none_becomes_empty_string(self):
        assert _normalise_reason(None) == ""


class TestDedupeProtectionFlagsByClient:
    # R-003: llm_call._dedupe_protection_flags already collapsed same-row
    # (id, flag_type) duplicates before client_id existed. This pass runs
    # after client_id is attached and catches the same CLIENT flagged from
    # two different rows restating the identical concern.

    def test_identical_key_collapses_to_one_entry(self):
        flags = [
            _flag("CI-587099342", "unfair_claim_denial", "high",
                  "Client says claim was denied without explanation.", id_="row_0011"),
            _flag("CI-587099342", "unfair_claim_denial", "high",
                  "Client says claim was denied without explanation.", id_="row_0087"),
        ]
        deduped, n_unresolved = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 1
        assert n_unresolved == 0

    def test_reason_normalisation_still_collapses_whitespace_and_case_variants(self):
        flags = [
            _flag("CI-1", "staff_misconduct", "medium", "Unresponsive branch staff.", id_="row_0001"),
            _flag("CI-1", "staff_misconduct", "medium", "  unresponsive   branch staff.  ", id_="row_0002"),
        ]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 1

    def test_collision_keeps_higher_severity_copy(self):
        flags = [
            _flag("CI-1", "coercion", "low", "Same concern restated.", id_="row_0001"),
            _flag("CI-1", "coercion", "high", "Same concern restated.", id_="row_0002"),
        ]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 1
        assert deduped[0]["severity"] == "high"

    def test_same_client_different_flag_type_both_kept_and_annotated(self):
        flags = [
            _flag("CI-1", "unfair_claim_denial", "high", "Claim denied without reason.", id_="row_0001"),
            _flag("CI-1", "staff_misconduct", "medium", "Separate complaint about staff.", id_="row_0002"),
        ]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 2
        assert all(f["same_client_multiple_concerns"] for f in deduped)

    def test_same_client_same_flag_type_different_reason_both_kept(self):
        flags = [
            _flag("CI-1", "staff_misconduct", "medium", "Unresponsive at the branch.", id_="row_0001"),
            _flag("CI-1", "staff_misconduct", "medium", "Rude to my daughter at pickup.", id_="row_0002"),
        ]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 2
        assert {f["reason"] for f in deduped} == {
            "Unresponsive at the branch.", "Rude to my daughter at pickup.",
        }

    def test_single_concern_client_is_not_annotated(self):
        flags = [_flag("CI-1", "coercion", "high", "One concern.", id_="row_0001")]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert deduped[0]["same_client_multiple_concerns"] is False

    def test_no_client_id_passes_through_unresolved_and_is_counted(self):
        flags = [
            _flag(None, "coercion", "high", "Unresolved case.", id_="row_9999"),
            _flag("CI-1", "coercion", "high", "Resolved case.", id_="row_0001"),
        ]
        deduped, n_unresolved = _dedupe_protection_flags_by_client(flags)
        assert n_unresolved == 1
        assert len(deduped) == 2

    def test_different_clients_never_collapsed_even_with_identical_reason(self):
        flags = [
            _flag("CI-1", "coercion", "high", "Same wording, different client.", id_="row_0001"),
            _flag("CI-2", "coercion", "high", "Same wording, different client.", id_="row_0002"),
        ]
        deduped, _ = _dedupe_protection_flags_by_client(flags)
        assert len(deduped) == 2


class TestParseAndSaveStage1And2Wiring:
    """Confirms compute_stage1_sentiment_splits(),
    compute_stage2_sentiment_splits(), and compute_part7_sentiment_splits()
    are actually wired into parse_and_save(), not just correct in
    isolation. Every section is nested-by-group (session-8)."""

    def _df(self):
        return pd.DataFrame({
            "flag_child_wellbeing_denominator": [True, False],
            "q_claim_submitted": [False, False],
            "q_sex": ["Female", "Male"],
        }, index=[0, 1])

    def test_part5_sentiment_split_is_overridden_with_deterministic_values(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        raw = _base_raw(
            nps_tags={
                "promoters": [["row_0000", ["child_family"], "positive"]],
                "passives": [], "detractors": [],
            },
            section_insights={
                "part5": {"theme_summary": "model's own summary", "top_drivers": ["staff_service"],
                          "sentiment_split": {"positive": 3, "negative": 10, "neutral": 3}},
            },
        )
        result = parse_and_save(raw, self._df(), run_id="test_run")

        part5 = result["section_insights"]["part5"]
        # Deterministic split replaces the model's estimate, nested under "all"...
        assert part5["sentiment_split"]["all"]["base_n"] == 1
        assert part5["sentiment_split"]["all"]["positive"] == 1
        assert "selection_rule" in part5["sentiment_split"]["all"]
        # ...but theme_summary/top_drivers (still the model's own) are untouched.
        assert part5["theme_summary"] == "model's own summary"

    def test_part1_sentiment_split_is_overridden_via_stage2_theme_mapping(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        raw = _base_raw(
            nps_tags={
                # product_understanding -> part1 only (config.yaml's mapping)
                "promoters": [["row_0000", ["product_understanding"], "positive"]],
                "passives": [], "detractors": [],
            },
            section_insights={
                "part1": {"theme_summary": "model's own summary", "top_drivers": [],
                          "sentiment_split": {"positive": 1, "negative": 2, "neutral": 3}},
            },
        )
        result = parse_and_save(raw, self._df(), run_id="test_run")

        part1 = result["section_insights"]["part1"]
        assert part1["sentiment_split"]["all"]["base_n"] == 1
        assert part1["sentiment_split"]["all"]["positive"] == 1
        assert "selection_rule" in part1["sentiment_split"]["all"]
        assert part1["theme_summary"] == "model's own summary"

    def test_part7_sentiment_split_is_overridden_with_two_groups(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        raw = _base_raw(
            nps_tags={
                "promoters": [
                    ["row_0000", ["staff_service"], "positive"],  # female (row 0)
                    ["row_0001", ["staff_service"], "negative"],  # male (row 1)
                ],
                "passives": [], "detractors": [],
            },
            section_insights={
                "part7": {"theme_summary": "model's own summary", "top_drivers": [],
                          "sentiment_split": {"positive": 1, "negative": 2, "neutral": 3}},
            },
        )
        result = parse_and_save(raw, self._df(), run_id="test_run")

        part7 = result["section_insights"]["part7"]
        assert set(part7["sentiment_split"].keys()) == {"female", "male"}
        assert part7["sentiment_split"]["female"]["base_n"] == 1
        assert part7["sentiment_split"]["female"]["positive"] == 1
        assert part7["sentiment_split"]["male"]["base_n"] == 1
        assert part7["sentiment_split"]["male"]["negative"] == 1
        assert part7["theme_summary"] == "model's own summary"
        assert "base_n" not in part7["sentiment_split"]


class TestHumanizeTopDrivers:
    def test_raw_taxonomy_code_is_relabeled(self):
        section_insights = {
            "part2": {"theme_summary": "x", "top_drivers": ["claims_process", "documentation burden"],
                      "sentiment_split": {"positive": 1, "negative": 1, "neutral": 0}},
        }
        result = _humanize_top_drivers(section_insights)
        assert result["part2"]["top_drivers"] == ["the claims process", "documentation burden"]

    def test_freeform_label_passes_through_unchanged(self):
        section_insights = {
            "part4": {"theme_summary": "x", "top_drivers": ["slow payout", "lack of premium clarity"],
                      "sentiment_split": {"positive": 0, "negative": 1, "neutral": 0}},
        }
        result = _humanize_top_drivers(section_insights)
        assert result["part4"]["top_drivers"] == ["slow payout", "lack of premium clarity"]

    def test_missing_top_drivers_key_is_left_alone(self):
        section_insights = {"part1": {"theme_summary": "x"}}
        result = _humanize_top_drivers(section_insights)
        assert result["part1"] == {"theme_summary": "x"}

    def test_non_dict_entry_passes_through_unchanged(self):
        section_insights = {"part1": None}
        result = _humanize_top_drivers(section_insights)
        assert result["part1"] is None

    def test_empty_section_insights_returns_empty_dict(self):
        assert _humanize_top_drivers({}) == {}
        assert _humanize_top_drivers(None) == {}
