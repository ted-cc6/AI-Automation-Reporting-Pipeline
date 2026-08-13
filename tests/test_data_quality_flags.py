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
