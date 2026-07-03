# Developer Prompt — Track B: Regression (Product Uptake → Child Wellbeing)
# Files: analysis_engine/stats.py, analysis_engine/sections/part_5.py,
#        run_analysis.py (version bump), requirements.txt

---

## Context

Track A (confidence intervals) is complete and merged — `stats.py` now adds `ci_lower`,
`ci_upper`, `ci_level` to every proportion and Spearman-correlation result, and
`SCHEMA_VERSION` is `"1.2"`.

Track B adds a logistic regression to Part 5, sitting **alongside** the existing Spearman
correlation table (`drivers`), not replacing it. Spearman shows direction/strength of
association per variable; the regression adds odds ratios across multiple predictors at
once — both are useful in the report and the boss has confirmed both should appear.

**Scope decision (already made, do not re-litigate):** the survey has no income or savings
question, so the outcome stays `q_child_wellbeing` (same as the Spearman table). The
predictors are reframed from "drivers" (Likert attitude variables) to **product uptake**
variables — which insurance product, and which other services the client uses — since that
is what the boss's brief actually asked for ("how product uptake relates to outcomes").

---

## What currently exists (do not modify unless specified)

```
analysis_engine/
    stats.py                 ← MODIFY (add one new function)
    sections/
        part_5.py             ← MODIFY (add regression block)
        part_1.py … part_4.py, part_6.py, part_7.py   ← do not touch
run_analysis.py               ← MODIFY (one line: SCHEMA_VERSION bump)
requirements.txt              ← MODIFY (add statsmodels)
```

### Relevant existing columns (already present on every `CleanDataset.df`, including `ds.child_wellbeing_base`)

These are core engine columns set by the transformer for every country/wave — not
Vietnam-specific, even though only Vietnam currently has non-zero `is_crop`:

```
is_health        bool   — insurance_type == "health"
is_crop          bool   — insurance_type == "crop"
is_credit_life   bool   — insurance_type == "credit_life"
```

### Relevant existing segments (already computed once per run, passed into every section as `segment_masks`)

```
"bundled_service_client"   — used ≥1 non-None bundled service in past 12 months
"first_time_access"        — q_prior_access == False (no insurance before VisionFund)
```

`part_5.calculate(ds, segment_masks)` already receives `segment_masks` as its second
argument — it is currently unused inside `part_5.py`. This update starts using it.

---

## STEP 1 — Add `logistic_regression()` to `stats.py`

### Add the import

Near the top of `stats.py`, alongside the existing `import pandas as pd` /
`from scipy.stats import norm as _norm, spearmanr`:

```python
import statsmodels.api as sm
```

### Add the function

Place it after `spearman_correlation`, under a new `# --- Regression ---` section header,
before the existing `# --- Disaggregation helper ---` header.

```python
# --- Regression ---

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
            "odds_ratio":  math.exp(coef),
            "std_err":     std_err,
            "p_value":     p_val,
            "ci_lower":    math.exp(coef - z * std_err),
            "ci_upper":    math.exp(coef + z * std_err),
            "ci_level":    confidence,
            "significant": bool(p_val < 0.05),
        }

    return result
```

Note: `math` is already imported in `stats.py` from Track A — no new import needed for it.

---

## STEP 2 — Update `part_5.py` to build predictors and call the regression

### Add import

```python
import pandas as pd

from analysis_engine.stats import spearman_correlation, logistic_regression
```

### Add new module-level constants (below the existing `_DRIVERS` list)

```python
COL_IS_CROP        = "is_crop"
COL_IS_CREDIT_LIFE = "is_credit_life"

# (output_key, source_name, source_type)
#   "column"  → read directly from cwb_base[source_name]
#   "segment" → pulled from the shared segment_masks dict, reindexed onto cwb_base.index
_REGRESSION_PREDICTORS = [
    ("is_crop",                COL_IS_CROP,               "column"),
    ("is_credit_life",         COL_IS_CREDIT_LIFE,        "column"),
    ("bundled_service_client", "bundled_service_client",  "segment"),
    ("first_time_access",      "first_time_access",       "segment"),
]

_REGRESSION_REFERENCE_NOTE = (
    "insurance_type reference category: is_health (implicit baseline — not included as "
    "a predictor, to avoid the dummy-variable trap)"
)
```

### Add a predictor-builder helper

```python
def _build_regression_predictors(cwb_base: "pd.DataFrame", segment_masks: dict) -> "pd.DataFrame":
    """Build the product-uptake predictor frame for logistic_regression().

    A predictor is silently omitted (not an error) when its source column or segment
    is unavailable in this run — keeps the regression reusable across future country
    datasets that may not have every product-uptake source.
    """
    predictors = pd.DataFrame(index=cwb_base.index)
    for key, source, source_type in _REGRESSION_PREDICTORS:
        if source_type == "column":
            if source not in cwb_base.columns:
                log.warning(f"Part 5 regression: column '{source}' missing — omitting predictor '{key}'")
                continue
            predictors[key] = cwb_base[source].astype("Int8")
        else:  # "segment"
            mask = segment_masks.get(source)
            if mask is None:
                log.warning(f"Part 5 regression: segment '{source}' unavailable — omitting predictor '{key}'")
                continue
            predictors[key] = mask.reindex(cwb_base.index, fill_value=False).astype("Int8")
    return predictors
```

### Update `calculate()`

Insert the regression block after the existing `correlations` loop, and add `"regression"`
to the returned dict. The existing `drivers` computation is otherwise unchanged.

```python
def calculate(ds, segment_masks: dict) -> dict:
    """Part 5: CWB Drivers — Spearman correlations + logistic regression within child_wellbeing_base."""
    cwb_base = ds.child_wellbeing_base
    log.info(f"Part 5: calculating child_wellbeing_base (n={len(cwb_base)})")

    if COL_CHILD_WELLBEING not in cwb_base.columns:
        log.warning(f"Part 5: outcome column '{COL_CHILD_WELLBEING}' missing — cannot compute drivers")
        return {
            "base": "child_wellbeing_base",
            "n_base": len(cwb_base),
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "method": "Spearman rank correlation",
            "drivers": {},
            "regression": {"error": "outcome column missing", "coefficients": {}},
        }

    cwb_outcome = cwb_base[COL_CHILD_WELLBEING].map({"Yes": 1, "No": 0}).astype("Int8")

    correlations: dict = {}
    for key, col, encoding in _DRIVERS:
        if col not in cwb_base.columns:
            log.warning(f"Part 5: column '{col}' missing — skipping driver '{key}'")
            continue
        y = cwb_base[col].copy()
        if encoding == "boolean_to_int":
            y = y.map({True: 1, False: 0}).astype("Int8")
        result = spearman_correlation(cwb_outcome, y)
        if key == "economic_strain_relief_proxy":
            result["note"] = _ECONOMIC_STRAIN_NOTE
        correlations[key] = result

    predictor_df = _build_regression_predictors(cwb_base, segment_masks)
    if predictor_df.shape[1] == 0:
        regression_result = {
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "predictors": [],
            "reference_category_note": _REGRESSION_REFERENCE_NOTE,
            "method": "Logistic regression (statsmodels Logit)",
            "error": "no predictor columns available",
        }
    else:
        reg = logistic_regression(cwb_outcome, predictor_df)
        regression_result = {
            "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
            "predictors": list(predictor_df.columns),
            "reference_category_note": _REGRESSION_REFERENCE_NOTE,
            "method": "Logistic regression (statsmodels Logit)",
            **reg,
        }

    return {
        "base": "child_wellbeing_base",
        "n_base": len(cwb_base),
        "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
        "method": "Spearman rank correlation",
        "drivers": correlations,
        "regression": regression_result,
    }
```

---

## STEP 3 — Bump schema version in `run_analysis.py`

```python
SCHEMA_VERSION = "1.3"   # was "1.2" — adds parts.part_5.regression
                          # (Track B: logistic regression, product uptake → child wellbeing)
```

---

## STEP 4 — Add the new dependency

In `requirements.txt`, add:

```
statsmodels>=0.14
```

---

## What NOT to do

- Do not remove or modify the existing `drivers` (Spearman) block in `part_5.py` — the
  regression is additive, sitting alongside it.
- Do not add income, savings, or any column that does not exist in the current schema —
  scope is locked to `is_crop`, `is_credit_life`, `bundled_service_client`,
  `first_time_access` as predictors.
- Do not hardcode a check for "Vietnam" anywhere in `stats.py` or `part_5.py` — the
  zero-variance-drop logic in `logistic_regression()` is what makes this reusable for
  future countries where `is_crop` might always be `False`. Country-specific behavior
  must never leak into the regression code itself.
- Do not change `part_1.py`–`part_4.py`, `part_6.py`, `part_7.py`, `segments.py`, or
  `country_config.py`.
- Do not silently include `is_health` as a fourth dummy — it must remain the implicit
  reference category (including it alongside the other two dummies plus an intercept
  would create perfect multicollinearity).
- Do not add `pytest` tests or a `__main__` block to `stats.py`.

---

## Acceptance criteria (verify against `runs/2026_Q2/analysis_results.json`)

1. `pip install -r requirements.txt` succeeds with `statsmodels` installed.
2. `python run_analysis.py --run-id 2026_Q2` exits 0, no new exceptions.
3. `meta.schema_version == "1.3"`.
4. `parts.part_5.drivers` is unchanged in shape/keys from before this update (Spearman
   table still present and untouched).
5. `parts.part_5.regression.predictors` includes all four of `is_crop`, `is_credit_life`,
   `bundled_service_client`, `first_time_access` (none should be dropped on this dataset —
   Vietnam has variance in all four within `child_wellbeing_base`).
6. `parts.part_5.regression.predictors_dropped == []` on this run.
7. `parts.part_5.regression.coefficients` has an `intercept` entry plus one entry per kept
   predictor, each with `coef`, `odds_ratio`, `std_err`, `p_value`, `ci_lower`, `ci_upper`,
   `ci_level`, `significant`.
8. For every coefficient, `ci_lower < odds_ratio < ci_upper` (sanity bound check) and
   `odds_ratio == math.exp(coef)` (within floating-point tolerance).
9. `parts.part_5.regression.converged == True` and `pseudo_r2` is a float between 0 and 1.
10. `parts.part_5.regression.reference_category_note` mentions `is_health` as the baseline.
11. Code review (not runtime-testable on this single-country dataset, since all four
    predictors currently have variance): confirm that if a predictor column were
    all-`False` for a given run, `logistic_regression()` would add it to
    `predictors_dropped`, exclude it from the fit, and the run would still complete
    successfully rather than crashing.
