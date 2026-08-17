"""
Unit tests for utils.py -- shared formatting helpers. Focused mainly on
format_value()'s not_applicable vs suppressed distinction (the gap flagged
after Phase 5: a population-exclusive metric like worth_premium in a
country-scoped report must render as "NOT APPLICABLE", not "SUPPRESSED").
Run: pytest tests/test_utils.py -v
"""
from __future__ import annotations

from utils import format_period_label, format_p_value, format_value, get_nested, parse_period


# ---------------------------------------------------------------------------
# format_value
# ---------------------------------------------------------------------------

class TestFormatValue:
    def test_not_applicable_returns_distinct_marker(self):
        assert format_value(0.5, "pct", not_applicable=True) == "NOT APPLICABLE"

    def test_not_applicable_takes_precedence_over_suppressed(self):
        # A not_applicable metric is always suppressed too (0 valid
        # responses) -- not_applicable must win, not fall through to the
        # generic SUPPRESSED string.
        assert format_value(None, "pct", suppressed=True, not_applicable=True) == "NOT APPLICABLE"

    def test_not_applicable_with_a_real_value_still_wins(self):
        # Shouldn't happen in practice (not_applicable implies value is
        # None), but the marker must win regardless of what v is.
        assert format_value(0.9, "pct", not_applicable=True) == "NOT APPLICABLE"

    def test_suppressed_without_not_applicable_unchanged(self):
        assert format_value(None, "pct", suppressed=True) == "SUPPRESSED"
        assert format_value(None, "pct", suppressed=True, not_applicable=False) == "SUPPRESSED"

    def test_none_value_without_suppressed_flag_still_suppressed(self):
        assert format_value(None, "pct") == "SUPPRESSED"

    def test_normal_formatting_unaffected(self):
        assert format_value(0.512, "pct") == "51.2%"
        assert format_value(3, "count") == "3"
        assert format_value(-0.234, "rho") == "-0.234"
        assert format_value(7.5, "nps") == "7.5"

    def test_default_not_applicable_is_false_for_existing_callers(self):
        # Every pre-existing call site omits not_applicable -- confirms the
        # new parameter is additive and doesn't change default behavior.
        assert format_value(0.5, "pct") == format_value(0.5, "pct", not_applicable=False)


# ---------------------------------------------------------------------------
# format_p_value
# ---------------------------------------------------------------------------

class TestFormatPValue:
    def test_floors_below_0001_instead_of_truncating_to_zero(self):
        # Real Part 5 driver correlation: p=2.28e-38 must never render as the
        # indistinguishable-from-p=0 "0.0000" a fixed .4f truncation produces.
        assert format_p_value(2.2797940250585584e-38) == "<0.0001"

    def test_boundary_just_below_threshold_floors(self):
        assert format_p_value(0.00009) == "<0.0001"

    def test_boundary_at_threshold_formats_normally(self):
        assert format_p_value(0.0001) == "0.0001"

    def test_ordinary_value_formats_to_four_decimals(self):
        assert format_p_value(0.0234) == "0.0234"

    def test_none_returns_placeholder(self):
        assert format_p_value(None) == "?"


# ---------------------------------------------------------------------------
# get_nested (baseline coverage -- central to orchestrator.py's path derivation)
# ---------------------------------------------------------------------------

class TestGetNested:
    def test_traverses_nested_dict(self):
        d = {"a": {"b": {"c": 42}}}
        assert get_nested(d, "a.b.c") == 42

    def test_missing_path_returns_default(self):
        assert get_nested({"a": {}}, "a.b.c", default="fallback") == "fallback"

    def test_empty_path_string_returns_default(self):
        assert get_nested({"a": 1}, "", default=False) is False

    def test_none_leaf_value_returns_default_not_none(self):
        d = {"a": {"b": None}}
        assert get_nested(d, "a.b", default="x") == "x"


# ---------------------------------------------------------------------------
# format_period_label (baseline coverage)
# ---------------------------------------------------------------------------

class TestFormatPeriodLabel:
    def test_extracts_year_quarter_from_run_id(self):
        assert format_period_label("2026_Q2") == "2026 Q2"

    def test_extracts_from_prefixed_run_id(self):
        assert format_period_label("vietnam_2026_Q2") == "2026 Q2"

    def test_falls_back_to_raw_run_id_when_no_pattern(self):
        assert format_period_label("weird-run-name") == "weird-run-name"


# ---------------------------------------------------------------------------
# parse_period (same pattern as format_period_label, int output instead of
# a display string -- see data_quality_flags.derive_period_mismatch_flag())
# ---------------------------------------------------------------------------

class TestParsePeriod:
    def test_extracts_year_and_quarter_as_ints(self):
        assert parse_period("2026_Q2") == (2026, 2)

    def test_extracts_from_prefixed_run_id(self):
        assert parse_period("default_2026_Q2") == (2026, 2)

    def test_falls_back_to_none_none_when_no_pattern(self):
        assert parse_period("weird-run-name") == (None, None)
