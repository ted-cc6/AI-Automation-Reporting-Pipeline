"""CC-094: year-over-year changes, computed in code, with significance and a country-mix check.

Every figure the writer will later say about change comes from here (CC-092). Both waves are
first cut to the comparison countries from the wave manifest, so a country present in one wave
only can't pass for a change. Metric definitions are reused, never restated: every MetricConfig
in the four config-driven sections, plus the gender scorecard's other headline rows (child
wellbeing, cutting food, savings, shock severity, promoters), plus the NPS score.

Significance (agreed 2026-11-20): two-sided tests at 95% for the portfolio and gender changes,
99% for country and loan-cycle changes, where hundreds of small tests would otherwise throw up
chance "changes". No minimum size on top of the test.

Country-mix check: the portfolio change is also directly standardised to a common country mix
(the CC-028 method). `mix_flag` marks a significant raw change that standardisation erases,
reverses, or halves: it may reflect which countries were surveyed rather than a change.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Optional

import pandas as pd

from metrics_engine.engine import _norm_cdf, directly_standardised_gap, top_box_mask, two_proportion_ztest
from metrics_engine.segments import clean_blank_strings, country, gender, loan_cycle
from section_configs.registry import SECTION_CONFIGS
from yoy.waves import COUNTRY_COL

PORTFOLIO_ALPHA = 0.05
SUBGROUP_ALPHA = 0.01
MIN_CELL_N = 30  # same floor as LOW_N_THRESHOLD elsewhere: below it a cell's change isn't tested
NPS_COL = "Client Satisfaction/CLIENTSAT01_resp_en"

MaskFn = Callable[[pd.DataFrame], pd.Series]


@dataclass(frozen=True)
class MetricSpec:
    metric_id: str
    label: str
    section: str
    mask_fn: MaskFn
    base_fn: Optional[MaskFn] = None
    headline: bool = False
    lower_is_better: bool = False


@dataclass
class Change:
    value_2025: Optional[float]
    n_2025: int
    value_2026: Optional[float]
    n_2026: int
    change_pts: Optional[float] = None
    p_value: Optional[float] = None
    significant: bool = False
    alpha: float = PORTFOLIO_ALPHA
    tested: bool = False
    extra: dict = field(default_factory=dict)

    def as_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k != "extra"}
        d.update(self.extra)
        return d


# --- metric inventory --------------------------------------------------------------------------

# Config metrics that are also gender-scorecard rows: the YoY table's headline set.
_HEADLINE_CONFIG_IDS = {
    "first_time_access", "alternative_lender_hard_to_find", "business_income_change", "quality_of_life_change",
    "financial_worry_decreased", "loan_terms_clear", "no_unfair_treatment", "loan_purpose_achieved_fully",
    "household_influence_improved", "community_respect_improved",
}
# Scorecard rows defined outside the section configs, by their scorecard label.
_EXTRA_SCORECARD_ROWS = {
    "Improved child wellbeing": ("improved_child_wellbeing", "child_wellbeing", False),
    "Cut food to repay (lower is better)": ("cut_food_to_repay", "client_protection", True),
    "Savings rose": ("savings_increased", "resilience", False),
    "VisionFund reduced shock severity": ("vf_reduced_shock_severity", "resilience", False),
    "Promoter on NPS": ("nps_promoter", "client_satisfaction", False),
}


def _config_mask(mc) -> MaskFn:
    return lambda df: top_box_mask(clean_blank_strings(df[mc.source_column]), set(mc.top_box_values))


def _config_base(mc) -> Optional[MaskFn]:
    if not mc.base_column:
        return None
    return lambda df: clean_blank_strings(df[mc.base_column]).isin(mc.base_values)


def metric_specs() -> list[MetricSpec]:
    from synthesis.build_gender_scorecard import ROWS  # the verified headline row definitions

    specs = [
        MetricSpec(mc.metric_id, mc.label, section_id, _config_mask(mc), _config_base(mc), mc.metric_id in _HEADLINE_CONFIG_IDS)
        for section_id, cfg in SECTION_CONFIGS.items()
        for mc in cfg.metrics
    ]
    for label, mask_fn, base_fn in ROWS:
        if label in _EXTRA_SCORECARD_ROWS:
            metric_id, section, lower = _EXTRA_SCORECARD_ROWS[label]
            specs.append(MetricSpec(metric_id, label, section, mask_fn, base_fn, True, lower))
    return specs


# --- tests -------------------------------------------------------------------------------------


def _answered(spec: MetricSpec, df: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """(mask, eligible): eligible = in the base and answered, as engine.share() counts it."""
    mask = spec.mask_fn(df)
    base = spec.base_fn(df).fillna(False) if spec.base_fn is not None else pd.Series(True, index=df.index)
    return mask, base.astype(bool) & mask.notna()


def share_change(mask_a, elig_a, mask_b, elig_b, alpha: float = PORTFOLIO_ALPHA, min_n: int = 1) -> Change:
    """2025 (a) to 2026 (b), in percentage points. Untested when either side is below min_n."""
    n_a, n_b = int(elig_a.sum()), int(elig_b.sum())
    x_a = int(mask_a[elig_a].astype(bool).sum()) if n_a else 0
    x_b = int(mask_b[elig_b].astype(bool).sum()) if n_b else 0
    out = Change(x_a / n_a if n_a else None, n_a, x_b / n_b if n_b else None, n_b, alpha=alpha)
    if n_a and n_b:
        out.change_pts = (out.value_2026 - out.value_2025) * 100
    if n_a >= min_n and n_b >= min_n:
        sig = two_proportion_ztest(x_b, n_b, x_a, n_a, alpha=alpha)
        out.p_value, out.significant, out.tested = sig.p_value, sig.significant, True
    return out


def nps_change(scores_a: pd.Series, scores_b: pd.Series, alpha: float = PORTFOLIO_ALPHA, min_n: int = 1) -> Change:
    """NPS in points (-100..100). Each answer is +1 (9-10), 0 (7-8) or -1 (0-6); the score is
    100 x their mean, so its variance is (p_promoter + p_detractor - nps^2) / n."""

    def parts(s):
        s = pd.to_numeric(s, errors="coerce").dropna()
        n = len(s)
        if not n:
            return None, 0, None
        p, d = (s >= 9).sum() / n, (s <= 6).sum() / n
        return (p - d) * 100, n, (p + d - (p - d) ** 2) / n

    a, n_a, var_a = parts(scores_a)
    b, n_b, var_b = parts(scores_b)
    out = Change(a, n_a, b, n_b, alpha=alpha)
    if n_a and n_b:
        out.change_pts = b - a
    if n_a >= min_n and n_b >= min_n:
        se = 100 * math.sqrt(var_a + var_b)
        z = 0.0 if se == 0 else out.change_pts / se
        out.p_value = 2 * (1 - _norm_cdf(abs(z)))
        out.significant, out.tested = out.p_value < alpha, True
    return out


# --- the run -----------------------------------------------------------------------------------


def _in_set(df: pd.DataFrame, countries: list[str]) -> pd.DataFrame:
    return df[df[COUNTRY_COL].astype(str).str.strip().isin(countries)]


def _mix_check(spec: MetricSpec, df_a: pd.DataFrame, df_b: pd.DataFrame, raw: Change) -> dict:
    both = pd.concat([df_a, df_b], ignore_index=True)
    is_b = pd.Series([False] * len(df_a) + [True] * len(df_b), index=both.index)
    mask, elig = _answered(spec, both)
    strata = country(both)
    weights = strata[elig].value_counts().to_dict()
    std = directly_standardised_gap(mask.where(elig), is_b, ~is_b, strata, weights, min_group_b_n=MIN_CELL_N)
    std_pts = std["standardised_gap"] * 100 if std["standardised_gap"] is not None else None
    flag = bool(
        raw.significant
        and (std_pts is None or std_pts * raw.change_pts <= 0 or abs(std_pts) < 0.5 * abs(raw.change_pts))
    )
    return {"standardised_change_pts": std_pts, "mix_flag": flag, "mix_excluded_countries": sorted(std["excluded"])}


def _segment_changes(spec, df_a, df_b, segment_fn, alpha) -> dict:
    mask_a, elig_a = _answered(spec, df_a)
    mask_b, elig_b = _answered(spec, df_b)
    seg_a, seg_b = segment_fn(df_a), segment_fn(df_b)
    out = {}
    for value in sorted(set(seg_a.dropna()) | set(seg_b.dropna())):
        c = share_change(mask_a, elig_a & (seg_a == value), mask_b, elig_b & (seg_b == value), alpha, MIN_CELL_N)
        out[str(value)] = c.as_dict()
    return out


def compute_deltas(df_2025: pd.DataFrame, df_2026: pd.DataFrame, comparison_countries: list[str]) -> dict:
    a, b = _in_set(df_2025, comparison_countries), _in_set(df_2026, comparison_countries)
    metrics = []
    for spec in metric_specs():
        mask_a, elig_a = _answered(spec, a)
        mask_b, elig_b = _answered(spec, b)
        portfolio = share_change(mask_a, elig_a, mask_b, elig_b, PORTFOLIO_ALPHA)
        portfolio.extra = _mix_check(spec, a, b, portfolio)
        metrics.append(
            {
                "metric_id": spec.metric_id,
                "label": spec.label,
                "section": spec.section,
                "headline": spec.headline,
                "lower_is_better": spec.lower_is_better,
                "portfolio": portfolio.as_dict(),
                "by_gender": _segment_changes(spec, a, b, gender, PORTFOLIO_ALPHA),
                "by_loan_cycle": _segment_changes(spec, a, b, loan_cycle, SUBGROUP_ALPHA),
                "by_country": _segment_changes(spec, a, b, country, SUBGROUP_ALPHA),
            }
        )
    nps = {
        "portfolio": nps_change(a[NPS_COL], b[NPS_COL], PORTFOLIO_ALPHA).as_dict(),
        "by_country": {
            c: nps_change(a.loc[country(a) == c, NPS_COL], b.loc[country(b) == c, NPS_COL], SUBGROUP_ALPHA, MIN_CELL_N).as_dict()
            for c in comparison_countries
        },
    }
    return {
        "comparison_countries": comparison_countries,
        "alphas": {"portfolio_and_gender": PORTFOLIO_ALPHA, "country_and_loan_cycle": SUBGROUP_ALPHA},
        "min_cell_n": MIN_CELL_N,
        "metrics": metrics,
        "nps_score": nps,
    }
