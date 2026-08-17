# Architecture Overview

This document is the entry point for an engineer taking over maintenance of
this codebase. It explains what the system is, how its major components fit
together, how it is deployed, and the load-bearing conventions a new
maintainer needs to know before touching anything. For a stage-by-stage trace
of how a single upload turns into a report, see
[pipeline-data-flow.md](pipeline-data-flow.md). For a directory-by-directory
inventory, see [module-reference.md](module-reference.md).

## What this system is

The repository implements the **VFI Report Dashboard**, a web application
that turns an uploaded survey CSV export into a finished impact report
(`.docx`). It is deployed as a single Docker container on **Hugging Face
Spaces** and serves three distinct report families from one app:

- **Cupboard Week** (Insurance Impact Reports, quarterly, per-country or
  region-pooled)
- **Gender Study** (a GEDSI-focused Insurance Impact Report variant)
- **Core Credit Impact Report** (a global, multi-country portfolio report
  benchmarked against an MFI Index)

These three report families are not three deployments of the same code —
they are three genuinely different pipelines with different backends,
different report-authoring mechanisms, and different levels of automation,
unified only by a shared FastAPI + React shell. Understanding that they are
different is the single most important fact for a new maintainer: a fix or
feature added to Cupboard Week does not automatically apply to Gender Study
or Core Credit.

## The three pipelines, and how the backend invokes each one

All three flows start the same way at the HTTP layer:
`dashboard/api/routes/run_routes.py` receives `POST /api/runs`, creates a
`RunState` in `dashboard/api/jobs.py`'s in-memory `RUNS` registry, and hands
off to one of three different runner modules depending on
`report_type`/`product`. Only one run can be active server-wide at a time
(`jobs.py`), and progress streams back to the browser over Server-Sent
Events (`GET /api/runs/{run_id}/events`).

**Cupboard Week** is driven by `dashboard/api/pipeline_runner.py`, executed
in a background thread (`asyncio.to_thread`). It runs four stages
**in-process**, as direct Python function calls, not subprocesses:

1. Data loading (`data_loader/*.py`)
2. Analysis (reuses `run_analysis.py`'s `SECTIONS` registry directly, not a
   copy of it)
3. Qualitative tagging (`qualitative/*.py`)
4. Report generation (`generation/*.py`)

Notably, `pipeline_runner.py` does **not** call the root `run_pipeline.py`
script even though that script exists and does something similar. The
dashboard reimplements the same stage-1 logic in-process for its own
reasons (progress reporting, partial-failure isolation); `run_pipeline.py`
remains as a standalone CLI orchestrator that runs the same `data_loader`
steps as subprocesses, useful for local debugging but not part of the
production request path.

**Gender Study** is driven by `dashboard/api/gedsi_runner.py`, also run via
`asyncio.to_thread`. It calls the six stage modules of
`GENDSI/gedsi_pipeline/` (`ingest`, `quant_engine`, `qual_engine`,
`triangulate`, `draft_writer`, `assemble`) directly, in-process, the same
way `pipeline_runner.py` does for Cupboard Week. Unlike Cupboard Week,
`GENDSI/gedsi_pipeline` was not designed with partial-failure isolation
between stages: a failure in one stage generally aborts the whole run
rather than being recorded and continuing. `GENDSI/gedsi_pipeline/run_pipeline.py`
is a separate, standalone CLI entry point with interactive codebook-approval
prompting; the dashboard does not invoke it and instead calls the same
underlying stage modules non-interactively, using pre-approved codebooks
that are checked into the repository rather than re-derived per run.

**Core Credit** is driven by `dashboard/api/core_credit_runner.py`, and
unlike the other two, this one genuinely spawns a **separate OS process**:
`sys.executable core_credit/agent/orchestrator/run_for_dashboard.py`. This
is a deliberate architectural choice, documented in that module's own
docstring, for two reasons:

1. `core_credit`'s internal scripts add directories to `sys.path` and use
   short, generic module names (`state`, `schemas`, `graph`, `driver`,
   `writer`, `synthesis`) that would permanently collide with and shadow
   entries in `sys.modules` if imported into the same process as the
   FastAPI server.
2. Isolation: a Core Credit run typically takes **40 to 90 minutes or
   more**, and a crash inside it should not be able to take the FastAPI
   server down with it.

The subprocess streams one JSON line per completed pipeline node to stdout
(`{"event": "node", "node": ...}`), which `core_credit_runner.py` tails and
turns into log lines and per-node status updates in the same `RunState`
object the frontend polls via SSE. The Anthropic API key is passed to the
subprocess only through its environment, never written to disk.

`core_credit/` itself is a genuine multi-agent system built on LangGraph,
not just a script bundle. Its graph (`core_credit/agent/orchestrator/graph.py`)
wires together: a data-prep tier (two real LangChain tool-calling agents,
a "Column Cleaner" and a "Row Checker," each running on Claude Haiku 4.5,
with an independent hard-coded `REQUIRED_COLUMNS` check as a fail-fast net
after a real production incident where the Column Cleaner agent silently
dropped a required audit column); an independent dashboard-visuals
resolution branch that runs in parallel from the start; nine concurrent
theme-section nodes (six built directly, three built through a
config-driven sub-graph); a cross-cutting synthesis tier (gender scorecard,
client voices, executive summary); an assembly tier that composes
everything into a report data structure and checks for completeness and
"meta-text leaks" (LLM commentary that shouldn't appear in final prose);
and a render tier that produces the `.docx` and runs an automated QA review,
in parallel. The whole graph is checkpointed to SQLite, which is what makes
the CLI entry point (`run_orchestrator.py`) resumable after a crash; the
dashboard's `run_for_dashboard.py` entry point uses the same checkpointing
machinery.

## The `report_spec` validation package: live at runtime, not just design-time

It would be reasonable to assume `report_spec` (documented in the root
[README.md](../../README.md)) is a design-time or CI-only tool that report
authors run against `insurance-report-spec.yaml` before committing changes.
**It is not.** For the Cupboard Week Africa/Vietnam schema, `report_spec.load_spec()`
is called twice on every single production run:

- Once in Stage 1, inside `data_loader/data_loader_validator.py`, which
  cross-checks the cleaned dataframe's columns against the spec's declared
  `source_questions` and `referenced_variables`.
- Once in Stage 2, inside `data_loader/data_loader_api.py::load_survey_data()`,
  which every downstream consumer (`run_analysis.py`,
  `pipeline_runner.py`) calls to obtain a `CleanDataset`. If the spec fails
  to load here, it raises `RuntimeError("Report spec failed to load")` and
  the run fails outright.

For the **LARCO** dataset schema, the Stage 1 spec-alignment check is
explicitly skipped (logged as a warning: no LARCO-equivalent spec YAML
exists yet), but Stage 2's `load_survey_data()` still unconditionally calls
`load_spec()` against the same Africa/Vietnam-oriented
`insurance-report-spec.yaml`, regardless of which dataset schema is
active. No schema-conditional branch was found in `load_survey_data()`
itself. **This is worth confirming with the team rather than assuming it is
intentional** — it means a LARCO run's Stage 2 still depends on the
Africa/Vietnam spec loading successfully, even though Stage 1 has already
decided the spec doesn't fully apply to LARCO data.

Gender Study and Core Credit do not import `report_spec` at all; their
report structure is defined by their own pipeline code
(`GENDSI/gedsi_pipeline/`, `core_credit/agent/report_assembly/`), not by a
validated YAML spec.

`coverage_report.py`, `inspect_spec.py`, and the `report_spec`/coverage
test suites are the design-time, CI, and manual-inspection consumers of the
package — separate from the two live call sites above.

## `SCHEMA_VERSION`

`SCHEMA_VERSION` is defined once, as a plain string constant, at
`run_analysis.py:38`:

```python
SCHEMA_VERSION = "1.5"   # was "1.4" — inverted Likert scale corrected:
                          # bottom_two_box replaces top_two_box for all
                          # positive-outcome Likert metrics (Track D scale fix)
```

It is not defined inside `analysis_engine/` itself; it lives in the root
orchestrator script and is written into every `analysis_results.json`'s
`meta.schema_version` field, by both `run_analysis.py` and
`pipeline_runner.py` (which imports and reuses the same constant rather
than duplicating it). It versions the **shape and semantics of the computed
metrics**, not a database schema or an API contract. The comment on that
one line is the only surviving record of the "Track D" Likert-inversion
fix; there is no separate changelog document, and no code anywhere was
found that actually checks this string against an expected value before
using an `analysis_results.json` file. In practice, this means: bumping
`SCHEMA_VERSION` without updating the corresponding section calculators
does not break anything mechanically today (nothing gates behavior on the
string), but it does silently desynchronize the version label from the
real computation shape, which will mislead whoever reads it next. Treat it
as a changelog entry that happens to also be a runtime-visible string, and
keep the inline comment current whenever a metric's computation semantics
change, even though nothing will force you to.

## Deployment: Docker on Hugging Face Spaces

The [Dockerfile](../../Dockerfile) builds in two stages:

1. **`frontend-build`** (`node:20-slim`) runs `npm ci && npm run build`
   inside `dashboard/web/`, producing the static SPA bundle at
   `/frontend/dist`.
2. **`runtime`** (`python:3.11-slim`) copies in the Python source tree
   (root scripts, `analysis_engine`, `data_loader`, `data_loader_larco`,
   `generation`, `qualitative`, `report_spec`, `dashboard_alignment`, the
   whole `dashboard` tree including `dashboard/api`, `country_configs`,
   and the spec YAML/schema files), copies `core_credit` in whole (as a
   sibling project run via subprocess, not pip-installed — see above),
   copies only `GENDSI/gedsi_pipeline` and `GENDSI/work/codebooks` from
   `GENDSI/` (explicitly excluding `GENDSI/cache`, docs, and
   `RUNBOOK.md`, which are dev-only and never read at runtime), installs
   the package with `pip install ".[dashboard,core_credit]" openpyxl`,
   and finally copies the built frontend from stage 1 into
   `dashboard/web/dist`.

Three runtime-writable directories are created **empty** in the image:
`/app/runs`, `/app/dashboard/api/uploads`, and `/app/GENDSI/cache`. This
matters operationally: **Hugging Face Spaces' container filesystem is
ephemeral by default**, and nothing in this Dockerfile mounts a persistent
volume. Anything written to those three directories during a session,
meaning uploaded CSVs, generated `.docx`/`.xlsx` outputs, intermediate run
artifacts, and GEDSI's LLM response cache, is lost whenever the container
restarts or a new version is deployed. Users must download their report
before the Space restarts; there is currently no server-side persistence
of run history across deploys. (The `runs/` directory visible in this
repository checkout, with entries like `bolivia_2026` and
`lacro_2025_pooled`, is local development history; none of it ships in the
image or exists on the deployed Space.)

The FastAPI app (`dashboard/api/main.py`) serves the built frontend itself:
static assets are mounted at `/assets`, and a catch-all route registered
after every `/api/*` router returns `dist/index.html` for any other path,
giving standard single-page-app client-side routing with no separate
frontend server or process.

Hugging Face Spaces' Docker SDK proxies external traffic to whatever port
is declared as `app_port` in the Space's README frontmatter
([README_SPACE.md](../../README_SPACE.md) declares `7860`). The Dockerfile
sets `ENV PORT=7860`, and `main()` in `dashboard/api/main.py` reads
`os.environ.get("PORT", "7860")` and passes it to `uvicorn.run(host="0.0.0.0", port=port)`.
These two numbers must stay in sync: if you ever change one, change the
other. `docker run -e PORT=...` overrides it for local development.

## Known rough edges worth flagging to a new maintainer

- **`cupboard_week_host/`** at the repository root, and a second
  **`dashboard/web/cupboard_week_host/`**, are both completely empty
  directories with no files. They appear to be vestigial or placeholder
  directories from an earlier iteration of the project structure. Nobody
  currently reads or writes to them. Confirm with the team before deleting,
  but do not assume they are load-bearing.
- **`GENDSI/.claude/settings.local.json`** is a Claude Code configuration
  file that was apparently committed by accident inside the GENDSI sibling
  project. It is not read by any application code, but it should probably
  be removed or added to `.gitignore` rather than left in place.
- **`dashboard_alignment/check_alignment.py`** is a manual audit script
  (compares `analysis_engine` output for a given run ID against hand
  recorded Power BI dashboard values for Vietnam, using tolerance
  thresholds of 0.5 percentage points and 5 percentage points) that is
  copied into the Docker image but never invoked automatically by any
  pipeline. It exists purely for a human to run by hand when validating a
  new country or a suspicious metric.
- **The LARCO-schema `report_spec` validation gap** described above (Stage
  1 skips it, Stage 2 does not) is a genuine architectural inconsistency
  worth resolving deliberately rather than leaving as an accident of how
  the code evolved.

## Where to go next

- For the exact stage-by-stage data flow within Cupboard Week (what each
  function computes, how qualitative batching works, how the prior-year
  trend baseline is built), read
  [pipeline-data-flow.md](pipeline-data-flow.md).
- For a directory-by-directory reference of every module in the
  repository, read [module-reference.md](module-reference.md).
- For the concrete history of non-obvious bugs already fixed in this
  system (so you don't reintroduce them), read
  [known-issues-log.md](known-issues-log.md).
- For how to add a new report family or region scope, read
  [extension-guide.md](extension-guide.md).
- For how the test suites are organized and how to run them, read
  [testing-guide.md](testing-guide.md).
