"""Pure statistical primitives used across every quantitative report section.

Every function here takes plain pandas Series (boolean masks or categorical
segment columns) and returns one of the shared Pydantic schema objects.
Deriving a boolean mask from a raw survey column (e.g. "which values count as
'top box'?") is deliberately kept out of this module -- see segments.py and
the future section-config layer for that. This module only knows how to
turn masks into numbers.
"""

from __future__ import annotations

import math
from typing import Optional

import pandas as pd

from schemas.client_satisfaction import NPSResult
from schemas.common import (
    BenchmarkComparison,
    GapComparison,
    MetricResult,
    RankedOption,
    RankedOptions,
    SegmentAxis,
    SegmentedValue,
    SignificanceResult,
)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def share(
    mask: pd.Series,
    base: Optional[pd.Series] = None,
    axis: SegmentAxis = SegmentAxis.OVERALL,
    value_label: str = "Overall",
) -> SegmentedValue:
    """Proportion of `base` (default: everyone `mask` has a non-null answer for) that is True in `mask`."""
    if base is None:
        base = pd.Series(True, index=mask.index)
    eligible = base.fillna(False) & mask.notna()
    n = int(eligible.sum())
    if n == 0:
        return SegmentedValue(axis=axis, value_label=value_label, share=None, n=0)
    share_val = float(mask[eligible].astype(bool).sum()) / n
    return SegmentedValue(axis=axis, value_label=value_label, share=share_val, n=n)


def mean_value(
    series: pd.Series,
    base: Optional[pd.Series] = None,
    axis: SegmentAxis = SegmentAxis.OVERALL,
    value_label: str = "Overall",
) -> SegmentedValue:
    """Mean of `series` over `base` (default: everyone with a non-null value)."""
    if base is None:
        base = pd.Series(True, index=series.index)
    eligible = base.fillna(False) & series.notna()
    n = int(eligible.sum())
    if n == 0:
        return SegmentedValue(axis=axis, value_label=value_label, mean=None, n=0)
    return SegmentedValue(axis=axis, value_label=value_label, mean=float(series[eligible].mean()), n=n)


def top_box_mask(series: pd.Series, top_values: set) -> pd.Series:
    """The boolean mask a top-box metric is built from: True/False for answered rows, null for blanks.

    Exposed separately from top_box() so callers building a full MetricResult (mask +
    every segment cut via metric_result()) can reuse the exact same null-handling
    instead of re-deriving it.
    """
    mask = series.isin(top_values)
    return mask.where(series.notna())  # keep non-answers as null, not False


def top_box(
    series: pd.Series,
    top_values: set,
    base: Optional[pd.Series] = None,
    axis: SegmentAxis = SegmentAxis.OVERALL,
    value_label: str = "Overall",
) -> SegmentedValue:
    """Share of `base` whose answer in `series` falls in `top_values` (e.g. the top two boxes of a scale)."""
    mask = top_box_mask(series, top_values)
    return share(mask, base=base, axis=axis, value_label=value_label)


def crosstab_by_segment(
    mask: pd.Series,
    segment: pd.Series,
    axis: SegmentAxis,
    base: Optional[pd.Series] = None,
) -> list[SegmentedValue]:
    """One SegmentedValue per distinct non-null value of `segment`, restricted to `base`."""
    if base is None:
        base = pd.Series(True, index=mask.index)
    eligible = base.fillna(False) & segment.notna() & mask.notna()
    results: list[SegmentedValue] = []
    if not eligible.any():
        return results
    for value_label, idx in mask[eligible].groupby(segment[eligible]).groups.items():
        sub_mask = mask.loc[idx].astype(bool)
        n = len(sub_mask)
        share_val = float(sub_mask.sum()) / n if n else None
        results.append(SegmentedValue(axis=axis, value_label=str(value_label), share=share_val, n=n))
    return results


def metric_result(
    metric_id: str,
    label: str,
    mask: pd.Series,
    base: Optional[pd.Series] = None,
    segments: Optional[dict[SegmentAxis, pd.Series]] = None,
    benchmark: Optional[BenchmarkComparison] = None,
    benchmark_comparable_mask: Optional[pd.Series] = None,
    notes: Optional[str] = None,
) -> MetricResult:
    """Overall share plus every requested segment cut, packaged as one MetricResult.

    `benchmark_comparable_mask`: pass this when `benchmark` is on a different box definition
    than `mask` (e.g. mask is top-2-box "very much + slightly improved" for the report's own
    headline figure, but the MFI Index benchmark is scored on "very much" alone) -- its overall
    share becomes MetricResult.benchmark_comparable_value, the number that's actually
    apples-to-apples with benchmark.external_mfi_index.
    """
    overall = share(mask, base=base, axis=SegmentAxis.OVERALL, value_label="Overall")
    by_segment: list[SegmentedValue] = []
    if segments:
        for axis, seg_series in segments.items():
            by_segment.extend(crosstab_by_segment(mask, seg_series, axis, base=base))
    benchmark_comparable_value = None
    if benchmark_comparable_mask is not None:
        benchmark_comparable_value = share(benchmark_comparable_mask, base=base, axis=SegmentAxis.OVERALL, value_label="Overall")
    return MetricResult(
        metric_id=metric_id,
        label=label,
        overall=overall,
        by_segment=by_segment,
        benchmark=benchmark,
        benchmark_comparable_value=benchmark_comparable_value,
        notes=notes,
    )


def two_proportion_ztest(x1: int, n1: int, x2: int, n2: int, alpha: float = 0.05) -> SignificanceResult:
    """Two-tailed, large-sample two-proportion z-test. No scipy dependency."""
    if n1 <= 0 or n2 <= 0:
        raise ValueError("both groups need n > 0")
    p1, p2 = x1 / n1, x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1 / n1 + 1 / n2))
    z = 0.0 if se == 0 else (p1 - p2) / se
    p_value = 2 * (1 - _norm_cdf(abs(z)))
    return SignificanceResult(method="two-proportion z-test", p_value=p_value, significant=p_value < alpha, alpha=alpha)


def gap_comparison(
    mask: pd.Series,
    group_a: pd.Series,
    label_a: str,
    group_b: pd.Series,
    label_b: str,
    base: Optional[pd.Series] = None,
    run_significance: bool = True,
) -> GapComparison:
    """Share of `mask` within group A vs group B, with an optional significance test on the gap."""
    base_a = group_a.fillna(False) if base is None else base.fillna(False) & group_a.fillna(False)
    base_b = group_b.fillna(False) if base is None else base.fillna(False) & group_b.fillna(False)
    sv_a = share(mask, base=base_a)
    sv_b = share(mask, base=base_b)

    sig = None
    if run_significance and sv_a.n > 0 and sv_b.n > 0 and sv_a.share is not None and sv_b.share is not None:
        x1 = round(sv_a.share * sv_a.n)
        x2 = round(sv_b.share * sv_b.n)
        sig = two_proportion_ztest(x1, sv_a.n, x2, sv_b.n)

    gap = None
    if sv_a.share is not None and sv_b.share is not None:
        # Round each share to the same precision it's DISPLAYED at (1 decimal place of percent
        # = 3 decimal places of share) before subtracting, so the printed gap always equals the
        # difference of the two printed percentages. Subtracting full-precision shares let the
        # two independent roundings diverge by 0.1pp in real report output (e.g. 42.2% vs 50.5%
        # displayed, but the full-precision gap printed as 8.4pp instead of 8.3pp).
        gap = round(sv_a.share, 3) - round(sv_b.share, 3)

    return GapComparison(
        group_a_label=label_a,
        group_a_share=sv_a.share,
        group_a_n=sv_a.n,
        group_b_label=label_b,
        group_b_share=sv_b.share,
        group_b_n=sv_b.n,
        gap=gap,
        significance=sig,
    )


def nps(scores: pd.Series, base: Optional[pd.Series] = None) -> NPSResult:
    """Standard NPS: promoters (9-10) minus detractors (0-6), as a share of `base`."""
    if base is None:
        base = pd.Series(True, index=scores.index)
    eligible = base.fillna(False) & scores.notna()
    s = scores[eligible].astype(int)
    n = len(s)
    if n == 0:
        return NPSResult(score=0.0, promoter_share=0.0, passive_share=0.0, detractor_share=0.0, n=0)
    promoters = int((s >= 9).sum())
    detractors = int((s <= 6).sum())
    passives = n - promoters - detractors
    promoter_share = promoters / n
    detractor_share = detractors / n
    passive_share = passives / n
    score = (promoter_share - detractor_share) * 100
    return NPSResult(
        score=score, promoter_share=promoter_share, passive_share=passive_share, detractor_share=detractor_share, n=n
    )


def nps_by_segment(scores: pd.Series, segment: pd.Series, axis: SegmentAxis, base: Optional[pd.Series] = None) -> list:
    """One SegmentedValue (NPS score in `.mean`, never `.share` -- NPS runs -100..100, outside
    SegmentedValue.share's 0-1 constraint) per distinct non-null value of `segment`. Mirrors
    crosstab_by_segment's shape but reuses nps() itself per group rather than re-deriving the
    promoter/detractor math.
    """
    if base is None:
        base = pd.Series(True, index=scores.index)
    eligible = base.fillna(False) & segment.notna() & scores.notna()
    results: list = []
    if not eligible.any():
        return results
    for value_label, idx in scores[eligible].groupby(segment[eligible]).groups.items():
        sub_result = nps(scores.loc[idx])
        results.append(SegmentedValue(axis=axis, value_label=str(value_label), mean=sub_result.score, n=sub_result.n))
    return results


def categorical_distribution(series: pd.Series, base: Optional[pd.Series] = None) -> RankedOptions:
    """Share of each distinct value in a single-select categorical column, e.g. gender split
    or education level -- the single-select counterpart to ranked_options()'s multi-select
    "select all that apply" case. Reuses the exact same share/RankedOptions plumbing: a
    single-select "share per category" is the same computation as a multi-select "share who
    ticked each option," just with option_masks derived from one column's own distinct values
    instead of K separate 0/1 columns.
    """
    if base is None:
        base = series.notna()
    option_masks = {str(v): (series == v) for v in series.dropna().unique()}
    return ranked_options(option_masks, base=base)


def multiselect_distribution(
    slot_columns: list, base: Optional[pd.Series] = None, exclude_labels: frozenset = frozenset()
) -> RankedOptions:
    """RankedOptions for a "select all that apply" question stored as K variable-slot columns
    (e.g. RESILIENCE03a_resp_1_en..resp_9_en), where a row's first-selected option lands in
    slot 1, second in slot 2, etc. -- NOT one fixed column per option. That rules out reusing
    categorical_distribution() directly (its `series == v` only checks one column). One mask
    per distinct label is built by OR-ing "this slot equals that label" across every slot, then
    handed to ranked_options() exactly as any other option_masks dict would be.

    `slot_columns` must already be through clean_blank_strings() -- blanks as real None, not ""
    -- since blank slots must never be treated as a selected label.
    `exclude_labels`: sentinel "none of these" / "not applicable" style options that shouldn't
    appear in a ranked list of real selections (verify these against the real data's own values
    -- don't guess the exact label text).
    """
    if base is None:
        base = pd.Series(True, index=slot_columns[0].index)
    labels = set()
    for col in slot_columns:
        labels.update(v for v in col.dropna().unique() if v not in exclude_labels)
    option_masks = {}
    for label in labels:
        mask = pd.Series(False, index=slot_columns[0].index)
        for col in slot_columns:
            mask = mask | (col == label)
        option_masks[str(label)] = mask
    return ranked_options(option_masks, base=base)


def ranked_options(option_masks: dict[str, pd.Series], base: pd.Series) -> RankedOptions:
    """Ranked multi-select summary: one option per key in `option_masks`, sorted by share descending.

    `base` must be supplied explicitly -- it defines who was eligible to select
    these options at all (there's no generic way to infer that from the masks
    alone for a "select all that apply" question).
    """
    base = base.fillna(False)
    base_n = int(base.sum())
    opts: list[RankedOption] = []
    for label, mask in option_masks.items():
        m = mask.fillna(False) & base
        n = int(m.sum())
        opts.append(RankedOption(label=label, share=(n / base_n if base_n else 0.0), n=n))
    opts.sort(key=lambda o: o.share, reverse=True)
    return RankedOptions(base_n=base_n, options=opts)
