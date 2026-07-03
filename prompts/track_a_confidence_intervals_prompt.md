# Developer Prompt — Track A: Confidence Intervals
# File: analysis_engine/stats.py (+ one-line version bump in run_analysis.py)

---

## Context

The analysis engine (segments, stats, 7 section calculators, orchestrator, country config
layer) is fully built and working — `python run_analysis.py --run-id 2026_Q2` produces a
valid `analysis_results.json` today.

This update adds confidence intervals to every proportion-based and correlation-based stat
function, so the report layer can show uncertainty alongside point estimates (e.g. "23.4%
[20.1%–26.9%]" instead of a bare "23.4%"). This is a backward-compatible additive change —
no existing field is removed or renamed, and no section calculator (`part_1.py` …
`part_7.py`) needs to change.

---

## What currently exists (do not modify unless specified)

```
analysis_engine/
    stats.py              ← MODIFY (only file with logic changes)
    sections/
        part_1.py … part_7.py   ← do not touch — they consume stats.py output as-is
run_analysis.py            ← MODIFY (one line: SCHEMA_VERSION bump)
```

### Current relevant state of `stats.py`

- `import math` is **not** currently present — you will need to add it.
- `from scipy.stats import norm as _norm, spearmanr` is already imported — reuse `_norm`
  for the z critical value, do not add a second normal-distribution import.
- `_base_result(n_valid, n_total)` is the shared result skeleton used by `top_two_box`,
  `share_selecting`, `share_true`, `ranked_options`, and `nps_score`.
- `LOW_N_THRESHOLD = 30` — suppression threshold, unchanged.

---

## STEP 1 — Add two private CI helpers

Place these directly below `_base_result`, above the "Single-series stat functions"
section header.

### `_wilson_ci(n_success, n_valid, confidence=0.95) -> tuple[float | None, float | None]`

Wilson score interval for a proportion. Returns `(None, None)` when `n_valid == 0`.

```python
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
```

### `_fisher_z_ci(r, n_valid, confidence=0.95) -> tuple[float | None, float | None]`

Fisher z-transform interval for a correlation coefficient. Returns `(None, None)` when
`n_valid <= 3` (the transform is undefined below that).

```python
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
```

Add `import math` near the top of the file alongside the existing `import logging`.

---

## STEP 2 — Add `ci_lower` / `ci_upper` / `ci_level` to `_base_result`

Modify `_base_result` to include the three new keys with neutral defaults. This means
every function that already calls `_base_result` (`top_two_box`, `share_selecting`,
`share_true`, `ranked_options`, `nps_score`) automatically gets these keys in its output —
for `ranked_options` and `nps_score` they simply stay `None` (out of scope for this track,
see "What NOT to do" below).

```python
def _base_result(n_valid: int, n_total: int) -> dict:
    """Standard result skeleton with suppression flag pre-computed."""
    suppressed = n_valid < LOW_N_THRESHOLD
    return {
        "value": None,
        "n_valid": n_valid,
        "n_total": n_total,
        "suppressed": suppressed,
        "suppress_reason": (
            f"n_valid={n_valid} below threshold={LOW_N_THRESHOLD}" if suppressed else None
        ),
        "ci_lower": None,
        "ci_upper": None,
        "ci_level": 0.95,
    }
```

---

## STEP 3 — Populate CI fields in the four target functions

Only these four functions get `ci_lower`/`ci_upper` actually computed (not left at the
`None` default). In each case, compute the CI **only when `value` is computed** (i.e. not
suppressed, `n_valid > 0`) — mirror the existing guard that's already there for `value`.

### `top_two_box`

```python
def top_two_box(series: pd.Series, top_n: int = 2) -> dict:
    """Proportion of valid respondents scoring in the top top_n values (nullable Int8 Likert)."""
    n_total = len(series)
    valid   = series.dropna()
    n_valid = len(valid)
    result  = _base_result(n_valid, n_total)

    if n_valid == 0:
        result["top_values"] = []
        result["scale_max"]  = None
        return result

    max_val   = int(valid.max())
    threshold = max_val - top_n + 1
    result["top_values"] = list(range(threshold, max_val + 1))
    result["scale_max"]  = max_val

    if not result["suppressed"]:
        n_success = int((valid >= threshold).sum())
        result["value"] = n_success / n_valid
        result["ci_lower"], result["ci_upper"] = _wilson_ci(n_success, n_valid)

    return result
```

### `share_selecting`

```python
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
```

### `share_true`

```python
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
```

### `spearman_correlation`

```python
def spearman_correlation(x: pd.Series, y: pd.Series) -> dict:
    """Spearman rank correlation; aligns x and y on index (inner), drops nulls."""
    n_total = len(x)
    aligned = pd.concat([x, y], axis=1).dropna()
    n_valid = len(aligned)
    result  = _base_result(n_valid, n_total)
    result["p_value"]     = None
    result["significant"] = False

    if result["suppressed"] or n_valid == 0:
        return result

    corr, p_val = spearmanr(aligned.iloc[:, 0], aligned.iloc[:, 1])
    result["value"]       = float(corr)
    result["p_value"]     = float(p_val)
    result["significant"] = bool(p_val < 0.05)
    result["ci_lower"], result["ci_upper"] = _fisher_z_ci(float(corr), n_valid)

    return result
```

---

## STEP 4 — `disaggregate()` needs NO changes

`disaggregate()` calls `stat_fn(seg_series, **stat_kwargs)` and passes the returned dict
straight through into `results[seg_name]`. Since the four functions above now include
`ci_lower`/`ci_upper`/`ci_level` in their own return dict, every segment-level result
automatically carries the same fields — including the existing suppression override logic
(`disaggregate` already nulls `result["value"]` when it forces suppression below
`low_n_threshold`; it should also null `ci_lower`/`ci_upper` in that same branch).

Add two lines to the existing forced-suppression branch in `disaggregate`:

```python
        # Guarantee suppression when n_valid is below threshold
        if result["n_valid"] < low_n_threshold and not result["suppressed"]:
            result["suppressed"]      = True
            result["suppress_reason"] = (
                f"n_valid={result['n_valid']} below threshold={low_n_threshold}"
            )
            result["value"]    = None
            result["ci_lower"] = None
            result["ci_upper"] = None
```

This is the only change inside `disaggregate()`. Nothing else in that function changes.

---

## STEP 5 — Bump schema version in `run_analysis.py`

One line, near the top of the file:

```python
SCHEMA_VERSION = "1.2"   # was "1.1" — adds ci_lower/ci_upper/ci_level to all proportion
                          # and Spearman correlation results (Track A: Confidence Intervals)
```

No other change to `run_analysis.py`.

---

## What NOT to do

- Do not add CI fields to `ranked_options()`, `nps_score()`, or `claims_funnel()` — out of
  scope for this track. `ranked_options` and `nps_score` will pick up `ci_lower: None,
  ci_upper: None, ci_level: 0.95` automatically via `_base_result` — that is expected and
  fine, do not try to populate them.
- Do not change any file under `analysis_engine/sections/`.
- Do not change `segments.py`, `country_config.py`, or any `country_configs/*.yaml`.
- Do not add a second normal-distribution import — reuse the existing `_norm` import.
- Do not clamp Spearman CI bounds to `[0, 1]` — correlation CIs are bounded to `(-1, 1)` by
  `math.tanh`, which is already correct without manual clamping.
- Do not add `pytest` tests or a `__main__` block to `stats.py`.

---

## Acceptance criteria (verify against `runs/2026_Q2/analysis_results.json`)

1. Run `python run_analysis.py --run-id 2026_Q2` — exits 0, no new exceptions.
2. `meta.schema_version == "1.2"`.
3. `parts.part_1.metrics.coverage_understanding.headline` has `ci_lower`, `ci_upper`,
   `ci_level` keys, and `ci_lower < value < ci_upper`.
4. Same check holds for at least one `share_selecting`-based metric (e.g.
   `parts.part_3.metrics.alternative_access_difficult.headline`) and one `share_true`-based
   metric (e.g. `parts.part_3.metrics.negative_coping.headline`).
5. `parts.part_5.drivers.financial_stress` (a `spearman_correlation` result) has
   `ci_lower`, `ci_upper` populated and `ci_lower < value < ci_upper` when not suppressed.
6. Any segment result with `suppressed: true` (e.g. a small segment crossed with
   `climate_shock`, n < 30) has `ci_lower: null` and `ci_upper: null` — never a numeric
   value alongside `suppressed: true`.
7. `parts.part_4` / `parts.part_6` / `parts.part_7` (which call `top_two_box`/`share_true`
   indirectly via `disaggregate`) all show CI fields on every non-suppressed metric without
   any code change in `part_4.py`, `part_6.py`, or `part_7.py` themselves — this confirms
   the change is fully isolated to `stats.py`.
8. No value anywhere in the JSON is `NaN` or `Infinity` (existing `_sanitise()` /
   `_AnalysisEncoder` already handle this — just confirm it still holds).
