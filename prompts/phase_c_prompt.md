# Phase C — Derived Variables

## Context

You are building Phase C of a data loader for the VisionFund Insurance Client Survey 2026.
Phase B produced a clean parquet at `data/survey_clean.parquet` (2,111 rows, 126 columns).
Phase C adds five derived boolean/flag columns to that parquet. Each derivation is a small,
named, independently testable function. No other transformation is performed.

---

## Input: survey_clean.parquet schema (relevant columns only)

```
q_nps_score                (Int16, nullable)   — NPS score 0–10
q_claim_result             (category)          — cleaned single-select, values:
                                                   "It was approved and paid"
                                                   "It was approved and not yet paid"
                                                   "It is currently in process"
                                                   "It was rejected"
                                                   "I don't know"
                                                   NaN (skipped / not applicable)
q_child_wellbeing          (category)          — cleaned single-select, values:
                                                   "Yes"   (675 rows)
                                                   "No"    (1,253 rows)
                                                   "Do not support any children"  (176 rows)
                                                   NaN     (7 rows)
q_insured_event_12m        (boolean, nullable) — True=Yes/experienced event (363 rows),
                                                   False=No (1,594 rows), NaN (154 rows)
q_coping_mechanisms__c     (boolean, nullable) — Sell assets or livestock
q_coping_mechanisms__d     (boolean, nullable) — Reduce food consumption or essential spending
q_coping_mechanisms__e     (boolean, nullable) — Take children out of school
q_coping_mechanisms__f     (boolean, nullable) — Closed business temporarily
is_health                  (bool)              — True for Health Insurance respondents (1,672)
is_crop                    (bool)              — True for Crop Insurance respondents (154)
is_credit_life             (bool)              — True for Credit Life respondents (285)
```

All coping columns (c/d/e/f) have no NaN values within the 363 rows where
`q_insured_event_12m == True`. Outside that base (rows where no insured event
was experienced), those coping columns are NaN — which is expected and correct.

---

## Five derived variables to compute

### 1. `flag_negative_coping`

**Definition:** Respondent selected at least one negative/severe coping strategy
after an insured event: selling assets, reducing food, taking children out of school,
or closing their business.

**Logic:**
```
flag_negative_coping = (
    (q_coping_mechanisms__c == True) |
    (q_coping_mechanisms__d == True) |
    (q_coping_mechanisms__e == True) |
    (q_coping_mechanisms__f == True)
)
```

**Scope:** Only defined (non-NaN) for rows where `q_insured_event_12m == True`.
For all other rows: `pd.NA`.

**Expected base:** 363 rows with insured event.
**Expected positives (rough check):** columns c/d/e/f have 44/16/7/16 True counts
respectively; with overlap, positive count will be ≤ 83, likely ~60–70.

---

### 2. `flag_promoter`

**Definition:** NPS promoter — respondent gave a score of 9 or 10.

**Logic:**
```
flag_promoter = q_nps_score >= 9
```

**Scope:** Defined for all rows where `q_nps_score` is not NaN (2,104 non-null rows).
For NaN NPS rows: `pd.NA`.

**Expected positives:** 429 (score 9) + 495 (score 10) = 924 promoters.

---

### 3. `flag_paid_claimant`

**Definition:** Respondent submitted a claim AND the result was approved and paid.

**Logic:**
```
flag_paid_claimant = q_claim_result == "It was approved and paid"
```

**Scope:** Defined for all rows (False if not a claimant or different result,
NaN only if `q_claim_result` is NaN).

**Expected positives:** 58 respondents (from profile: "a. It was approved and paid" = 58).

---

### 4. `flag_child_wellbeing_denominator`

**Definition:** Respondent is in the valid base for child wellbeing analysis —
they answered the question AND indicated they do support children
(i.e., excludes "Do not support any children" responses and NaN).

**Logic:**
```
flag_child_wellbeing_denominator = q_child_wellbeing.isin(["Yes", "No"])
```

This flag is True for both "Yes" and "No" responders (the base for computing
the proportion who said children's wellbeing improved). The 176 who said
"Do not support any children" and 7 NaN rows are excluded (False).

**Expected True count:** 675 + 1,253 = 1,928 rows.

---

### 5. `insurance_type` (confirm already present)

`insurance_type` is already present from Phase B routing as a clean categorical
(`"health"`, `"crop"`, `"credit_life"`). Confirm it exists and has the right
distribution; do not recompute. If it is missing, raise a clear error.

---

## Deliverable: phase_c_derived.py

A Python script that:

1. Loads `data/survey_clean.parquet`.
2. Confirms `insurance_type` is present and logs its distribution.
3. Computes each of the four new derived variables (1–4 above) as named functions:
   ```python
   def compute_flag_negative_coping(df: pd.DataFrame) -> pd.array: ...
   def compute_flag_promoter(df: pd.DataFrame) -> pd.array: ...
   def compute_flag_paid_claimant(df: pd.DataFrame) -> pd.array: ...
   def compute_flag_child_wellbeing_denominator(df: pd.DataFrame) -> pd.array: ...
   ```
   Each function:
   - Takes the full DataFrame as input.
   - Returns a `pd.array` with `dtype=pd.BooleanDtype()` (nullable boolean).
   - Raises `KeyError` with a clear message if a required input column is missing.

4. Adds the four columns to the DataFrame:
   ```
   flag_negative_coping
   flag_promoter
   flag_paid_claimant
   flag_child_wellbeing_denominator
   ```

5. Runs built-in sanity assertions (not a separate test file — inline, after computation):
   - `flag_negative_coping`: only non-NaN where `q_insured_event_12m == True`;
     count is > 0 and ≤ 363.
   - `flag_promoter`: True count == 924 (exactly, since NPS has only 7 NaN rows).
   - `flag_paid_claimant`: True count == 58.
   - `flag_child_wellbeing_denominator`: True count == 1928.
   - `insurance_type` distribution: health=1672, crop=154, credit_life=285.
   If any assertion fails, print a clear FAIL message and exit with code 1.

6. Writes the augmented DataFrame to `data/survey_clean.parquet`
   (overwrite in place — same path, same format).

7. Prints a completion summary:
   ```
   Phase C complete.
     flag_negative_coping      : N True of 363 in-scope rows
     flag_promoter             : 924 True of 2104 scored rows
     flag_paid_claimant        : 58 True of 2111 rows
     flag_child_wellbeing_denom: 1928 True of 2111 rows
     insurance_type            : health=1672, crop=154, credit_life=285
     Output: data/survey_clean.parquet (130 columns)
   ```

---

## Requirements

- Use only `pandas` and stdlib. No other dependencies.
- All assertions run before the write step — do not write if assertions fail.
- Script runnable as: `python phase_c_derived.py`
- Paths hardcoded relative to script location (or accepted as optional CLI arg).
- No YAML or external config needed — logic is simple enough to be in code.

---

## Note on nullable booleans in pandas

Use `pd.array([...], dtype=pd.BooleanDtype())` for the return type of each function.
When building the array from boolean operations on nullable boolean Series:

```python
# Correct pattern for nullable boolean OR:
result = df["q_coping_mechanisms__c"].fillna(False) | df["q_coping_mechanisms__d"].fillna(False) | ...
# Then set NaN back for out-of-scope rows:
out_of_scope = df["q_insured_event_12m"] != True
result = result.astype(pd.BooleanDtype())
result[out_of_scope] = pd.NA
```

This avoids `pd.NA | False = pd.NA` propagation swallowing True values when
one sibling column has NaN but another has True.
