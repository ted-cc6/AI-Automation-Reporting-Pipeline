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


LOW_N_THRESHOLD = 30
"""Minimum answered base for a stratum (e.g. a country) to be trusted on its own in a
subgroup comparison. Mirrors graph.nodes._LOW_N_THRESHOLD and, in the Insurance pipeline,
analysis_engine.stats.LOW_N_THRESHOLD -- kept here so direct-standardisation callers reuse
the same cutoff instead of re-inventing one."""


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


def directly_standardised_gap(
    mask: pd.Series,
    group_a: pd.Series,
    group_b: pd.Series,
    stratum: pd.Series,
    stratum_weights: dict,
    min_group_b_n: int = LOW_N_THRESHOLD,
) -> dict:
    """Direct standardisation (the epidemiological kind) of the group_a-minus-group_b gap in
    `mask` to a common `stratum` distribution.

    `stratum` is typically country; `group_b` is the smaller / sparser group (e.g.
    non-caregivers). A stratum enters the standardisation only where `group_b` has at least
    `min_group_b_n` answered rows for this outcome -- strata below that, or with no group_b
    answers at all, are excluded and reported rather than folded in at full population weight
    (a country with three group_b rows all scoring 100% would otherwise swing the result).
    Weights come from `stratum_weights` (e.g. the full sample's per-country row counts),
    renormalised over the included strata.

    Returns a plain dict (the caller wraps it in whatever schema it needs):
      raw_gap            group_a share minus group_b share over every answered row -- reproduces
                         the unstandardised comparison; None if either group has no answers
      standardised_gap   size-weighted mean of the within-stratum gaps, included strata only;
                         None when no stratum clears `min_group_b_n`
      composition_share  (raw_gap - standardised_gap) / raw_gap: the fraction of the observed
                         gap that stratum mix accounts for. >1 or negative sign when
                         standardisation reverses the gap. None when raw_gap is ~0 or
                         standardised_gap is None
      included           {stratum: group_b answered n} for the strata used
      excluded           {stratum: group_b answered n} for strata dropped (thin or absent)
      contributions      {stratum: additive contribution to raw_gap - standardised_gap} over
                         the included strata, largest absolute contribution first
      group_a_n, group_b_n   total answered rows per group
    """
    a_all = group_a.fillna(False).astype(bool)
    b_all = group_b.fillna(False).astype(bool)
    answered = mask.notna()
    a_ans = a_all & answered
    b_ans = b_all & answered
    m01 = mask.where(answered).astype(float)  # 1.0 / 0.0 / NaN

    raw_gap = None
    if a_ans.any() and b_ans.any():
        raw_gap = float(m01[a_ans].mean()) - float(m01[b_ans].mean())

    per: dict = {}  # stratum -> (p_a, n_a, p_b, n_b)
    for value in stratum.dropna().unique():
        in_s = stratum == value
        n_a = int((a_ans & in_s).sum())
        n_b = int((b_ans & in_s).sum())
        p_a = float(m01[a_ans & in_s].mean()) if n_a else None
        p_b = float(m01[b_ans & in_s].mean()) if n_b else None
        per[str(value)] = (p_a, n_a, p_b, n_b)

    included = {
        s: v[3]
        for s, v in per.items()
        if v[3] >= min_group_b_n and v[1] > 0 and v[0] is not None and v[2] is not None
    }
    excluded = {s: v[3] for s, v in per.items() if s not in included}

    out = {
        "raw_gap": raw_gap,
        "standardised_gap": None,
        "composition_share": None,
        "included": dict(sorted(included.items())),
        "excluded": dict(sorted(excluded.items())),
        "contributions": {},
        "group_a_n": int(a_ans.sum()),
        "group_b_n": int(b_ans.sum()),
    }

    cs = list(included)
    w_tot = sum(stratum_weights.get(s, 0) for s in cs)
    n_a_tot = sum(per[s][1] for s in cs)
    n_b_tot = sum(per[s][3] for s in cs)
    if not cs or w_tot <= 0 or n_a_tot == 0 or n_b_tot == 0:
        return out

    w = {s: stratum_weights.get(s, 0) / w_tot for s in cs}
    alpha = {s: per[s][1] / n_a_tot for s in cs}
    beta = {s: per[s][3] / n_b_tot for s in cs}
    standardised = sum(w[s] * (per[s][0] - per[s][2]) for s in cs)
    contributions = {s: (alpha[s] - w[s]) * per[s][0] - (beta[s] - w[s]) * per[s][2] for s in cs}

    out["standardised_gap"] = standardised
    if raw_gap is not None and abs(raw_gap) > 0.005:
        out["composition_share"] = (raw_gap - standardised) / raw_gap
    out["contributions"] = dict(sorted(contributions.items(), key=lambda kv: abs(kv[1]), reverse=True))
    return out


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
