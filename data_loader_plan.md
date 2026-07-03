# Data Loader & Cleaner — Development Plan

Box 2 in the pipeline architecture. Every downstream box (analysis engine, report
generator) depends on this component. The goal is a single entry point,
`load_survey_data(...) -> CleanDataset`, that converts the raw KoBoToolbox CSV
export into a validated, typed, analysis-ready dataset whose `question_ref` column
names match the spec exactly.

Build these phases in order, as separate prompts. Carry each phase's output
artifact forward into the next. Do **not** start Phase B until you have reviewed
Phase A's mapping file.

---

## Phase A — Column mapping & profiling

**Goal:** Understand the file before writing a single transformation rule. The
mapping produced here is the single artifact most likely to be wrong, and
everything downstream inherits it.

**Inputs:** Raw CSV file.

**Key facts about the file (noted here to avoid silent failures):**

- Delimiter is **semicolon** (`;`), not comma. Any tool using default CSV parsing
  will produce a single-column dataframe. Pass `delimiter=";"` explicitly.
- 133 columns, ~2,111 response rows (KoBoToolbox export format).
- System metadata columns live at the end of the file (cols 124–132).

**Column categories to map — all seven must appear in the output:**

| Category | Description | Example columns |
|---|---|---|
| `question_ref` | Maps to a spec `q_`-slug | "How would you rate your understanding..." → `q_understanding_coverage` |
| `multi_select_child` | A `/a.`, `/b.`, `/c.` split of a parent question; record parent ref | cols 14–20 (children of col 13) |
| `free_text_child` | "If other, please specify:" — record parent question ref | col 21 → parent col 13 |
| `drop_scaffold` | Section header rows; survey scaffolding, not data | cols 10, 24, 41, 51, 62, 74, 82, 85, 88, 91, 99, 123 |
| `keep_identity` | KoBoToolbox metadata needed for deduplication and audit | `_uuid`, `_submission_time`, `_id`, `_index` |
| `drop_system` | KoBoToolbox system columns not needed downstream | `_validation_status`, `_notes`, `_status`, `_submitted_by`, `_tags` |
| `keep_metadata` | Interviewer/fieldwork columns to retain as context | `Device Info`, `start`, `end`, `Username`, `Region`, `Country`, client ID, branch, `Insurance_Type` |

**Output artifacts:**

1. **`column_mapping.csv`** — one row per raw column:
   `raw_index | raw_column_header | category | question_ref | parent_ref | notes`
   This file is the human-review checkpoint. Do not proceed to Phase B until it
   has been reviewed and corrected.

2. **Profile report** — per column: fill rate, distinct value count, top-5 values,
   sample. Flag columns with >20% missing as warnings.

---

## Phase B — Value coding, type normalisation & insurance-type routing

**Goal:** Transform raw string values into clean, typed fields. Every
coding decision must be visible in a reviewable artifact, not hardcoded.

**First step — insurance-type routing (must come before all other transforms):**

Column `Insurance_Type` (col 8) routes each respondent to one of three product
blocks. This must be resolved first:

1. Create a clean `insurance_type` categorical: `health | crop | credit_life`.
2. Mark cells in out-of-scope blocks as `expected_null` (not missing data):
   - Health block (cols 85–87): valid only where `insurance_type == "health"`
   - Crop block (cols 88–90): valid only where `insurance_type == "crop"`
   - Credit life block (cols 91–98): valid only where `insurance_type == "credit_life"`

If you skip this step, Phase D's fill-rate checks will fire false alarms for every
insurance-type-specific question.

**Remaining transforms (driven by a `value_coding_map.yaml` artifact):**

- Likert scales: decode "a. Very good / b. Good / c. Poor / d. Very poor" into a
  clean ordered integer (4/3/2/1) with a human-readable label column alongside.
- Binaries: standardise to Python `bool`.
- NPS: parse the 0–10 scale to a clean integer.
- Multi-select splits: collapse `/a.`, `/b.`, `/c.` child columns into a
  structured list field on the parent `question_ref`.
- Free-text children: keep as separate `{question_ref}_other_text` columns,
  paired to their parent.
- `expected_null` cells: store as a sentinel distinct from `NaN` so downstream
  code can distinguish "respondent skipped" from "question did not apply".

**Output artifact:** `value_coding_map.yaml` (reviewable before Phase C).

**Output data:** Typed dataframe with clean `question_ref` column names.

---

## Phase C — Derived variables

**Goal:** Compute the composite flags and segmentation variables that the spec's
metrics reference but that do not exist as raw columns.

Each derivation is a small, named, independently tested function.

| Derived variable | Logic | Source columns |
|---|---|---|
| `insurance_type` | Clean Health / Crop / Credit Life categorical | `Insurance_Type` (col 8) — promoted from routing step in Phase B |
| `flag_negative_coping` | `True` if respondent selected any of options c, d, e, or f in the coping question (col 41 block) | `/c` Sell assets, `/d` Reduce food, `/e` Take children out of school, `/f` Close business |
| `flag_promoter` | `True` if NPS score ≥ 9 | col 75 |
| `flag_paid_claimant` | `True` if claim result = "approved and paid" | col 29 |
| `denominator_child_wellbeing` | Exclude respondents who answered "do not support children" from child-wellbeing base (A8 denominator fix) | col 64 |

Note: `insurance_type` is listed here for completeness but is created in Phase B
routing. Treat Phase C as confirming it is present and correctly typed before
computing the flags that depend on it.

---

## Phase D — Validation & data-quality report (two checkpoints)

Validation runs at **two points**, not one. A Phase C bug can produce a dataset
that passes a single post-derivation check while the derivations are wrong.

**Checkpoint 1 — after Phase B, before derivations:**

- Every raw column mapped as `question_ref` or `multi_select_child` in Phase A
  is present in the typed dataframe.
- Expected value ranges hold (NPS 0–10, Likert 1–4, etc.).
- `expected_null` vs genuine `NaN` counts are consistent with skip-logic:
  e.g., nobody has a claim result (col 29) without a `Yes` to the insured event
  question (col 25).
- Insurance-type routing is self-consistent: out-of-scope block cells are
  `expected_null`, not mixed with real responses.
- Fill-rate report per column (warnings at <80%, errors at <50%).

**Checkpoint 2 — after Phase C, before handing to the analysis engine:**

- Every `question_ref` returned by `all_source_questions()` from the existing
  `report_spec` package is present in the cleaned dataframe and correctly typed.
  This is the loader-meets-spec integration check.
- Every derived variable flag exists, is boolean, and has a plausible base rate
  (e.g., `flag_promoter` between 20–80% — extreme values warrant a manual check).
- Referenced metric variables from `referenced_variables()` that are *not* in
  `all_source_questions()` (i.e., derived variables) are present and typed.

**Output:** `CleanDataset` object + a data-quality report listing all failures,
warnings, and fill rates. The loader should refuse to return data that fails any
ERROR-level check.

---

## Phase E — Loader API & integration

**Goal:** Wrap Phases A–D into one clean, typed entry point that the analysis
engine consumes.

```python
from survey_loader import load_survey_data, CleanDataset

dataset = load_survey_data(
    csv_path="data/Insurance_Survey_2026_....csv",
    column_mapping="column_mapping.csv",
    value_coding_map="value_coding_map.yaml",
    spec_path="insurance-report-spec.yaml",
    schema_path="insurance-report-spec.schema.json",
    strict=True,          # raise on ERROR-level quality failures
)
```

**`CleanDataset` should expose convenience accessors, not just a raw dataframe:**

```python
dataset.df                              # full clean dataframe
dataset.for_insurance_type("health")   # rows where insurance_type == "health"
dataset.claimants                       # rows where flag_paid_claimant == True
dataset.for_segment(Segment.female)    # rows matching a spec Segment enum value
dataset.quality_report                 # data-quality report from Phase D
```

Without these accessors, downstream code will re-implement the same filtering
logic ad hoc in multiple places. The accessor pattern mirrors the convenience API
already established in `ReportSpec` (`auto_subsections()`, `all_source_questions()`
etc.) — keep the pattern consistent.

**Cross-check on load:** The loader calls both `load_spec()` and runs Phase D
Checkpoint 2 internally, so any `question_ref` mismatch between the spec and the
real data is surfaced at load time, not silently propagated into analysis.

**Testing:** Each phase (A–D) should have its own test module, exercisable
independently with a small fixture CSV. The full `load_survey_data()` integration
test runs against the real file.

---

## Sequencing note

Do each phase as a separate prompt, carrying the output artifacts forward — exactly
as you did for the `report_spec` package. Phase A especially should be its own
prompt whose output you review before Phase B builds on it. The column mapping is
the one phase where your eyes on the real data matter more than the code.

The two `value_coding_map.yaml` and `column_mapping.csv` artifacts are the
human-in-the-loop checkpoints. Everything else is automatable.
