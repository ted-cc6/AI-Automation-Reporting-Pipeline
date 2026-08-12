import math

import numpy as np
import pandas as pd
import pytest

from metrics_engine.engine import (
    categorical_distribution,
    crosstab_by_segment,
    gap_comparison,
    mean_value,
    metric_result,
    multiselect_distribution,
    nps,
    nps_by_segment,
    ranked_options,
    share,
    top_box,
    two_proportion_ztest,
)
from schemas.common import SegmentAxis


def test_share_basic():
    mask = pd.Series([True, False, True, False, np.nan], dtype=object)
    result = share(mask)
    assert result.n == 4
    assert result.share == pytest.approx(0.5)


def test_share_empty_base_returns_none_share():
    mask = pd.Series([np.nan, np.nan], dtype=object)
    result = share(mask)
    assert result.n == 0
    assert result.share is None


def test_share_respects_base_filter():
    mask = pd.Series([True, True, False, False])
    base = pd.Series([True, False, True, False])
    # only rows 0 and 2 count: True, False -> share 0.5
    result = share(mask, base=base)
    assert result.n == 2
    assert result.share == pytest.approx(0.5)


def test_top_box_nulls_non_answers():
    series = pd.Series(["a", "b", "c", "a", None])
    result = top_box(series, top_values={"a", "b"})
    assert result.n == 4  # the None row is excluded from the base entirely
    assert result.share == pytest.approx(0.75)


def test_mean_value():
    series = pd.Series([10, 20, 30, np.nan])
    result = mean_value(series)
    assert result.n == 3
    assert result.mean == pytest.approx(20.0)


def test_crosstab_by_segment():
    mask = pd.Series([True, True, False, False, True])
    segment = pd.Series(["Female", "Female", "Male", "Male", "Male"])
    results = {r.value_label: r for r in crosstab_by_segment(mask, segment, SegmentAxis.GENDER)}
    assert results["Female"].n == 2
    assert results["Female"].share == pytest.approx(1.0)
    assert results["Male"].n == 3
    assert results["Male"].share == pytest.approx(1 / 3)


def test_crosstab_by_segment_ignores_null_segment_rows():
    mask = pd.Series([True, False, True])
    segment = pd.Series(["Female", None, "Male"])
    results = crosstab_by_segment(mask, segment, SegmentAxis.GENDER)
    labels = {r.value_label for r in results}
    assert labels == {"Female", "Male"}


def test_metric_result_combines_overall_and_segments():
    mask = pd.Series([True, True, False, False])
    segments = {SegmentAxis.GENDER: pd.Series(["Female", "Male", "Female", "Male"])}
    result = metric_result("first_time_access", "First time access", mask, segments=segments)
    assert result.overall.share == pytest.approx(0.5)
    assert result.overall.n == 4
    by_gender = {s.value_label: s for s in result.by_segment}
    assert by_gender["Female"].share == pytest.approx(0.5)
    assert by_gender["Male"].share == pytest.approx(0.5)
    assert result.benchmark_comparable_value is None  # not requested, stays unset


def test_metric_result_benchmark_comparable_mask_is_a_separate_share():
    # e.g. mask = top-2-box ("very much" + "slightly"), benchmark_comparable_mask = "very much" only
    mask = pd.Series([True, True, True, False])  # 3/4
    very_much_mask = pd.Series([True, False, False, False])  # 1/4
    result = metric_result("business_income_change", "Business income improved", mask, benchmark_comparable_mask=very_much_mask)
    assert result.overall.share == pytest.approx(0.75)
    assert result.benchmark_comparable_value is not None
    assert result.benchmark_comparable_value.share == pytest.approx(0.25)


def test_two_proportion_ztest_identical_shares_is_not_significant():
    result = two_proportion_ztest(10, 20, 10, 20)
    assert result.p_value == pytest.approx(1.0)
    assert result.significant is False


def test_two_proportion_ztest_known_value():
    # p1=1.0 (n=1), p2=0.0 (n=1): p_pool=0.5, se=sqrt(0.5), z=1/se
    result = two_proportion_ztest(1, 1, 0, 1)
    se = math.sqrt(0.5 * 0.5 * 2)
    z = 1.0 / se
    expected_p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    assert result.p_value == pytest.approx(expected_p)


def test_two_proportion_ztest_requires_nonzero_n():
    with pytest.raises(ValueError):
        two_proportion_ztest(0, 0, 1, 5)


def test_gap_comparison():
    mask = pd.Series([True, True, False, False, True, False])
    group_a = pd.Series([True, True, True, False, False, False])  # first 3 rows
    group_b = pd.Series([False, False, False, True, True, True])  # last 3 rows
    result = gap_comparison(mask, group_a, "Caregiver", group_b, "Non-caregiver")
    assert result.group_a_n == 3
    assert result.group_a_share == pytest.approx(2 / 3)
    assert result.group_b_n == 3
    assert result.group_b_share == pytest.approx(1 / 3)
    # gap is computed from shares rounded to the same precision they're displayed at (3
    # decimal places = 1 decimal place of percent), not the raw fractions, so the printed
    # gap always equals the difference of the printed percentages -- see gap_comparison()'s
    # comment for the real report discrepancy (8.4pp shown instead of 8.3pp) this fixes.
    assert result.gap == pytest.approx(round(2 / 3, 3) - round(1 / 3, 3))
    assert result.significance is not None


def test_gap_comparison_matches_the_displayed_percentages():
    # Regression test for a real incident: a report showed 42.2% and 50.5% (rounded to 1
    # decimal place) with a gap printed as 8.4pp, even though 50.5 - 42.2 == 8.3. These exact
    # group sizes (27/64 and 46/91) reproduce that: each share individually rounds to 42.2%/
    # 50.5%, but their full-precision difference rounds to 8.4pp -- only rounding each share
    # first, THEN subtracting, gives the 8.3pp a reader checking the two printed numbers by
    # hand would expect.
    group_a = pd.Series([True] * 64)
    mask_a = pd.Series([True] * 27 + [False] * 37)
    group_b = pd.Series([True] * 91)
    mask_b = pd.Series([True] * 46 + [False] * 45)

    result_a = gap_comparison(mask_a, group_a, "A", pd.Series([False] * 64), "unused", run_significance=False)
    result_b = gap_comparison(mask_b, group_b, "B", pd.Series([False] * 91), "unused", run_significance=False)
    assert f"{result_a.group_a_share:.1%}" == "42.2%"
    assert f"{result_b.group_a_share:.1%}" == "50.5%"

    combined_gap = gap_comparison(
        pd.concat([mask_a, mask_b], ignore_index=True),
        pd.concat([pd.Series([True] * 64), pd.Series([False] * 91)], ignore_index=True),
        "A",
        pd.concat([pd.Series([False] * 64), pd.Series([True] * 91)], ignore_index=True),
        "B",
        run_significance=False,
    )
    assert f"{combined_gap.gap:+.1%}" == "-8.3%"


def test_nps_known_value():
    scores = pd.Series([10, 10, 10, 9, 8, 3, 0])
    result = nps(scores)
    assert result.n == 7
    assert result.promoter_share == pytest.approx(4 / 7)
    assert result.detractor_share == pytest.approx(2 / 7)
    assert result.passive_share == pytest.approx(1 / 7)
    assert result.score == pytest.approx((4 / 7 - 2 / 7) * 100)


def test_nps_ignores_missing_scores():
    scores = pd.Series([9, 9, np.nan])
    result = nps(scores)
    assert result.n == 2
    assert result.promoter_share == pytest.approx(1.0)


def test_nps_by_segment_uses_mean_not_share():
    scores = pd.Series([10, 10, 0, 9, 3])
    segment = pd.Series(["Female", "Female", "Female", "Male", "Male"])
    results = nps_by_segment(scores, segment, SegmentAxis.GENDER)
    by_label = {r.value_label: r for r in results}
    # Female: promoters=2 (10,10), detractors=1 (0), n=3 -> (2/3 - 1/3)*100 = 33.33
    assert by_label["Female"].mean == pytest.approx(33.33, abs=0.01)
    assert by_label["Female"].share is None
    assert by_label["Female"].n == 3
    # Male: promoters=1 (9), detractors=1 (3), n=2 -> 0.0
    assert by_label["Male"].mean == pytest.approx(0.0)
    assert by_label["Male"].n == 2


def test_nps_by_segment_ignores_missing_scores_and_segments():
    scores = pd.Series([9, np.nan, 5])
    segment = pd.Series(["A", "A", None])
    results = nps_by_segment(scores, segment, SegmentAxis.GENDER)
    assert len(results) == 1
    assert results[0].value_label == "A"
    assert results[0].n == 1


def test_nps_by_segment_empty_when_nothing_eligible():
    scores = pd.Series([np.nan, np.nan])
    segment = pd.Series(["A", "B"])
    assert nps_by_segment(scores, segment, SegmentAxis.GENDER) == []


def test_categorical_distribution_covers_every_distinct_value():
    series = pd.Series(["Female", "Female", "Male", None])
    result = categorical_distribution(series)
    assert result.base_n == 3  # the None is excluded from base, not counted as a category
    by_label = {o.label: o for o in result.options}
    assert by_label["Female"].share == pytest.approx(2 / 3)
    assert by_label["Female"].n == 2
    assert by_label["Male"].share == pytest.approx(1 / 3)


def test_categorical_distribution_accepts_an_explicit_base():
    series = pd.Series(["a", "b", "a", "a"])
    base = pd.Series([True, True, True, False])  # excludes the last row
    result = categorical_distribution(series, base=base)
    assert result.base_n == 3
    by_label = {o.label: o for o in result.options}
    assert by_label["a"].n == 2
    assert by_label["b"].n == 1


def test_multiselect_distribution_counts_a_label_regardless_of_which_slot_it_lands_in():
    # Row 0 picked "X" first (slot 1); row 1 picked "X" second (slot 2) -- both must count
    # towards "X", which categorical_distribution's single-column check would miss for row 1.
    slot1 = pd.Series(["X", "Y", None])
    slot2 = pd.Series([None, "X", None])
    result = multiselect_distribution([slot1, slot2])
    by_label = {o.label: o for o in result.options}
    assert by_label["X"].n == 2
    assert by_label["Y"].n == 1
    assert result.base_n == 3


def test_multiselect_distribution_excludes_sentinel_labels():
    slot1 = pd.Series(["a. None of these", "b. Flooding", "b. Flooding"])
    result = multiselect_distribution([slot1], exclude_labels=frozenset({"a. None of these"}))
    labels = {o.label for o in result.options}
    assert labels == {"b. Flooding"}


def test_multiselect_distribution_accepts_an_explicit_base():
    slot1 = pd.Series(["X", "X", "X"])
    base = pd.Series([True, True, False])
    result = multiselect_distribution([slot1], base=base)
    assert result.base_n == 2
    assert result.options[0].n == 2


def test_multiselect_distribution_blank_slots_never_count_as_a_label():
    slot1 = pd.Series([None, None, None])
    slot2 = pd.Series(["X", None, None])
    result = multiselect_distribution([slot1, slot2])
    assert len(result.options) == 1
    assert result.options[0].label == "X"
    assert result.options[0].n == 1


def test_ranked_options_sorted_descending():
    base = pd.Series([True, True, True, True])
    option_masks = {
        "A": pd.Series([True, True, True, False]),  # 3/4
        "B": pd.Series([True, False, False, False]),  # 1/4
    }
    result = ranked_options(option_masks, base=base)
    assert result.base_n == 4
    assert [o.label for o in result.options] == ["A", "B"]
    assert result.options[0].share == pytest.approx(0.75)
    assert result.options[1].share == pytest.approx(0.25)
