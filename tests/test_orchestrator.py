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
    _format_coping_components,
    _not_applicable_path,
    _resolve_population,
    default_parts_filter,
    extract_metrics,
)


# ---------------------------------------------------------------------------
# default_parts_filter -- regression coverage for a real bug: this used to
# hardcode ("part_9", "part_10") as the only "conditionally gated" parts, so
# adding Part 11/12 (also conditionally gated, on report_scope=="africa")
# silently passed the filter on EVERY run regardless of whether analysis_
# results.json actually had that part's data -- caught against real
# LACRO-scope output, where Part 11/12 have zero credit-life/crop clients.
# ---------------------------------------------------------------------------

class TestDefaultPartsFilter:
    def test_only_includes_parts_present_in_analysis_results(self):
        spec = {"parts": {"part_1": {}, "part_9": {}, "part_11": {}}}
        analysis = {"parts": {"part_1": {}, "part_9": {}}}  # part_11 absent
        assert default_parts_filter(spec, analysis) == ["part_1", "part_9"]

    def test_generalizes_to_a_hypothetical_future_conditional_part(self):
        # Must not require hardcoding new part names as they're added --
        # any part_spec key absent from analysis["parts"] is excluded,
        # regardless of what it's called.
        spec = {"parts": {"part_1": {}, "part_99": {}}}
        analysis = {"parts": {"part_1": {}}}  # part_99 absent
        assert default_parts_filter(spec, analysis) == ["part_1"]

    def test_empty_parts_dict_excludes_everything(self):
        spec = {"parts": {"part_1": {}, "part_2": {}}}
        analysis = {"parts": {}}
        assert default_parts_filter(spec, analysis) == []

    def test_missing_parts_key_in_analysis_excludes_everything(self):
        spec = {"parts": {"part_1": {}}}
        analysis = {}
        assert default_parts_filter(spec, analysis) == []


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
# _resolve_population -- a report_spec.yaml population note is usually a
# plain string (shown for every scope), but some (worth_premium) describe an
# Africa/Vietnam-specific product split that is simply false for a
# LACRO-scoped report (100% Health product, no Vietnam/credit-life clients
# to exclude) -- caught from a real generated LACRO report showing this
# exact wrong caveat, even though its own products table read 100% Health.
# ---------------------------------------------------------------------------

class TestResolvePopulation:
    def test_plain_string_passes_through_unchanged_regardless_of_scope(self):
        assert _resolve_population("Some fixed caveat", "lacro") == "Some fixed caveat"
        assert _resolve_population("Some fixed caveat", None) == "Some fixed caveat"

    def test_none_passes_through_unchanged(self):
        assert _resolve_population(None, "lacro") is None

    def test_dict_resolves_named_scope_key(self):
        pop = {"default": "Africa caveat", "lacro": None}
        assert _resolve_population(pop, "lacro") is None
        assert _resolve_population(pop, "africa") == "Africa caveat"

    def test_dict_falls_back_to_default_for_unlisted_scope(self):
        pop = {"default": "Africa caveat", "lacro": None}
        assert _resolve_population(pop, None) == "Africa caveat"
        assert _resolve_population(pop, "some_future_scope") == "Africa caveat"

    def test_dict_with_no_default_and_unlisted_scope_returns_none(self):
        assert _resolve_population({"lacro": None}, "africa") is None


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

    def test_components_path_threads_named_components_into_metrics(self):
        # R-008: negative_coping's components_path/suppressed_components_path
        # feed _format_coping_components() into a "<key>_components" entry
        # writer.py's prompt renders as [components: ...].
        analysis = {"parts": {"part_3": {"metrics": {"negative_coping": {
            "headline": {"value": 0.065, "n_valid": 124},
            "components": [{"key": "sold_assets_livestock", "label": "Sold assets or livestock", "n": 7}],
            "suppressed_components": 1,
        }}}}}
        section_spec = {"metrics": {"negative_coping": {
            "path": "parts.part_3.metrics.negative_coping.headline.value", "fmt": "pct",
            "components_path": "parts.part_3.metrics.negative_coping.components",
            "suppressed_components_path": "parts.part_3.metrics.negative_coping.suppressed_components",
        }}}
        result = extract_metrics(analysis, section_spec)
        assert result["negative_coping_components"] == (
            "sold assets or livestock (n=7); 1 further component(s) suppressed "
            "(too few respondents to name without risk of identifying them)"
        )

    def test_no_components_path_configured_is_unaffected(self):
        # Every other metric on the codebase has no components_path at all --
        # must not raise or add a spurious "_components" key.
        analysis = {"parts": {"part_1": {"metrics": {"foo": {"headline": {"value": 0.4}}}}}}
        section_spec = {"metrics": {"foo": {
            "path": "parts.part_1.metrics.foo.headline.value", "fmt": "pct",
        }}}
        result = extract_metrics(analysis, section_spec)
        assert "foo_components" not in result


class TestFormatCopingComponents:
    def test_named_components_only(self):
        components = [{"key": "a", "label": "Sold assets or livestock", "n": 7}]
        assert _format_coping_components(components, 0) == "sold assets or livestock (n=7)"

    def test_multiple_components_ranked_and_joined(self):
        components = [
            {"key": "a", "label": "Reduced food consumption", "n": 10},
            {"key": "b", "label": "Sold assets or livestock", "n": 3},
        ]
        assert _format_coping_components(components, 0) == (
            "reduced food consumption (n=10); sold assets or livestock (n=3)"
        )

    def test_suppressed_count_appended(self):
        components = [{"key": "a", "label": "Sold assets or livestock", "n": 7}]
        result = _format_coping_components(components, 2)
        assert result.startswith("sold assets or livestock (n=7); ")
        assert "2 further component(s) suppressed" in result

    def test_all_suppressed_no_named_components(self):
        result = _format_coping_components([], 3)
        assert result == (
            "no single behaviour is common enough to name; 3 further component(s) "
            "suppressed (too few respondents to name without risk of identifying them)"
        )

    def test_nothing_found_and_nothing_suppressed_returns_empty_string(self):
        assert _format_coping_components([], 0) == ""

    def test_driver_loop_within_extract_metrics_omits_not_applicable_entirely(self):
        # Regression test: this loop used to lack the `continue` the metrics
        # loop above it (and _build_drivers_data()) already had, so a
        # not_applicable driver's key survived into the flat dict with a
        # "NOT APPLICABLE" string value -- reaching writer.py's "Metrics"
        # prompt section even though the correctly-filtered "Drivers"
        # section already omitted the same driver. A region-scoped report
        # whose clients were never asked a driver's question (e.g.
        # renewal_intent for a LACRO-scoped run) must not see that driver's
        # key at all, not just a masked value -- see project_region_scoping
        # memory.
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
        assert "renewal_intent_rho" not in result
        assert "renewal_intent_p" not in result
        assert "renewal_intent_n" not in result

    def test_driver_loop_within_extract_metrics_still_marks_suppressed(self):
        # A driver that WAS asked but has too few responses (suppressed,
        # not not_applicable) must still appear, marked SUPPRESSED -- only
        # not_applicable drivers are omitted entirely.
        analysis = {"parts": {"part_4": {"drivers": {"worth_premium": {
            "value": None, "n_valid": 12, "suppressed": True, "not_applicable": False,
            "p_value": None,
        }}}}}
        section_spec = {"drivers": {"worth_premium": {
            "rho_path": "parts.part_4.drivers.worth_premium.value",
            "p_path": "parts.part_4.drivers.worth_premium.p_value",
            "n_path": "parts.part_4.drivers.worth_premium.n_valid",
            "suppressed_path": "parts.part_4.drivers.worth_premium.suppressed",
        }}}
        result = extract_metrics(analysis, section_spec)
        assert result["worth_premium_rho"] == "SUPPRESSED"
        assert result["worth_premium_p"] == "SUPPRESSED"
        assert result["worth_premium_n"] == "SUPPRESSED"


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

    def test_group_labels_state_the_population_not_a_bare_word(self):
        # _B (JSON key "non_claimant") is clients who experienced an insured
        # event but did not file, not the full never-claimed population.
        # "Non-Claimant" invited exactly that misreading in a real generated
        # report (its NPS read as directly comparable to the whole-portfolio
        # NPS, a different population); "Non-Filer" fixed the scope
        # confusion but was itself opaque about what population it named
        # (R-011, session-10) -- both are retired in favour of labels that
        # state the population directly. The JSON key stays "non_claimant"
        # for path stability; only the display label changed.
        analysis = {"parts": {"part_6": {"metrics": {"worth_premium": {
            "claimant": {"value": 0.58, "suppressed": False, "not_applicable": False},
            "non_claimant": {"value": 0.64, "suppressed": False, "not_applicable": False},
            "significance": {"p_value": 0.02},
        }}}}}
        rows = _build_scorecard_6(analysis, self._SPEC)
        assert rows[0]["group_a_label"] == "Claimant (filed)"
        assert rows[0]["group_b_label"] == "Did not file"

    def test_population_is_omitted_for_lacro_scope(self):
        spec = [{**self._SPEC[0], "population": {
            "default": "Health & credit-life clients only",
            "lacro": None,
        }}]
        analysis = {
            "meta": {"report_scope": "lacro"},
            "parts": {"part_6": {"metrics": {"worth_premium": {
                "claimant": {"value": 0.98, "suppressed": False, "not_applicable": False},
                "non_claimant": {"value": 0.83, "suppressed": False, "not_applicable": False},
                "significance": {"p_value": 0.02},
            }}}},
        }
        rows = _build_scorecard_6(analysis, spec)
        assert rows[0]["population"] is None

    def test_population_default_used_for_africa_scope(self):
        spec = [{**self._SPEC[0], "population": {
            "default": "Health & credit-life clients only",
            "lacro": None,
        }}]
        analysis = {
            "meta": {"report_scope": "africa"},
            "parts": {"part_6": {"metrics": {"worth_premium": {
                "claimant": {"value": 0.98, "suppressed": False, "not_applicable": False},
                "non_claimant": {"value": 0.83, "suppressed": False, "not_applicable": False},
                "significance": {"p_value": 0.02},
            }}}},
        }
        rows = _build_scorecard_6(analysis, spec)
        assert rows[0]["population"] == "Health & credit-life clients only"


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

_FTA_REASON = "Identical question wording and options in both waves."


def _trend_analysis(definition_match) -> dict:
    return {"parts": {"part_10": {
        "current": {"first_time_access": {
            "value": 0.8, "n_valid": 500, "n_total": 500, "suppressed": False, "not_applicable": False,
        }},
        "prior_available": True,
        "comparison": {"first_time_access": {
            "comparability": "clean",
            "comparability_reason": _FTA_REASON,
            "current_common_scope": {
                "value": 0.79, "n_valid": 300, "n_total": 300, "suppressed": False, "not_applicable": False,
            },
            "prior": {"value": 0.7, "n_valid": 480, "n_total": 480, "suppressed": False, "not_applicable": False},
            "significance": {"p_value": 0.02},
            "definition_match": definition_match,
        }},
    }}}


class TestBuildTrendDataDefinitionMismatch:
    def test_mismatch_adds_warning_note(self):
        rows, _ = _build_trend_data(_trend_analysis(False), _TREND_SPEC)
        assert "DEFINITION MISMATCH" in rows[0]["sig_test_note"]

    def test_match_adds_no_mismatch_warning(self):
        # A "clean" row's footnote is just its comparability reason unless
        # a definition mismatch is also flagged -- the common-country
        # explanation this used to carry moved to the table-level
        # scope_note (R-005: stated once, not per row) once the row's own
        # displayed value became the common-country figure itself.
        rows, scope_note = _build_trend_data(_trend_analysis(True), _TREND_SPEC)
        assert "DEFINITION MISMATCH" not in rows[0]["sig_test_note"]
        assert rows[0]["sig_test_note"] == _FTA_REASON
        assert "five countries surveyed in both waves" in scope_note
        assert "Dominican Republic" in scope_note

    def test_unknown_match_adds_no_mismatch_warning(self):
        rows, scope_note = _build_trend_data(_trend_analysis(None), _TREND_SPEC)
        assert "DEFINITION MISMATCH" not in rows[0]["sig_test_note"]
        assert "five countries surveyed in both waves" in scope_note

    def test_mismatch_note_appends_to_existing_reason_not_overwrites(self):
        rows, _ = _build_trend_data(_trend_analysis(False), _TREND_SPEC)
        assert _FTA_REASON in rows[0]["sig_test_note"]
        assert "DEFINITION MISMATCH" in rows[0]["sig_test_note"]

    def test_sig_p_and_significant_are_never_populated_for_part_10(self):
        # R-009: Part 10 never puts a real p-value into sig_p/significant,
        # even for a "clean" row with a real significance test computed
        # upstream (part_10.py) -- this is the actual fix for the p-value
        # leak into generated narrative (writer.py's _build_scorecard_text()
        # only quotes a p-value when sig_p is not None).
        rows, _ = _build_trend_data(_trend_analysis(True), _TREND_SPEC)
        assert rows[0]["sig_p"] is None
        assert rows[0]["significant"] is False

    def test_clean_row_uses_common_scope_as_current_wave_value(self):
        # R-005: the table's own current-wave figure for a "clean" row is
        # the five-country comparable subset (0.79), not the six-country
        # full-scope figure (0.8) every other row uses.
        rows, _ = _build_trend_data(_trend_analysis(True), _TREND_SPEC)
        assert rows[0]["group_a_value"] == "79.0%"


# ---------------------------------------------------------------------------
# _build_trend_data -- current-wave NOT APPLICABLE gets distinct footnote
# wording from a real new-baseline indicator. A real generated report called
# a wave with NO figure for product_understanding at all (2026's format has
# no single combined question to compute it from) the "founding baseline"
# for that indicator -- "new baseline" implies a real number exists for
# future waves to compare against, which isn't true when the current wave
# itself is not_applicable.
# ---------------------------------------------------------------------------

def _not_comparable_analysis(current_not_applicable: bool, comparability: str = "not_comparable") -> dict:
    return {"parts": {"part_10": {
        "current": {"product_understanding": {
            "value": None if current_not_applicable else 0.75,
            "n_valid": 0 if current_not_applicable else 500,
            "n_total": 0 if current_not_applicable else 500,
            "suppressed": current_not_applicable,
            "not_applicable": current_not_applicable,
        }},
        "prior_available": True,
        "comparison": {"product_understanding": {
            "comparability": comparability,
            "comparability_reason": "the 2025 instrument used one combined 6-option question; "
                                     "2026 splits it into two separate 4-point questions",
            # session-5: a real 2025 figure -- product_understanding's OWN
            # not_comparable case is exactly "2025 has a figure, 2026
            # doesn't" (the combined question only existed in 2025).
            "prior": {
                "value": 0.20, "n_valid": 480, "n_total": 480,
                "suppressed": False, "not_applicable": False,
            },
        }},
    }}}


_PU_SPEC = [{"key": "product_understanding", "label": "Product Understanding", "fmt": "pct"}]


class TestBuildTrendDataNotApplicableCurrentWave:
    def test_not_applicable_current_wave_names_the_missing_2026_figure(self):
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert "new baseline" not in rows[0]["sig_test_note"]
        assert "only the prior wave's own figure is available" in rows[0]["sig_test_note"]

    def test_not_applicable_current_wave_still_names_the_reason(self):
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert "one combined 6-option question" in rows[0]["sig_test_note"]

    def test_not_applicable_current_wave_still_shows_the_real_prior_value(self):
        # session-5 (LM3, per Lorenz): product_understanding's own
        # current-wave figure is genuinely absent (2026's split-question
        # schema has no combined form), but its real 2025 value must
        # still render, not "NOT COMPARABLE".
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert rows[0]["group_b_value"] == "20.0%"

    def test_real_current_wave_figure_does_not_add_the_missing_2026_note(self):
        # A genuinely non-"clean" indicator whose current wave DOES have a
        # real figure (access_to_alternatives/child_wellbeing_improvement
        # in practice) must not get the "only the prior wave's own figure
        # is available" sentence -- that's specific to product_
        # understanding's own not_applicable case.
        rows, _ = _build_trend_data(_not_comparable_analysis(False), _PU_SPEC)
        assert "only the prior wave's own figure is available" not in rows[0]["sig_test_note"]
        assert "Both figures are shown for reference" in rows[0]["sig_test_note"]

    def test_current_wave_table_cell_reads_not_applicable(self):
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert rows[0]["group_a_value"] == "NOT APPLICABLE"

    def test_no_comparative_language_note_present_regardless(self):
        # The "do not use comparative language" instruction must survive
        # even though both cells can now show real numbers -- this is the
        # actual restriction that stops the writer treating two displayed
        # figures as an implied delta.
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert "do not use comparative language" in rows[0]["sig_test_note"]

    def test_comparability_field_carried_through_to_row(self):
        rows, _ = _build_trend_data(_not_comparable_analysis(True), _PU_SPEC)
        assert rows[0]["comparability"] == "not_comparable"

    def test_indicative_footnote_reads_differently_from_not_comparable(self):
        # R-004: the Comparability column already distinguishes "indicative"
        # from "not_comparable"; the footnote prose should too, not repeat
        # identical "not comparable" wording for a row Lorenz specifically
        # wanted read as indicative rather than flatly non-comparable.
        indicative_rows, _ = _build_trend_data(
            _not_comparable_analysis(False, comparability="indicative"), _PU_SPEC
        )
        not_comparable_rows, _ = _build_trend_data(
            _not_comparable_analysis(False, comparability="not_comparable"), _PU_SPEC
        )
        assert "Indicative only" in indicative_rows[0]["sig_test_note"]
        assert "Indicative only" not in not_comparable_rows[0]["sig_test_note"]
        assert "Not comparable to the prior wave" in not_comparable_rows[0]["sig_test_note"]
