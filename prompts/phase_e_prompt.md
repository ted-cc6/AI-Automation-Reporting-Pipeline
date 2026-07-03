# Phase E — Survey Loader API (`survey_loader.py`)

## Context

You are building Phase E (the final phase) of a data loader for the VisionFund Insurance
Client Survey 2026. Phases A–D have produced and validated:

```
data/survey_clean.parquet   — 2,111 rows × 130 columns (clean, validated)
insurance-report-spec.yaml  — the report spec
report_spec/                — existing Python package with load_spec(), ReportSpec, etc.
data_quality_report.md      — Phase D validation output (PASS, 0 errors)
```

Phase E creates `survey_loader.py` — the single import point for the analysis engine (Box 3).
The analysis engine will do:

```python
from survey_loader import load_survey_data
ds = load_survey_data()
# Then use ds.df, ds.health, ds.promoters, etc.
```

Phase E does NOT re-run the pipeline. It only loads and wraps the existing parquet.

---

## Parquet schema (relevant columns)

All columns present in `data/survey_clean.parquet` (130 total):

**Identity / metadata (str)**
```
device_info, interview_start, interview_end, enumerator, region, country,
client_id, branch, insurance_type_raw, kobotoolbox_id, uuid,
submission_time, kobotoolbox_index
```

**Insurance routing (str / bool)**
```
insurance_type        str       — "health" | "crop" | "credit_life"
is_health             bool      — True for 1,672 respondents
is_crop               bool      — True for 154 respondents
is_credit_life        bool      — True for 285 respondents
```

**Likert columns (Int8, nullable; 1=most positive, higher=worse)**
```
q_coverage_understanding      Int8  (1–4, n=2,104 non-null)
q_claim_process_understanding Int8  (1–4, n=2,104)
q_financial_stress            Int8  (1–5, n=2,104)
q_worth_premium               Int8  (1–5, n=1,957)
q_renewal_intent              Int8  (1–5, n=154; crop-only)
q_confidence_pay              Int8  (1–5, n=2,104)
```
Plus companion `*__label` string columns for each Likert.

**Binary (boolean, nullable)**
```
q_insured_event_12m           boolean — True=363, False=1,594, NaN=154
q_claim_submitted             boolean — True=153, False=210, NaN=1,748
q_claim_challenges_experienced boolean
q_prior_access                boolean
```

**Multi-select lists (object — Python list of str labels)**
```
q_comm_channel_effective, q_claim_challenges, q_coping_mechanisms,
q_bundled_services_used, q_child_improvements, q_credit_other_benefits,
q_vf_services_received, q_income_sources
```
Plus individual `*__a` / `*__b` … boolean child columns for each.

**Single-select (category)**
```
q_claim_channel_preferred, q_no_claim_reason, q_claim_result,
q_payout_cost_coverage, q_services_helped, q_child_wellbeing,
q_alternative_access, q_healthcare_access, q_medical_cost_change,
q_crop_recovery_speed, q_crop_farming_change, q_credit_additional_value,
q_client_education, q_household_size, q_sex, q_disability
```

**Numeric (Int16)**
```
q_nps_score       — 0–10, n=2,104 non-null
q_client_age      — 18–100
```

**Free text (string)**
```
q_nps_detractor_followup, q_nps_passive_followup, q_nps_promoter_followup,
q_comm_channel_effective__other_text, q_claim_channel_preferred__other_text,
q_no_claim_reason__other_text, q_claim_challenges__other_text,
q_claim_challenges__support_text, q_coping_mechanisms__other_text,
q_bundled_services_used__other_text, q_child_improvements__other_text,
q_vf_services_received__other_text, q_income_sources__other_text
```

**Derived flags (boolean, nullable)**
```
flag_negative_coping              — True=73, NaN for non-insured-event rows
flag_promoter                     — True=924, NaN where q_nps_score=NaN
flag_paid_claimant                — True=58, NaN where q_claim_result=NaN
flag_child_wellbeing_denominator  — True=1,928, False otherwise (no NaN)
```

---

## Deliverable: `survey_loader.py`

### 1. `CleanDataset` class

A lightweight wrapper around the loaded DataFrame. All properties return filtered
DataFrames (not copies — use boolean indexing). The class is read-only after
construction; do not expose a setter for `.df`.

```python
class CleanDataset:
    def __init__(self, df: pd.DataFrame, spec: ReportSpec) -> None:
        self._df = df
        self._spec = spec

    @property
    def df(self) -> pd.DataFrame:
        """Full dataset: 2,111 rows × 130 columns."""

    @property
    def spec(self) -> ReportSpec:
        """Parsed ReportSpec from insurance-report-spec.yaml."""

    @property
    def n(self) -> int:
        """Total respondent count (2,111)."""

    # ── Insurance-type splits ────────────────────────────────────────────
    @property
    def health(self) -> pd.DataFrame:
        """Health insurance respondents (n=1,672)."""

    @property
    def crop(self) -> pd.DataFrame:
        """Crop insurance respondents (n=154)."""

    @property
    def credit_life(self) -> pd.DataFrame:
        """Enhanced Credit Life respondents (n=285)."""

    # ── NPS segments ────────────────────────────────────────────────────
    @property
    def promoters(self) -> pd.DataFrame:
        """NPS promoters: score 9–10 (n=924)."""

    @property
    def passives(self) -> pd.DataFrame:
        """NPS passives: score 7–8 (n=609)."""

    @property
    def detractors(self) -> pd.DataFrame:
        """NPS detractors: score 0–6 (n=571)."""

    # ── Claims analysis ─────────────────────────────────────────────────
    @property
    def claimants(self) -> pd.DataFrame:
        """Respondents who submitted a claim (q_claim_submitted==True, n=153)."""

    @property
    def paid_claimants(self) -> pd.DataFrame:
        """Claimants whose claim was approved and paid (flag_paid_claimant==True, n=58)."""

    # ── Analysis bases ───────────────────────────────────────────────────
    @property
    def insured_event_base(self) -> pd.DataFrame:
        """Respondents who experienced an insured event in past 12m (n=363)."""

    @property
    def child_wellbeing_base(self) -> pd.DataFrame:
        """Respondents in the child wellbeing analysis base (n=1,928).
        Excludes 'Do not support any children' and NaN."""
```

**NPS mask note:** Use `q_nps_score` for NPS segments; treat NaN as excluded.
Passives: `(q_nps_score >= 7) & (q_nps_score <= 8)`.
Detractors: `q_nps_score <= 6` (and not NaN).

**Nullable boolean comparisons:** Use `== True` (not `.astype(bool)`) on nullable
boolean columns, since `pd.NA == True` → `pd.NA` (treated as False in boolean mask).

---

### 2. `load_survey_data()` function

```python
def load_survey_data(
    parquet_path: Path | str | None = None,
    spec_yaml_path: Path | str | None = None,
    spec_schema_path: Path | str | None = None,
) -> CleanDataset:
```

Default paths (relative to the module file's directory):
- `parquet_path` → `data/survey_clean.parquet`
- `spec_yaml_path` → `insurance-report-spec.yaml`
- `spec_schema_path` → `insurance-report-spec.schema.json`

**Steps:**
1. Resolve paths (convert str to Path, apply defaults).
2. Verify parquet exists; if not, raise `FileNotFoundError` with a message that
   tells the user to run the pipeline first:
   `"survey_clean.parquet not found at {path}. Run phase_b_transformer.py, phase_c_derived.py, and phase_d_validator.py first."`
3. Load the parquet: `pd.read_parquet(parquet_path)`.
4. Quick sanity check — verify the three required columns are present:
   `insurance_type`, `flag_promoter`, `flag_child_wellbeing_denominator`.
   Raise `ValueError` if any are missing, naming the missing columns.
5. Load the spec using:
   ```python
   from report_spec import load_spec
   result = load_spec(spec_yaml_path, spec_schema_path, strict=False)
   ```
   If `result.spec is None`, raise `RuntimeError("Report spec failed to load")`.
6. Return `CleanDataset(df, result.spec)`.

Log at INFO level: loading path, row/column count, spec source question count.

---

### 3. `__main__` block

When run directly (`python survey_loader.py`), print a human-readable summary:

```
Survey Loader — VisionFund Insurance Survey 2026
================================================
Dataset  : 2,111 rows × 130 columns
Spec     : 18 source questions

Insurance-type split:
  Health       : 1,672 respondents (79.2%)
  Crop         :   154 respondents ( 7.3%)
  Credit Life  :   285 respondents (13.5%)

NPS (n=2,104 scored):
  Promoters (9–10) :   924 ( 43.9%)
  Passives  (7–8)  :   609 ( 29.0%)
  Detractors (0–6) :   571 ( 27.1%)

Claims:
  Experienced insured event : 363 ( 17.2% of 2,111)
  Submitted a claim         : 153 ( 42.1% of insured-event base)
  Claim approved & paid     :  58 ( 37.9% of claimants)

Analysis bases:
  Child wellbeing base      : 1,928 (of 2,111)
  Negative coping base      :   363 (of 2,111)

All properties accessible.  Use load_survey_data() to get a CleanDataset.
```

Compute all numbers from the actual data (not hardcoded), so the summary reflects
any future re-run of the pipeline with updated data.

---

## Requirements

- File: `survey_loader.py` in the project root.
- Dependencies: `pandas`, `pathlib`, `logging`, `sys`, and the existing `report_spec`
  package. No new dependencies.
- No module-level code that runs on import (only function/class definitions and
  logging setup). Import is always safe and fast.
- `CleanDataset` properties must not raise on the expected data — they will be called
  repeatedly by the analysis engine without defensive error-handling at the call site.
- Do not re-run any pipeline phase (B/C/D) inside `load_survey_data()`. Trust the
  existing parquet.
- The `__main__` block must call `load_survey_data()` and work correctly end-to-end.
