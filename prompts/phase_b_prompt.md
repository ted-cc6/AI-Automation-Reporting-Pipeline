# Phase B — Value Coding, Type Normalisation & Insurance-Type Routing

## Context

You are building Phase B of a data loader for the VisionFund Insurance Client Survey 2026.
Phase A produced two artifacts that you will use as inputs:
- `column_mapping.csv` — maps each raw CSV column to a `question_ref`, category, and parent_ref
- `profile_report.md` — per-column fill rates and top-5 observed values

Phase B has one job: transform raw string values into clean, typed fields. Every coding
decision must be visible in a reviewable artifact (`value_coding_map.yaml`) before
the transformation script consumes it. Do not hardcode value translations in Python.

---

## Inputs

**Raw CSV:**
`data/Insurance_Survey_2026_-_LIVE_-_latest_version_-_English_en_-_2026-06-25-16-53-33.csv`
Delimiter: `;` | Encoding: UTF-8 | Rows: 2,111 | Columns: 133

**Column mapping:** `column_mapping.csv`

---

## Key findings from Phase A profiling (carry these into Phase B)

These are the actual raw values observed in the data. Use them verbatim in
`value_coding_map.yaml` — do not guess or approximate.

### Insurance_Type (col 8) — raw values and counts
```
"Health Insurance"    → 1,672 respondents  (79.2%)
"Enhanced Credit Life" → 285 respondents   (13.5%)
"Crop Insurance"      →  154 respondents   (7.3%)
```
These three values are the only values present. Clean slugs: `health`, `credit_life`, `crop`.

### Type-specific section routing (confirmed by fill rates)
The fill rates in the profile are fully explained by insurance-type routing:
- Health block (cols 86–87): 79.2% fill = Health Insurance respondents only
- Crop block (cols 89–90): 7.0% fill = Crop Insurance respondents only
- Credit Life block (cols 92–98): 13.5% fill = Enhanced Credit Life respondents only
- col 80 (`q_renewal_intent`): 7.0% fill — Vietnam/crop-specific question
  (question text references "700,000 VND/hectare") — treat as crop-scoped

### Likert-4 observed values (cols 11, 12)
```
"a. Very good"
"b. Good"
"c. Poor"
"d. Very poor"
```

### Likert-5 observed values — vary by question, all follow "letter. label" pattern

**q_financial_stress (col 63):**
```
"a. Significantly reduced"
"b. Somewhat reduced"
"c. No effect"
"d. Somewhat increased"
"e. Significantly increased"
```

**q_confidence_pay (col 81):**
```
"a. Very confident"
"b. Somewhat confident"
"c. Neither confident nor not confident"
"d. Somewhat not confident"
"e. Not confident at all"
```

**q_worth_premium (col 79):**
```
"a. Definitely worth it"
"b. Somewhat worth it"
"c. Neither worth it nor not worth it"
"d. Somewhat not worth it"
"e. Definitely not worth it"
```

**q_renewal_intent (col 80):**
```
"a. Definitely would renew"
"b. Probably would renew"
"c. Not sure"
"d. Probably would not renew"
"e. Definitely would not renew"
```

### Binary question observed values (NOT multi-select children)
Binary standalone questions use `"a. Yes"` / `"b. No"` — not `"1"`/`"0"`.
Affected columns: q_insured_event_12m (col 25), q_claim_submitted (col 26),
q_claim_challenges_experienced (col 31), q_prior_access (col 83).

### Multi-select child observed values (cols 14–20, 33–38, 42–49, etc.)
Multi-select children use `"1"` (selected) or `"0"` (not selected) — not `"True"`/`"False"`.
This is distinct from binary standalone questions above.

### NPS (col 75 — q_nps_score)
String representations of integers: `"0"` through `"10"`.
All 11 values observed (distinct_count = 11).

### Single-select questions — observed values

**q_claim_result (col 29):**
```
"a. It was approved and paid"
"b. It was approved and not yet paid"
"c. It is currently in process"
"d. It was rejected"
"e. I don't know"
```

**q_payout_cost_coverage (col 30):**
```
"a. All of the cost"
"b. Most of the cost"
"c. Some of the cost"
```

**q_no_claim_reason (col 27):**
```
"a. The loss was not significant"
"c. I did not know how to file a claim"
"d. Claim process is cumbersome"
"e. I was not covered at that time"
"f. Other (please specify)"
```
Note: option "b." is absent from the data — do not invent it.

**q_claim_channel_preferred (col 22):**
```
"a. Through an MFI officer coming to collect the documents"
"c. Whatsapp or other messages applications"
"d. Directly at VisionFund office/ counter"
"e. Through the insurer smartphone application"
"f. Other (please specify)"
```
Note: option "b." is absent from the data.

**q_child_wellbeing (col 64):**
```
"a. Yes"
"b. No"
"c. Do not support any children"
```

**q_healthcare_access (col 86):**
```
"a. Yes"
"b. No"
"c. Not applicable (I/my family have not needed medical care)"
```

**q_medical_cost_change (col 87):**
```
"a. Much lower"
"b. Slightly lower"
"c. No difference"
"d. Slightly higher"
"f. Not applicable (I have not needed medical care)"
```
Note: option "e." is absent from the data.

**q_alternative_access (col 84):**
```
"a. Very difficult"
"b. Slightly difficult"
"c. Neither difficult nor easy"
"d. Slightly easy"
"f. I don't know"
```
Note: option "e." is absent from the data.

**q_crop_recovery_speed (col 89):**
```
"a. Immediately or within 1 month"
"b. After 1–3 months"
"c. After more than 3 months"
```

**q_crop_farming_change (col 90):**
```
"a. Very much improved"
"b. Slightly improved"
"c. No change"
"d. Got slightly worse"
```

**q_credit_additional_value (col 98):**
```
"a. Very valuable"
"b. Somewhat valuable"
"c. Neither valuable nor not valuable"
"e. Not valuable at all"
"f. I am not aware of the additional benefits"
```
Note: option "d." is absent from the data.

**q_services_helped (col 61):**
```
"a. Very helpful"
"b. Somewhat helpful"
"c. Neither helpful nor unhelpful"
"d. Not very helpful"
```

**q_client_education (col 101):**
```
"a. Tertiary"
"b. Upper Secondary"
"c. Lower Secondary"
"d. Primary"
"e. None"
```

**q_household_size (col 102):**
```
"a. 1-3 People"
"b. 4-6 People"
"c. 7 or more People"
```

**q_sex (col 103):**
```
"a. Male"
"b. Female"
```

**q_disability (col 104):**
Distinct count = 3. Actual values not fully captured in top-5; expected options are Yes/No/partial.

**q_client_age (col 100):** String integers (e.g., "45", "40", "50"). Convert to int.

### Important data quality note
`q_bundled_services_used` (col 52) and its children (cols 53–59) have only 0.4% fill
(~9 respondents). This section is effectively empty for this dataset. Transform it
using the same rules as other multi-select groups but flag it clearly in the coding map.

---

## Step 1 (mandatory first): Insurance-type routing

Before any other transform, create a clean `insurance_type` column and scope flags.

**Routing rules:**
```
"Health Insurance"     → insurance_type = "health"
"Enhanced Credit Life" → insurance_type = "credit_life"
"Crop Insurance"       → insurance_type = "crop"
```

**Scope flags** (boolean columns added to the dataframe):
```python
df["is_health"]       = df["insurance_type"] == "health"
df["is_crop"]         = df["insurance_type"] == "crop"
df["is_credit_life"]  = df["insurance_type"] == "credit_life"
```

**Out-of-scope sentinel:**
For cells that are empty BECAUSE the respondent is the wrong insurance type
(not because they skipped), store the string sentinel `"__SCOPE_NA__"` — not
pandas `NaN` or empty string. This lets downstream code distinguish:
- `""` or `NaN`  → respondent skipped a question that applied to them
- `"__SCOPE_NA__"` → question did not apply to this respondent's insurance type

Apply `"__SCOPE_NA__"` to:
- Cols 86–87 where `insurance_type != "health"`
- Cols 89–90 where `insurance_type != "crop"`
- Cols 92–98 where `insurance_type != "credit_life"`
- Col 80 where `insurance_type != "crop"` (VND/hectare framing confirms crop-only scope)

Only apply the sentinel to cells that are currently empty/null. If a cell already has
a non-empty value outside its expected scope, log a WARNING rather than overwriting it
(this would indicate a data routing error).

---

## Step 2: Value coding rules

### 2a. Likert scales → ordered integers

Both Likert-4 and Likert-5 questions follow the pattern `"a. Label"`, `"b. Label"`, etc.
The letter maps to the integer: `a=1`, `b=2`, `c=3`, `d=4`, `e=5`.

For each Likert column:
1. Create an integer column `{question_ref}` with value 1–4 or 1–5.
2. Create a string label column `{question_ref}__label` with the label part only
   (e.g., `"Very good"` not `"a. Very good"`).
3. For empty/null cells: leave both as `NaN` (genuine skip — not `"__SCOPE_NA__"`).

Likert-4 columns: `q_coverage_understanding` (col 11), `q_claim_process_understanding` (col 12).
Likert-5 columns: `q_financial_stress` (col 63), `q_confidence_pay` (col 81),
`q_worth_premium` (col 79), `q_renewal_intent` (col 80).

Do NOT include columns where the options don't have a clear ordered scale
(e.g., q_credit_additional_value uses `a/b/c/e/f` with "f. not aware" which
is not a point on the value scale — treat those as unordered single-select).

### 2b. Binary standalone questions → bool

These use `"a. Yes"` / `"b. No"`. Map:
- `"a. Yes"` → `True`
- `"b. No"` → `False`
- Empty/null → `NaN`

Columns: `q_insured_event_12m` (col 25), `q_claim_submitted` (col 26),
`q_claim_challenges_experienced` (col 31), `q_prior_access` (col 83).

### 2c. Multi-select children → bool

Children use `"1"` (selected) and `"0"` (not selected).
Map: `"1"` → `True`, `"0"` → `False`, empty → `NaN`.

Rename each child column from its raw name to:
`{parent_question_ref}__{option_letter}` (e.g., `q_coping_mechanisms__a`,
`q_coping_mechanisms__b`, etc.), where the option letter comes from the mapping
(the `/a.` suffix in the raw header).

### 2d. Multi-select parent columns → list of selected option labels

After renaming the children, derive a list-valued column for each multi-select parent.
The column name is the `question_ref` itself (e.g., `q_coping_mechanisms`).

The list contains the **label portion** of each selected option (stripping the `"a. "` prefix).
Example: if `/a` = 1 and `/b` = 1 and `/c` = 0: `["Use savings", "Borrow money"]`.
If no options selected (or all NaN): empty list `[]`.

The option letter-to-label mapping for each multi-select parent must be declared in
`value_coding_map.yaml` (see format below). Use the actual option text from the
CSV column headers.

After deriving the list column, drop the original raw parent concatenated-string
column (the one with 0.4% or similarly low fill from KoBoToolbox), since the
children are the authoritative source.

### 2e. NPS → integer

`q_nps_score` (col 75): strip whitespace, cast to int. Range 0–10.
Empty → `NaN`.

### 2f. Numeric open → int/float

`q_client_age` (col 100): cast to int. Empty → `NaN`.
No other numeric opens in the question_ref columns.

### 2g. Single-select → category string (cleaned)

For all remaining `question_ref` columns that are single-select but not Likert:
1. Strip the `"a. "` prefix to get the clean label string.
2. Store as a pandas `Categorical` with ordered=False.
3. No integer coding — downstream analysis will use the label directly.

Affected columns: `q_claim_result`, `q_payout_cost_coverage`, `q_no_claim_reason`,
`q_claim_channel_preferred`, `q_child_wellbeing`, `q_healthcare_access`,
`q_medical_cost_change`, `q_alternative_access`, `q_crop_recovery_speed`,
`q_crop_farming_change`, `q_credit_other_benefits` (multi-select, handle via 2d),
`q_credit_additional_value`, `q_services_helped`, `q_client_education`,
`q_household_size`, `q_sex`, `q_disability`, `q_bundled_services_used`.

Note on `q_sex`: `"a. Male"` → `"Male"`, `"b. Female"` → `"Female"`.
Store as Categorical.

### 2h. Free-text columns → string

Columns with category `free_text_child` and `question_ref` open-text columns
(q_nps_detractor_followup, q_nps_passive_followup, q_nps_promoter_followup,
q_comm_channel_effective, q_child_improvements, etc.):
- Strip leading/trailing whitespace.
- Keep as `str` (or `pd.StringDtype()`).
- Rename to `{parent_ref}__other_text` for free_text_child columns.
  For standalone open_text question_refs, keep the question_ref name as-is.

### 2i. Keep-metadata and keep-identity columns

Pass through unchanged, renaming to clean names:
- `Device Info` → `device_info`
- `start` → `interview_start`
- `end` → `interview_end`
- `Username` → `enumerator`
- `Region` → `region`
- `Country` → `country`
- `What is the client's ID number...` → `client_id`
- `To which branch does the client belong?` → `branch`
- `Insurance_Type` → `insurance_type_raw` (keep original alongside clean `insurance_type`)
- `_id` → `kobotoolbox_id`
- `_uuid` → `uuid`
- `_submission_time` → `submission_time`
- `_index` → `kobotoolbox_index`

---

## Deliverable 1: value_coding_map.yaml

This YAML file is the human-review checkpoint. It must contain every coding decision
made in steps 2a–2h. Write it before the Python script, so a reviewer can inspect
and correct it independently of the code.

Required structure:

```yaml
# value_coding_map.yaml — VisionFund Insurance Survey 2026
# Reviewed: [leave blank for reviewer to fill]

insurance_type_routing:
  "Health Insurance": health
  "Enhanced Credit Life": credit_life
  "Crop Insurance": crop

scope_rules:
  health_only_cols: [86, 87]
  crop_only_cols: [89, 90, 80]
  credit_life_only_cols: [92, 93, 94, 95, 96, 97, 98]
  sentinel: "__SCOPE_NA__"

likert_4:
  # Used for: q_coverage_understanding (col 11), q_claim_process_understanding (col 12)
  "a. Very good": {int: 4, label: "Very good"}
  "b. Good":      {int: 3, label: "Good"}
  "c. Poor":      {int: 2, label: "Poor"}
  "d. Very poor": {int: 1, label: "Very poor"}

likert_5:
  # Template — EACH likert_5 question has its own block below
  # because labels differ across questions even though the a=1..e=5 rule is constant
  q_financial_stress:
    "a. Significantly reduced": {int: 5, label: "Significantly reduced"}
    "b. Somewhat reduced":      {int: 4, label: "Somewhat reduced"}
    "c. No effect":             {int: 3, label: "No effect"}
    "d. Somewhat increased":    {int: 2, label: "Somewhat increased"}
    "e. Significantly increased": {int: 1, label: "Significantly increased"}
  # ... [fill in q_confidence_pay, q_worth_premium, q_renewal_intent the same way]

binary_standalone:
  "a. Yes": true
  "b. No":  false

multi_select_child:
  "1": true
  "0": false

multi_select_option_labels:
  # Maps each multi-select parent to its option letter → clean label mapping.
  # These labels populate the derived list column.
  q_coping_mechanisms:
    a: "Use savings"
    b: "Borrow money"
    c: "Sell assets or livestock"
    d: "Reduce food consumption or essential spending"
    e: "Take children out of school"
    f: "Closed business temporarily"
    g: "None of the above"
    h: "Other"
  # ... [fill in q_comm_channel_effective, q_claim_challenges, q_bundled_services_used,
  #      q_child_improvements, q_credit_other_benefits, q_vf_services_received,
  #      q_income_sources the same way]

single_select_strip_prefix:
  # For these columns: strip the "a. " prefix to get clean label.
  # List only columns that need non-obvious notes.
  q_sex:
    "a. Male": "Male"
    "b. Female": "Female"
  # ... [fill in other single-select columns]

column_renames:
  # keep_metadata and keep_identity renames
  "Device Info": device_info
  start: interview_start
  end: interview_end
  Username: enumerator
  Region: region
  Country: country
  # ... [fill in remaining renames]

notes:
  q_bundled_services_used: "Only 9 respondents (~0.4% fill) — effectively empty for this dataset. Transform is valid but do not draw conclusions from this data."
  q_renewal_intent: "Vietnam/crop-specific question (VND/hectare framing). Treat as crop-scoped; 7.0% fill matches Crop Insurance respondent count."
  multi_select_parents: "Parent concatenated-string columns are dropped after child columns are renamed and list column is derived."
```

Complete the YAML fully — every multi-select parent must have its full option map
in `multi_select_option_labels`. Every Likert-5 question must have its own block
in `likert_5`. Do not leave placeholder comments without filling them in.

---

## Deliverable 2: phase_b_transformer.py

A Python script that:

1. Loads `column_mapping.csv` and `value_coding_map.yaml`.
2. Loads the raw CSV (semicolon-delimited, UTF-8, all columns as `str`).
3. Applies transformations in this exact order:
   a. Insurance-type routing (scope flags + `"__SCOPE_NA__"` sentinel).
   b. Column renames (metadata/identity).
   c. Likert coding (integer + label columns).
   d. Binary standalone coding.
   e. Multi-select child coding (bool) + rename to `{parent_ref}__{letter}`.
   f. Multi-select list derivation (one list per parent).
   g. Drop original multi-select parent concatenated-string columns.
   h. NPS cast to int.
   i. Numeric open cast (q_client_age).
   j. Single-select prefix strip + cast to Categorical.
   k. Free-text strip and rename.
4. Logs a WARNING (do not raise) for any raw value not present in the coding map
   (unexpected values should not crash the script).
5. Writes the output to `data/survey_clean.parquet` using pyarrow.
6. Prints a completion summary: rows, final column count, and any unexpected-value
   warnings encountered.

Requirements:
- Use only `pandas`, `pyarrow`, `pyyaml`, and stdlib. No other dependencies.
- Load coding decisions from `value_coding_map.yaml`, not hardcoded in Python.
- All column position lookups use `raw_index` from `column_mapping.csv`
  (not header text), because the mapping confirmed 48 header-truncation mismatches.
- Script must be runnable as: `python phase_b_transformer.py`
  (paths are hardcoded relative to script location or accepted as optional CLI args).

---

## Important sequencing note

Write and complete `value_coding_map.yaml` first — in full. Then write
`phase_b_transformer.py`. The YAML is the artifact for human review;
it must be complete and independently readable without running any code.
