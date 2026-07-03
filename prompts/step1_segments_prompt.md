# Developer Prompt — Analysis Engine Step 1: Segment Definitions
# File: analysis_engine/segments.py

---

## Context

You are building Step 1 of an analysis engine for the VisionFund Insurance Client Survey.
The analysis engine sits on top of an already-complete data loader pipeline. Your job in
this step is only to implement the segment definitions module. Do not implement any stat
functions or section calculators — those are separate steps.

This engine must be designed for reuse across future quarterly survey runs. Every design
decision should assume the survey is re-run quarterly with a new CSV, producing a new
parquet at `runs/{run_id}/survey_clean.parquet`. The code you write must work correctly
for any quarterly dataset, not just the current Q2 2026 data.

---

## Existing codebase you must integrate with

### Data loader API (already built — do not modify)

```
data_loader/
    data_loader_api.py       ← public API; import from here
    data_loader_profiler.py
    data_loader_transformer.py
    data_loader_derived.py
    data_loader_validator.py
    column_mapping.csv
    value_coding_map.yaml
```

Load data like this:

```python
from data_loader.data_loader_api import load_survey_data, CleanDataset

ds = load_survey_data(run_id="2026_Q2")   # specific quarter
ds = load_survey_data()                    # auto-selects latest run in runs/
```

`CleanDataset` exposes:
- `ds.df` — full pd.DataFrame (2,111 rows × 130 columns for Q2)
- `ds.n` — total respondent count
- `ds.health` — health insurance respondents only (`is_health == True`)
- `ds.crop` — crop insurance respondents only
- `ds.credit_life` — credit life respondents only
- `ds.promoters` — NPS score >= 9
- `ds.passives` — NPS score 7–8
- `ds.detractors` — NPS score <= 6
- `ds.claimants` — `q_claim_submitted == True`
- `ds.paid_claimants` — `flag_paid_claimant == True`
- `ds.insured_event_base` — `q_insured_event_12m == True`
- `ds.child_wellbeing_base` — `flag_child_wellbeing_denominator == True`

### Run output structure

```
runs/
    2026_Q2/
        survey_clean.parquet
        profile_report.md
        data_quality_report.md
        run_summary.txt
        analysis_results.json    ← written by the full engine (Step 4, not now)
```

---

## Critical dtype facts — read carefully

The parquet uses pandas nullable dtypes. Standard Python truthiness checks WILL silently
fail. Follow these rules exactly:

| Column type | dtype | Correct comparison | Wrong comparison |
|---|---|---|---|
| Boolean flag columns | `pd.BooleanDtype()` | `series == True` | `series`, `series.astype(bool)` |
| Multi-select child cols | `pd.BooleanDtype()` | `series == True` | `series is True` |
| Categorical (single-select) | `pd.Categorical` | `series == "Female"` | `series.isin(["Female"])` alone is ok |
| Likert scores | `pd.Int8Dtype()` | `series.notna()` for null check | `series != None` |
| NPS score | `pd.Int16Dtype()` | `series.notna()` | `series != None` |
| Lists (multi-select parent) | `object` (Python list) | `series.apply(len) > 0` | `series.notna()` (empty list is not NaN) |

Boolean columns that MUST use `== True`:
- `q_insured_event_12m`, `q_claim_submitted`, `q_claim_challenges_experienced`, `q_prior_access`
- `flag_negative_coping`, `flag_promoter`, `flag_paid_claimant`, `flag_child_wellbeing_denominator`
- All multi-select child columns: `q_coping_mechanisms__a` through `__h`,
  `q_bundled_services_used__a` through `__g`, etc.

---

## What you must build

### File to create: `analysis_engine/segments.py`

Also create:
- `analysis_engine/__init__.py` (empty)
- `analysis_engine/sections/__init__.py` (empty — sections module, to be populated in Step 3)

### Purpose

`segments.py` is the single source of truth for all client segment definitions used
throughout the analysis engine. Every section calculator will import from here.
No other file should define what a segment means.

---

## The 8 standard client segments

These are fixed by the report template (the "Golden Framework"). They are used to
disaggregate every key metric across the entire report.

| Segment name (key) | Definition | Column(s) | Notes |
|---|---|---|---|
| `female` | Female respondents | `q_sex == "Female"` | Categorical |
| `male` | Male respondents | `q_sex == "Male"` | Categorical |
| `claimant` | Submitted an insurance claim | `q_claim_submitted == True` | BooleanDtype |
| `non_claimant` | Did not submit a claim | `q_claim_submitted == False` | BooleanDtype; includes those with no insured event |
| `first_time_access` | No insurance before VisionFund | `q_prior_access == False` | BooleanDtype |
| `caregiver` | Supports children (answered Yes or No to child wellbeing) | `flag_child_wellbeing_denominator == True` | BooleanDtype |
| `pwd` | PWD household | `q_disability == "Yes"` | Categorical |
| `bundled_service_client` | Used at least one bundled service | see definition below | Multi-select; n≈9 in Q2 — include regardless of low n |
| `female_hh_head` | SKIP — not yet defined | N/A | Placeholder only; to be added when column source confirmed |
| `climate_shock` | SKIP — not yet defined | N/A | Placeholder only; to be added when definition confirmed |

**Bundled service client definition:**
A respondent is a bundled service client if they selected at least one non-None option in
`q_bundled_services_used`. The "None" option is child column `q_bundled_services_used__f`.
Therefore:

```python
bundled = (df["q_bundled_services_used__f"] == False) & df["q_bundled_services_used__f"].notna()
# OR more robustly: any of the non-None children is True
non_none_children = [
    "q_bundled_services_used__a", "q_bundled_services_used__b",
    "q_bundled_services_used__c", "q_bundled_services_used__d",
    "q_bundled_services_used__e", "q_bundled_services_used__g",
]
bundled = pd.Series(False, index=df.index)
for col in non_none_children:
    if col in df.columns:
        bundled |= (df[col] == True)
```

Use the second (child-by-child) approach as it is more robust to column availability.

---

## Required public interface

### 1. Segment registry

A module-level dict `SEGMENT_REGISTRY` mapping segment name → metadata. This is what
makes the module extensible — adding a new segment means adding one entry here, nowhere
else.

```python
SEGMENT_REGISTRY: dict[str, dict] = {
    "female": {
        "label": "Female",
        "description": "Female respondents",
        "column": "q_sex",
        "available": True,
    },
    "female_hh_head": {
        "label": "Female HH Head",
        "description": "Female-headed households — column source TBC",
        "column": None,
        "available": False,         # skipped this quarter
        "skip_reason": "Column source not yet confirmed",
    },
    # ... etc for all 10 entries
}
```

`available: False` entries must be silently skipped in all loops — they must never raise
an error, and they must never produce output.

### 2. `get_segment_mask(df, segment_name) -> pd.Series`

Returns a boolean `pd.Series` aligned to `df.index`. Series values are `True` for
respondents in the segment, `False` for all others. Never contains `pd.NA`.

Raises `KeyError` if `segment_name` is not in `SEGMENT_REGISTRY`.
Returns `None` if the segment exists but `available == False`.

Must handle missing columns gracefully: if a required column is absent from `df` (e.g.,
because a future survey form dropped it), log a warning and return `None` rather than
raising.

### 3. `get_all_segment_masks(df) -> dict[str, pd.Series]`

Returns a dict of `{segment_name: mask}` for all segments where `available == True` AND
the required column exists in `df`. Skips unavailable or missing-column segments silently.

This is the function every section calculator will call once and pass the result dict into
each stat function.

### 4. `describe_segments(df) -> list[dict]`

Returns a list of dicts summarising each segment for logging/debugging:

```python
[
    {
        "name": "female",
        "label": "Female",
        "available": True,
        "n": 1203,
        "pct_of_total": 57.0,
    },
    {
        "name": "female_hh_head",
        "label": "Female HH Head",
        "available": False,
        "n": None,
        "skip_reason": "Column source not yet confirmed",
    },
    ...
]
```

This is used by `run_analysis.py` (Step 4) to print a segment summary at the start of
each run.

---

## File management and structure requirements

Create the following structure. Only create the files listed — do not create anything else:

```
analysis_engine/
    __init__.py                  ← empty
    segments.py                  ← implement this fully
    sections/
        __init__.py              ← empty
```

`segments.py` must have no imports beyond the standard library and pandas. Do not import
from `data_loader` — `segments.py` only operates on a plain `pd.DataFrame` that the
caller passes in.

---

## Reusability requirements

1. **Column names as constants.** All column name strings used in segment definitions
   must be defined as module-level constants at the top of the file, grouped under a
   comment `# --- Column name constants ---`. This makes future survey form changes
   a one-line edit.

2. **Registry-driven, not function-driven.** The logic for computing each segment must
   live in the registry entry (as a callable, or as a declarative field), not as a
   series of if/elif branches in `get_segment_mask`. This means adding a segment in
   a future quarter requires only adding a registry entry, not modifying any function.

3. **No hardcoded respondent counts.** Do not assert, check, or hard-code any
   specific row counts (e.g., `assert n_female == 1203`). The function must work
   correctly for any n.

4. **Graceful column absence.** If a column named in the registry does not exist in the
   DataFrame passed in, the segment returns `None` and logs a warning. It does not crash.
   This protects against future survey form changes removing a question.

---

## Suggested implementation pattern for registry

Each registry entry can store a callable `mask_fn` that takes a DataFrame and returns a
boolean Series:

```python
SEGMENT_REGISTRY = {
    "female": {
        "label": "Female",
        "description": "Female respondents",
        "required_columns": [COL_SEX],
        "available": True,
        "mask_fn": lambda df: df[COL_SEX] == "Female",
    },
    "claimant": {
        "label": "Claimant",
        "description": "Submitted an insurance claim",
        "required_columns": [COL_CLAIM_SUBMITTED],
        "available": True,
        "mask_fn": lambda df: df[COL_CLAIM_SUBMITTED] == True,  # noqa: E712
    },
    ...
}
```

`get_segment_mask` then becomes:

```python
def get_segment_mask(df, segment_name):
    entry = SEGMENT_REGISTRY[segment_name]        # KeyError if not found
    if not entry["available"]:
        return None
    for col in entry["required_columns"]:
        if col not in df.columns:
            log.warning(f"Segment '{segment_name}': required column '{col}' missing — skipping")
            return None
    mask = entry["mask_fn"](df)
    return mask.fillna(False)                     # never return NA in mask
```

---

## Logging

Use Python's standard `logging` module. Logger name: `"analysis_engine.segments"`.
Log at INFO level when `get_all_segment_masks` is called (one line: how many segments
active). Log at WARNING for any skipped or missing-column segment.
Do not use `print()`.

---

## What NOT to do

- Do not implement any stat functions — those are Step 2 (`stats.py`)
- Do not import from `data_loader` — segments.py takes a plain DataFrame
- Do not add any `__main__` block or CLI entry point
- Do not create any files outside `analysis_engine/`
- Do not add `pytest` tests (test infrastructure is separate)
- Do not add docstrings longer than one line — inline comments only where the logic
  is non-obvious

---

## Acceptance criteria

The implementation is correct when all of the following hold:

1. `get_all_segment_masks(ds.df)` returns exactly the available segments, each as a
   boolean Series with no NA values, aligned to `ds.df.index`.

2. Calling with a DataFrame missing `q_sex` logs a warning for `female` and `male`
   and omits them from the result, without raising.

3. `describe_segments(ds.df)` returns one entry per registry item, with correct `n`
   counts for available segments and `n=None` for unavailable ones.

4. All 8 available segments produce non-empty masks (at least 1 True) against the
   Q2 2026 data. Exception: `bundled_service_client` is expected to have n≈9.

5. `female_hh_head` and `climate_shock` entries exist in the registry with
   `available=False` and do not appear in `get_all_segment_masks` output.

6. No segment definition contains a hardcoded respondent count.
