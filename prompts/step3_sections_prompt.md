# Developer Prompt — Analysis Engine Step 3: Section Calculators
# Files: analysis_engine/sections/part_1.py through part_7.py

---

## Context

You are building Step 3 of the analysis engine for the VisionFund Insurance Client Survey.
Steps 1 (segments.py) and 2 (stats.py) are already complete. Step 3 implements seven
section calculators — one per report part — which call the existing stat functions and
return structured dicts for the final `analysis_results.json`. Step 4 (run_analysis.py)
will call each section and assemble the JSON output; you are not writing Step 4 here.

All code must be reusable across future quarterly runs. No hardcoded respondent counts.

---

## What already exists

```
analysis_engine/
    __init__.py               ← empty
    segments.py               ← Step 1: SEGMENT_REGISTRY, get_all_segment_masks(), etc.
    stats.py                  ← Step 2: all stat functions
    sections/
        __init__.py           ← empty — ready for your files
```

### Imports available from Step 2

```python
from analysis_engine.stats import (
    top_two_box,
    share_selecting,
    share_true,
    ranked_options,
    claims_funnel,
    nps_score,
    significance_test,
    spearman_correlation,
    disaggregate,
    LOW_N_THRESHOLD,
)
```

### Key note from Step 2 implementation

`_to_python_list()` inside stats.py handles Python lists, PyArrow ListScalar, **and
numpy ndarrays** (Q2 data stores multi-select lists as numpy arrays when read back
from parquet). Section calculators do not need to handle this — just call `ranked_options()`.

### Data loader API

Section calculators receive a `CleanDataset` (`ds`) and `segment_masks` dict as arguments.
They do NOT call `load_survey_data()` themselves — that happens in Step 4.

`ds` properties available:
- `ds.df` — all 2,111 respondents
- `ds.health`, `ds.crop`, `ds.credit_life` — insurance-type splits
- `ds.insured_event_base` — `q_insured_event_12m == True`
- `ds.child_wellbeing_base` — `flag_child_wellbeing_denominator == True`
- `ds.claimants` — `q_claim_submitted == True`
- `ds.paid_claimants` — `flag_paid_claimant == True`
- `ds.promoters`, `ds.passives`, `ds.detractors` — NPS splits

`segment_masks`: dict from `get_all_segment_masks(ds.df)` — aligned to `ds.df.index`,
8 available segments (female, male, claimant, non_claimant, first_time_access,
caregiver, pwd, bundled_service_client). Already computed by the Step 4 orchestrator.

---

## Critical dtype rules (same as Steps 1 & 2)

- BooleanDtype comparisons: `series == True` / `series == False`, never bare `series`
- Likert scores: Int8 nullable — use `.dropna()` or `series.notna()` before arithmetic
- Categorical: `series == "Yes"` or `.isin([...])`
- NPS: Int16 nullable
- Multi-select list columns: pass to `ranked_options()` — handled internally

---

## What you must build

### Files to create

```
analysis_engine/sections/
    part_1.py    ← Client Understanding & Value Perception
    part_2.py    ← Claims Experience
    part_3.py    ← Financial Resilience
    part_4.py    ← Child Wellbeing Outcomes
    part_5.py    ← CWB Drivers (Spearman correlations)
    part_6.py    ← Claimant vs Non-Claimant Scorecard
    part_7.py    ← Female vs Male Scorecard
```

Do not create any other files. Do not modify `__init__.py` or any Step 1/2 files.

### Uniform function signature for all section calculators

Every part file must expose exactly one public function:

```python
def calculate(ds, segment_masks: dict) -> dict:
    ...
```

This is the only thing Step 4 needs to import from each file.

### Standard metric output structure

Every metric inside a section result must follow this pattern:

```python
"metric_key": {
    "headline": { ...stat_result_dict... },    # full base, no segment filter
    "segments": {                               # result of disaggregate()
        "female":      { ...stat_result_dict... },
        "male":        { ...stat_result_dict... },
        # ... all available segments
    },
}
```

Suppressed cells (n < 30) appear in the output as `{"value": null, "suppressed": true, ...}`.
Do not omit suppressed cells — the generation layer handles display logic.

### Column name constants

Each part file must define its required column names as module-level constants at the
top of the file, grouped under `# --- Column constants ---`. Never write raw column
name strings inside function bodies.

---

## Part-by-part specifications

---

### PART 1 — Client Understanding & Value Perception
**File:** `analysis_engine/sections/part_1.py`

**Base population:** `ds.df` (all respondents, n≈2,111)

**Metrics and stat functions:**

| Key | Column | Dtype | Stat function | Notes |
|---|---|---|---|---|
| `coverage_understanding` | `q_coverage_understanding` | Int8 | `top_two_box` | top 2 of 4-point scale |
| `claim_process_understanding` | `q_claim_process_understanding` | Int8 | `top_two_box` | top 2 of 4-point scale |
| `worth_premium` | `q_worth_premium` | Int8 | `top_two_box` | top 2 of 5-point scale |
| `renewal_intent` | `q_renewal_intent` | Int8 | `top_two_box` | top 2 of 5-point scale |

**Output structure:**

```python
{
    "base": "all_respondents",
    "n_base": len(ds.df),
    "metrics": {
        "coverage_understanding": {
            "headline": { ...top_two_box result... },
            "segments": { ...disaggregate result... },
        },
        # ... same for other 3 metrics
    }
}
```

**Implementation pattern for each metric:**

```python
headline = top_two_box(ds.df[COL_COVERAGE_UNDERSTANDING])
segments = disaggregate(ds.df, COL_COVERAGE_UNDERSTANDING, top_two_box, segment_masks)
```

---

### PART 2 — Claims Experience
**File:** `analysis_engine/sections/part_2.py`

This part has multiple sub-bases — read the denominator rules carefully.

#### 2.1 Claims Funnel

Call `claims_funnel(ds.df)` directly. No disaggregation (funnel is a structural metric).

#### 2.2 No-Claim Reasons (leakage analysis)

**Base:** respondents who had an insured event but did NOT file a claim.

```python
leakage_base = ds.insured_event_base[
    ds.insured_event_base[COL_CLAIM_SUBMITTED] == False   # noqa: E712
]
```

Column: `q_no_claim_reason` (Categorical — single-select with prefix stripped)
Stat: distribution of all selected values, sorted by frequency.

Use `share_selecting` for each distinct observed value, OR build the distribution manually:

```python
valid = leakage_base[COL_NO_CLAIM_REASON].dropna()
# exclude scope sentinel
valid = valid[valid != "__SCOPE_NA__"]
counts = valid.value_counts()
distribution = [
    {"value": v, "n": int(n), "pct": float(n / len(valid))}
    for v, n in counts.items()
]
```

Headline: `n_leakage` (size of leakage_base) and distribution. No disaggregation (sub-base is already a sub-population; further splitting would suppress everything).

#### 2.3 Claim Challenges

**Base:** claimants who experienced challenges: `q_claim_challenges_experienced == True`

```python
challenges_base = ds.claimants[
    ds.claimants[COL_CLAIM_CHALLENGES_EXPERIENCED] == True   # noqa: E712
]
```

Column: `q_claim_challenges` (object list — multi-select)
Stat: `ranked_options(challenges_base[COL_CLAIM_CHALLENGES])`

No disaggregation (sub-base is small; segments would suppress completely).
Include `n_base` = size of challenges_base.

#### 2.4 Claim Channel Preferred

**Base:** `ds.claimants` (all who submitted a claim)
Column: `q_claim_channel_preferred` (Categorical)
Stat: distribution (same manual approach as no-claim reasons).
No disaggregation.

#### 2.5 Claim Result

**Base:** `ds.claimants`
Column: `q_claim_result` (Categorical)
Stat: distribution.
No disaggregation.

#### 2.6 Payout Cost Coverage

**Base:** `ds.paid_claimants`
Column: `q_payout_cost_coverage` (Categorical)
Stat: distribution.
No disaggregation.

**Output structure:**

```python
{
    "base": "all_respondents",
    "n_base": len(ds.df),
    "claims_funnel": { ...claims_funnel result... },
    "no_claim_reasons": {
        "base": "leakage_respondents",
        "n_base": len(leakage_base),
        "distribution": [...],
    },
    "claim_challenges": {
        "base": "claimants_with_challenges",
        "n_base": len(challenges_base),
        "ranked": { ...ranked_options result... },
    },
    "claim_channel_preferred": {
        "base": "claimants",
        "n_base": len(ds.claimants),
        "distribution": [...],
    },
    "claim_result": {
        "base": "claimants",
        "n_base": len(ds.claimants),
        "distribution": [...],
    },
    "payout_cost_coverage": {
        "base": "paid_claimants",
        "n_base": len(ds.paid_claimants),
        "distribution": [...],
    },
}
```

---

### PART 3 — Financial Resilience
**File:** `analysis_engine/sections/part_3.py`

**Bases vary by metric — see table:**

| Key | Column | Dtype | Stat function | Base | Notes |
|---|---|---|---|---|---|
| `negative_coping` | `flag_negative_coping` | BooleanDtype | `share_true` | `ds.insured_event_base` | share who used negative coping strategies |
| `financial_stress_high` | `q_financial_stress` | Int8 | `top_two_box` | `ds.insured_event_base` | top 2 = high-stress responses |
| `alternative_access_difficult` | `q_alternative_access` | Categorical | `share_selecting` | `ds.df` | values=["Very difficult", "Slightly difficult"] |
| `confidence_pay` | `q_confidence_pay` | Int8 | `top_two_box` | `ds.df` | top 2 of 5-point scale = high confidence |

**Implementation for share_selecting:**

```python
headline = share_selecting(
    ds.df[COL_ALTERNATIVE_ACCESS],
    values=["Very difficult", "Slightly difficult"]
)
segments = disaggregate(
    ds.df,
    COL_ALTERNATIVE_ACCESS,
    share_selecting,
    segment_masks,
    values=["Very difficult", "Slightly difficult"],
)
```

**Output structure:**

```python
{
    "metrics": {
        "negative_coping": {
            "base": "insured_event_base",
            "n_base": len(ds.insured_event_base),
            "headline": { ...share_true result... },
            "segments": { ...disaggregate result... },
        },
        "financial_stress_high": {
            "base": "insured_event_base",
            "n_base": len(ds.insured_event_base),
            "headline": { ...top_two_box result... },
            "segments": { ...disaggregate result... },
        },
        "alternative_access_difficult": {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": { ...share_selecting result... },
            "segments": { ...disaggregate result... },
        },
        "confidence_pay": {
            "base": "all_respondents",
            "n_base": len(ds.df),
            "headline": { ...top_two_box result... },
            "segments": { ...disaggregate result... },
        },
    }
}
```

---

### PART 4 — Child Wellbeing Outcomes
**File:** `analysis_engine/sections/part_4.py`

#### 4.1 NPS

Call `nps_score(ds.df)` directly. No disaggregation.
Include `n_base` = number of respondents with a valid NPS score
(compute as `int(ds.df["q_nps_score"].notna().sum())`).

#### 4.2 Child Wellbeing

**Base:** `ds.child_wellbeing_base`
Column: `q_child_wellbeing` (Categorical: "Yes" / "No")
Stat: `share_selecting(series, values=["Yes"])` for headline
Disaggregation: `disaggregate(ds.child_wellbeing_base, COL_CHILD_WELLBEING, share_selecting, segment_masks, values=["Yes"])`

#### 4.3 Healthcare Access

**Base:** `ds.health` (health insurance respondents only)
Column: `q_healthcare_access` (Categorical)
Stat: distribution of all values (same manual approach as Part 2 distributions)
Also compute headline = `share_selecting` for the most positive value(s):
observe the actual values in the data and select the "access improved" options.
Use `series.dropna().unique()` to identify the values present, then pick the positive ones.
Since exact option labels may change across survey waves, use a configurable constant:

```python
# At module level — update if survey wording changes
HEALTHCARE_ACCESS_POSITIVE_VALUES = ["Yes, a lot", "Yes, somewhat"]
```

If none of the values in `HEALTHCARE_ACCESS_POSITIVE_VALUES` appear in the data, log a
WARNING and set headline `value = None` with `suppress_reason = "no matching values found"`.

No disaggregation (health-only respondents; further splitting would suppress most segments).

#### 4.4 Medical Cost Change (health respondents only)

**Base:** `ds.health`
Column: `q_medical_cost_change` (Int8 nullable)
Encoding: 1=Much lower, 2=Slightly lower, 3=No difference, 4=Slightly higher, null=Not applicable

**Critical:** Lower values (1, 2) are POSITIVE outcomes. `top_two_box` returns the highest
values — wrong for this metric. Instead, derive a boolean "cost improved" column and call
`share_true`:

```python
base_series = ds.health[COL_MEDICAL_COST_CHANGE]
cost_improved = base_series.map(
    lambda x: True if (pd.notna(x) and int(x) <= 2) else (False if pd.notna(x) else pd.NA)
).astype("boolean")
headline = share_true(cost_improved)
```

Do not disaggregate (health-only sub-population; cross with segments would suppress heavily).
Include a `"note"` key in the output: `"Lower values (1-2) coded as improved; Not applicable=null"`.

**Output structure:**

```python
{
    "nps": {
        "base": "all_respondents_with_score",
        "n_base": int(ds.df["q_nps_score"].notna().sum()),
        "result": { ...nps_score result... },
    },
    "child_wellbeing": {
        "base": "child_wellbeing_base",
        "n_base": len(ds.child_wellbeing_base),
        "headline": { ...share_selecting result... },
        "segments": { ...disaggregate result... },
    },
    "healthcare_access": {
        "base": "health_respondents",
        "n_base": len(ds.health),
        "positive_values_used": HEALTHCARE_ACCESS_POSITIVE_VALUES,
        "headline": { ...share_selecting result... },
        "distribution": [...],
    },
    "medical_cost_change": {
        "base": "health_respondents",
        "n_base": len(ds.health),
        "note": "Lower values (1-2) coded as improved; Not applicable=null",
        "headline": { ...share_true result on derived boolean... },
    },
}
```

---

### PART 5 — CWB Drivers
**File:** `analysis_engine/sections/part_5.py`

Spearman rank correlation between CWB outcome (child wellbeing Yes/No) and each driver
variable. All computed within `ds.child_wellbeing_base`.

**CWB outcome encoding:**

```python
cwb_base = ds.child_wellbeing_base
cwb_outcome = cwb_base[COL_CHILD_WELLBEING].map({"Yes": 1, "No": 0}).astype("Int8")
```

**Driver variables:**

| Key | Column | Dtype | Encoding before correlation |
|---|---|---|---|
| `financial_stress` | `q_financial_stress` | Int8 | pass as-is (already numeric) |
| `coverage_understanding` | `q_coverage_understanding` | Int8 | pass as-is |
| `claim_process_understanding` | `q_claim_process_understanding` | Int8 | pass as-is |
| `worth_premium` | `q_worth_premium` | Int8 | pass as-is |
| `renewal_intent` | `q_renewal_intent` | Int8 | pass as-is |
| `confidence_pay` | `q_confidence_pay` | Int8 | pass as-is |
| `nps_score` | `q_nps_score` | Int16 | pass as-is |
| `economic_strain_relief_proxy` | `q_child_improvements__d` | BooleanDtype | `.map({True: 1, False: 0}).astype("Int8")` |

The income/economic strain proxy is labeled `"economic_strain_relief_proxy"` in the output.
Include a `"note"` key: `"q_child_improvements__d — Reduced need to work extra hours after a shock (proxy for economic strain relief)"`.

**Implementation loop:**

```python
DRIVERS = [
    ("financial_stress", COL_FINANCIAL_STRESS, None),
    ("coverage_understanding", COL_COVERAGE_UNDERSTANDING, None),
    # ... etc
    ("economic_strain_relief_proxy", COL_ECONOMIC_STRAIN_PROXY, "boolean_to_int"),
]

correlations = {}
for key, col, encoding in DRIVERS:
    if col not in cwb_base.columns:
        log.warning(f"Part 5: column '{col}' missing — skipping driver '{key}'")
        continue
    x = cwb_outcome.copy()
    y = cwb_base[col].copy()
    if encoding == "boolean_to_int":
        y = y.map({True: 1, False: 0}).astype("Int8")
    result = spearman_correlation(x, y)
    correlations[key] = result

correlations["economic_strain_relief_proxy"]["note"] = "..."
```

**Output structure:**

```python
{
    "base": "child_wellbeing_base",
    "n_base": len(cwb_base),
    "outcome_variable": "q_child_wellbeing (Yes=1, No=0)",
    "method": "Spearman rank correlation",
    "drivers": {
        "financial_stress":           { ...spearman_correlation result... },
        "coverage_understanding":     { ...spearman_correlation result... },
        "claim_process_understanding":{ ...spearman_correlation result... },
        "worth_premium":              { ...spearman_correlation result... },
        "renewal_intent":             { ...spearman_correlation result... },
        "confidence_pay":             { ...spearman_correlation result... },
        "nps_score":                  { ...spearman_correlation result... },
        "economic_strain_relief_proxy": {
            ...spearman_correlation result...,
            "note": "q_child_improvements__d — Reduced need to work extra hours after a shock (proxy for economic strain relief)",
        },
    },
}
```

---

### PART 6 — Claimant vs Non-Claimant Scorecard
**File:** `analysis_engine/sections/part_6.py`

Compares the `claimant` and `non_claimant` segments across key metrics, each using the
same scope (base population) as that metric's defining section.

**Define a module-level helper** `_scorecard_row()` to avoid repetition:

```python
def _scorecard_row(
    scoped_df,
    col_or_series,
    stat_fn,
    segment_masks: dict,
    label: str,
    **stat_kwargs,
) -> dict:
    disag = disaggregate(scoped_df, col_or_series, stat_fn, segment_masks, **stat_kwargs)
    a = disag.get("claimant",     {"value": None, "n_valid": 0, "suppressed": True, "suppress_reason": "segment absent"})
    b = disag.get("non_claimant", {"value": None, "n_valid": 0, "suppressed": True, "suppress_reason": "segment absent"})

    if a.get("value") is not None and b.get("value") is not None:
        sig = significance_test(
            round(a["value"] * a["n_valid"]),
            a["n_valid"],
            round(b["value"] * b["n_valid"]),
            b["n_valid"],
        )
    else:
        sig = None

    return {
        "label":        label,
        "claimant":     a,
        "non_claimant": b,
        "significance": sig,
    }
```

**Scorecard metrics** (in order — use the same scopes as the parent sections):

| Key | Column | Stat fn | Scope | Notes |
|---|---|---|---|---|
| `coverage_understanding` | `q_coverage_understanding` | `top_two_box` | `ds.df` | |
| `claim_process_understanding` | `q_claim_process_understanding` | `top_two_box` | `ds.df` | |
| `worth_premium` | `q_worth_premium` | `top_two_box` | `ds.df` | |
| `renewal_intent` | `q_renewal_intent` | `top_two_box` | `ds.df` | |
| `negative_coping` | `flag_negative_coping` | `share_true` | `ds.insured_event_base` | claimant ∩ insured_event_base = all claimants (153); non_claimant ∩ insured_event_base = leakage group (210) |
| `financial_stress_high` | `q_financial_stress` | `top_two_box` | `ds.insured_event_base` | |
| `confidence_pay` | `q_confidence_pay` | `top_two_box` | `ds.df` | |

**Output structure:**

```python
{
    "groups": {
        "claimant":     {"label": "Claimant",     "n": int((segment_masks["claimant"] == True).sum())},
        "non_claimant": {"label": "Non-Claimant", "n": int((segment_masks["non_claimant"] == True).sum())},
    },
    "metrics": {
        "coverage_understanding":      { ...scorecard_row result... },
        "claim_process_understanding": { ...scorecard_row result... },
        "worth_premium":               { ...scorecard_row result... },
        "renewal_intent":              { ...scorecard_row result... },
        "negative_coping":             { ...scorecard_row result... },
        "financial_stress_high":       { ...scorecard_row result... },
        "confidence_pay":              { ...scorecard_row result... },
    },
}
```

---

### PART 7 — Female vs Male Scorecard
**File:** `analysis_engine/sections/part_7.py`

Same pattern as Part 6. Define the same `_scorecard_row()` helper locally (copy it —
do not import from part_6 to keep files independent).

The only differences:
- Group keys are `"female"` and `"male"` instead of `"claimant"` and `"non_claimant"`
- Different metric set (see below)

**Scorecard metrics:**

| Key | Column | Stat fn | Scope |
|---|---|---|---|
| `coverage_understanding` | `q_coverage_understanding` | `top_two_box` | `ds.df` |
| `claim_process_understanding` | `q_claim_process_understanding` | `top_two_box` | `ds.df` |
| `worth_premium` | `q_worth_premium` | `top_two_box` | `ds.df` |
| `renewal_intent` | `q_renewal_intent` | `top_two_box` | `ds.df` |
| `negative_coping` | `flag_negative_coping` | `share_true` | `ds.insured_event_base` |
| `child_wellbeing` | `q_child_wellbeing` | `share_selecting` | `ds.child_wellbeing_base` |
| `confidence_pay` | `q_confidence_pay` | `top_two_box` | `ds.df` |

For `child_wellbeing`, pass `values=["Yes"]` to `_scorecard_row` via `**stat_kwargs`.

**Output structure:**

```python
{
    "groups": {
        "female": {"label": "Female", "n": int((segment_masks["female"] == True).sum())},
        "male":   {"label": "Male",   "n": int((segment_masks["male"] == True).sum())},
    },
    "metrics": {
        # same key names as the table above
        ...
    },
}
```

---

## Reusability requirements

1. **Column constants in every file.** All column name strings live at the top of each
   file under `# --- Column constants ---`. Never write `"q_child_wellbeing"` inside a
   function body.

2. **No hardcoded respondent counts.** Use `len(ds.df)`, `len(ds.insured_event_base)`, etc.

3. **No hardcoded option labels except where noted.** Healthcare access positive values
   are a module-level constant (`HEALTHCARE_ACCESS_POSITIVE_VALUES`) so they can be
   updated without touching function logic.

4. **Fail gracefully on missing columns.** If a required column is absent from the
   DataFrame, log a WARNING and return `{"value": None, "suppressed": True,
   "suppress_reason": "column missing: <col_name>"}` for that metric. Do not raise.

5. **All section files are independent.** Do not import between part files. Each file
   imports only from `analysis_engine.stats`. This means Part 6 and Part 7 each define
   their own `_scorecard_row()` helper — duplication is acceptable here.

---

## Logging

Logger name per file: `"analysis_engine.sections.part_N"` (e.g. `part_1`, `part_5`).
Each `calculate()` call logs one INFO line: `"Part N: calculating <base> (n=<n>)"`.
Warn on missing columns or no-match option labels. Do not log inside loops.

---

## What NOT to do

- Do not load data (`load_survey_data`) inside section files
- Do not call `get_all_segment_masks` — segment_masks is passed in by the caller
- Do not add `__main__` blocks or CLI entry points
- Do not create `base.py` or shared helpers across files — keep files independent
- Do not add `pytest` tests
- Do not write multi-line docstrings

---

## Acceptance criteria

1. All 7 `calculate(ds, segment_masks)` functions run without error on Q2 2026 data
   when called as: `part_1.calculate(ds, get_all_segment_masks(ds.df))`.

2. Every metric output dict contains the keys `"headline"` (with `"value"`, `"n_valid"`,
   `"n_total"`, `"suppressed"`) and `"segments"` (dict of segment results).
   Exceptions: `claims_funnel`, `nps`, and distribution-only metrics which have different
   structures as specified above.

3. `part_3.calculate()`: `negative_coping["headline"]["n_total"]` equals
   `len(ds.insured_event_base)` (~363), NOT `len(ds.df)` (~2,111).

4. `part_6.calculate()`: `metrics["negative_coping"]["claimant"]["n_total"]` ≤ 363
   (claimant scope intersected with insured_event_base, not full 2,111).

5. `part_5.calculate()`: all 8 driver keys present in `result["drivers"]`. The
   `economic_strain_relief_proxy` entry contains a `"note"` key.

6. `part_4.calculate()`: `medical_cost_change["headline"]["value"]` is not None (some
   health respondents report lower costs). The metric uses `share_true` on a derived
   boolean, not `top_two_box`.

7. `part_6.calculate()` and `part_7.calculate()`: every metric row contains a
   `"significance"` key. When either group has `value=None` (suppressed), significance
   is `None` (not an error).

8. `bundled_service_client` appears in all `"segments"` dicts with `"suppressed": true`
   and `"value": null` (n≈9 always below threshold).

9. No section calculator imports from another section calculator file.

10. `part_2.calculate()`: `claims_funnel["filed_claim"]["n_total"]` equals
    `claims_funnel["experienced_event"]["n"]` (chained denominators correct).
