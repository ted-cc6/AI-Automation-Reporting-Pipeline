"""
Unit tests for generation/orchestrator.py's not_applicable wiring (the gap
picked up after Phase 5). Confirms _not_applicable_path() correctly derives
a sibling path from a suppressed_path string, and that extract_metrics(),
_build_drivers_data(), and the scorecard builders all thread not_applicable
through to the formatted output -- while a metric with real data (the
unscoped/global shape) is completely unaffected.
Run: pytest tests/test_orchestrator.py -v
"""
from __future__ import annotations

from generation.orchestrator import (
    _build_drivers_data,
    _build_scorecard_5,
    _build_scorecard_6,
    _build_scorecard_7,
    _not_applicable_path,
    extract_metrics,
)


# ---------------------------------------------------------------------------
# _not_applicable_path
# ---------------------------------------------------------------------------

class TestNotApplicablePath:
    def test_derives_sibling_path_from_suppressed_path(self):
        assert (
            _not_applicable_path("parts.part_1.metrics.worth_premium.headline.suppressed")
            == "parts.part_1.metrics.worth_premium.headline.not_applicable"
        )

    def test_empty_string_returns_empty_string(self):
        assert _not_applicable_path("") == ""

    def test_path_not_ending_in_suppressed_returns_empty_string(self):
        assert _not_applicable_path("parts.part_1.metrics.worth_premium.headline.value") == ""


# ---------------------------------------------------------------------------
# extract_metrics -- headline metrics (worth_premium/renewal_intent shape)
# ---------------------------------------------------------------------------

_WORTH_PREMIUM_SPEC = {
    "path": "parts.part_1.metrics.worth_premium.headline.value",
    "fmt": "pct",
    "n_path": "parts.part_1.metrics.worth_premium.headline.n_valid",
    "suppressed_path": "parts.part_1.metrics.worth_premium.headline.suppressed",
    "population": "Health & credit-life clients only",
}


class TestExtractMetrics:
    def test_global_shaped_data_formats_normally(self):
        # Global/unscoped run: worth_premium has real data -- must be
        # completely unaffected by the not_applicable wiring.
        analysis = {
            "parts": {"part_1": {"metrics": {"worth_premium": {"headline": {
                "value": 0.62, "n_valid": 1957, "suppressed": False, "not_applicable": False,
            }}}}}
        }
        section_spec = {"metrics": {"worth_premium": _WORTH_PREMIUM_SPEC}}
        result = extract_metrics(analysis, section_spec)
        assert result["worth_premium"] == "62.0%"
        assert result["worth_premium_n"] == "1957"

    def test_country_scoped_not_applicable_data_renders_marker(self):
        # Vietnam-scoped run: worth_premium was never asked -- must render
        # as NOT APPLICABLE, not SUPPRESSED or a formatted percentage.
        analysis = {
            "parts": {"part_1": {"metrics": {"worth_premium": {"headline": {
                "value": None, "n_valid": 0, "suppressed": True, "not_applicable": True,
            }}}}}
        }
        section_spec = {"metrics": {"worth_premium": _WORTH_PREMIUM_SPEC}}
        result = extract_metrics(analysis, section_spec)
        assert result["worth_premium"] == "NOT APPLICABLE"

    def test_ordinary_low_n_suppression_still_says_suppressed(self):
        # A real low-N suppression (asked, but too few answered) must keep
        # showing SUPPRESSED, not be reclassified as NOT APPLICABLE.
        analysis = {
            "parts": {"part_1": {"metrics": {"worth_premium": {"headline": {
                "value": None, "n_valid": 12, "suppressed": True, "not_applicable": False,
            }}}}}
        }
        section_spec = {"metrics": {"worth_premium": _WORTH_PREMIUM_SPEC}}
        result = extract_metrics(analysis, section_spec)
        assert result["worth_premium"] == "SUPPRESSED"

    def test_spec_entry_without_suppressed_path_is_unaffected(self):
        # A metric spec with no suppressed_path at all must not crash and
        # must never be misclassified as not_applicable.
        analysis = {"parts": {"part_1": {"metrics": {"foo": {"headline": {"value": 0.4}}}}}}
        section_spec = {"metrics": {"foo": {
            "path": "parts.part_1.metrics.foo.headline.value", "fmt": "pct",
        }}}
        result = extract_metrics(analysis, section_spec)
        assert result["foo"] == "40.0%"

    def test_driver_loop_within_extract_metrics_handles_not_applicable(self):
        analysis = {"parts": {"part_4": {"drivers": {"renewal_intent": {
            "value": None, "n_valid": 0, "suppressed": True, "not_applicable": True,
            "p_value": None,
        }}}}}
        section_spec = {"drivers": {"renewal_intent": {
            "rho_path": "parts.part_4.drivers.renewal_intent.value",
            "p_path": "parts.part_4.drivers.renewal_intent.p_value",
            "n_path": "parts.part_4.drivers.renewal_intent.n_valid",
            "suppressed_path": "parts.part_4.drivers.renewal_intent.suppressed",
        }}}
        result = extract_metrics(analysis, section_spec)
        assert result["renewal_intent_rho"] == "NOT APPLICABLE"
        assert result["renewal_intent_p"] == "NOT APPLICABLE"
        assert result["renewal_intent_n"] == "NOT APPLICABLE"


# ---------------------------------------------------------------------------
# _build_drivers_data
# ---------------------------------------------------------------------------

class TestBuildDriversData:
    _DRIVERS_SPEC = {
        "worth_premium": {
            "rho_path": "parts.part_4.satisfaction_drivers.drivers.worth_premium.value",
            "p_path": "parts.part_4.satisfaction_drivers.drivers.worth_premium.p_value",
            "n_path": "parts.part_4.satisfaction_drivers.drivers.worth_premium.n_valid",
            "suppressed_path": "parts.part_4.satisfaction_drivers.drivers.worth_premium.suppressed",
            "population": "Health & credit-life clients only",
        }
    }

    def test_global_shaped_driver_carries_not_applicable_false(self):
        analysis = {"parts": {"part_4": {"satisfaction_drivers": {"drivers": {"worth_premium": {
            "value": 0.31, "p_value": 0.001, "n_valid": 1957, "suppressed": False, "not_applicable": False,
        }}}}}}
        rows = _build_drivers_data(analysis, self._DRIVERS_SPEC)
        assert rows[0]["not_applicable"] is False
        assert rows[0]["suppressed"] is False

    def test_country_scoped_driver_carries_not_applicable_true(self):
        analysis = {"parts": {"part_4": {"satisfaction_drivers": {"drivers": {"worth_premium": {
            "value": None, "p_value": None, "n_valid": 0, "suppressed": True, "not_applicable": True,
        }}}}}}
        rows = _build_drivers_data(analysis, self._DRIVERS_SPEC)
        assert rows[0]["not_applicable"] is True
        assert rows[0]["suppressed"] is True


# ---------------------------------------------------------------------------
# Scorecard builders (Parts 5, 6, 7) -- exercised via _build_scorecard_6,
# the same pattern applies identically to _build_scorecard_5/7.
# ---------------------------------------------------------------------------

class TestBuildScorecard6:
    _SPEC = [{
        "key": "worth_premium",
        "label": "Worth Premium",
        "fmt": "pct",
        "claimant_path": "parts.part_6.metrics.worth_premium.claimant.value",
        "non_claimant_path": "parts.part_6.metrics.worth_premium.non_claimant.value",
        "sig_path": "parts.part_6.metrics.worth_premium.significance.p_value",
        "claimant_sup": "parts.part_6.metrics.worth_premium.claimant.suppressed",
        "non_claimant_sup": "parts.part_6.metrics.worth_premium.non_claimant.suppressed",
        "population": "Health & credit-life clients only",
    }]

    def test_country_scoped_both_groups_not_applicable(self):
        analysis = {"parts": {"part_6": {"metrics": {"worth_premium": {
            "claimant": {"value": None, "suppressed": True, "not_applicable": True},
            "non_claimant": {"value": None, "suppressed": True, "not_applicable": True},
            "significance": {"p_value": None},
        }}}}}
        rows = _build_scorecard_6(analysis, self._SPEC)
        assert rows[0]["group_a_value"] == "NOT APPLICABLE"
        assert rows[0]["group_b_value"] == "NOT APPLICABLE"

    def test_global_shaped_both_groups_format_normally(self):
        analysis = {"parts": {"part_6": {"metrics": {"worth_premium": {
            "claimant": {"value": 0.58, "suppressed": False, "not_applicable": False},
            "non_claimant": {"value": 0.64, "suppressed": False, "not_applicable": False},
            "significance": {"p_value": 0.02},
        }}}}}
        rows = _build_scorecard_6(analysis, self._SPEC)
        assert rows[0]["group_a_value"] == "58.0%"
        assert rows[0]["group_b_value"] == "64.0%"
        assert rows[0]["significant"] is True


def test_build_scorecard_5_wires_not_applicable():
    spec = [{
        "label": "Financial Stress",
        "fmt": "pct",
        "caregiver_path": "x.caregiver.value",
        "non_caregiver_path": "x.non_caregiver.value",
        "sig_path": "x.significance.p_value",
        "caregiver_sup": "x.caregiver.suppressed",
        "non_caregiver_sup": "x.non_caregiver.suppressed",
    }]
    analysis = {"x": {
        "caregiver": {"value": None, "suppressed": True, "not_applicable": True},
        "non_caregiver": {"value": 0.4, "suppressed": False, "not_applicable": False},
        "significance": {"p_value": None},
    }}
    rows = _build_scorecard_5(analysis, spec)
    assert rows[0]["group_a_value"] == "NOT APPLICABLE"
    assert rows[0]["group_b_value"] == "40.0%"


def test_build_scorecard_7_wires_not_applicable():
    spec = [{
        "label": "Renewal Intent",
        "fmt": "pct",
        "female_path": "x.female.value",
        "male_path": "x.male.value",
        "sig_path": "x.significance.p_value",
        "female_sup": "x.female.suppressed",
        "male_sup": "x.male.suppressed",
    }]
    analysis = {"x": {
        "female": {"value": 0.7, "suppressed": False, "not_applicable": False},
        "male": {"value": None, "suppressed": True, "not_applicable": True},
        "significance": {"p_value": None},
    }}
    rows = _build_scorecard_7(analysis, spec)
    assert rows[0]["group_a_value"] == "70.0%"
    assert rows[0]["group_b_value"] == "NOT APPLICABLE"
