"""
analysis_engine/stats.py — reusable stat primitives for all section calculators.

Single-series functions receive a Series from the caller; they never reference column
names internally.  DataFrame-level functions (claims_funnel, nps_score) are the only
exceptions and use private module-level column-name constants.
"""
import logging
import math

import pandas as pd
import statsmodels.api as sm
from scipy.stats import norm as _norm, spearmanr, mannwhitneyu

log = logging.getLogger("analysis_engine.stats")

# --- Constants ---
LOW_N_THRESHOLD: int = 30
SCOPE_SENTINEL: str = "__SCOPE_NA__"

# Column names for DataFrame-level functions only — never used inside single-series fns
_COL_INSURED_EVENT   = "q_insured_event_12m"
_COL_CLAIM_SUBMITTED = "q_claim_submitted"
_COL_PAID_CLAIMANT   = "flag_paid_claimant"
_COL_PAYOUT_COVERAGE = "q_payout_cost_coverage"
_COL_NPS_SCORE       = "q_nps_score"


# --- Internal helpers ---

def _to_python_list(val) -> list:
    """Convert a list-column cell to a plain Python list.

    Handles: PyArrow ListScalar, numpy ndarray, Python list, None/NaN.
    """
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if hasattr(val, "as_py"):      # pyarrow ListScalar
        val = val.as_py()
        if val is None:
            return []
    if isinstance(val, list):
        return val
    if hasattr(val, "tolist"):     # numpy ndarray or similar
        return val.tolist()
    return []


def _base_result(n_valid: int, n_total: int) -> dict:
    """Standard result skeleton with suppression flag pre-computed.

    not_applicable is distinct from suppressed: suppressed means "asked, but
    too few answered to report reliably" (n_valid below LOW_N_THRESHOLD);
    not_applicable means "nobody in this population was ever asked this
    question at all" (n_valid == 0 while the population itself is non-empty
    -- e.g. worth_premium for a Vietnam-only run, or renewal_intent for a
    non-Vietnam country run; see report_spec.yaml's population: notes for
    which metrics are population-exclusive like this). A metric with zero
    valid responses is always suppressed too (0 < LOW_N_THRESHOLD), but the
    writer should say "not asked of this population" instead of "sample too
    small" when not_applicable is True -- see generation/writer.py Phase 5.
    """
    suppressed = n_valid < LOW_N_THRESHOLD
    not_applicable = n_total > 0 and n_valid == 0
    return {
        "value": None,
        "n_valid": n_valid,
        "n_total": n_total,
        "suppressed": suppressed,
        "suppress_reason": (
            f"n_valid={n_valid} below threshold={LOW_N_THRESHOLD}" if suppressed else None
        ),
        "not_applicable": not_applicable,
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": 0.95,
    }


def _wilson_ci(n_success: int, n_valid: int, confidence: float = 0.95) -> tuple:
    """Wilson score interval for a binomial proportion."""
    if n_valid == 0:
        return (None, None)
    z = _norm.ppf((1 + confidence) / 2)
    p = n_success / n_valid
    denom = 1 + z ** 2 / n_valid
    center = (p + z ** 2 / (2 * n_valid)) / denom
    margin = (z * math.sqrt((p * (1 - p) / n_valid) + (z ** 2 / (4 * n_valid ** 2)))) / denom
    lower = max(0.0, center - margin)
    upper = min(1.0, center + margin)
    return (lower, upper)


def _fisher_z_ci(r: float, n_valid: int, confidence: float = 0.95) -> tuple:
    """Fisher z-transform confidence interval for a correlation coefficient."""
    if n_valid <= 3:
        return (None, None)
    z = _norm.ppf((1 + confidence) / 2)
    r_clamped = max(min(r, 0.999999), -0.999999)  # avoid atanh domain error at |r| == 1
    z_r = math.atanh(r_clamped)
    se = 1 / math.sqrt(n_valid - 3)
    lower_z = z_r - z * se
    upper_z = z_r + z * se
    return (math.tanh(lower_z), math.tanh(upper_z))


# --- Single-series stat functions ---

def top_two_box(series: pd.Series, top_n: int = 2, scale_max: "int | None" = None) -> dict:
    """Proportion of valid respondents scoring in the top top_n values (nullable Int8 Likert).

    scale_max: the question's true fixed scale maximum (4 for a Likert-4
    question, 5 for a Likert-5 one) -- ALWAYS pass this explicitly. Without
    it, the "top N" threshold is derived from valid.max() of whatever subset
    was passed in, which silently produces a WRONG, DIFFERENT threshold for
    any scoped call (a segment, a country) whose responses happen not to
    include the true top value -- confirmed in production: a caregiver
    segment that never reported the worst financial-stress value ("5") had
    its "top 2" silently redefined as {3,4} instead of {4,5}, reporting 48.6%
    where the correct figure (using the survey's real scale) was ~1.4%. The
    auto-detect fallback below exists only so this function never crashes on
    a legacy call site that hasn't been updated yet -- it logs a warning so
    any such site is easy to find, not a silent, intentional behavior.
    """
    n_total = len(series)
    valid   = series.dropna()
    n_valid = len(valid)
    result  = _base_result(n_valid, n_total)

    if n_valid == 0:
        result["top_values"] = []
        result["scale_max"]  = None
        return result

    if scale_max is None:
        max_val = int(valid.max())
        log.warning(
            "top_two_box: scale_max not passed -- falling back to this subset's own "
            f"observed max ({max_val}), which is WRONG whenever the subset doesn't "
            "include the survey's true top value. Pass scale_max explicitly."
        )
    else:
        max_val = scale_max
    threshold = max_val - top_n + 1
    result["top_values"] = list(range(threshold, max_val + 1))
    result["scale_max"]  = max_val

    if not result["suppressed"]:
        n_success = int((valid >= threshold).sum())
        result["value"] = n_success / n_valid
        result["ci_lower"], result["ci_upper"] = _wilson_ci(n_success, n_valid)

    return result


def bottom_two_box(series: pd.Series, bottom_n: int = 2, scale_min: "int | None" = None) -> dict:
    """Proportion of valid respondents in the LOWEST bottom_n values.

    For inverted Likert scales where 1 = best (e.g., 1='Very good', 4='Very poor'),
    this counts the positive responses correctly.  Mirrors top_two_box but anchors
    to the minimum observed value instead of the maximum.

    scale_min: the question's true fixed scale minimum -- in every Likert
    question in this codebase that's 1, since the coding convention is
    always a=1..d=4 or a=1..e=5 (never a different starting point), but pass
    it explicitly rather than assuming for the same reason top_two_box's
    scale_max must be explicit -- see that function's docstring for the
    confirmed production bug this guards against. bottom_two_box is
    theoretically less exposed (a subset failing to include the true MINIMUM
    observed value, i.e. no one picking "1", is rarer than failing to include
    the true maximum), but the auto-detect fallback is exactly as unsafe.
    """
    n_total = len(series)
    valid   = series.dropna()
    n_valid = len(valid)
    result  = _base_result(n_valid, n_total)

    if n_valid == 0:
        result["bottom_values"] = []
        result["scale_min"]     = None
        return result

    if scale_min is None:
        min_val = int(valid.min())
        log.warning(
            "bottom_two_box: scale_min not passed -- falling back to this subset's own "
            f"observed min ({min_val}), which is WRONG whenever the subset doesn't "
            "include the survey's true bottom value. Pass scale_min explicitly."
        )
    else:
        min_val = scale_min
    threshold = min_val + bottom_n - 1
    result["bottom_values"] = list(range(min_val, threshold + 1))
    result["scale_min"]     = min_val

    if not result["suppressed"]:
        n_success = int((valid <= threshold).sum())
        result["value"] = n_success / n_valid
        result["ci_lower"], result["ci_upper"] = _wilson_ci(n_success, n_valid)

    return result


def share_selecting(series: pd.Series, values: list) -> dict:
    """Proportion of valid (non-null, non-sentinel) respondents whose value is in values."""
    n_total = len(series)
    valid   = series[series.notna() & (series != SCOPE_SENTINEL)]
    n_valid = len(valid)
    result  = _base_result(n_valid, n_total)
    result["matched_values"] = values

    if not result["suppressed"] and n_valid > 0:
        n_success = int(valid.isin(values).sum())
        result["value"] = n_success / n_valid
        result["ci_lower"], result["ci_upper"] = _wilson_ci(n_success, n_valid)

    return result


def share_true(series: pd.Series) -> dict:
    """Proportion of valid (non-null) respondents where value == True (BooleanDtype)."""
    n_total = len(series)
    valid   = series[series.notna()]
    n_valid = len(valid)
    n_true  = int((valid == True).sum())   # noqa: E712
    n_false = int((valid == False).sum())  # noqa: E712
    result  = _base_result(n_valid, n_total)
    result["n_true"]  = n_true
    result["n_false"] = n_false

    if not result["suppressed"] and n_valid > 0:
        result["value"] = n_true / n_valid
        result["ci_lower"], result["ci_upper"] = _wilson_ci(n_true, n_valid)

    return result


def ranked_options(series: pd.Series, top_n: "int | None" = None) -> dict:
    """Frequency ranking of multi-select list column options (handles PyArrow ListScalar)."""
    n_total = len(series)
    counts: dict[str, int] = {}
    n_valid = 0

    for val in series:
        items = _to_python_list(val)
        if items:                           # empty list → not a valid response
            n_valid += 1
            for item in items:
                counts[item] = counts.get(item, 0) + 1

    result = _base_result(n_valid, n_total)
    result["value"] = None                  # scalar value not applicable for ranked lists

    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    if top_n is not None:
        ranked = ranked[:top_n]

    result["ranked"] = [
        {"option": opt, "n": n, "pct": n / n_valid if n_valid > 0 else 0.0}
        for opt, n in ranked
    ]

    return result


# --- DataFrame-level stat functions ---

def claims_funnel(df: pd.DataFrame) -> dict:
    """Claims funnel (Part 2.1). Schema-aware: Africa/Vietnam gates "filed a
    claim" behind an "experienced insured event" step; LARCO's survey has no
    such gate at all (data_loader_larco/column_mapping.csv has no
    q_insured_event_12m row) -- claims are filed independent of any "did an
    insured event happen" question, so when that column is absent, filed_claim
    is counted directly against the full population instead of a nonexistent
    event base. Confirmed in production: without this, LARCO's funnel silently
    showed 0/0/0 (n_event=0, so pct_claim=0/0) despite q_claim_submitted
    having 230 real claimants -- the SAME report's claim-result distribution
    (which reads q_claim_submitted directly, bypassing this funnel) correctly
    showed 230, exposing the gate as the sole culprit.

    LARCO also has no claim OUTCOME data at all (no flag_paid_claimant, no
    q_payout_cost_coverage -- it asks a subjective claim EXPERIENCE rating
    instead, q_claim_experience_rating, a different construct entirely). Those
    steps are marked not_applicable rather than a misleading "0% paid".
    """
    for col in (_COL_INSURED_EVENT, _COL_CLAIM_SUBMITTED, _COL_PAID_CLAIMANT, _COL_PAYOUT_COVERAGE):
        if col not in df.columns:
            log.warning(f"claims_funnel: required column '{col}' missing from DataFrame")

    n_all = len(df)
    has_event_gate       = _COL_INSURED_EVENT in df.columns
    has_claim_submitted  = _COL_CLAIM_SUBMITTED in df.columns
    has_paid_flag        = _COL_PAID_CLAIMANT in df.columns
    has_payout_col       = _COL_PAYOUT_COVERAGE in df.columns

    # Step 1: experienced insured event — not_applicable (not zero) when this
    # schema never asks the question at all.
    if has_event_gate:
        n_event = int((df[_COL_INSURED_EVENT] == True).sum())  # noqa: E712
    else:
        n_event = None

    # Step 2: filed claim — denominator is the insured-event base when this
    # schema has one, otherwise the full population.
    if has_claim_submitted:
        if has_event_gate:
            event_base  = df[df[_COL_INSURED_EVENT] == True]  # noqa: E712
            n_claimants = int((event_base[_COL_CLAIM_SUBMITTED] == True).sum())  # noqa: E712
        else:
            n_claimants = int((df[_COL_CLAIM_SUBMITTED] == True).sum())  # noqa: E712
    else:
        n_claimants = 0
    filed_claim_base_n = n_event if has_event_gate else n_all

    # Step 3: claim paid — requires flag_paid_claimant; not_applicable (not
    # "0% paid") when this schema doesn't collect claim outcomes at all.
    claim_paid_not_applicable = not has_paid_flag
    if has_paid_flag and has_claim_submitted:
        claimant_base = df[df[_COL_CLAIM_SUBMITTED] == True]  # noqa: E712
        n_paid        = int((claimant_base[_COL_PAID_CLAIMANT] == True).sum())  # noqa: E712
    else:
        n_paid = None if claim_paid_not_applicable else 0

    # Step 4: payout adequacy distribution — same not_applicable reasoning as step 3.
    payout_not_applicable = not (has_paid_flag and has_payout_col)
    n_payout_valid = 0
    payout_dist: list = []
    if has_paid_flag and has_payout_col:
        paid_base = df[df[_COL_PAID_CLAIMANT] == True]  # noqa: E712
        cov       = paid_base[_COL_PAYOUT_COVERAGE]
        valid_cov = cov[cov.notna() & (cov != SCOPE_SENTINEL)]
        n_payout_valid = len(valid_cov)
        if n_payout_valid > 0:
            vc = valid_cov.value_counts()
            payout_dist = [
                {"value": str(v), "n": int(c), "pct": c / n_payout_valid}
                for v, c in vc.items()
            ]

    pct_event = (n_event / n_all) if (has_event_gate and n_all > 0) else None
    pct_claim = (n_claimants / filed_claim_base_n) if filed_claim_base_n > 0 else 0.0
    pct_paid  = (n_paid / n_claimants) if (not claim_paid_not_applicable and n_claimants > 0) else None

    return {
        "experienced_event": {
            "n":              n_event,
            "n_total":        n_all,
            "pct_of_total":   pct_event,
            "not_applicable": not has_event_gate,
            "suppressed":     not has_event_gate,
        },
        "filed_claim": {
            "n":                 n_claimants,
            "n_total":           filed_claim_base_n,
            "pct_of_event_base": pct_claim,
            "leakage":           (1 - pct_claim) if filed_claim_base_n > 0 else None,
            "base":              "insured_event_base" if has_event_gate else "all_respondents",
            "not_applicable":    False,
            "suppressed":        False,
        },
        "claim_paid": {
            "n":                n_paid,
            "n_total":          n_claimants,
            "pct_of_claimants": pct_paid,
            "not_applicable":   claim_paid_not_applicable,
            "suppressed":       claim_paid_not_applicable,
        },
        "payout_adequacy": {
            "n_valid":        n_payout_valid,
            "n_total":        n_paid or 0,
            "distribution":   payout_dist,
            "not_applicable": payout_not_applicable,
            "suppressed":     payout_not_applicable,
        },
    }


def nps_score(df: pd.DataFrame) -> dict:
    """Headline NPS and promoter/passive/detractor breakdown from q_nps_score (Int16)."""
    n_total = len(df)

    if _COL_NPS_SCORE not in df.columns:
        log.warning(f"nps_score: required column '{_COL_NPS_SCORE}' missing from DataFrame")
        result = _base_result(0, n_total)
        result["promoters"]  = {"n": 0, "pct": 0.0}
        result["passives"]   = {"n": 0, "pct": 0.0}
        result["detractors"] = {"n": 0, "pct": 0.0}
        return result

    valid    = df[_COL_NPS_SCORE].dropna()
    n_valid  = len(valid)
    result   = _base_result(n_valid, n_total)

    n_promoters  = int((valid >= 9).sum())
    n_passives   = int(((valid >= 7) & (valid <= 8)).sum())
    n_detractors = int((valid <= 6).sum())

    denom = n_valid if n_valid > 0 else 1   # guard for zero-n edge case
    result["promoters"]  = {"n": n_promoters,  "pct": n_promoters  / denom}
    result["passives"]   = {"n": n_passives,   "pct": n_passives   / denom}
    result["detractors"] = {"n": n_detractors, "pct": n_detractors / denom}

    if not result["suppressed"] and n_valid > 0:
        result["value"] = (n_promoters - n_detractors) / n_valid * 100

    return result


def nps_scorecard_row(df: pd.DataFrame, segment_masks: "dict[str, pd.Series]",
                      label: str, group_a: str, group_b: str) -> dict:
    """Two-group NPS comparison, shaped like scorecard_row()'s output so it
    drops into the same generic scorecard plumbing (Parts 6/7).

    NPS isn't a proportion (it's promoters% - detractors%, range -100..+100),
    so it can't reuse significance_test()'s two-proportion z-test the way
    every other scorecard row does. Instead each group's underlying 0-10
    scores are compared directly with a Mann-Whitney U test (appropriate for
    ordinal data), and each group's displayed value is still its own NPS via
    nps_score() for a like-for-like read against the rest of the report.
    """
    _absent = {"value": None, "n_valid": 0, "suppressed": True, "suppress_reason": "segment absent",
               "not_applicable": False}

    def _group_nps(seg_name: str) -> dict:
        mask = segment_masks.get(seg_name)
        if mask is None:
            return _absent
        seg_mask = mask.reindex(df.index, fill_value=False)
        return nps_score(df[seg_mask])

    a = _group_nps(group_a)
    b = _group_nps(group_b)

    p_value = None
    if not a["suppressed"] and not b["suppressed"] and _COL_NPS_SCORE in df.columns:
        mask_a = segment_masks[group_a].reindex(df.index, fill_value=False)
        mask_b = segment_masks[group_b].reindex(df.index, fill_value=False)
        scores_a = df.loc[mask_a, _COL_NPS_SCORE].dropna()
        scores_b = df.loc[mask_b, _COL_NPS_SCORE].dropna()
        if len(scores_a) > 0 and len(scores_b) > 0:
            _, p_value = mannwhitneyu(scores_a, scores_b, alternative="two-sided")
            p_value = float(p_value)

    row = {"label": label, group_a: a, group_b: b}
    row["significance"] = {
        "p_value":     p_value,
        "significant": bool(p_value is not None and p_value < 0.05),
        "test":        "Mann-Whitney U (on underlying 0-10 scores; not a two-proportion z-test)",
    }
    return row


# --- Comparison / correlation ---

def significance_test(a_n: int, a_total: int, b_n: int, b_total: int) -> dict:
    """Two-proportion z-test (two-sided, α=0.05)."""
    if a_total == 0 or b_total == 0:
        log.warning("significance_test: zero denominator")
        return {
            "a_pct": 0.0, "b_pct": 0.0, "gap": 0.0,
            "z_stat": None, "p_value": None,
            "significant": False, "error": "zero denominator",
        }
    if a_n > a_total or b_n > b_total:
        log.warning("significance_test: n > total")
        return {
            "a_pct": a_n / a_total,
            "b_pct": b_n / b_total,
            "gap":   a_n / a_total - b_n / b_total,
            "z_stat": None, "p_value": None,
            "significant": False, "error": "n > total",
        }

    # Two-proportion z-test (two-sided) implemented via pooled SE + scipy norm CDF
    pooled_p = (a_n + b_n) / (a_total + b_total)
    se = (pooled_p * (1 - pooled_p) * (1 / a_total + 1 / b_total)) ** 0.5
    z_stat  = ((a_n / a_total) - (b_n / b_total)) / se if se > 0 else 0.0
    p_value = float(2 * (1 - _norm.cdf(abs(z_stat))))
    a_pct = a_n / a_total
    b_pct = b_n / b_total

    return {
        "a_pct":       a_pct,
        "b_pct":       b_pct,
        "gap":         a_pct - b_pct,
        "z_stat":      float(z_stat),
        "p_value":     float(p_value),
        "significant": bool(p_value < 0.05),
        "error":       None,
    }


def spearman_correlation(x: pd.Series, y: pd.Series) -> dict:
    """Spearman rank correlation; aligns x and y on index (inner), drops nulls."""
    n_total = len(x)
    aligned = pd.concat([x, y], axis=1).dropna()
    n_valid = len(aligned)
    result  = _base_result(n_valid, n_total)
    result["p_value"]    = None
    result["significant"] = False

    if result["suppressed"] or n_valid == 0:
        return result

    corr, p_val = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    result["value"]       = float(corr)
    result["p_value"]     = float(p_val)
    result["significant"] = bool(p_val < 0.05)
    result["ci_lower"], result["ci_upper"] = _fisher_z_ci(float(corr), n_valid)

    return result


# --- Regression ---

def _safe_exp(x: float) -> float:
    """math.exp() that returns inf instead of raising OverflowError.

    An unconverged fit (quasi/complete separation -- a predictor that
    near-perfectly splits the outcome, more likely the smaller a
    country-scoped sample is) can drive a coefficient or std_err large
    enough that coef ± z*std_err overflows a Python float's ~709 exp()
    ceiling. inf is the mathematically honest answer (an unbounded odds
    ratio/CI, the expected symptom of separation) -- run_analysis.py's
    _sanitise() already converts inf/nan to None before JSON output, the
    same representation used for every other undefined value in this
    schema, so this only needs to stop the crash, not re-derive a value.
    `converged: False` (see logistic_regression() below) already flags the
    whole result as not to be trusted at face value.
    """
    try:
        return math.exp(x)
    except OverflowError:
        return math.inf


def logistic_regression(y: pd.Series, X: "pd.DataFrame", confidence: float = 0.95) -> dict:
    """Binary logistic regression (statsmodels Logit).

    Drops zero-variance predictor columns before fitting (e.g. a product-type flag
    that is all-False outside the one country where that product exists) so the
    model stays fittable across different country datasets without code changes.
    """
    n_total = len(y)
    combined = pd.concat([y, X], axis=1).dropna()
    n_valid  = len(combined)
    suppressed = n_valid < LOW_N_THRESHOLD

    result = {
        "n_obs":              n_valid,
        "n_total":            n_total,
        "suppressed":         suppressed,
        "suppress_reason": (
            f"n_valid={n_valid} below threshold={LOW_N_THRESHOLD}" if suppressed else None
        ),
        # Regression predictors that don't apply to this population are
        # dropped individually (see the zero-variance filter below), not
        # represented by not_applicable -- kept here only for schema
        # consistency with every other suppressed-bearing result dict.
        "not_applicable":     False,
        "converged":          False,
        "pseudo_r2":          None,
        "predictors_dropped": [],
        "coefficients":       {},
        "error":              None,
    }

    if suppressed or n_valid == 0:
        return result

    y_aligned = combined.iloc[:, 0].astype(float)
    X_aligned = combined.iloc[:, 1:].astype(float)

    kept_cols = []
    for col in X_aligned.columns:
        if X_aligned[col].nunique(dropna=True) <= 1:
            result["predictors_dropped"].append(col)
            log.warning(f"logistic_regression: dropping zero-variance predictor '{col}'")
        else:
            kept_cols.append(col)

    if not kept_cols:
        result["error"] = "no predictors with variance — cannot fit model"
        return result

    X_kept = sm.add_constant(X_aligned[kept_cols], has_constant="add")

    try:
        fit = sm.Logit(y_aligned, X_kept).fit(disp=False)
    except Exception as exc:
        log.error(f"logistic_regression: fit failed — {type(exc).__name__}: {exc}")
        result["error"] = f"{type(exc).__name__}: {exc}"
        return result

    result["converged"] = bool(fit.mle_retvals.get("converged", False))
    result["pseudo_r2"] = float(fit.prsquared)

    z = _norm.ppf((1 + confidence) / 2)
    for name in X_kept.columns:
        coef    = float(fit.params[name])
        std_err = float(fit.bse[name])
        p_val   = float(fit.pvalues[name])
        key = "intercept" if name == "const" else name
        result["coefficients"][key] = {
            "coef":        coef,
            "odds_ratio":  _safe_exp(coef),
            "std_err":     std_err,
            "p_value":     p_val,
            "ci_lower":    _safe_exp(coef - z * std_err),
            "ci_upper":    _safe_exp(coef + z * std_err),
            "ci_level":    confidence,
            "significant": bool(p_val < 0.05),
        }

    return result


# --- Disaggregation helper ---

def disaggregate(
    scoped_df: pd.DataFrame,
    series_or_col: "pd.Series | str",
    stat_fn,
    segment_masks: "dict[str, pd.Series]",
    low_n_threshold: int = LOW_N_THRESHOLD,
    **stat_kwargs,
) -> dict:
    """Apply stat_fn for each segment, intersecting masks with scoped_df.index."""
    series = scoped_df[series_or_col] if isinstance(series_or_col, str) else series_or_col

    log.info(
        f"disaggregate: {stat_fn.__name__} over {len(segment_masks)} segment(s), "
        f"n_scope={len(scoped_df)}"
    )

    results: dict[str, dict] = {}
    for seg_name, full_mask in segment_masks.items():
        seg_mask   = full_mask.reindex(scoped_df.index, fill_value=False)
        seg_series = series[seg_mask]
        result     = stat_fn(seg_series, **stat_kwargs)

        # Guarantee suppression when n_valid is below threshold
        if result["n_valid"] < low_n_threshold and not result["suppressed"]:
            result["suppressed"]     = True
            result["suppress_reason"] = (
                f"n_valid={result['n_valid']} below threshold={low_n_threshold}"
            )
            result["value"]    = None
            result["ci_lower"] = None
            result["ci_upper"] = None

        if result["suppressed"]:
            log.warning(
                f"disaggregate: segment '{seg_name}' suppressed "
                f"(n_valid={result['n_valid']})"
            )

        results[seg_name] = result

    return results


# --- Two-group scorecard row (shared by Parts 5, 6, 7) ---

def scorecard_row(
    scoped_df: pd.DataFrame,
    col_or_series: "pd.Series | str",
    stat_fn,
    segment_masks: "dict[str, pd.Series]",
    label: str,
    group_a: str,
    group_b: str,
    **stat_kwargs,
) -> dict:
    """Disaggregate stat_fn across segment_masks, then add a two-proportion
    significance test between group_a and group_b specifically.

    Used by any part comparing two segments head-to-head (Part 6 claimant vs
    non-claimant, Part 7 female vs male, Part 5 caregiver vs non-caregiver).
    """
    disag = disaggregate(scoped_df, col_or_series, stat_fn, segment_masks, **stat_kwargs)
    _absent = {"value": None, "n_valid": 0, "suppressed": True, "suppress_reason": "segment absent",
               "not_applicable": False}
    a = disag.get(group_a, _absent)
    b = disag.get(group_b, _absent)

    if a.get("value") is not None and b.get("value") is not None:
        sig = significance_test(
            round(a["value"] * a["n_valid"]), a["n_valid"],
            round(b["value"] * b["n_valid"]), b["n_valid"],
        )
    else:
        sig = None

    row = {"label": label}
    row.update(disag)   # all segment keys present (including any country-config segments)
    row["significance"] = sig
    return row


# --- Composite index ---

def composite_index(
    dimension_scores: "dict[str, dict]",
    min_dimensions: int = 2,
) -> dict:
    """Average a set of 0–1 dimension scores into a single composite index.

    Each dimension dict must contain:
        value:          float | None    the 0–1 score
        suppressed:     bool            True when value is None or unreliable

    Returns a result dict with:
        value:                  float | None    composite score 0–1 (None if suppressed)
        suppressed:             bool
        suppress_reason:        str | None
        dimensions_included:    list[str]       names of dimensions that contributed
        dimensions_excluded:    list[str]       names excluded (suppressed or missing value)
        n_dimensions:           int             total number of dimensions passed in
    """
    included = []
    excluded = []
    values   = []

    for dim_name, dim_result in dimension_scores.items():
        if dim_result.get("suppressed", True) or dim_result.get("value") is None:
            excluded.append(dim_name)
        else:
            included.append(dim_name)
            values.append(float(dim_result["value"]))

    suppressed = len(values) < min_dimensions
    return {
        "value": (sum(values) / len(values)) if not suppressed else None,
        "suppressed": suppressed,
        "suppress_reason": (
            f"only {len(values)} of {len(dimension_scores)} dimensions available "
            f"(minimum {min_dimensions} required)" if suppressed else None
        ),
        # A composite aggregates several dimensions -- "not applicable" isn't a
        # meaningful state for the composite itself (each dimension already
        # carries its own not_applicable and is excluded above if so).
        "not_applicable": False,
        "dimensions_included": included,
        "dimensions_excluded": excluded,
        "n_dimensions": len(dimension_scores),
    }
