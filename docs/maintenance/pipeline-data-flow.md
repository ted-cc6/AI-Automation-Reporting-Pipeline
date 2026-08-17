# Pipeline Data Flow: From Uploaded CSV to Finished Report

This document traces the Cupboard Week pipeline stage by stage, from a raw
KoBoToolbox CSV upload to a finished `.docx`, with concrete file paths and
function names. It is the most detailed of the maintenance documents; read
[architecture-overview.md](architecture-overview.md) first for the
higher-level picture of how Cupboard Week, Gender Study, and Core Credit
differ.

A terminology note up front: prior project memory referred to this
pipeline's analysis stage as having "Tracks A through D" plus a "Track E"
qualitative pipeline. A full-repository search found no such grouping
anywhere in code, comments, or documentation. The only surviving trace is a
single code comment referring to a "Track D scale fix" attached to the
`SCHEMA_VERSION` bump described below. The real structural unit is the
**section** (one Python module per report part), not a "track," and this
document describes the pipeline in those terms rather than perpetuating a
label that does not exist in the codebase.

"Cupboard Week" is the product name for this pipeline as used in the
dashboard (`dashboard/web/src/CupboardWeekApp.tsx`); there is no separate
directory of that name containing code (`cupboard_week_host/` exists but is
empty, see [module-reference.md](module-reference.md)).

## Stage 1: Ingestion and cleaning (`data_loader/`)

Orchestrated by `run_pipeline.py` (CLI, runs each step as a subprocess) and,
in-process, by `dashboard/api/pipeline_runner.py`'s `_load_and_clean()`.
Both run the same five scripts in the same order, against one of two
configuration pairs: `data_loader/column_mapping.csv` +
`value_coding_map.yaml` for the Africa/Vietnam schema, or
`data_loader_larco/column_mapping.csv` + `value_coding_map.yaml` for the
LARCO schema. Note that `data_loader_larco/` contains no Python code at
all, only these two configuration files; the LARCO schema reuses the exact
same five step scripts with different configuration inputs, selected via a
`--dataset-schema larco` flag.

1. **`data_loader_profiler.py`** (Step 1 of 5). Reads the raw CSV with
   `pd.read_csv(delimiter=";", encoding="utf-8", dtype=str, keep_default_na=False)`,
   computes fill rate, distinct-value count, and top-5 values per mapped
   column, and writes `profile_report.md`. Read-only; produces no parquet
   output.
2. **`data_loader_transformer.py`** (Step 2 of 5). The real raw-CSV-to-typed-parquet
   step. In order: insurance-type routing and scope-sentinel fill,
   metadata/identity renames, Likert-4/5 coding, binary coding, multi-select
   child coding, multi-select list derivation, NPS-to-integer conversion
   with a 0-10 range check, age-to-integer conversion, single-select
   columns to pandas `Categorical`, and free-text passthrough. Column
   resolution is header-text-first with a positional index as fallback,
   so the pipeline self-heals if a later CSV export reorders columns, but
   raises on an unresolvable naming collision. Writes `survey_clean.parquet`.
3. **`data_loader_screening.py`** (Step 3 of 5). This is the dedup and
   test-row screening step. Four checks actually remove rows, run in this
   order:
   - **Test and QA rows**: a case-insensitive, word-boundary regex match of
     `test`, `demo`, `training`, `pilot`, or `qa` against the `client_id`,
     `enumerator`, or `branch` columns. Matching rows are removed entirely.
   - **Exact-content duplicates**: two rows are treated as duplicates if
     they match on every column except a short list of KoBoToolbox
     logistics columns (submission ID, UUID, submission time, row index,
     device info, interview start/end time, enumerator). One canonical
     copy is kept: the earliest submission time, tie-broken by the lowest
     row index.
   - **Non-consenting rows**: rows where the survey consent question is
     explicitly `False`. Missing/unmapped consent answers are treated as
     `False` explicitly, to avoid a coding bug where an unmapped column
     could silently empty the entire dataset.
   - **Out-of-scope country rows**: an allow-list, not a deny-list, of
     countries valid for the current dataset schema. As of the 2026 wave
     this allow-list includes the LARCO countries as well, since LARCO was
     folded into the same schema.
   Three additional checks are report-only and never remove rows: client-ID
   reuse with differing content, shared-UUID pairs with a similarity score,
   and interview-duration outliers (see the next section). Writes
   `screening_report.md` and `screening_summary.json`.

   Two figures circulate for this step and both are correct, just for
   different points in time. When this screening step was first added
   (2026-07-21), only the test/QA and duplicate checks existed, and on
   that quarter's real CSV they took the row count from 2,111 down to
   **2,105** (2 test rows plus 4 duplicates). The non-consenting and
   out-of-scope-country checks were added later, as part of the 2026-08-13
   region-scoping rollout (see
   [known-issues-log.md](known-issues-log.md)). With all four checks
   active, a real smoke-test run
   (`runs/Africa_2026_pipeline_smoke/screening_report.md`) shows 2,111
   rows after transform, then 2 test/QA rows, 4 duplicates, 7
   non-consenting rows, and 7 out-of-scope-country rows removed, leaving
   **2,091**. If you see either number quoted on its own, check which set
   of screening checks was active for that run before assuming it is
   wrong; the exact count also depends on the specific upload.
4. **`data_loader_derived.py`** (Step 4 of 5). Computes derived flag
   columns: `flag_negative_coping`, `flag_promoter` (NPS score of 9 or
   above), `flag_paid_claimant`, `flag_child_wellbeing_denominator`. Each
   flag is schema-aware: it is skipped when the active dataset schema does
   not have the source column it depends on (for example, LARCO has no
   insured-event-in-last-12-months column). Runs a set of structural
   sanity assertions afterward and exits with a non-zero status on failure.
5. **`data_loader_validator.py`** (Step 5 of 5). Six checks: spec
   alignment (see the dedicated section below), value-range checks,
   skip-logic consistency, insurance-type scope checks, derived-variable
   sanity, and fill-rate checks, each gated between Africa/Vietnam and
   LARCO variants. Writes `data_quality_report.md`; exits with status 1 on
   any error.

## Data quality flags and how a flagged country propagates

`find_duration_outliers()` lives inside `data_loader_screening.py`, not in
the root-level `data_quality_flags.py` (that module only consumes its
output). It computes each interview's duration, flags any interview under
40% of that run's own median duration, then checks per country whether that
country's own outlier rate is at least twice the overall rate (with a
minimum sample size), and whether at least half of that country's outliers
trace back to a single enumerator. This result is report-only within
Stage 1 and is written into `screening_summary.json` under a
`duration_outliers` key.

From there:

1. The analysis stage (Stage 2, below) reads `duration_outliers` back out
   of `screening_summary.json`.
2. `data_quality_flags.py`'s `get_flags()` merges it with any hand-entered
   override flags (empty by default) and auto-promotes only the
   concentrated findings (the ones meeting the enumerator-concentration
   threshold) into real flags.
3. The result is stored as a top-level `data_quality_flags` key in
   `analysis_results.json`.
4. **Headline exclusion** is a prompt-level instruction, not a Python-enforced
   filter: the qualitative synthesis prompt (built in `qualitative/llm_call.py`)
   tells the LLM that a flagged country's data must remain in every
   aggregate and theme count but must never be cited by name in the
   executive summary, top findings, or top actions.
5. **Verbatim-pool exclusion** is enforced deterministically in Python: a
   flagged country's candidate quotes are filtered out of the verbatim
   candidate pool before the synthesis call ever sees them.
6. Rendered into the finished `.docx` as a "Data Notes" subsection.

## Stage 2: Analysis (`analysis_engine/`)

The unit of computation is the **section**: one Python module per report
part under `analysis_engine/sections/`, each exposing a
`calculate(ds, segment_masks) -> dict` function. These are registered in a
`SECTIONS` list inside the root `run_analysis.py` script (not inside
`analysis_engine/` itself), and both the CLI (`run_analysis.py`) and the
dashboard (`pipeline_runner.py`, which imports the same registry rather
than duplicating it) call the same set of functions. A failure in one
section is recorded and isolated; it does not abort the whole run.

Concretely, per section:

- **`about_survey.py`** — respondent counts and the exclusion summary
  pulled from `data_notes`.
- **`part_1.py`** (Client Understanding and Value Perception) — bottom-two-box
  scoring on four inverted-Likert metrics (coverage understanding,
  claim-process understanding, worth of premium, renewal intent), broken
  out across every active demographic segment.
- **`part_2.py`** (Claims Experience) — a claims funnel (insured event to
  submitted to result) and ranked reasons/challenges.
- **`part_3.py`** (Financial Resilience) — scoring on financial stress,
  negative coping, alternative access, confidence to pay, and prior
  access.
- **`part_4.py`** (Child Wellbeing Outcomes) — NPS scoring and a
  correlation of NPS against child-wellbeing indicators.
- **`part_5.py`** (Child Wellbeing Drivers) — correlation and logistic
  regression of financial stress, understanding, worth of premium,
  renewal intent, confidence, and NPS against child wellbeing outcomes.
- **`part_6.py`** and **`part_7.py`** — significance-tested scorecards
  comparing claimants versus non-filers, and female versus male
  respondents.
- **`part_8.py`** — a composite Kling Index score. This is a dashboard-only
  metric: it deliberately has no corresponding `.docx` section and no
  entry in the generation-time report spec.
- **`part_9.py`** (Additional Services), **`part_10.py`** (Trend
  Comparison, see below), **`part_11.py`** (Credit Life Module), and
  **`part_12.py`** (Crop Module) — conditionally included depending on
  dataset schema, report scope, and whether a prior-year baseline was
  supplied. See [extension-guide.md](extension-guide.md) for exactly how
  this conditional inclusion, referred to informally as the "module
  manifest," works.

There is no "Track E" module inside `analysis_engine/`; the qualitative
pipeline is entirely separate (see the next section) and hands off only
through a file on disk (`qualitative_results.json`), not through any
in-process call from the analysis engine.

`SCHEMA_VERSION` is defined once, in `run_analysis.py`, currently `"1.5"`,
with an inline comment explaining the 1.4-to-1.5 change: an inverted Likert
scale was corrected, replacing top-two-box scoring with bottom-two-box
scoring for all positive-outcome Likert metrics. It is written into every
`analysis_results.json`'s `meta.schema_version` field. Unlike the
impression left by a bare version string, this value **is** checked at
runtime, just not inside the analysis stage itself: `generation/orchestrator.py`'s
data-loading step hard-fails with a `ValueError` if `meta.schema_version`
does not exactly equal `"1.5"` when Stage 4 begins. If you ever need to
bump `SCHEMA_VERSION`, update that check's expected value at the same time,
or every existing `analysis_results.json` on disk will suddenly be
rejected by report generation.

## Stage 3: Qualitative batching (`qualitative/`)

Rearchitected on 2026-08-13 from a single LLM call into a batched design.
The rationale is documented directly in `qualitative/llm_call.py`: the
original single-call design worked at roughly 2,100 respondents (about
52,600 input tokens), but broke once the 2026 wave folded LARCO into the
same schema, pushing the portfolio to roughly 3,800 or more respondents
(about 347,000 input tokens), with NPS-tagging output alone needing
56,000 to 75,000 tokens, exceeding the model's 65,536-token output ceiling.

- **What triggers a batch.** Every NPS follow-up response (promoters,
  passives, and detractors combined, roughly 90% of the response volume)
  is chunked into batches of 600 records, a size chosen to keep each
  batch's own tagging output comfortably under the output-token ceiling.
- **The batch call.** For each batch, the model produces one to three
  theme codes per record, a protection-flag scan, up to two verbatim
  candidates per report section per batch (a shortlist, not the final
  picks), and pricing/service classification for "not worth it" records.
- **The synthesis call.** Run once per report, given the small remaining
  groups of free-text responses that were not batched (together under 500
  records, in full), plus every batch's pooled output. This call produces
  the final verbatim quotes (exactly three per section), section-level
  insights, "not worth it" themes, other subthemes, the executive summary,
  top findings, and top actions.
- **Merging.** All pooling and merging of batch outputs happens in Python,
  in `call_gemini()`: theme tags are accumulated across batches, candidate
  quotes are filtered to exclude data-quality-flagged countries before the
  synthesis call ever sees them, and protection flags are deduplicated
  across the batch and synthesis calls, keeping the higher-severity copy
  when the same flag appears twice. The final merged data structure
  matches the pre-rearchitecture single-call shape exactly, so the
  downstream parsing code needed no changes.
- **Downstream.** `qualitative/parse_results.py` validates the required
  keys, computes theme counts, enriches verbatims and protection flags
  with the respondent's profile looked up by row ID, and writes
  `runs/{run_id}/qualitative_results.json`. Note this file carries its own
  schema version, currently `"1.1"`, which is a separate number from the
  analysis engine's `SCHEMA_VERSION`, do not conflate the two.

## Stage 4: Report generation (`generation/`)

Before writing this section, note a genuine naming trap: there are **two
separate files that could both be called "the report spec,"** and they are
not the same thing:

- **`insurance-report-spec.yaml`** (repository root) is the governance and
  design spec, validated by the `report_spec/` package against 13 code-level
  rules. This is where `fill_mode` (`auto`, `hybrid`, `bespoke`) and
  `source_questions` live. It is validated only by the manual
  `inspect_spec.py` diagnostic and by `coverage_report.py`/the test suite.
  It is not loaded by `run_pipeline.py` or by `pipeline_runner.py` during a
  real run.
- **`generation/report_spec.yaml`** is a different, much larger, flat file
  that actually drives report generation: for each part and section, it
  declares which metric paths inside `analysis_results.json` and
  `qualitative_results.json` feed in, formatting, and which LLM model to
  use. It contains no `fill_mode` field at all.

The consequence of this split is worth internalizing: **`fill_mode` is a
design-intent classification that the real generation code does not act
on.** Every report part gets exactly one LLM call that produces all of its
subsection text, regardless of whether the governance spec labels that part
`auto`, `hybrid`, or `bespoke`. If a future change is meant to make
generation actually vary by `fill_mode`, that logic does not exist yet and
would need to be added to `generation/writer.py`.

The real generation flow:

1. `generation/orchestrator.py`'s `preflight_check()` confirms
   `analysis_results.json` and `qualitative_results.json` exist, that
   visuals exist, and flags any metric with suspiciously low data coverage
   as a likely column-mapping bug (distinct from the deliberate
   small-sample suppression the analysis engine already applies).
2. `orchestrate()` builds one "package" per report part, where the set of
   real parts is derived directly from whichever `parts` keys are actually
   present in `analysis_results.json`, so it always stays in lockstep with
   Stage 2's section registry rather than needing a second hardcoded list
   maintained in parallel.
3. `generation/writer.py`'s `write_all_parts()` makes one LLM call per
   part, using a shared house-voice system prompt built once per run (with
   a single-country variant swapped in for single-country runs), with
   retries and exponential backoff. A part that exhausts its retries is
   marked as failed and rendered as a manual-write-up placeholder rather
   than aborting the whole run.
4. `generation/validate_output.py`'s `validate_report()` runs advisory
   checks only; it never blocks assembly.
5. `generation/assembler.py`'s `assemble()` does the actual `.docx`
   layout, using `python-docx` only, with no LLM calls at all.

Provider routing for both LLM-calling stages (qualitative tagging and
report writing) goes through the single `llm_providers.py` module at the
repository root, which handles Gemini, Anthropic, and OpenAI. Its internal
docstring still claims a path of `dashboard/api/llm_providers.py`, which is
stale; the file lives at the repository root and there is no copy under
`dashboard/api/`.

Summary of which stages touch an LLM and which are pure computation: Stage
1 (data loading) and Stage 2 (analysis) never call an LLM; Stage 3
(qualitative tagging) and Stage 4's writing step do; Stage 4's assembly
step does not.

## Trend comparison and the prior-year baseline

The "Prior year's data for trend comparison" upload described in
[quick-start.md](../user-guide/quick-start.md) is implemented by
`pipeline_runner.py`'s `_build_prior_baseline()`, called before Stage 1 of
the main run when a prior CSV was supplied. It runs only Stage 1 (clean)
and Stage 2 (analyze) against the standalone prior CSV, meaning no
qualitative tagging and no report generation, and therefore no LLM calls at
all for the baseline itself. It never raises: any failure degrades
gracefully to "no trend comparison" for the main run rather than failing
it. Its output is written to its own `analysis_results.json` under a
`{run_id}__prior` run identifier.

The merge into Part 10 works like this: Part 10's calculation function
reads the prior run's own `parts.part_10.current` snapshot, deliberately
self-referential so that wave N compares against wave N minus 1's own Part
10 output rather than depending on some other section's JSON shape staying
stable across schema versions. Only two of the five trend indicators are
comparable across the 2025-to-2026 instrument change (first-time access and
client satisfaction NPS); the other three are structurally blocked from
ever exposing a prior value, and the comparable pair's delta and
significance are computed on the subset of countries common to both waves,
while the headline figure shown everywhere else in the report retains its
full scope. The result is written into the main run's own
`analysis_results.json`, under `parts.part_10.comparison`.

Rendering Part 10's prose still goes through Stage 4's ordinary LLM call
like every other part; the "no LLM" property applies only to constructing
the prior-wave baseline data, not to writing up the comparison in the final
report text.

## Where `report_spec`/R5 and the real data actually intersect

Two genuinely different mechanisms are easy to conflate, so it is worth
being precise:

- **R5**, the rule inside `report_spec/rules.py` that checks every metric
  variable reference against a subsection's declared `source_questions`,
  is a static, file-only check. It never reads a CSV or a parquet file. It
  runs only inside the manual `inspect_spec.py` diagnostic and the test
  suite, never as part of a real pipeline run.
- The genuine runtime check against real data is Stage 1's spec-alignment
  check inside `data_loader_validator.py`, which loads the governance spec
  and verifies that every declared source question actually exists as a
  column in the cleaned parquet, with a data type matching what the spec
  declares. This check is explicitly skipped for the LARCO schema, logged
  as a warning rather than silently passed, because no LARCO-equivalent
  governance spec exists yet.

So: nothing in the real run path re-validates R5's metric-reference graph
against live data. The only two places the governance spec touches a real
run are that Stage 1 presence/type check (skipped for LARCO) and Stage 2's
unconditional `load_spec()` call inside `load_survey_data()`, which loads
and attaches the spec but does not itself enforce anything beyond the spec
loading successfully at all.
