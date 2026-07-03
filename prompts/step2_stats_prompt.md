# Developer Prompt — Analysis Engine Step 2: Core Stat Functions
# File: analysis_engine/stats.py

---

## Context

You are building Step 2 of the analysis engine for the VisionFund Insurance Client Survey.
Step 1 (segments.py) is already complete. Step 2 produces all the reusable stat functions
that every section calculator (Step 3) will call. Do not implement any section calculators
here — only the stat primitives and the disaggregation helper.

This module must be reusable across all future quarterly survey runs. No function may
contain hardcoded respondent counts, column names, or scale sizes.

---

## What Step 1 produced (already exists — do not modify)

```
analysis_engine/
    __init__.py               ← empty
    segments.py               ← fully implemented
    sections/
        __init__.py           ← empty
```

Key import from Step 1:

```python
from analysis_engine.segments import get_all_segment_masks, SEGMENT_REGISTRY
```

Confirmed segment n-counts from Q2 2026 (for reference only — not to be hardcoded):
female=1518, male=586, claimant=153, non_claimant=210, first_time_access=1803,
caregiver=1928, pwd=477, bundled_service_client=9.

---

## What you must build

### File to create: `analysis_engine/stats.py`

Do not create any other files. Do not modify anything in Step 1.

---

## Critical dtype facts — identical to Step 1 rules

| Column type | dtype | Correct comparison | Wrong |
|---|---|---|---|
| Boolean flag / binary cols | `pd.BooleanDtype()` | `series == True` | bare `series` |
| Categorical (single-select) | `pd.Categorical` | `series == "Female"` | |
| Likert scores | `pd.Int8Dtype()` | `series.dropna()` | `series.notna()` alone |
| NPS score | `pd.Int16Dtype()` | `series.dropna()` | |
| Multi-select list cols | `object` (Python lists or PyArrow ListScalar) | see ranked_options below | `series.notna()` |

### PyArrow ListScalar handling (critical for ranked_options)

Multi-select list columns (e.g., `q_coping_mechanisms`, `q_claim_challenges`) are stored as
Python lists in the parquet but may be read back as `pyarrow.ListScalar` objects. Always
convert before iterating:

```python
def _to_python_list(val) -> list:
    """Convert a cell value from a list column to a plain Python list."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return []
    if hasattr(val, "as_py"):          # pyarrow scalar
        val = val.as_py()
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return []
```

Use this helper inside `ranked_options` when iterating over rows.

---

## Low-n suppression rule (applies to every function)

Any stat result where `n_valid < LOW_N_THRESHOLD` must be suppressed:
- Set `"value": None`
- Set `"suppressed": True`
- Set `"suppress_reason": f"n_valid={n_valid} below threshold={LOW_N_THRESHOLD}"`

Define as a module-level constant:

```python
LOW_N_THRESHOLD: int = 30
```

Suppression does NOT raise an error. The result dict is still returned with `value=None`.
The section calculators and generation layer handle suppressed cells downstream.

---

## Standard result dict schema

Every stat function must return a dict conforming to this base schema. Functions may add
extra keys but must always include these:

```python
{
    "value":          float | None,   # primary stat; None if suppressed or no valid data
    "n_valid":        int,            # respondents with a non-null answer
    "n_total":        int,            # total rows passed to the function (the base/scope)
    "suppressed":     bool,           # True if n_valid < LOW_N_THRESHOLD
    "suppress_reason": str | None,    # reason string if suppressed, else None
}
```

---

## Required functions

### 1. `top_two_box(series: pd.Series, top_n: int = 2) -> dict`

For **nullable integer Likert columns** (`pd.Int8Dtype()`).

Computes the proportion of valid respondents who scored in the top `top_n` values.
Derives the scale maximum from the observed data — do not hardcode 4 or 5.

Logic:
1. Drop null values → `valid`
2. `max_val = int(valid.max())`
3. `threshold = max_val - top_n + 1`
4. Top-two-box = count of valid where `value >= threshold` / `len(valid)`

Returns:
```python
{
    "value":           float | None,
    "n_valid":         int,
    "n_total":         int,
    "suppressed":      bool,
    "suppress_reason": str | None,
    "top_values":      list[int],   # e.g. [3, 4] for a 4-point scale
    "scale_max":       int,         # observed maximum value
}
```

Example: for Likert-4 (values 1–4) with top_n=2, top_values=[3,4].
Example: for Likert-5 (values 1–5) with top_n=2, top_values=[4,5].

---

### 2. `share_selecting(series: pd.Series, values: list[str]) -> dict`

For **Categorical single-select columns**.

Proportion of valid (non-null) respondents whose value is in `values`.

Used for:
- `q_alternative_access`: `values=["Very difficult", "Slightly difficult"]` → "difficult" headline
- `q_prior_access` as binary: but note this column is BooleanDtype, not Categorical —
  use `share_true()` for booleans (see function 3 below)
- Any Categorical where the report calls for a specific option share

Logic:
1. Valid = rows where value is not null and not the scope sentinel `"__SCOPE_NA__"`
   (sentinel may appear in Categorical columns — always exclude it from valid count)
2. Proportion = count where value in `values` / `len(valid)`

Returns:
```python
{
    "value":           float | None,
    "n_valid":         int,
    "n_total":         int,
    "suppressed":      bool,
    "suppress_reason": str | None,
    "matched_values":  list[str],   # the values argument, for traceability
}
```

---

### 3. `share_true(series: pd.Series) -> dict`

For **BooleanDtype columns** (`pd.BooleanDtype()`).

Proportion of valid (non-null) respondents where `value == True`.

Used for:
- `q_prior_access == False` (first time access rate — note: call with `~series` if needed,
  but see note below)
- `q_insured_event_12m`, `q_claim_submitted`, `flag_negative_coping`, `flag_promoter`, etc.

**Important:** Always compare with `== True` and `== False`, never use bare truthiness.

```python
valid = series[series.notna()]
n_true = int((valid == True).sum())   # noqa: E712
```

Returns:
```python
{
    "value":           float | None,   # n_true / n_valid
    "n_valid":         int,
    "n_total":         int,
    "suppressed":      bool,
    "suppress_reason": str | None,
    "n_true":          int,
    "n_false":         int,
}
```

---

### 4. `ranked_options(series: pd.Series, top_n: int | None = None) -> dict`

For **object-dtype multi-select list columns** (each row is a Python list of selected
option labels).

Counts frequency of each selected option across all rows. Returns options ranked by
frequency descending.

Use `_to_python_list()` (defined above) on every cell before iterating.
Ignore empty lists — do not count them as "selected" for any option.

`top_n`: if provided, return only the top N options. If None, return all.

`n_valid` = count of rows with at least one selected option (non-empty list after
conversion). Rows with empty lists are NOT valid responses.

Returns:
```python
{
    "value":           None,          # not applicable for ranked lists — always None
    "n_valid":         int,           # rows with ≥1 selection
    "n_total":         int,
    "suppressed":      bool,
    "suppress_reason": str | None,
    "ranked":          [             # sorted descending by n
        {
            "option": str,
            "n":      int,
            "pct":    float,          # n / n_valid
        },
        ...
    ],
}
```

---

### 5. `claims_funnel(df: pd.DataFrame) -> dict`

Specific to Part 2.1. Computes the four-step claims funnel from the scoped DataFrame.

Required columns (must check each exists and log warning if missing):
- `q_insured_event_12m` (BooleanDtype)
- `q_claim_submitted` (BooleanDtype)
- `flag_paid_claimant` (BooleanDtype)
- `q_payout_cost_coverage` (Categorical)

Funnel steps and their denominators:

| Step | Numerator | Denominator |
|---|---|---|
| Experienced event | `q_insured_event_12m == True` | all rows in df |
| Filed claim | `q_claim_submitted == True` | insured event base |
| Claim paid | `flag_paid_claimant == True` | claimants (submitted==True) |
| Payout adequacy | distribution of `q_payout_cost_coverage` | paid claimants |

Returns:
```python
{
    "experienced_event": {
        "n":            int,
        "n_total":      int,
        "pct_of_total": float,
    },
    "filed_claim": {
        "n":                  int,
        "n_total":            int,    # = experienced_event.n
        "pct_of_event_base":  float,
        "leakage":            float,  # 1 - pct_of_event_base
    },
    "claim_paid": {
        "n":               int,
        "n_total":         int,       # = filed_claim.n
        "pct_of_claimants": float,
    },
    "payout_adequacy": {
        "n_valid":      int,
        "n_total":      int,          # = claim_paid.n
        "distribution": [
            {"value": str, "n": int, "pct": float},
            ...
        ],
    },
}
```

---

### 6. `nps_score(df: pd.DataFrame) -> dict`

Computes headline NPS and segment split from `q_nps_score` (Int16, values 0–10).

NPS formula: `(n_promoters - n_detractors) / n_valid * 100`

Promoters: score >= 9. Passives: 7 <= score <= 8. Detractors: score <= 6.

Required column: `q_nps_score`. Log warning and return nulls if missing.

Returns:
```python
{
    "value":       float | None,  # headline NPS (-100 to +100)
    "n_valid":     int,           # respondents with a score
    "n_total":     int,
    "suppressed":  bool,
    "suppress_reason": str | None,
    "promoters":   {"n": int, "pct": float},
    "passives":    {"n": int, "pct": float},
    "detractors":  {"n": int, "pct": float},
}
```

---

### 7. `significance_test(a_n: int, a_total: int, b_n: int, b_total: int) -> dict`

Two-proportion z-test for comparing two proportions (e.g., female vs male, claimant
vs non-claimant).

Used for the gap columns in Parts 6 and 7 scorecards.

Use `scipy.stats.proportions_ztest` with `alternative="two-sided"`.

Handle edge cases:
- If either total == 0, return `{"significant": False, "p_value": None, "z_stat": None, "error": "zero denominator"}`
- If either n > total, return error dict

Returns:
```python
{
    "a_pct":       float,          # a_n / a_total
    "b_pct":       float,          # b_n / b_total
    "gap":         float,          # a_pct - b_pct
    "z_stat":      float | None,
    "p_value":     float | None,
    "significant": bool,           # True if p_value < 0.05
    "error":       str | None,     # populated only on edge-case failure
}
```

---

### 8. `spearman_correlation(x: pd.Series, y: pd.Series) -> dict`

For Part 5 CWB driver correlation table. Spearman rank correlation.

Use `scipy.stats.spearmanr`.

Before computing:
1. Align x and y on index (inner join — only rows where BOTH are non-null)
2. Drop rows where either value is null

Required: both series must have at least `LOW_N_THRESHOLD` valid paired rows after
alignment. If not, return suppressed result.

Returns:
```python
{
    "value":           float | None,  # Spearman r coefficient
    "n_valid":         int,           # paired rows used
    "n_total":         int,           # len of x (before alignment)
    "p_value":         float | None,
    "significant":     bool,
    "suppressed":      bool,
    "suppress_reason": str | None,
}
```

---

### 9. `disaggregate(scoped_df: pd.DataFrame, series_or_col: pd.Series | str, stat_fn, segment_masks: dict[str, pd.Series], low_n_threshold: int = LOW_N_THRESHOLD, **stat_kwargs) -> dict`

Applies any single-series stat function across all segments. This is what every section
calculator calls instead of looping manually.

Parameters:
- `scoped_df` — the correctly scoped DataFrame (e.g., `ds.insured_event_base`, not always `ds.df`)
- `series_or_col` — either a column name string (extracted from `scoped_df`) or a pre-built Series
- `stat_fn` — one of: `top_two_box`, `share_selecting`, `share_true`, `ranked_options`
- `segment_masks` — from `get_all_segment_masks(ds.df)` (aligned to full df index)
- `**stat_kwargs` — passed through to `stat_fn` (e.g., `values=["Very difficult", ...]` for `share_selecting`)

Logic:
1. Resolve `series_or_col` to a Series from `scoped_df`
2. For each `(seg_name, full_mask)` in `segment_masks`:
   a. Intersect `full_mask` with `scoped_df.index` using `.reindex(scoped_df.index, fill_value=False)`
   b. Filter `series` to only the segment rows: `seg_series = series[seg_mask_in_scope]`
   c. Call `stat_fn(seg_series, **stat_kwargs)` → result dict
   d. Apply suppression if `result["n_valid"] < low_n_threshold` (override the fn's own suppression check)
3. Return `{seg_name: result_dict, ...}` for all segments

Note: `claims_funnel` and `nps_score` take a full DataFrame, not a single Series — they are
NOT used with `disaggregate`. Section calculators call them directly.

Returns:
```python
{
    "female":            { ...stat_result... },
    "male":              { ...stat_result... },
    "claimant":          { ...stat_result... },
    "non_claimant":      { ...stat_result... },
    "first_time_access": { ...stat_result... },
    "caregiver":         { ...stat_result... },
    "pwd":               { ...stat_result... },
    "bundled_service_client": { ...stat_result... },
}
```

---

## File management and structure

Only create `analysis_engine/stats.py`. Do not create any other files or modify Step 1.

Module-level organisation inside `stats.py`:

```
# --- Constants ---
LOW_N_THRESHOLD = 30
SCOPE_SENTINEL = "__SCOPE_NA__"

# --- Internal helpers ---
def _to_python_list(val) -> list: ...
def _base_result(n_valid, n_total) -> dict: ...   # builds the standard base dict

# --- Single-series stat functions ---
def top_two_box(...) -> dict: ...
def share_selecting(...) -> dict: ...
def share_true(...) -> dict: ...
def ranked_options(...) -> dict: ...

# --- DataFrame-level stat functions ---
def claims_funnel(...) -> dict: ...
def nps_score(...) -> dict: ...

# --- Comparison / correlation ---
def significance_test(...) -> dict: ...
def spearman_correlation(...) -> dict: ...

# --- Disaggregation helper ---
def disaggregate(...) -> dict: ...
```

---

## Dependencies

Allowed imports:
- `pandas` (already in environment)
- `scipy.stats` (available in Anaconda — use for `proportions_ztest` and `spearmanr`)
- `logging` (standard library)
- No imports from `data_loader` or `analysis_engine.segments`

`stats.py` must have zero imports from the rest of the analysis engine. It is a pure
utility module — it operates only on Series and DataFrames passed by the caller.

---

## Reusability requirements

1. **No column name strings inside functions.** All functions receive Series or DataFrames
   as arguments — they never reference column names by string internally.
   Column selection happens at the call site (section calculators), not here.

2. **No hardcoded scale sizes.** `top_two_box` derives the scale maximum from the data.

3. **No hardcoded respondent counts.** Functions work for any n.

4. **`LOW_N_THRESHOLD` as a single constant.** Never write `30` in function bodies —
   always reference the constant so a future change is a one-line edit.

5. **`SCOPE_SENTINEL` as a constant.** The string `"__SCOPE_NA__"` must not appear
   anywhere in function bodies — reference the constant.

---

## Logging

Logger name: `"analysis_engine.stats"`.
Log at WARNING for:
- Missing required columns in `claims_funnel` or `nps_score`
- Suppressed results in `disaggregate` (one line per suppressed segment: name and n)
- Edge-case failures in `significance_test`

Do not log at INFO inside individual stat functions — they are called many times per run
and would flood the log. `disaggregate` may log one INFO line summarising the run.

---

## What NOT to do

- Do not implement any section calculators
- Do not import from `data_loader` or `analysis_engine.segments`
- Do not add a `__main__` block or CLI
- Do not add `pytest` tests
- Do not reference any specific question column names (e.g., `"q_coverage_understanding"`)
  anywhere inside `stats.py` — those belong in section calculators
- Do not add docstrings longer than one line per function

---

## Acceptance criteria

The implementation is correct when all of the following hold:

1. `top_two_box` on a Likert-4 series (values 1–4) returns `top_values=[3,4]` and a
   `value` between 0 and 1. On a Likert-5 series (values 1–5) it returns `top_values=[4,5]`.

2. `share_selecting` excludes rows containing `"__SCOPE_NA__"` from `n_valid`.

3. `share_true` uses `== True` comparison (not bare truthiness) and excludes `pd.NA` rows
   from both numerator and denominator.

4. `ranked_options` handles `pyarrow.ListScalar` cells without raising. Empty lists
   do not contribute to `n_valid` or any option count.

5. `claims_funnel` returns four keys: `experienced_event`, `filed_claim`, `claim_paid`,
   `payout_adequacy`. Each step's `n_total` equals the previous step's `n`.

6. `nps_score` NPS value for Q2 data lands near 17 (= (924 promoters − 571 detractors)
   / 2104 scored × 100). Not hardcoded — computed from data.

7. `significance_test(900, 1518, 450, 586)` returns `significant=True` (this gap is
   large enough to be significant at α=0.05).

8. `spearman_correlation` on two identical non-null series returns `value` close to 1.0.

9. `disaggregate` correctly intersects segment masks with a scoped DataFrame. When called
   with `scoped_df=ds.insured_event_base` (n=363), the `female` segment result has
   `n_total <= 363`, not 2111.

10. Any segment with `n_valid < 30` in the `disaggregate` output has `value=None` and
    `suppressed=True`. The `bundled_service_client` segment (n≈9) is always suppressed.
