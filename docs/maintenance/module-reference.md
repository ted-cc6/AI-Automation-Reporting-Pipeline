# Module Reference

A directory-by-directory inventory of the repository, for locating code
quickly. For how these pieces connect at runtime, read
[architecture-overview.md](architecture-overview.md) first; this document
is a reference to come back to, not a narrative to read start to finish.

Each entry gives: what the directory is for, its main entry point(s), who
calls into it, and its rough size/complexity.

## `analysis_engine/`

Pure Python statistics and aggregation library. No LLM calls happen here;
this is the deterministic "compute the numbers" layer of the Cupboard Week
pipeline (Stage 2).

- `country_config.py` — loads per-country YAML from `country_configs/`
  (see that entry below) via `load_country_config()`.
- `segments.py` / `stats.py` — build demographic segment masks and
  low-N-safe statistics; `LOW_N_THRESHOLD` guards against reporting
  unstable percentages from tiny subgroups.
- `sections/` — one module per report part (`part_1.py` through
  `part_12.py`, plus `about_survey.py`), each exposing a
  `calculate_fn(ds, segment_masks) -> dict` function that computes that
  part's metrics.

Note that the `SECTIONS`/`build_sections()` registry that ties these
section modules together does **not** live inside `analysis_engine/`
itself; it lives in the root `run_analysis.py` script, and both
`run_analysis.py` (CLI) and `dashboard/api/pipeline_runner.py` (dashboard)
import that same registry rather than each defining their own. If you add
a new section module here, you must also register it in `run_analysis.py`.

Medium size, around 15 files. Covered by `tests/test_part_4.py`,
`test_part_6.py`, `test_part_10.py`, `test_part_11.py`, `test_part_12.py`,
`test_about_survey.py`, and `test_stats.py`.

## `core_credit/`

A large, largely self-contained sibling project implementing the Core
Credit Impact Report as a multi-agent LangGraph pipeline. It is copied
into the Docker image as a whole directory and run as a subprocess, not
pip-installed as a dependency of the dashboard package.

Entry points:

- `agent/orchestrator/run_for_dashboard.py` — the machine-readable,
  JSON-streaming entry point the dashboard's `core_credit_runner.py`
  spawns as a subprocess.
- `agent/orchestrator/run_orchestrator.py` — an interactive CLI entry
  point with resume-from-checkpoint support, for local/manual runs.
- `agent/orchestrator/graph.py::build_graph()` — defines the actual
  LangGraph node graph. See the "Core Credit" section of
  [architecture-overview.md](architecture-overview.md) for how the tiers
  compose.

Major subpackages under `agent/`:

- `column_clean/` and `row_check/` — two standalone LangChain
  tool-calling agents (Claude Haiku 4.5) that clean columns and check row
  quality automatically at the start of a run. Each has its own
  `tools.py` and `config.yaml`; because both directories use the
  filename `tools.py`, the orchestrator's data-prep nodes load them onto
  `sys.path` one at a time rather than importing both simultaneously.
- `dashboard_visuals/` — filesystem-based lookup (`lookup.py`) that
  resolves which dashboard visual assets are available for a given run,
  independent of the rest of the pipeline.
- `analysis/` — the bulk of the report logic: `driver/` (six theme
  sections built directly: client_profile, poverty_likelihood,
  child_wellbeing, resilience, client_satisfaction,
  business_household_impact), `section_configs/` and `graph/` (three
  theme sections built through a smaller, config-driven sub-graph:
  financial_access, client_protection, agency), `synthesis/`
  (cross-cutting outputs: gender scorecard, client voices, executive
  summary), `schemas/` (Pydantic output shapes per section),
  `metrics_engine/`, `ppi_module/` (poverty likelihood scoring),
  `benchmark_module/` (external MFI Index benchmark lookups, degrades
  gracefully if the reference workbook is missing rather than crashing),
  `qualitative_agent/`, and `writer/` (the LLM prose-writing chain and
  its `section_prompts.py`).
- `report_assembly/` — `build_report.py` (defines
  `CROSS_CUTTING_SECTIONS` and `THEME_SECTIONS` and assembles them into a
  single report data structure), `completeness.py` (checks the
  assembled report for gaps and for "meta-text leaks," meaning LLM
  commentary that should not appear in final prose), and
  `translate_verbatims.py`.
- `report_render/` — `section_layout.py` (renders the assembled report
  into a `.docx` via `python-docx`) and `qa_review.py` (an automated QA
  pass over the rendered report).

Very large: dozens of subpackages, most with their own `requirements.txt`,
their own test suite (`agent/**/tests/`, separate from the top-level
`tests/` directory), and their own `output/` scratch directories
accumulating JSON and `.docx` files from prior manual runs (these are
development artifacts, not part of the deployed application).

## `cupboard_week_host/` and `dashboard/web/cupboard_week_host/`

Both are completely empty directories, no files at all. They appear to be
vestigial or placeholder directories from an earlier project layout.
Nothing in the codebase reads from or writes to them. Confirm with the
team before removing them, but do not assume they are load-bearing;
nothing currently depends on their existence.

## `dashboard/api/`

The FastAPI backend.

- `main.py` — the ASGI entry point. Mounts all routers, serves the built
  frontend (`dashboard/web/dist`) as a single-page-app with a catch-all
  fallback route, and reads the `PORT` environment variable for
  `uvicorn.run()`.
- `routes/` — one router module per concern:
  - `csv_routes.py` — file upload, schema detection, per-upload country
    listing.
  - `country_routes.py` — `/api/countries` (from `country_configs/`) and
    `/api/report-scopes` (from `report_scopes.py`).
  - `llm_routes.py` — API key validation, delegates to root
    `llm_providers.py`.
  - `reconcile_routes.py`, `reconcile_larco_routes.py`,
    `gedsi_reconcile_routes.py` — the three dataset-validation/column
    reconciliation flows (Cupboard Week Africa/Vietnam, Cupboard Week
    LARCO, Gender Study), each backed by its own module under
    `dashboard/api/reconciliation*.py`.
  - `run_routes.py` — starts runs, exposes the SSE progress stream, and
    serves download endpoints for the finished `.docx`/`.xlsx`.
  - `visuals_routes.py` — manual visual (PNG) upload handling for
    Cupboard Week.
- `pipeline_runner.py` — the in-process Cupboard Week runner (see
  [architecture-overview.md](architecture-overview.md)).
- `gedsi_runner.py` — the in-process Gender Study runner.
- `core_credit_runner.py` — the out-of-process Core Credit subprocess
  driver.
- `jobs.py` — the in-memory `RUNS` registry and `RunState` class; this is
  where the "only one run at a time" constraint lives.
- `config.py` — path constants, including the `sys.path` injection that
  makes `GENDSI/gedsi_pipeline` importable from within `dashboard/api`.
- `schema_detection.py` — the Africa/Vietnam vs. LARCO column-matching
  heuristic used on upload.
- `powerbi_client.py`, `visuals_source.py` — Power BI integration
  scaffolding (the frontend currently shows Power BI API access as "not
  yet available," so this is partially built-ahead-of-need
  infrastructure).
- `uploads/` — where uploaded CSVs land at runtime. Empty in the Docker
  image; not persisted across container restarts on Hugging Face Spaces.

Medium-to-large, around 20 modules.

## `dashboard/web/`

The Vite + React (TypeScript) single-page app.

- `src/App.tsx` — top-level state machine: which product (`insurance` /
  `core_credit`) and, within Insurance, which report type
  (`cupboard_week` / `gender_study`) is selected.
- `src/CupboardWeekApp.tsx`, `src/GenderStudyApp.tsx`,
  `src/CoreCreditApp.tsx` — one top-level app component per report flow,
  each composing its own `SetupPanel` / `RunPanel` / `ResultsPanel`
  component triad from `src/components/`.
- `src/api/client.ts` — the typed HTTP client for every backend endpoint.
- `src/state/useRunEvents.ts` — the hook that consumes the SSE stream and
  turns it into live UI state (stage pills, log lines).
- `dist/` — the built output. Only a stub `index.html` is committed to
  this repository; the real built assets are produced fresh during the
  Docker build's `frontend-build` stage and are not meant to be committed.
- `node_modules/` — standard local dependency cache (not committed
  logic; ignore when reading the codebase).

For the exact screen-by-screen user flow through this frontend, see
[quick-start.md](../user-guide/quick-start.md), which was written from a
direct trace of this code.

## `dashboard_alignment/`

A single standalone script, `check_alignment.py`, used to manually audit
`analysis_engine` output against hand-recorded Power BI dashboard figures
for Vietnam (via `indicator_map.yaml`), flagging results as matching or
needing investigation using tolerance thresholds of 0.5 and 5 percentage
points. It takes a `RUN_ID` and is run by hand from the command line; it
is copied into the Docker image but never invoked automatically. Useful
when onboarding a new country or investigating a metric that looks wrong,
as a way to cross-check against an independently maintained reference.

## `data_loader/`

Stage 1 of the Cupboard Week pipeline: cleaning and validating the raw
Africa/Vietnam-schema CSV export (also reused, via
`data_loader_larco/`'s config files, for the LARCO schema).

- `data_loader_profiler.py`, `data_loader_transformer.py`,
  `data_loader_screening.py`, `data_loader_derived.py`,
  `data_loader_validator.py` — the five sequential cleaning/validation
  steps, each runnable standalone as a CLI (invoked as subprocesses by
  the root `run_pipeline.py`) or called in-process as plain functions
  (invoked by `dashboard/api/pipeline_runner.py`).
- `data_loader_api.py` — the `load_survey_data()` facade and
  `CleanDataset` type that every downstream consumer actually imports.
  This is also where `report_spec.load_spec()` is called unconditionally
  on every run; see the "report_spec" section of
  [architecture-overview.md](architecture-overview.md).
- `mapping_diff.py` — a helper for comparing column mappings.
- `column_mapping.csv`, `value_coding_map.yaml` — the Africa/Vietnam
  schema's column-name and coded-value definitions.

For the exact behavior of each stage (what the dedup/test-row screening
heuristic actually checks, what the derived-variable step computes), see
[pipeline-data-flow.md](pipeline-data-flow.md). Covered by
`tests/test_screening.py`, `test_transformer.py`, `test_validator.py`,
`test_derived.py`, and `test_schema_detection.py`.

## `data_loader_larco/`

Not a Python package. Just two configuration files,
`column_mapping.csv` and `value_coding_map.yaml`, defining the LARCO
schema's column names and coded values. The same `data_loader/*.py`
step scripts run against these files instead of `data_loader/`'s own
config, selected via the `dataset_schema="larco"` key in the
`DATASET_SCHEMA_PATHS` dictionaries defined in both `run_pipeline.py` and
`dashboard/api/pipeline_runner.py`.

## `GENDSI/`

The Gender Study ("GEDSI") pipeline, a sibling project. Like
`core_credit/`, it is not pip-installed as a dependency; instead,
`dashboard/api/config.py` adds `GENDSI_ROOT` to `sys.path` so its package
can be imported directly.

- `gedsi_pipeline/` — the real package: `ingest.py`, `quant_engine.py`,
  `qual_engine.py`, `triangulate.py`, `draft_writer.py`, `assemble.py`,
  `screening.py`, `mapping.py`, `visuals.py`, `config.py`, and
  `run_pipeline.py` (a standalone CLI entry point with interactive
  codebook-approval prompting, not used by the dashboard, which instead
  calls the six stage modules directly and non-interactively via
  `dashboard/api/gedsi_runner.py`, using pre-approved codebooks already
  checked into the repository).
- `work/codebooks/` — the approved theme codebooks for the Net Promoter
  Score driver questions. Copied into the Docker image.
- `cache/` — LLM response cache (over 200 files at last check).
  Explicitly excluded from the Docker image; development-only.
- `RUNBOOK.md` — developer documentation for running this pipeline
  standalone. Not copied into the Docker image.
- `.claude/settings.local.json` — a Claude Code configuration file that
  appears to have been committed by accident. Not read by any
  application code; consider removing it or adding it to `.gitignore`.

## `generation/`

Stage 4 of the Cupboard Week pipeline: turning `analysis_results.json`
plus the qualitative-tagging results into report prose and a finished
`.docx`.

- `orchestrator.py` — `preflight_check()` and `orchestrate()`, the
  top-level driver for this stage.
- `writer.py` — `write_all_parts()`, including per-part retry logic for
  LLM calls that fail or produce invalid output.
- `assembler.py` — `assemble()`, turning generated prose plus visuals
  into the final `.docx`.
- `executive_summary.py` — the executive summary generation step.
- `validate_output.py` — advisory, post-generation checks on the
  produced report (does not block generation, but surfaces issues for
  the results panel).
- `run_generation.py` — a standalone CLI entry point for this stage.
- `report_spec.yaml` — **do not confuse this with the root
  `insurance-report-spec.yaml`.** This is a different, unrelated file: a
  flat generation-parameters map (per-part word limits, which visuals to
  include, which paths in `analysis_results.json` feed which metrics,
  which LLM model to use, output filename). `pipeline_runner.py`'s Stage
  4 loads this file directly with `yaml.safe_load()`; it has nothing to
  do with the `report_spec` Python package or its validation rules. The
  naming collision here is a real trap for a new maintainer; read
  carefully before assuming these two files are related.

Covered by `tests/test_orchestrator.py`, `test_writer.py`,
`test_assembler.py`, `test_executive_summary.py`, and
`test_validate_output.py`.

## `qualitative/`

Stage 3 of the Cupboard Week pipeline: NPS and verbatim-response tagging
via Gemini, batched (see [known-issues-log.md](known-issues-log.md) for
why this was rearchitected from a single call into batches).

- `prepare_payload.py` — `build_payload()`.
- `llm_call.py` — `call_gemini()`, including the batching logic governed
  by an `_NPS_BATCH_SIZE` constant.
- `parse_results.py` — `parse_and_save()`.
- `config.yaml` — batching and prompt configuration.
- `run_qualitative.py` — a standalone CLI entry point.

Covered by `tests/test_llm_call.py` and `test_parse_results.py`.

## `report_spec/`

The report-spec validation package documented in the root
[README.md](../../README.md). Small (five files) but, contrary to what
its README-only framing might suggest, invoked **live at runtime** for
the Cupboard Week Africa/Vietnam schema; see the dedicated "report_spec"
section in [architecture-overview.md](architecture-overview.md) for the
exact call sites and what happens on failure.

- `loader.py` — `load_spec()`.
- `models.py` — `ReportSpec` and its Pydantic sub-models.
- `schema_validation.py` — JSON Schema (Draft 2020-12) structural
  validation.
- `rules.py` — the thirteen code-level rules R1 through R13.
- `errors.py` — `Finding` and `Severity` types.

`coverage_report.py` (root) and `inspect_spec.py` (root) are the
design-time/manual consumers of this package; they are not part of the
production run path.

## `country_configs/`

Eight YAML files: `default.yaml`, `bolivia.yaml`,
`dominican_republic.yaml`, `ecuador.yaml`, `guatemala.yaml`,
`honduras.yaml`, `mexico.yaml`, `vietnam.yaml`. Each defines, per the
`CountryConfig` dataclass in `analysis_engine/country_config.py`:

- `country`, `label`, `report_context` (free-text context injected into
  report generation)
- `segment_overrides` — per-segment `available`, `column`, `label`,
  `description`, and `skip_reason`, letting a country disable or
  redirect a demographic segment (for example, a country that did not
  collect a gender column)
- `metric_notes` — free-text caveats tied to specific metrics and the
  segments they apply to

`default.yaml` is the fallback template (empty overrides and notes).
`load_country_config(country)` slugifies its input (handling both a CLI
`--country` flag and a raw CSV country value from the dashboard picker),
looks up the matching file, and falls back to `default.yaml` with a
logged warning if no match is found. Because
`dashboard/api/routes/country_routes.py`'s `/api/countries` endpoint
dynamically lists whatever YAML files exist in this directory, **adding
a new country to the dashboard's country picker requires no frontend
changes at all**, only a new YAML file here.

## `runs/`

Output directory: one subfolder per `run_id`, each containing
`survey_clean.parquet`, `analysis_results.json`, the generated report
markdown, `run_metadata.yaml`, `run_summary.txt`, and sometimes
`dry_run_packages.json` or `screening_summary.json`. In this repository
checkout it contains a large amount of historical and smoke-test run
data (for example `bolivia_2026`, `lacro_2025_pooled`,
`Africa_2026_pipeline_smoke`). None of this ships in the Docker image;
the directory is created empty at build time, and on the deployed Space
its contents do not persist across container restarts.

## `tests/`

The top-level pytest suite, roughly 25 files, covering
`analysis_engine` sections, `data_loader` stages, `generation` stages,
`qualitative`, the `report_spec`/`coverage_report.py` package, and
`dashboard/api`'s CSV routes and data quality flags. See
[testing-guide.md](testing-guide.md) for exactly how to run this suite
and how it relates to the separate test suites living under
`core_credit/agent/**/tests/`.

## Root-level scripts

- `run_analysis.py` — the CLI entry point for Stage 2 (analysis). Defines
  `SECTIONS`, `build_sections()`, and `SCHEMA_VERSION`, all of which are
  imported and reused by `dashboard/api/pipeline_runner.py` rather than
  duplicated.
- `run_pipeline.py` — a CLI orchestrator that runs the five
  `data_loader` steps as subprocesses in sequence. Useful for local,
  Stage-1-only debugging; not used by the dashboard's production request
  path, which reimplements the same logic in-process.
- `coverage_report.py` — a design-time CLI/library that turns a
  validated `ReportSpec` into a stakeholder-facing Markdown coverage
  report (automation percentage, data demands, visuals manifest). See
  the root [README.md](../../README.md) for full usage.
- `inspect_spec.py` — a twelve-line diagnostic script that loads the
  real spec and prints findings grouped by rule ID; the fastest way to
  sanity-check a spec edit.
- `generate_visuals.py` — generates the eleven report charts as PNG
  files directly from a run's `analysis_results.json`, as a standalone
  matplotlib script (`--run-id`).
- `llm_providers.py` — the single call-through module (`call_llm()`,
  `validate_key()`) for Gemini, Anthropic, and OpenAI, used by
  `dashboard/api/routes/llm_routes.py`. (Its own docstring claims a path
  of `dashboard/api/llm_providers.py`, which is stale; the file actually
  lives at the repository root.)
- `report_scopes.py` — defines `REPORT_SCOPES`, the named region
  groupings (`lacro`, `africa`) that are distinct from `dataset_schema`.
  Consumed by `run_pipeline.py`, `pipeline_runner.py`,
  `data_loader_screening.py`, `data_loader_derived.py`, and exposed to
  the frontend via `country_routes.py`'s `/api/report-scopes` endpoint.
  See [extension-guide.md](extension-guide.md) for how to add a new one.
- `data_quality_flags.py` — `get_flags()` and `flagged_countries()`:
  hand-entered and automatically derived (duration-outlier-based) data
  quality flags that get surfaced explicitly in a report's Data Notes
  section rather than silently dropped from the data.
- `utils.py` — small shared helpers (`format_period_label()`,
  `get_nested()`).
