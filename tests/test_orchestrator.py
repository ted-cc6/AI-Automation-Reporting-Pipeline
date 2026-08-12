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
    _build_trend_data,
    _check_metric_coverage,
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

    def test_country_scoped_not_applicable_data_is_omitted_entirely(self):
        # Vietnam-scoped run: worth_premium was never asked -- omit the metric
        # (and its _n/_population companions) entirely rather than sending a
        # dead "NOT APPLICABLE" line into the prompt/table.
        analysis = {
            "parts": {"part_1": {"metrics": {"worth_premium": {"headline": {
                "value": None, "n_valid": 0, "suppressed": True, "not_applicable": True,
            }}}}}
        }
        section_spec = {"metrics": {"worth_premium": _WORTH_PREMIUM_SPEC}}
        result = extract_metrics(analysis, section_spec)
        assert "worth_premium" not in result
        assert "worth_premium_n" not in result
        assert "worth_premium_population" not in result

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

    def test_country_scoped_driver_is_omitted_entirely(self):
        analysis = {"parts": {"part_4": {"satisfaction_drivers": {"drivers": {"worth_premium": {
            "value": None, "p_value": None, "n_valid": 0, "suppressed": True, "not_applicable": True,
        }}}}}}
        rows = _build_drivers_data(analysis, self._DRIVERS_SPEC)
        assert rows == []


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

    def test_country_scoped_both_groups_not_applicable_row_omitted(self):
        analysis = {"parts": {"part_6": {"metrics": {"worth_premium": {
            "claimant": {"value": None, "suppressed": True, "not_applicable": True},
            "non_claimant": {"value": None, "suppressed": True, "not_applicable": True},
            "significance": {"p_value": None},
        }}}}}
        rows = _build_scorecard_6(analysis, self._SPEC)
        assert rows == []

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

    def test_only_one_group_not_applicable_row_is_kept_not_dropped(self):
        # not_applicable is a column-presence property shared by the whole
        # dataset, so both groups should always agree in practice -- but the
        # drop must require BOTH sides to be not_applicable, never just one,
        # so a genuine per-group suppression is never silently discarded.
        analysis = {"parts": {"part_6": {"metrics": {"worth_premium": {
            "claimant": {"value": None, "suppressed": True, "not_applicable": True},
            "non_claimant": {"value": 0.64, "suppressed": False, "not_applicable": False},
            "significance": {"p_value": None},
        }}}}}
        rows = _build_scorecard_6(analysis, self._SPEC)
        assert len(rows) == 1
        assert rows[0]["group_a_value"] == "NOT APPLICABLE"
        assert rows[0]["group_b_value"] == "64.0%"


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


# ---------------------------------------------------------------------------
# _check_metric_coverage -- pre-flight gate (Phase E) catching a metric whose
# answer coverage craters relative to its own declared population without
# being marked not_applicable, which is far more likely a column-mapping bug
# than genuine small-sample suppression.
# ---------------------------------------------------------------------------

def _spec_with_one_metric(path: str) -> dict:
    return {"parts": {"part_1": {"sections": {"s1_1": {"metrics": {
        "some_metric": {"path": path, "fmt": "pct"},
    }}}}}}


class TestCheckMetricCoverage:
    def test_normal_high_coverage_metric_raises_no_problem(self):
        analysis = {"parts": {"part_1": {"metrics": {"x": {"headline": {
            "value": 0.5, "n_valid": 480, "n_total": 500, "not_applicable": False,
        }}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.headline.value")
        assert _check_metric_coverage(analysis, spec) == []

    def test_suspiciously_low_coverage_flagged(self):
        analysis = {"parts": {"part_1": {"metrics": {"x": {"headline": {
            "value": 0.5, "n_valid": 5, "n_total": 500, "not_applicable": False,
        }}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.headline.value")
        problems = _check_metric_coverage(analysis, spec)
        assert len(problems) == 1
        assert "5/500" in problems[0]
        assert "1.0%" in problems[0]

    def test_not_applicable_metric_never_flagged_regardless_of_coverage(self):
        analysis = {"parts": {"part_1": {"metrics": {"x": {"headline": {
            "value": None, "n_valid": 0, "n_total": 500, "not_applicable": True,
        }}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.headline.value")
        assert _check_metric_coverage(analysis, spec) == []

    def test_small_declared_population_not_flagged(self):
        # A genuinely small population (below _LOW_COVERAGE_MIN_POPULATION)
        # -- ordinary LOW_N_THRESHOLD suppression handles this case already,
        # this check must not double-flag it.
        analysis = {"parts": {"part_1": {"metrics": {"x": {"headline": {
            "value": 0.5, "n_valid": 1, "n_total": 10, "not_applicable": False,
        }}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.headline.value")
        assert _check_metric_coverage(analysis, spec) == []

    def test_missing_n_valid_or_n_total_skipped_not_crashed(self):
        analysis = {"parts": {"part_1": {"metrics": {"x": {"headline": {
            "value": 0.5, "not_applicable": False,
        }}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.headline.value")
        assert _check_metric_coverage(analysis, spec) == []

    def test_non_value_path_ignored(self):
        analysis = {"parts": {"part_1": {"metrics": {"x": {"n_base": 5}}}}}
        spec = _spec_with_one_metric("parts.part_1.metrics.x.n_base")
        assert _check_metric_coverage(analysis, spec) == []


# ---------------------------------------------------------------------------
# _build_trend_data -- Part 10's definition-mismatch surfacing (Phase E):
# a changed question/scale/base between waves must show up as a table-note
# warning, reusing the same distinct-footnote mechanism verified for NPS's
# own significance-test note.
# ---------------------------------------------------------------------------

_TREND_SPEC = [{"key": "first_time_access", "label": "First-Time Access to Insurance", "fmt": "pct"}]


def _trend_analysis(definition_match) -> dict:
    return {"parts": {"part_10": {
        "current": {"first_time_access": {
            "value": 0.8, "n_valid": 500, "n_total": 500, "suppressed": False, "not_applicable": False,
        }},
        "prior_available": True,
        "comparison": {"first_time_access": {
            "prior": {"value": 0.7, "n_valid": 480, "n_total": 480, "suppressed": False, "not_applicable": False},
            "significance": {"p_value": 0.02},
            "definition_match": definition_match,
        }},
    }}}


class TestBuildTrendDataDefinitionMismatch:
    def test_mismatch_adds_warning_note(self):
        rows = _build_trend_data(_trend_analysis(False), _TREND_SPEC)
        assert "DEFINITION MISMATCH" in rows[0]["sig_test_note"]

    def test_match_adds_no_note(self):
        rows = _build_trend_data(_trend_analysis(True), _TREND_SPEC)
        assert rows[0]["sig_test_note"] is None

    def test_unknown_match_adds_no_note(self):
        rows = _build_trend_data(_trend_analysis(None), _TREND_SPEC)
        assert rows[0]["sig_test_note"] is None

    def test_mismatch_note_appends_to_existing_nps_note_not_overwrites(self):
        analysis = _trend_analysis(False)
        analysis["parts"]["part_10"]["comparison"]["first_time_access"]["significance"] = {
            "p_value": None, "test": "NPS-style existing note",
        }
        spec = [{"key": "first_time_access", "label": "X", "fmt": "pct"}]
        # Simulate an indicator that (hypothetically) already had its own note
        # by reusing the NPS key so the "if key == client_satisfaction_nps"
        # branch populates sig_note before the mismatch check runs.
        analysis["parts"]["part_10"]["current"]["client_satisfaction_nps"] = analysis["parts"]["part_10"]["current"].pop("first_time_access")
        analysis["parts"]["part_10"]["comparison"]["client_satisfaction_nps"] = analysis["parts"]["part_10"]["comparison"].pop("first_time_access")
        rows = _build_trend_data(analysis, [{"key": "client_satisfaction_nps", "label": "NPS", "fmt": "nps"}])
        assert "NPS-style existing note" in rows[0]["sig_test_note"]
        assert "DEFINITION MISMATCH" in rows[0]["sig_test_note"]
