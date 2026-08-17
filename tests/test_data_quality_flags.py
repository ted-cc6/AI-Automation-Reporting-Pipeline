"""
Unit tests for data_quality_flags.py -- footnoting/exclusion flags derived
from data_loader_screening.find_duration_outliers() findings, plus
hand-entered overrides. Core guarantee: a flag never causes data to be
dropped or adjusted (Requirement 7(a)) -- this module only ever produces
metadata describing which country/note to surface, exclude from headlines,
and exclude from quotes.
Run: pytest tests/test_data_quality_flags.py -v
"""
from __future__ import annotations

from data_quality_flags import (
    DATA_QUALITY_FLAGS,
    auto_derive_duration_flags,
    derive_period_mismatch_flag,
    flagged_countries,
    get_flags,
)


def _finding(country="Bolivia", concentration=0.986, **overrides):
    base = {
        "country": country, "n_total": 278, "n_outliers": 213,
        "outlier_share": 0.766, "scope_median_minutes": 13.4,
        "threshold_minutes": 5.3, "overall_scope_outlier_share": 0.176,
        "top_enumerator": "rosa_cardenas", "top_enumerator_n": 210,
        "top_enumerator_share_of_outliers": concentration, "concentrated": concentration >= 0.5,
    }
    base.update(overrides)
    return base


class TestAutoDeriveDurationFlags:
    def test_concentrated_finding_becomes_a_flag(self):
        flags = auto_derive_duration_flags([_finding()])
        assert len(flags) == 1
        assert flags[0]["country"] == "Bolivia"
        assert flags[0]["source"] == "auto_derived"
        assert "213" in flags[0]["note"]
        assert "rosa_cardenas" in flags[0]["note"]

    def test_unconcentrated_finding_does_not_become_a_flag(self):
        # A spread-out fast-interview pattern across many enumerators is
        # more likely a genuinely quick population than a data problem.
        flags = auto_derive_duration_flags([_finding(concentration=0.2)])
        assert flags == []

    def test_note_states_it_is_not_evidence_of_invalidity(self):
        flags = auto_derive_duration_flags([_finding()])
        assert "not evidence the records are invalid" in flags[0]["note"]

    def test_empty_findings_produce_no_flags(self):
        assert auto_derive_duration_flags([]) == []

    def test_id_is_derived_from_country_name(self):
        flags = auto_derive_duration_flags([_finding(country="Dominican Republic")])
        assert flags[0]["id"] == "dominican_republic_duration_outlier"


class TestGetFlags:
    def test_combines_hand_entered_and_auto_derived(self, monkeypatch):
        monkeypatch.setitem(DATA_QUALITY_FLAGS, "lacro", [
            {"id": "manual_flag", "country": "Ecuador", "note": "hand-entered", "source": "manual"},
        ])
        flags = get_flags("lacro", [_finding(country="Bolivia")])
        ids = {f["id"] for f in flags}
        assert ids == {"manual_flag", "bolivia_duration_outlier"}

    def test_no_duration_findings_returns_only_hand_entered(self, monkeypatch):
        monkeypatch.setitem(DATA_QUALITY_FLAGS, "lacro", [
            {"id": "manual_flag", "country": "Ecuador", "note": "hand-entered"},
        ])
        flags = get_flags("lacro", None)
        assert len(flags) == 1
        assert flags[0]["id"] == "manual_flag"

    def test_unknown_scope_with_no_flags_returns_empty(self):
        assert get_flags("africa", []) == []

    def test_none_scope_still_applies_duration_findings(self):
        # get_flags() must not crash when report_scope is None (a run with
        # no report_scope at all) -- DATA_QUALITY_FLAGS.get(None, []) is a
        # safe empty default, auto-derived flags still apply.
        flags = get_flags(None, [_finding()])
        assert len(flags) == 1


class TestDerivePeriodMismatchFlag:
    # --- Single-quarter fieldwork: entered-vs-actual check only ---

    def test_single_quarter_fieldwork_matching_entered_quarter_no_flag(self):
        fieldwork = {"available": True, "start_date": "2026-04-05", "end_date": "2026-04-20"}
        assert derive_period_mismatch_flag(2026, 2, fieldwork) == []

    def test_single_quarter_fieldwork_not_matching_entered_quarter_flags(self):
        fieldwork = {"available": True, "start_date": "2026-04-05", "end_date": "2026-04-20"}
        flags = derive_period_mismatch_flag(2026, 1, fieldwork)
        assert len(flags) == 1
        assert flags[0]["id"] == "period_label_mismatch"
        assert "2026 Q1" in flags[0]["note"]

    def test_single_quarter_fieldwork_states_one_quarter_in_note(self):
        fieldwork = {"available": True, "start_date": "2026-04-05", "end_date": "2026-04-20"}
        flags = derive_period_mismatch_flag(2026, 1, fieldwork)
        assert "fieldwork falls in 2026 Q2" in flags[0]["note"]
        assert "through" not in flags[0]["note"]

    # --- Multi-quarter fieldwork: flagged unconditionally, regardless of
    # which single quarter was entered (the gap in the original, too-
    # lenient version of this rule: entering the START quarter used to
    # pass silently even when fieldwork ran a full extra month into the
    # next quarter) ---

    def test_multi_quarter_fieldwork_flags_even_when_entered_matches_start(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = derive_period_mismatch_flag(2026, 2, fieldwork)
        assert len(flags) == 1
        assert "spans more than one calendar quarter" in flags[0]["note"]

    def test_multi_quarter_fieldwork_flags_even_when_entered_matches_end(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = derive_period_mismatch_flag(2026, 3, fieldwork)
        assert len(flags) == 1

    def test_multi_quarter_fieldwork_flags_when_entered_matches_neither(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = derive_period_mismatch_flag(2026, 4, fieldwork)
        assert len(flags) == 1
        assert flags[0]["id"] == "period_label_mismatch"
        assert "2026 Q4" in flags[0]["note"]
        assert "2026-06-26 to 2026-08-04" in flags[0]["note"]

    def test_spanning_fieldwork_states_a_range_in_note(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = derive_period_mismatch_flag(2026, 4, fieldwork)
        assert "2026 Q2 through 2026 Q3" in flags[0]["note"]

    def test_missing_fieldwork_produces_no_flag(self):
        assert derive_period_mismatch_flag(2026, 2, None) == []
        assert derive_period_mismatch_flag(2026, 2, {"available": False}) == []

    def test_missing_entered_period_produces_no_flag(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        assert derive_period_mismatch_flag(None, None, fieldwork) == []
        assert derive_period_mismatch_flag(2026, None, fieldwork) == []

    def test_never_carries_a_country_key(self):
        # flagged_countries()'s exclusion mechanism is country-scoped; this
        # flag is whole-run, not country-specific, and must stay invisible
        # to that mechanism (see flagged_countries()'s .get("country") guard).
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = derive_period_mismatch_flag(2026, 4, fieldwork)
        assert "country" not in flags[0]
        assert flagged_countries(flags) == []


class TestGetFlagsPeriodMismatchIntegration:
    def test_get_flags_includes_period_mismatch_when_supplied(self):
        fieldwork = {"available": True, "start_date": "2026-06-26", "end_date": "2026-08-04"}
        flags = get_flags("lacro", None, entered_year=2026, entered_quarter=4, fieldwork=fieldwork)
        assert {f["id"] for f in flags} == {"period_label_mismatch"}

    def test_get_flags_defaults_omit_period_mismatch(self):
        # Existing call sites that don't pass the new kwargs must see
        # unchanged behavior.
        assert get_flags("lacro", None) == []


class TestFlaggedCountries:
    def test_extracts_unique_sorted_country_names(self):
        flags = [
            {"country": "Bolivia"}, {"country": "Ecuador"}, {"country": "Bolivia"},
        ]
        assert flagged_countries(flags) == ["Bolivia", "Ecuador"]

    def test_empty_flags_returns_empty_list(self):
        assert flagged_countries([]) == []

    def test_ignores_flags_without_a_country(self):
        assert flagged_countries([{"id": "x"}]) == []
