# VisionFund Insurance Report Spec — Python Package

A small Python 3.11+ package that loads the report-spec YAML, validates it against
the JSON Schema and 13 code-level rules, and exposes the spec as typed Pydantic v2
objects for a downstream pipeline.

## Install

```bash
pip install -r requirements.txt
```

## Quick start

```python
from report_spec import load_spec

result = load_spec("insurance-report-spec.yaml")   # raises on any ERROR
print(result.is_valid)                              # True
for part, sub in result.spec.subsections():
    print(part.part_id, sub.subsection_id, sub.fill_mode)
```

Set `strict=False` to get a `LoadResult` even when errors exist:

```python
result = load_spec("insurance-report-spec.yaml", strict=False)
for f in result.errors:
    print(f)
```

## Run the diagnostic script

```bash
python inspect_spec.py
```

## Run tests

```bash
pytest tests/ -v
```

---

## Validation pipeline

`load_spec` runs three stages in order:

| Stage | What it checks | On failure |
|---|---|---|
| 1. YAML parse | Valid YAML syntax | ERROR finding, returns early |
| 2. JSON Schema | Draft 2020-12 structural rules | ERROR findings, returns early |
| 3. Code-level rules | R1–R13 (see below) | All collected; never returns early |

---

## Code-level rules (R1–R13)

| Rule | Description | Severity |
|---|---|---|
| R1 | `part_id` values must be exactly `[1,2,3,4,5,6,7]` in order | ERROR |
| R2 | Each part must have exactly one `N.insight` subsection | ERROR |
| R3 | `subsection_id` prefix must match enclosing `part_id` | ERROR |
| R4 | No duplicate `segment` in `disaggregation` | ERROR |
| R5 | Every metric variable must appear in `source_questions` | ERROR / WARNING* |
| R6 | `correlation`, `significance_test`, `gap_analysis` require `against` | ERROR |
| R7 | `frequency_rank` requires `top_n` | ERROR |
| R8 | `benchmark_comparison` is out of scope — flag if used | ERROR |
| R9 | `verbatims_required: true` requires `verbatim_count` | ERROR |
| R10 | `verbatim_block` output requires `qualitative.verbatims_required: true` | ERROR |
| R11 | `analysis_prose` / `insight_prose` output requires `word_cap != null` | ERROR |
| R12 | `benchmark_overlay: true` requires `report_metadata.benchmark_dataset_id` | ERROR |
| R13 | `auto` subsection with `powerbi_screenshot` visual — advisory | WARNING |

### KNOWN_GAP (R5 WARNING)

When an R5 violation involves a variable that is an *intentionally derived* column
(not a raw survey column), it is downgraded from ERROR to WARNING with
`category = KNOWN_GAP`. The current known-derived variables are:

- `q_coping_mechanisms` — a composite binary flag built from options c/d/e/f of the
  multi-select coping-mechanisms question (negative coping indicator)
- `q_nps_score` — used as both a raw score and as a derived promoter flag (score ≥ 9)
- `q_claim_result` — a derived binary paid-claimant flag (value = "It was approved and paid")

The pipeline is expected to materialise these derived columns before running metrics.

---

## `LoadResult` API

| Attribute / property | Type | Description |
|---|---|---|
| `.spec` | `ReportSpec \| None` | Parsed spec; `None` if parsing failed |
| `.findings` | `list[Finding]` | All findings (errors + warnings) |
| `.is_valid` | `bool` | `True` when `spec is not None` and no ERRORs |
| `.errors` | `list[Finding]` | ERROR-severity subset |
| `.warnings` | `list[Finding]` | WARNING-severity subset |

## `ReportSpec` convenience methods

| Method | Returns |
|---|---|
| `.subsections()` | Flat `list[(Part, Subsection)]` in document order |
| `.auto_subsections()` | Filtered to `fill_mode = auto` |
| `.hybrid_subsections()` | Filtered to `fill_mode = hybrid` |
| `.bespoke_subsections()` | Filtered to `fill_mode = bespoke` |
| `.all_source_questions()` | Deduplicated `list[SourceQuestion]` across all subsections |
| `.referenced_variables()` | `set[str]` of all `question_ref`s used in metrics |
| `.derived_variables()` | `set[str]` of refs in metrics but absent from `source_questions` |

---

## Coverage Report CLI

`coverage_report.py` is a planning and stakeholder-communication tool. It answers
**"what does this spec commit us to and how much is automatable?"** without touching
survey data or making network calls.

### Install

`rich` is optional but strongly recommended — it renders the Markdown tables in the
terminal with colour and alignment:

```bash
pip install -r requirements.txt   # includes rich>=13.0
```

### Invocations

```bash
# Full report printed to terminal
python coverage_report.py insurance-report-spec.yaml \
    --schema insurance-report-spec.schema.json

# Full report + write Markdown file
python coverage_report.py insurance-report-spec.yaml \
    --schema insurance-report-spec.schema.json \
    --markdown coverage.md

# Per-part breakdown for Part 4 only
python coverage_report.py insurance-report-spec.yaml \
    --schema insurance-report-spec.schema.json \
    --part 4

# Print only the data-request checklist
python coverage_report.py insurance-report-spec.yaml \
    --schema insurance-report-spec.schema.json \
    --section data_demands
```

Available `--section` values: `header`, `automation_coverage`, `per_part_breakdown`,
`data_demands`, `derived_variables`, `qualitative_footprint`, `visuals_manifest`.

### Run tests

```bash
pytest tests/test_coverage_report.py -v
```

### Sample output (plain text, real spec)

```
# VisionFund Insurance Impact Report 2026

Template version: 2.0 | Priority segments: female, male, claimant, non_claimant
Total: 7 parts, 23 subsections

## 2. Automation Coverage
| fill_mode | count | %   | meaning                                               |
| --------- | ----- | --- | ----------------------------------------------------- |
| auto      | 0     | 0%  | Pipeline computes everything; no human writing        |
| hybrid    | 4     | 17% | Pipeline computes inputs; human writes interpretation |
| bespoke   | 19    | 83% | Human writer only; pipeline renders scaffold          |

**Automatable (auto+hybrid): 4 of 23 subsections (17%)**

Note: 7 of 19 bespoke subsections are deliberate N.insight synthesis blocks —
intentionally human-written end-of-part synthesis, not automation gaps.

## 4. Data Demands (use this as the row-level data request checklist)
Spec consumes 18 distinct survey questions across 7 survey section(s).
...

## 7. Visuals Manifest (screenshot/export work-list)
...
⚠ Duplicate visual referenced: `NPS — Score, Split & Drivers` appears in
  subsections: 4.2, 4.3 — confirm this is intentional or correct the spec.
```

### Programmatic use (e.g. in a pipeline or notebook)

```python
from report_spec import load_spec
from coverage_report import generate_coverage_report

result = load_spec("insurance-report-spec.yaml", strict=False)
report_md = generate_coverage_report(result.spec, result.findings)
print(report_md)

# Single section
checklist = generate_coverage_report(result.spec, section_filter="data_demands")
```
