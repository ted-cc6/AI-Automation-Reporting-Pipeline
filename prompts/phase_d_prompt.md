# Phase D — Validation & Data-Quality Report

## Context

You are building Phase D of a data loader for the VisionFund Insurance Client Survey 2026.
Phases A–C have produced `data/survey_clean.parquet` (2,111 rows, 130 columns).
Phase D runs a systematic validation and writes `data_quality_report.md`.

The validation has two purposes:
1. **Gatekeeping** — the loader must refuse to hand broken data to the analysis engine.
   Any ERROR-level finding exits with code 1 and does NOT proceed.
2. **Documentation** — a Markdown report that a human reviewer can read to understand
   data quality without running code.

---

## Inputs

```
data/survey_clean.parquet          — the clean dataset (130 cols, from Phases A–C)
insurance-report-spec.yaml         — the report spec
insurance-report-spec.schema.json  — the JSON schema for validation
column_mapping.csv                 — Phase A mapping (for reference)
```

The project already has a `report_spec` Python package. Use it:
```python
from report_spec import load_spec
result = load_spec(
    "insurance-report-spec.yaml",
    "insurance-report-spec.schema.json",
    strict=False,
)
spec = result.spec   # ReportSpec object
# spec.all_source_questions()   → list of 18 SourceQuestion objects
# spec.referenced_variables()   → set of question_ref strings used in metrics
```

---

## Checks to implement (in this order)

### Check 1 — Spec alignment (ERROR if any question_ref missing)

For every `SourceQuestion` in `spec.all_source_questions()` (18 total):
- The `question_ref` must be present as a column in the parquet.
- The parquet column dtype must be compatible with the spec's `response_type`.

**Expected type mapping** (spec `response_type` → acceptable parquet dtypes):
```
likert_4      → Int8
likert_5      → Int8
binary        → boolean  (acceptable also: category — log as WARNING, not ERROR)
single_select → category
multi_select_n → object  (Python list column)
numeric_open  → Int16
open_text     → string
```

**Known intentional mismatch (WARNING, not ERROR):**
`q_sex` has `response_type: binary` in the spec but is stored as `category`
("Male"/"Female") in the parquet. This is correct — sex stores labels.
All other mismatches are ERROR.

**Severity:** Missing question_ref → ERROR. Wrong dtype → ERROR (except q_sex → WARNING).

---

### Check 2 — Value range checks (ERROR if any violation found)

| Column | Expected range | Dtype |
|--------|---------------|-------|
| `q_nps_score` | 0–10 inclusive | Int16 |
| `q_coverage_understanding` | 1–4 | Int8 |
| `q_claim_process_understanding` | 1–4 | Int8 |
| `q_financial_stress` | 1–5 | Int8 |
| `q_confidence_pay` | 1–5 | Int8 |
| `q_worth_premium` | 1–5 | Int8 |
| `q_renewal_intent` | 1–5 | Int8 |
| `q_client_age` | 18–100 | Int16 |

For each: count rows outside the valid range (ignoring NaN). Log ERROR if count > 0.

---

### Check 3 — Skip-logic consistency (ERROR if violation > 1% of base; WARNING if > 0%)

These checks verify that conditional routing in the survey was respected:

| Check | Description |
|-------|-------------|
| SL-1 | `q_claim_submitted` non-null only where `q_insured_event_12m == True` |
| SL-2 | `q_no_claim_reason` non-null only where `q_claim_submitted == False` |
| SL-3 | `q_claim_result` non-null only where `q_claim_submitted == True` |
| SL-4 | `q_claim_challenges_experienced` non-null only where `q_claim_submitted == True` |
| SL-5 | `q_child_improvements` non-empty list only where `q_child_wellbeing == "Yes"` |
| SL-6 | `flag_negative_coping` non-null only where `q_insured_event_12m == True` |

For each check: report violation count and % of base. ERROR if > 1%. WARNING if 0 < n ≤ 1%.

---

### Check 4 — Insurance-type scope (ERROR if any violation)

Verify that out-of-scope cells are null (NaN) for each insurance-type-specific block:

| Columns | Scope condition |
|---------|----------------|
| `q_healthcare_access`, `q_medical_cost_change` | `is_health == True` |
| `q_crop_recovery_speed`, `q_crop_farming_change`, `q_renewal_intent` | `is_crop == True` |
| `q_credit_other_benefits`, `q_credit_other_benefits__a` through `__e`, `q_credit_additional_value` | `is_credit_life == True` |

For each column: count non-null rows outside the scope flag. ERROR if count > 0.

Note: `q_renewal_intent` is stored as an **Int8** Likert column (not category) —
use `.notna()` to check fill.

---

### Check 5 — Derived variable sanity (ERROR if assertion fails)

| Variable | Expected value |
|----------|---------------|
| `flag_negative_coping` True count | > 0 and ≤ 363 (in-scope rows with insured event) |
| `flag_negative_coping` NaN outside insured-event rows | = 0 violations |
| `flag_promoter` True count | exactly 924 |
| `flag_paid_claimant` True count | exactly 58 |
| `flag_child_wellbeing_denominator` True count | exactly 1,928 |
| `insurance_type` distribution | health=1672, crop=154, credit_life=285 |

All are ERROR-level if they fail.

---

### Check 6 — Fill-rate summary (INFO only — no ERROR/WARNING threshold)

For the 18 spec question_refs plus the 4 derived flags, report fill rate (% non-null).
Use the correct denominator for each:
- Insurance-type-scoped columns: denominator = rows where scope flag is True
- Conditionally asked columns (claim branch): note that low fill is expected
- All others: denominator = 2,111

Report as a Markdown table: `question_ref | scope | denominator_n | fill_rate | note`.
Add a note for columns where low fill is structurally expected (claims branch,
insurance-type-specific, crop-only q_renewal_intent).

---

## Deliverable: phase_d_validator.py

A script that:

1. Loads the parquet and the spec (using `load_spec`).
2. Runs all six checks in order.
3. On any ERROR-level finding: logs it, adds it to an error list.
4. After all checks: if any ERRORs → print summary, write report, **exit code 1**.
   If only WARNINGs or INFO → write report, **exit code 0**.
5. Writes `data_quality_report.md` (always — even if there are errors).

**Report structure (`data_quality_report.md`):**

```markdown
# Phase D Data Quality Report — VisionFund Insurance Survey 2026
Generated: <timestamp>

## Summary
- Dataset: 2111 rows × 130 columns
- Spec: <N> source questions, <N> metric variables
- Result: PASS / FAIL (N errors, N warnings)

## Check 1: Spec Alignment
[table: question_ref | spec_type | parquet_dtype | status]

## Check 2: Value Ranges
[table: column | valid_range | violations | status]

## Check 3: Skip-Logic Consistency
[table: check_id | description | base_n | violations | pct | status]

## Check 4: Insurance-Type Scope
[table: column | scope | out_of_scope_non_null | status]

## Check 5: Derived Variable Sanity
[table: variable | expected | actual | status]

## Check 6: Fill Rates
[table: question_ref | scope | denominator_n | fill_rate | note]
```

Use `PASS ✓`, `WARN ⚠`, `FAIL ✗` as status symbols.

---

## Requirements

- Use only `pandas`, `stdlib`, and the existing `report_spec` package. No new dependencies.
- Script runnable as: `python phase_d_validator.py`
  (paths hardcoded relative to script, or accepted as optional CLI args).
- The report must be readable standalone — include column counts and thresholds
  in the table, not just pass/fail symbols.
- Exit code 1 if any ERROR; exit code 0 otherwise.

---

## Important: what this validation proves

When Phase D passes cleanly, it means:
- Every question_ref the analysis engine will ask for exists and is correctly typed
- Value ranges are valid for all numeric/ordinal columns  
- Skip-logic routing produced no impossible combinations
- Insurance-type scoping is correct (no data bleed between product blocks)
- Derived flags match their expected definitions

This is the integration point where Box 2 (Data Loader) connects to Box 3 (Analysis Engine).
A clean Phase D exit code 0 is the signal that Box 3 can consume the data.
