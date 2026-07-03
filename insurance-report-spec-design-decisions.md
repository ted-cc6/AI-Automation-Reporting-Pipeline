# Insurance Report Spec — Schema Design Notes

## 1. Field-by-field decisions

### `report_metadata`

| Field | Required? | Rationale |
|---|---|---|
| `name` | Yes | Identifies the run in logs and generated output headers |
| `template_version` | Yes | Breaking changes to the template would invalidate the spec; version-pinning catches mismatches early |
| `priority_segments` | Yes | Minimum one segment; forces the spec author to set the report-wide disaggregation baseline rather than leaving it implicit |
| `reporting_period` | No | Useful for labelling but not semantically needed by the pipeline |
| `regions` | No | A spec could cover multiple regions (or a single country); the pipeline uses this for benchmark lookups but can fall back to defaults |
| `benchmark_dataset_id` | No | Only required when a metric uses `benchmark_comparison`; made optional at metadata level because not all runs have benchmark data available |

### `parts`

`minItems: 7, maxItems: 7` encodes the "Golden Framework must not be expanded" rule directly in the schema. Part ordering and ID uniqueness require code (see §3).

### `subsection_id` pattern `^[1-7]\.([1-9][0-9]*|insight)$`

- Rejects `1.0` (zero-indexed subsections are not in the template)
- Rejects `8.1` (only 7 parts)
- Accepts `N.insight` for end-of-part synthesis blocks
- The subsection prefix must match the enclosing `part_id` — a JSON Schema cross-reference between a string pattern and a sibling integer is not expressible without `$data` (not Draft 2020-12 core); enforce in code.

### `fill_mode`

| Value | Meaning |
|---|---|
| `auto` | Pipeline computes all metrics and qualitative themes; output is ready for human review but no human writing is required |
| `bespoke` | Human writer does everything (insight blocks, NPS narrative synthesis); the pipeline only renders the scaffold |
| `hybrid` | Pipeline runs metrics and theme extraction; human writes interpretation from those pre-computed inputs |

The `if/then` block enforces: **an `auto` or `hybrid` subsection must have at least one `Metric` or a non-null `QualitativeConfig`, and at least one `SourceQuestion`.** This catches the most common authoring mistake (copying a subsection stub and forgetting to add the computation config). `bespoke` is deliberately exempt — a human can write without any structured input spec.

### `word_cap`

Nullable rather than absent because the *absence* of the field is ambiguous (was it intentionally omitted or forgotten?). Spec authors must explicitly set `null` for table-only subsections, making the decision visible in review.

### `source_questions`

Required at top level but `minItems` is not enforced for `bespoke` subsections — insight blocks synthesise from the whole section, not specific questions. The `if/then` enforces `minItems: 1` for `auto` / `hybrid`.

### `metrics.variables` vs `source_questions`

`source_questions` is the human-readable documentation layer (question text, survey section, response type, skip-logic). `metrics.variables` is what the pipeline actually queries. Keeping them separate means the pipeline can validate column names against a data dictionary independently of the documentation. Referential integrity (every variable in metrics must appear as a question_ref in source_questions) is a code-level rule.

### `disaggregation` per subsection vs `priority_segments` in metadata

Report-level `priority_segments` sets the default. Subsection-level `disaggregation` allows overrides: some sections need extra cuts (e.g., claimant vs non-claimant in §2) or fewer cuts (e.g., the correlation table in §5 doesn't need all segments). The `required` / `nice_to_have` flag lets the pipeline decide whether to skip a cut when cell sizes are too small.

### `visual`

Nullable because insight subsections have no dedicated Power BI visual. `powerbi_screenshot` source means a human must paste it — valid alongside any `fill_mode` because the visual step is independent of the analysis computation step.

### `outputs` `minItems: 1`

Every subsection must produce something; a subsection with an empty outputs list is a spec authoring error with no safe default.

### `QualitativeConfig`

`verbatims_required`, `verbatim_count`, and `verbatim_profile_fields` are separated rather than collapsed into a single boolean because the template consistently specifies count (2–3) and profile fields (gender, age, branch, claimant_status) — these are distinct decisions a spec author must make.

`client_protection_flag` is a boolean rather than a severity enum because the template is unambiguous: *"however few, these are surfaced as signals, not quantified."* The pipeline's job is binary (surface or don't surface); severity is a human call.

### `additionalProperties: false` throughout

Strict mode on all objects. Any unknown key is a schema violation. This catches typos (`word_cap` spelled `wordcap`) that would otherwise silently be ignored.

---

## 2. Controlled vocabulary rationale

### Segments (10 values)

Taken verbatim from the Golden Framework's stated list. No additions — the template says the list is fixed. If a new segment is needed, it should be added to the schema as a breaking change.

### MetricMethod (13 values)

Derived from the template's analytic requirements:

| Method | Used in |
|---|---|
| `top_two_box` / `bottom_two_box` | Likert 4-point scales throughout Product Understanding and Client Voice |
| `share` | Binary and single-select questions |
| `frequency_rank` | Preferred channels (§1.3), reasons for not claiming (§2.2), challenges (§2.3) |
| `claims_funnel` | The event → filed → paid pipeline in §2.1 |
| `nps_score` / `nps_split` | §4.2; kept separate because NPS score (integer) and promoter/passive/detractor split (three shares) are distinct outputs |
| `correlation` | §5.1 CWB driver analysis |
| `significance_test` | All gap comparisons (§5.2, §6, §7) |
| `gap_analysis` | §6 and §7 scorecard difference column |
| `benchmark_comparison` | §1.1 regional overlay |
| `confidence_interval` / `regression` | Available for deeper analyses but not required by the template; included to prevent spec authors creating free-text workarounds |

### OutputType (8 values)

`scorecard_table` and `correlation_table` are distinct from `table` because they have fixed row schemas defined by the template (the pipeline must know which specific structure to render).

---

## 3. Rules that JSON Schema cannot express — enforce in code

| # | Rule | Where to check |
|---|---|---|
| R1 | `part_id` values must be unique and exactly equal to `{1,2,3,4,5,6,7}` | On load, after schema validation |
| R2 | Each part must contain exactly one subsection whose `subsection_id` matches `N.insight` where `N` = `part_id` | Per-part check |
| R3 | `subsection_id` prefix (before the dot) must equal the enclosing `part_id` | Per-subsection check |
| R4 | `disaggregation` must not contain two items with the same `segment` value | Per-subsection check |
| R5 | Every `question_ref` in `metrics[].variables` must appear in the subsection's `source_questions` | Per-subsection check |
| R6 | When `method` is `correlation`, `significance_test`, or `gap_analysis`, the `against` field must be present | Per-metric check |
| R7 | When `method` is `frequency_rank`, the `top_n` field must be present | Per-metric check |
| R8 | When `method` is `benchmark_comparison`, `benchmark_source` must be present on the metric and `benchmark_dataset_id` must be set in `report_metadata` | Per-metric check + cross-document check |
| R9 | When `qualitative.verbatims_required` is `true`, `verbatim_count` must be present | Per-qualitative check |
| R10 | When `outputs` contains `verbatim_block`, `qualitative` must be non-null and `verbatims_required` must be `true` | Per-subsection check |
| R11 | When `outputs` contains `analysis_prose` or `insight_prose`, `word_cap` must not be `null` | Per-subsection check |
| R12 | When `benchmark_overlay` is `true`, `report_metadata.benchmark_dataset_id` must be set | Cross-document check |
| R13 | `auto` subsections should not reference `visual.source: powerbi_screenshot` unless the pipeline has an automated screenshot extraction step configured — warn, not error | Advisory check |

---

## 4. What is deliberately left out of the schema

- **Row-level data types**: The schema does not validate the survey data itself (column types, missing value codes). That belongs in a separate data dictionary schema.
- **Product-type filtering**: The survey has product-specific sections (Health, Crop, Enhanced Credit Life). The unified report template doesn't split by product, so no `insurance_type_filter` field was added. Spec authors can use `notes` and `source_questions[].survey_section` to document this.
- **Minimum cell size thresholds**: The `nice_to_have` priority flag signals that a cut should be skipped below threshold, but the threshold value itself is a pipeline configuration parameter, not part of the per-report spec.
- **Verbatim selection algorithm**: Whether verbatims are selected by semantic diversity, by sentiment extremes, or by quota is a pipeline concern, not a spec concern.
