"""
Unit tests for data_loader/data_loader_transformer.py — the coding functions
that turn raw KoBoToolbox strings into typed columns. Uses the real
value_coding_map.yaml (not made-up maps) so tests fail if the actual coding
rules drift.
Run: pytest tests/test_transformer.py -v
"""
from __future__ import annotations

import pandas as pd

from data_loader.data_loader_transformer import (
    DEFAULT_YAML,
    WarnTracker,
    code_binary,
    code_likert,
    code_ms_child,
    code_single_select,
    derive_ms_list,
    extract_option_letter,
    load_yaml,
    strip_letter_prefix,
)

SENTINEL = "__SCOPE_NA__"
CMAP = load_yaml(DEFAULT_YAML)


def _wt() -> WarnTracker:
    return WarnTracker()


# ---------------------------------------------------------------------------
# Small pure helpers
# ---------------------------------------------------------------------------

class TestPrefixHelpers:
    def test_strip_letter_prefix_removes_leading_letter_dot_space(self):
        assert strip_letter_prefix("a. Very good") == "Very good"
        assert strip_letter_prefix("c. Do not support any children") == "Do not support any children"

    def test_strip_letter_prefix_leaves_unprefixed_text_unchanged(self):
        assert strip_letter_prefix("Very good") == "Very good"

    def test_extract_option_letter_finds_letter_after_slash(self):
        header = "Which channel is most effective/a. In-person explanation"
        assert extract_option_letter(header) == "a"

    def test_extract_option_letter_returns_none_when_no_match(self):
        assert extract_option_letter("Plain header with no slash-letter") is None


# ---------------------------------------------------------------------------
# code_likert — real likert_4 and likert_5 maps from value_coding_map.yaml
# ---------------------------------------------------------------------------

class TestCodeLikert:
    def test_likert4_maps_known_values_to_ints_and_labels(self):
        lmap = CMAP["likert_4"]
        series = pd.Series(["a. Very good", "b. Good", "c. Poor", "d. Very poor"])
        wt = _wt()
        int_col, lbl_col = code_likert(series, lmap, col_idx=11, qref="q_coverage_understanding",
                                        sentinel=SENTINEL, wt=wt)
        assert list(int_col) == [1, 2, 3, 4]
        assert list(lbl_col) == ["Very good", "Good", "Poor", "Very poor"]
        assert wt.count == 0

    def test_likert4_scale_direction_1_is_best(self):
        # Locked convention: a=1 is the most positive response
        lmap = CMAP["likert_4"]
        assert lmap["a. Very good"]["int"] == 1
        assert lmap["d. Very poor"]["int"] == 4

    def test_sentinel_and_blank_become_na_not_a_warning(self):
        lmap = CMAP["likert_4"]
        series = pd.Series(["", SENTINEL, "a. Very good"])
        wt = _wt()
        int_col, lbl_col = code_likert(series, lmap, 11, "q_coverage_understanding", SENTINEL, wt)
        assert pd.isna(int_col[0]) and pd.isna(int_col[1])
        assert int_col[2] == 1
        assert wt.count == 0   # scope/blank is expected, not a data-quality warning

    def test_unrecognized_value_produces_warning_and_na(self):
        lmap = CMAP["likert_4"]
        series = pd.Series(["a. Very good", "z. Not a real option"])
        wt = _wt()
        int_col, _ = code_likert(series, lmap, 11, "q_coverage_understanding", SENTINEL, wt)
        assert int_col[0] == 1
        assert pd.isna(int_col[1])
        assert wt.count == 1
        assert "z. Not a real option" in wt.messages[0]

    def test_likert5_financial_stress_direction(self):
        # Locked convention: lower int = more stress REDUCED (a better outcome)
        lmap = CMAP["likert_5"]["q_financial_stress"]
        series = pd.Series(["a. Significantly reduced", "e. Significantly increased"])
        wt = _wt()
        int_col, _ = code_likert(series, lmap, 63, "q_financial_stress", SENTINEL, wt)
        assert int_col[0] == 1
        assert int_col[1] == 5


# ---------------------------------------------------------------------------
# code_binary — real binary_standalone map
# ---------------------------------------------------------------------------

class TestCodeBinary:
    def test_yes_no_map_to_true_false(self):
        bmap = CMAP["binary_standalone"]
        series = pd.Series(["a. Yes", "b. No", "a. Yes"])
        wt = _wt()
        result = code_binary(series, bmap, 25, "q_insured_event_12m", SENTINEL, wt)
        assert list(result) == [True, False, True]
        assert wt.count == 0

    def test_sentinel_becomes_na(self):
        bmap = CMAP["binary_standalone"]
        series = pd.Series([SENTINEL, "a. Yes"])
        wt = _wt()
        result = code_binary(series, bmap, 25, "q_insured_event_12m", SENTINEL, wt)
        assert pd.isna(result[0])
        assert result[1] == True  # noqa: E712

    def test_unexpected_value_warns_and_is_na(self):
        bmap = CMAP["binary_standalone"]
        series = pd.Series(["a. Yes", "maybe"])
        wt = _wt()
        result = code_binary(series, bmap, 25, "q_insured_event_12m", SENTINEL, wt)
        assert pd.isna(result[1])
        assert wt.count == 1


# ---------------------------------------------------------------------------
# code_ms_child — real multi_select_child map ("1"/"0" strings from KoboToolbox)
# ---------------------------------------------------------------------------

class TestCodeMsChild:
    def test_string_1_0_map_to_bool(self):
        ms_map = CMAP["multi_select_child"]
        series = pd.Series(["1", "0", "1"])
        wt = _wt()
        result = code_ms_child(series, ms_map, 42, "q_coping_mechanisms", SENTINEL, wt)
        assert list(result) == [True, False, True]
        assert wt.count == 0

    def test_blank_and_sentinel_become_na(self):
        ms_map = CMAP["multi_select_child"]
        series = pd.Series(["", SENTINEL, "1"])
        wt = _wt()
        result = code_ms_child(series, ms_map, 42, "q_coping_mechanisms", SENTINEL, wt)
        assert pd.isna(result[0])
        assert pd.isna(result[1])
        assert result[2] == True  # noqa: E712

    def test_true_false_strings_are_not_valid_and_warn(self):
        # Guards against a regression to "True"/"False"/"Yes"/"No" style values —
        # this coding map only recognizes literal "1"/"0" strings.
        ms_map = CMAP["multi_select_child"]
        series = pd.Series(["True", "Yes"])
        wt = _wt()
        result = code_ms_child(series, ms_map, 42, "q_coping_mechanisms", SENTINEL, wt)
        assert pd.isna(result[0]) and pd.isna(result[1])
        assert wt.count == 2


# ---------------------------------------------------------------------------
# code_single_select
# ---------------------------------------------------------------------------

class TestCodeSingleSelect:
    def test_strips_letter_prefix(self):
        series = pd.Series(["a. Male", "b. Female"])
        wt = _wt()
        result = code_single_select(series, 100, "q_sex", SENTINEL, wt)
        assert list(result) == ["Male", "Female"]

    def test_blank_becomes_missing_sentinel_stays_literal(self):
        series = pd.Series(["", SENTINEL, "a. Yes"])
        wt = _wt()
        result = code_single_select(series, 100, "q_child_wellbeing", SENTINEL, wt)
        # pd.Categorical normalizes a None entry to NaN internally
        assert pd.isna(result[0])
        assert result[1] == SENTINEL
        assert result[2] == "Yes"


# ---------------------------------------------------------------------------
# derive_ms_list — builds the list-valued column from bool children
# ---------------------------------------------------------------------------

class TestDeriveMsList:
    def test_builds_label_list_from_true_children_only(self):
        out = pd.DataFrame({
            "q_comm_channel_effective__a": pd.array([True, False], dtype="boolean"),
            "q_comm_channel_effective__b": pd.array([False, True], dtype="boolean"),
            "q_comm_channel_effective__c": pd.array([True, True], dtype="boolean"),
        })
        children_by_parent = {
            "q_comm_channel_effective": [
                ("a", "q_comm_channel_effective__a"),
                ("b", "q_comm_channel_effective__b"),
                ("c", "q_comm_channel_effective__c"),
            ]
        }
        labels = CMAP["multi_select_option_labels"]["q_comm_channel_effective"]
        derive_ms_list(out, children_by_parent, {"q_comm_channel_effective": labels})

        row0 = out["q_comm_channel_effective"].iloc[0]
        row1 = out["q_comm_channel_effective"].iloc[1]
        assert row0 == [labels["a"], labels["c"]]
        assert row1 == [labels["b"], labels["c"]]

    def test_no_true_children_produces_empty_list(self):
        out = pd.DataFrame({
            "q_x__a": pd.array([False], dtype="boolean"),
            "q_x__b": pd.array([pd.NA], dtype="boolean"),
        })
        children_by_parent = {"q_x": [("a", "q_x__a"), ("b", "q_x__b")]}
        derive_ms_list(out, children_by_parent, {"q_x": {"a": "A", "b": "B"}})
        assert out["q_x"].iloc[0] == []


# ---------------------------------------------------------------------------
# WarnTracker
# ---------------------------------------------------------------------------

class TestWarnTracker:
    def test_accumulates_messages_and_count(self):
        wt = _wt()
        wt.warn(5, "bad_value", "some context")
        wt.warn(6, "another_bad", "other context")
        assert wt.count == 2
        assert len(wt.messages) == 2
        assert "bad_value" in wt.messages[0]
