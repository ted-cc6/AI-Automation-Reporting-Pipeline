"""
Unit tests for analysis_engine/stats.py — the pure stat primitives every
report number flows through.
Run: pytest tests/test_stats.py -v
"""
from __future__ import annotations


import math

import numpy as np
import pandas as pd
import pytest

from analysis_engine.stats import (
    LOW_N_THRESHOLD,
    SCOPE_SENTINEL,
    _safe_exp,
    claims_funnel,
    composite_index,
    disaggregate,
    logistic_regression,
    nps_score,
    nps_scorecard_row,
    ranked_options,
    share_selecting,
    share_true,
    significance_test,
    spearman_correlation,
    top_two_box,
    bottom_two_box,
)


def _series(values, dtype=None) -> pd.Series:
    return pd.Series(values, dtype=dtype)


# ---------------------------------------------------------------------------
# top_two_box / bottom_two_box
# ---------------------------------------------------------------------------

class TestTopTwoBox:
    def test_basic_proportion_on_4point_scale(self):
        # 1..4 Likert, top_two_box(top_n=2) counts values in {3, 4}
        s = _series([1, 2, 3, 4, 4, 3, 2, 1] * 5)  # 40 rows, 20 in top two (3,4)
        result = top_two_box(s, top_n=2)
        assert result["n_valid"] == 40
        assert result["scale_max"] == 4
        assert result["top_values"] == [3, 4]
        assert result["value"] == pytest.approx(0.5)
        assert result["suppressed"] is False
        assert result["ci_lower"] < result["value"] < result["ci_upper"]

    def test_drops_nulls_from_denominator(self):
        s = _series([4] * 30 + [None] * 10)
        result = top_two_box(s, top_n=2)
        assert result["n_total"] == 40
        assert result["n_valid"] == 30
        assert result["value"] == pytest.approx(1.0)

    def test_empty_series_returns_none_value_no_crash(self):
        s = _series([], dtype="float64")
        result = top_two_box(s, top_n=2)
        assert result["n_valid"] == 0
        assert result["value"] is None
        assert result["top_values"] == []
        assert result["scale_max"] is None

    def test_low_n_suppression_boundary(self):
        # Exactly at threshold - 1 → suppressed
        just_below = _series([4] * (LOW_N_THRESHOLD - 1))
        result = top_two_box(just_below)
        assert result["n_valid"] == LOW_N_THRESHOLD - 1
        assert result["suppressed"] is True
        assert result["value"] is None
        assert result["suppress_reason"] is not None

        # Exactly at threshold → not suppressed
        at_threshold = _series([4] * LOW_N_THRESHOLD)
        result2 = top_two_box(at_threshold)
        assert result2["suppressed"] is False
        assert result2["value"] == pytest.approx(1.0)


class TestBottomTwoBox:
    def test_inverted_scale_counts_low_values_as_positive(self):
        # Inverted Likert: 1=best .. 4=worst. bottom_two_box should treat {1,2} as "good".
        s = _series([1, 1, 2, 2, 3, 4] * 10)  # 60 rows, 40 in bottom two (1,2)
        result = bottom_two_box(s, bottom_n=2)
        assert result["scale_min"] == 1
        assert result["bottom_values"] == [1, 2]
        assert result["value"] == pytest.approx(40 / 60)

    def test_empty_series(self):
        result = bottom_two_box(_series([], dtype="float64"))
        assert result["value"] is None
        assert result["bottom_values"] == []
        assert result["scale_min"] is None


# ---------------------------------------------------------------------------
# Regression: scale_max/scale_min must come from the question's fixed scale,
# never from the scoped subset's own observed max/min.
#
# Confirmed production bug: a caregiver segment (n=1,037) on q_financial_stress
# (1-5 scale) never reported the worst value ("5"). Without an explicit
# scale_max, top_two_box silently redefined "top two" as {3,4} instead of
# {4,5}, reporting 48.6% ("high financial stress") where the correct figure
# was ~1.4%. Every call site in analysis_engine/sections/*.py must pass
# scale_max/scale_min explicitly -- these tests pin both the correct
# behavior (explicit scale) and the old buggy fallback behavior (so the
# fallback path stays intentional, not an accidental regression).
# ---------------------------------------------------------------------------

class TestScaleRangeRegression:
    # 1,037 respondents on a 1-5 scale; nobody reports the true max ("5").
    _CAREGIVER_LIKE_VALUES = [3] * 489 + [4] * 15 + [1] * 300 + [2] * 233

    def test_top_two_box_explicit_scale_max_ignores_subset_ceiling(self):
        s = _series(self._CAREGIVER_LIKE_VALUES)  # spans 1-4 only, n=1037
        result = top_two_box(s, top_n=2, scale_max=5)
        assert result["n_valid"] == 1037
        assert result["scale_max"] == 5
        assert result["top_values"] == [4, 5]
        assert result["value"] == pytest.approx(15 / 1037)

    def test_top_two_box_without_scale_max_reproduces_old_bug(self):
        # Documents why the fallback is dangerous: omitting scale_max derives
        # the threshold from this subset's own max (4), not the survey's (5).
        s = _series(self._CAREGIVER_LIKE_VALUES)
        result = top_two_box(s, top_n=2)
        assert result["scale_max"] == 4
        assert result["top_values"] == [3, 4]
        assert result["value"] == pytest.approx(504 / 1037)

    def test_bottom_two_box_explicit_scale_min_ignores_subset_floor(self):
        # Mirror case: a subset that never reports the true minimum ("1").
        values = [2] * 300 + [3] * 15 + [4] * 489 + [5] * 233  # spans 2-5 only
        s = _series(values)
        result = bottom_two_box(s, bottom_n=2, scale_min=1)
        assert result["scale_min"] == 1
        assert result["bottom_values"] == [1, 2]
        assert result["value"] == pytest.approx(300 / 1037)

    def test_bottom_two_box_without_scale_min_reproduces_old_bug(self):
        values = [2] * 300 + [3] * 15 + [4] * 489 + [5] * 233
        s = _series(values)
        result = bottom_two_box(s, bottom_n=2)
        assert result["scale_min"] == 2
        assert result["bottom_values"] == [2, 3]
        assert result["value"] == pytest.approx(315 / 1037)


# ---------------------------------------------------------------------------
# share_selecting / share_true
# ---------------------------------------------------------------------------

class TestShareSelecting:
    def test_matches_named_values(self):
        s = _series(["a. Yes", "b. No", "a. Yes", "a. Yes"] + ["a. Yes"] * 26)
        result = share_selecting(s, values=["a. Yes"])
        assert result["n_valid"] == 30
        assert result["value"] == pytest.approx(29 / 30)

    def test_scope_sentinel_excluded_from_denominator(self):
        s = _series(["a. Yes"] * 30 + [SCOPE_SENTINEL] * 5)
        result = share_selecting(s, values=["a. Yes"])
        assert result["n_valid"] == 30
        assert result["n_total"] == 35
        assert result["value"] == pytest.approx(1.0)


class TestShareTrue:
    def test_boolean_dtype_proportion(self):
        s = pd.array([True] * 20 + [False] * 10 + [None] * 5, dtype="boolean")
        result = share_true(pd.Series(s))
        assert result["n_valid"] == 30
        assert result["n_true"] == 20
        assert result["n_false"] == 10
        assert result["value"] == pytest.approx(20 / 30)


# ---------------------------------------------------------------------------
# ranked_options
# ---------------------------------------------------------------------------

class TestRankedOptions:
    def test_ranks_multiselect_lists_by_frequency(self):
        s = _series([
            ["radio", "sms"],
            ["radio"],
            ["radio", "poster"],
            [],       # empty list → not a valid response
            None,     # missing → not a valid response
        ])
        result = ranked_options(s)
        assert result["n_valid"] == 3
        assert result["value"] is None
        options = {r["option"]: r["n"] for r in result["ranked"]}
        assert options == {"radio": 3, "sms": 1, "poster": 1}

    def test_top_n_truncates_ranking(self):
        s = _series([["a", "b"], ["a"], ["b", "c"], ["a"]])
        result = ranked_options(s, top_n=1)
        assert len(result["ranked"]) == 1
        assert result["ranked"][0]["option"] == "a"

    def test_pyarrow_list_scalar_like_object_is_unwrapped(self):
        class FakeListScalar:
            def __init__(self, items):
                self._items = items

            def as_py(self):
                return self._items

        s = _series([FakeListScalar(["radio"]), FakeListScalar([])])
        result = ranked_options(s)
        assert result["n_valid"] == 1
        assert result["ranked"] == [{"option": "radio", "n": 1, "pct": 1.0}]


# ---------------------------------------------------------------------------
# claims_funnel
# ---------------------------------------------------------------------------

class TestClaimsFunnel:
    def _df(self):
        return pd.DataFrame({
            "q_insured_event_12m":   pd.array([True, True, True, False, True], dtype="boolean"),
            "q_claim_submitted":     pd.array([True, True, False, False, None], dtype="boolean"),
            "flag_paid_claimant":    pd.array([True, False, False, False, False], dtype="boolean"),
            "q_payout_cost_coverage": ["Fully covered", None, None, None, None],
        })

    def test_funnel_steps_use_correct_denominators(self):
        result = claims_funnel(self._df())
        assert result["experienced_event"]["n"] == 4
        assert result["experienced_event"]["n_total"] == 5
        assert result["experienced_event"]["not_applicable"] is False
        assert result["filed_claim"]["n"] == 2
        assert result["filed_claim"]["n_total"] == 4         # denom = insured-event base
        assert result["filed_claim"]["base"] == "insured_event_base"
        assert result["claim_paid"]["n"] == 1
        assert result["claim_paid"]["n_total"] == 2           # denom = claimant base
        assert result["claim_paid"]["not_applicable"] is False
        assert result["payout_adequacy"]["n_valid"] == 1
        assert result["payout_adequacy"]["not_applicable"] is False

    def test_missing_columns_degrade_gracefully(self):
        result = claims_funnel(pd.DataFrame({"unrelated": [1, 2, 3]}))
        assert result["experienced_event"]["n"] is None
        assert result["experienced_event"]["not_applicable"] is True
        assert result["filed_claim"]["n"] == 0
        assert result["claim_paid"]["n"] is None
        assert result["claim_paid"]["not_applicable"] is True
        assert result["payout_adequacy"]["distribution"] == []
        assert result["payout_adequacy"]["not_applicable"] is True

    def test_larco_schema_filed_claim_counted_against_full_population(self):
        # LARCO has no q_insured_event_12m gate at all -- filed_claim must be
        # counted directly against every respondent, not a nonexistent event
        # base (which would otherwise silently produce 0/0 despite real
        # claimants existing -- the confirmed production bug).
        df = pd.DataFrame({
            "q_claim_submitted": pd.array([True, True, False, False, False], dtype="boolean"),
        })
        result = claims_funnel(df)
        assert result["experienced_event"]["n"] is None
        assert result["experienced_event"]["not_applicable"] is True
        assert result["filed_claim"]["n"] == 2
        assert result["filed_claim"]["n_total"] == 5          # denom = full population
        assert result["filed_claim"]["base"] == "all_respondents"
        assert result["filed_claim"]["pct_of_event_base"] == pytest.approx(0.4)
        assert result["filed_claim"]["not_applicable"] is False
        # No claim-outcome columns at all in this schema -- not_applicable, not 0.
        assert result["claim_paid"]["n"] is None
        assert result["claim_paid"]["not_applicable"] is True
        assert result["payout_adequacy"]["not_applicable"] is True

    def test_larco_schema_claim_paid_present_without_event_gate(self):
        # Defensive case: a schema with claim-outcome columns but no event
        # gate should still compute claim_paid normally against the claimant
        # base -- claim_paid's logic never depended on the event gate.
        df = pd.DataFrame({
            "q_claim_submitted":     pd.array([True, True, False], dtype="boolean"),
            "flag_paid_claimant":    pd.array([True, False, False], dtype="boolean"),
            "q_payout_cost_coverage": ["Fully covered", None, None],
        })
        result = claims_funnel(df)
        assert result["claim_paid"]["n"] == 1
        assert result["claim_paid"]["n_total"] == 2
        assert result["claim_paid"]["not_applicable"] is False


# ---------------------------------------------------------------------------
# nps_score
# ---------------------------------------------------------------------------

class TestNpsScore:
    def test_promoter_passive_detractor_split_and_value(self):
        # 18 promoters (9/10), 6 passives (7/8), 6 detractors (0-6) — n=30, at threshold
        scores = [9, 10] * 9 + [7, 8] * 3 + [6, 0] * 3
        df = pd.DataFrame({"q_nps_score": scores})
        result = nps_score(df)
        assert result["n_valid"] == 30
        assert result["promoters"]["n"] == 18
        assert result["passives"]["n"] == 6
        assert result["detractors"]["n"] == 6
        # NPS = (promoters - detractors) / n_valid * 100
        assert result["value"] == pytest.approx((18 - 6) / 30 * 100)

    def test_missing_column_returns_zeroed_result(self):
        result = nps_score(pd.DataFrame({"other": [1, 2]}))
        assert result["promoters"] == {"n": 0, "pct": 0.0}
        assert result["value"] is None


# ---------------------------------------------------------------------------
# nps_scorecard_row
# ---------------------------------------------------------------------------

class TestNpsScorecardRow:
    def _df_and_masks(self, scores_a, scores_b):
        scores = scores_a + scores_b
        df = pd.DataFrame({"q_nps_score": scores}, index=range(len(scores)))
        mask_a = pd.Series([True] * len(scores_a) + [False] * len(scores_b), index=df.index)
        mask_b = ~mask_a
        return df, {"group_a": mask_a, "group_b": mask_b}

    def test_shape_matches_scorecard_row_for_generic_plumbing(self):
        # 35 promoters/detractors per side so neither is suppressed (n>=30)
        scores_a = [9, 10] * 20  # all promoters -> NPS = 100
        scores_b = [0, 1] * 20   # all detractors -> NPS = -100
        df, masks = self._df_and_masks(scores_a, scores_b)
        row = nps_scorecard_row(df, masks, "Net Promoter Score", "group_a", "group_b")
        assert row["label"] == "Net Promoter Score"
        assert set(row) == {"label", "group_a", "group_b", "significance"}
        assert row["group_a"]["value"] == pytest.approx(100.0)
        assert row["group_b"]["value"] == pytest.approx(-100.0)
        assert row["significance"]["test"].startswith("Mann-Whitney U")

    def test_large_gap_is_significant(self):
        scores_a = [9, 10] * 20
        scores_b = [0, 1] * 20
        df, masks = self._df_and_masks(scores_a, scores_b)
        row = nps_scorecard_row(df, masks, "NPS", "group_a", "group_b")
        assert row["significance"]["p_value"] is not None
        assert row["significance"]["p_value"] < 0.05
        assert row["significance"]["significant"] is True

    def test_identical_distributions_not_significant(self):
        scores = [5, 6, 7, 8, 9] * 8  # n=40 per side
        df, masks = self._df_and_masks(scores, list(scores))
        row = nps_scorecard_row(df, masks, "NPS", "group_a", "group_b")
        assert row["significance"]["significant"] is False

    def test_suppressed_group_yields_no_p_value(self):
        # group_b has only 5 responses -- below LOW_N_THRESHOLD (30) -> suppressed
        scores_a = [9, 10] * 20
        scores_b = [5, 6, 7, 8, 9]
        df, masks = self._df_and_masks(scores_a, scores_b)
        row = nps_scorecard_row(df, masks, "NPS", "group_a", "group_b")
        assert row["group_b"]["suppressed"] is True
        assert row["significance"]["p_value"] is None
        assert row["significance"]["significant"] is False

    def test_absent_segment_returns_placeholder_not_crash(self):
        scores_a = [9, 10] * 20
        df = pd.DataFrame({"q_nps_score": scores_a})
        row = nps_scorecard_row(df, {"group_a": pd.Series([True] * len(df))}, "NPS", "group_a", "group_b")
        assert row["group_b"]["suppressed"] is True
        assert row["group_b"]["value"] is None
        assert row["significance"]["p_value"] is None


# ---------------------------------------------------------------------------
# significance_test
# ---------------------------------------------------------------------------

class TestSignificanceTest:
    def test_zero_denominator_returns_error_not_crash(self):
        result = significance_test(5, 0, 5, 10)
        assert result["error"] == "zero denominator"
        assert result["z_stat"] is None
        assert result["significant"] is False

    def test_n_greater_than_total_returns_error(self):
        result = significance_test(15, 10, 5, 10)
        assert result["error"] == "n > total"
        assert result["z_stat"] is None

    def test_large_gap_is_significant(self):
        result = significance_test(90, 100, 10, 100)
        assert result["error"] is None
        assert result["gap"] == pytest.approx(0.8)
        assert result["significant"] is True
        assert result["p_value"] < 0.05

    def test_identical_proportions_not_significant(self):
        result = significance_test(50, 100, 50, 100)
        assert result["gap"] == pytest.approx(0.0)
        assert result["z_stat"] == pytest.approx(0.0)
        assert result["significant"] is False


# ---------------------------------------------------------------------------
# spearman_correlation
# ---------------------------------------------------------------------------

class TestSpearmanCorrelation:
    def test_perfect_monotonic_relationship(self):
        x = _series(list(range(35)))
        y = _series(list(range(35)))
        result = spearman_correlation(x, y)
        assert result["value"] == pytest.approx(1.0)
        assert result["significant"] is True

    def test_suppressed_below_low_n_threshold(self):
        x = _series(list(range(LOW_N_THRESHOLD - 1)))
        y = _series(list(range(LOW_N_THRESHOLD - 1)))
        result = spearman_correlation(x, y)
        assert result["suppressed"] is True
        assert result["value"] is None

    def test_misaligned_indices_drop_to_intersection(self):
        x = pd.Series(list(range(40)), index=range(40))
        y = pd.Series(list(range(40)), index=range(10, 50))
        result = spearman_correlation(x, y)
        # only indices 10..39 overlap = 30 valid rows
        assert result["n_valid"] == 30


# ---------------------------------------------------------------------------
# not_applicable — distinct from suppressed: "nobody in this population was
# ever asked" (n_valid == 0 with a non-empty population) vs. "asked, but too
# few answered" (n_valid below LOW_N_THRESHOLD). Both worth_premium and
# renewal_intent hit this in a country-scoped run (see report_spec.yaml's
# population: notes) since each is only asked of a subset of countries.
# ---------------------------------------------------------------------------

class TestNotApplicable:
    def test_all_null_column_with_nonempty_population_is_not_applicable(self):
        # Simulates worth_premium in a Vietnam-only run: the column exists
        # and the population is real, but nobody was ever asked the question.
        s = _series([None] * 50, dtype="float64")
        result = bottom_two_box(s)
        assert result["n_total"] == 50
        assert result["n_valid"] == 0
        assert result["not_applicable"] is True
        assert result["suppressed"] is True  # still true -- 0 < LOW_N_THRESHOLD
        assert result["value"] is None

    def test_truly_empty_population_is_not_marked_not_applicable(self):
        # An empty series (n_total == 0) is a different failure mode entirely
        # (no population at all) -- must not be conflated with "population
        # exists but this question wasn't asked of it."
        result = top_two_box(_series([], dtype="float64"))
        assert result["n_total"] == 0
        assert result["n_valid"] == 0
        assert result["not_applicable"] is False

    def test_normal_answered_metric_is_not_flagged(self):
        s = _series([1, 2, 3, 4] * 20)  # 80 valid responses
        result = bottom_two_box(s)
        assert result["not_applicable"] is False
        assert result["suppressed"] is False

    def test_low_n_but_nonzero_is_suppressed_not_not_applicable(self):
        # A handful of real answers below threshold: suppressed (small
        # sample), but the question clearly WAS asked -- not not_applicable.
        s = _series([1, 2, 3] * 5)  # 15 valid responses, below LOW_N_THRESHOLD
        result = bottom_two_box(s)
        assert result["suppressed"] is True
        assert result["not_applicable"] is False

    def test_spearman_correlation_all_null_pair_is_not_applicable(self):
        x = _series([None] * 40, dtype="float64")
        y = _series([None] * 40, dtype="float64")
        result = spearman_correlation(x, y)
        assert result["n_valid"] == 0
        assert result["not_applicable"] is True

    def test_absent_segment_is_suppressed_but_not_not_applicable(self):
        # A segment missing from segment_masks (e.g. disabled by a country
        # config) is a different reason than "population never asked" --
        # the absent-group fallback must stay not_applicable=False.
        df = pd.DataFrame({"q_nps_score": [9, 8, 5] * 10}, index=range(30))
        segment_masks = {"female": pd.Series(True, index=df.index)}  # "male" absent
        row = nps_scorecard_row(df, segment_masks, "NPS", "female", "male")
        assert row["male"]["not_applicable"] is False
        assert row["male"]["suppressed"] is True

    def test_logistic_regression_result_has_not_applicable_key(self):
        y = _series([0, 1, 1, 0] * 10, dtype="float64")
        X = pd.DataFrame({"x": [0, 1, 0, 1] * 10})
        result = logistic_regression(y, X)
        assert result["not_applicable"] is False

    def test_composite_index_result_has_not_applicable_key(self):
        dims = {"a": {"value": 0.5, "suppressed": False}, "b": {"value": 0.7, "suppressed": False}}
        result = composite_index(dims)
        assert result["not_applicable"] is False


# ---------------------------------------------------------------------------
# disaggregate
# ---------------------------------------------------------------------------

class TestDisaggregate:
    def test_forces_suppression_below_threshold_even_if_stat_fn_did_not(self):
        df = pd.DataFrame({"score": [4] * 50}, index=range(50))
        small_segment_mask = pd.Series([True] * 10 + [False] * 40, index=df.index)
        large_segment_mask = pd.Series([True] * 40 + [False] * 10, index=df.index)

        results = disaggregate(
            df, "score", top_two_box,
            segment_masks={"small": small_segment_mask, "large": large_segment_mask},
        )
        assert results["small"]["suppressed"] is True
        assert results["small"]["value"] is None
        assert results["large"]["suppressed"] is False

    def test_segment_mask_reindexed_to_scope(self):
        df = pd.DataFrame({"score": [4] * 35}, index=range(100, 135))
        mask = pd.Series([True] * 35, index=range(100, 135))
        results = disaggregate(df, "score", top_two_box, segment_masks={"all": mask})
        assert results["all"]["n_valid"] == 35


# ---------------------------------------------------------------------------
# logistic_regression / _safe_exp — quasi-complete separation
#
# A country-scoped run can be small enough (e.g. n=272 for Mexico's 2026
# data) that a rare predictor near-perfectly aligns with the outcome
# (quasi-complete separation). statsmodels' MLE then fails to converge and
# can return a coefficient/std_err pair large enough that coef ± z*std_err
# overflows math.exp()'s ~709 ceiling -- this used to raise OverflowError
# and crash the entire Part 5 section (analysis_engine/sections/part_5.py),
# discarding real, valid data (drivers correlations, caregiver comparison)
# that had nothing to do with the one degenerate regression coefficient.
# ---------------------------------------------------------------------------

class TestSafeExp:
    def test_normal_values_match_math_exp(self):
        assert _safe_exp(1.0) == math.exp(1.0)
        assert _safe_exp(0.0) == math.exp(0.0)

    def test_overflow_returns_inf_instead_of_raising(self):
        with pytest.raises(OverflowError):
            math.exp(1000)
        assert _safe_exp(1000) == math.inf

    def test_large_negative_underflows_to_zero_like_math_exp(self):
        # math.exp() itself never raises on underflow, only overflow -- this
        # just documents that _safe_exp doesn't change that side's behavior.
        assert _safe_exp(-1000) == 0.0


class TestLogisticRegressionSeparation:
    def test_quasi_complete_separation_does_not_raise_overflowerror(self):
        # rare_flag is 1 for only 6 respondents, all of whom have y == 1 --
        # near-perfect (but not exact, avoiding a singular-matrix failure
        # mode) alignment with the outcome, the same shape as the real bug
        # (Mexico 2026's rare 'bundled_service_client' segment flag).
        rng = np.random.default_rng(42)
        n = 200
        y = pd.Series(rng.integers(0, 2, size=n).astype("float64"))
        rare_flag = np.zeros(n)
        ones_idx = np.where(y.values == 1)[0][:6]
        rare_flag[ones_idx] = 1
        X = pd.DataFrame({"rare_flag": rare_flag, "control": rng.normal(size=n)})

        result = logistic_regression(y, X)

        assert result["error"] is None
        assert result["converged"] is False
        rare = result["coefficients"]["rare_flag"]
        # The degenerate coefficient's CI is genuinely unbounded -- inf is
        # the honest answer, not a crash and not a silently wrong number.
        # run_analysis.py's _sanitise() converts inf to None before this
        # ever reaches JSON output (see stats.py's _safe_exp docstring).
        assert rare["ci_upper"] == math.inf
        assert not math.isnan(rare["odds_ratio"])

    def test_well_behaved_fit_has_finite_coefficients(self):
        # Sanity check the fix didn't change normal, converging output.
        rng = np.random.default_rng(7)
        n = 200
        control = rng.normal(size=n)
        y = pd.Series((control + rng.normal(scale=0.5, size=n) > 0).astype("float64"))
        X = pd.DataFrame({"control": control})

        result = logistic_regression(y, X)

        assert result["error"] is None
        for coef in result["coefficients"].values():
            assert math.isfinite(coef["odds_ratio"])
            assert math.isfinite(coef["ci_lower"])
            assert math.isfinite(coef["ci_upper"])


# ---------------------------------------------------------------------------
# composite_index
# ---------------------------------------------------------------------------

class TestCompositeIndex:
    def test_averages_included_dimensions_only(self):
        dims = {
            "a": {"value": 0.8, "suppressed": False},
            "b": {"value": 0.4, "suppressed": False},
            "c": {"value": None, "suppressed": True},
        }
        result = composite_index(dims, min_dimensions=2)
        assert result["value"] == pytest.approx(0.6)
        assert result["dimensions_included"] == ["a", "b"]
        assert result["dimensions_excluded"] == ["c"]
        assert result["suppressed"] is False

    def test_suppressed_when_fewer_than_min_dimensions_available(self):
        dims = {
            "a": {"value": 0.8, "suppressed": False},
            "b": {"value": None, "suppressed": True},
        }
        result = composite_index(dims, min_dimensions=2)
        assert result["suppressed"] is True
        assert result["value"] is None
