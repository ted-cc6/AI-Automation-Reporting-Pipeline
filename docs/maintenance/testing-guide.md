# Testing Guide

How the test suites in this repository are organized, and exactly how to
run each of them. There is no single command that runs everything; read
this before assuming a green `pytest` run means the whole codebase is
tested.

## Two independent test trees

This repository has two separate, independently-run test trees. Nothing
ties them together, and CI (see below) currently only runs one of them.

### The root pipeline tree: `tests/`

Covers the main Cupboard Week pipeline: `data_loader/`, `analysis_engine/`,
`generation/`, `qualitative/`, the `report_spec/` package and
`coverage_report.py`, and `dashboard/api`'s CSV routes and data quality
flags. 24 files, 472 test cases, no `conftest.py`, packaged via
`tests/__init__.py`. Almost all tests build synthetic pandas DataFrames
in-memory using local helper functions (for example `_base_df()` in
`test_validator.py`, `_make_sub()` in `test_coverage_report.py`) rather
than reading real fixture CSVs, so this tree runs with zero external setup
beyond installing the package.

Run it with:

```
pytest tests/ -v
```

from the repository root. This is exactly what CI runs, and exactly what
the root `README.md` documents for the `report_spec` tests specifically
(`pytest tests/test_coverage_report.py -v`).

### The Core Credit tree: `core_credit/agent/**/tests/`

Covers the separate Core Credit LangGraph pipeline. 12 subdirectories, 273
test cases total: `analysis/benchmark_module/tests`,
`analysis/graph/tests`, `analysis/metrics_engine/tests`,
`analysis/ppi_module/tests`, `analysis/qualitative_agent/tests`,
`analysis/section_configs/tests`, `analysis/synthesis/tests`,
`analysis/writer/tests`, `dashboard_visuals/tests`, `orchestrator/tests`,
`report_assembly/tests`, `report_render/tests`. Each subtree has its own
`conftest.py` that manipulates `sys.path` so its tests are importable
regardless of which directory you invoke pytest from.

Run the whole tree with:

```
cd core_credit/agent
pytest
```

This collects all 273 tests across all 12 subdirectories in one shot; no
per-module `pytest.ini` or `pyproject.toml` exists under `core_credit/`,
so this relies entirely on the `conftest.py` `sys.path` handling plus
pytest's normal rootdir auto-detection. You can also run any individual
submodule on its own, for example `cd core_credit/agent/analysis/ppi_module && pytest`,
since each has its own `conftest.py`.

**Important: the root `pytest` command does not see this tree at all.**
Root `pyproject.toml` sets `[tool.pytest.ini_options] testpaths = ["tests"]`,
so a bare `pytest` run from the repository root only discovers the root
`tests/` directory and silently skips everything under `core_credit/`.

## Why the two trees are not one

There is no `report_spec/tests/` directory; the `report_spec` package and
`coverage_report.py` are tested from the root `tests/` tree
(`test_models.py`, `test_validate_output.py`, `test_coverage_report.py`),
not a dedicated suite. No test directories exist under `dashboard/api/`
beyond what the root `tests/` tree already covers (`test_csv_routes.py`),
under `dashboard/web/` in any language, or under `GENDSI/`. The Gender
Study pipeline currently has no automated test coverage at all; keep this
in mind before assuming a change there is safe just because `pytest tests/`
passed.

## Two Core Credit test submodules require files that are not in the repository

`benchmark_module/tests/conftest.py` and `ppi_module/tests/conftest.py`
deliberately point at real, proprietary workbooks instead of synthetic
fixtures, by explicit design; the `ppi_module` conftest's own docstring
explains that these real production files are "the strongest fixtures
available," since two of the expected results were independently
cross-checked by two humans against them. The three files are:

- `core_credit/External Benchmarks.xlsx`
- `core_credit/PPI_scorecards.xlsx`
- `core_credit/PPI_lookups.xlsx`

None of these exist anywhere in the repository or in its git history; a
commit message elsewhere states plainly that the benchmarks workbook "is
not committed, add a real one when ready." As things stand, running
`pytest analysis/benchmark_module/tests` produces 22 errors for a missing
fixture workbook, and `pytest analysis/ppi_module/tests` produces 8 passes
and 28 errors. If you are a new maintainer setting up this repository for
the first time, do not be alarmed by these failures on the Core Credit
tree; they are expected until you obtain these three files out of band and
place them directly under `core_credit/`. They are not listed in
`.gitignore` by name, they were simply never committed.

The production code itself degrades gracefully without these files (the
benchmark module falls back to reporting the data as "not available"
rather than crashing), but the tests do not share that grace. Do not treat
a fully green Core Credit test run as confirmation that benchmarks are
wired up correctly in production; conversely, do not treat these 50
failing tests as a sign that something is broken in the application
itself.

`ppi_module/tests/conftest.py` also globs
`core_credit/processed_data/*_analysis_ready.csv` for a fourth fixture,
picking whichever file is lexicographically latest. This one works today,
since `core_credit/processed_data/` already contains several real prior
run outputs. This directory is pure pipeline output, regenerated with a
fresh timestamp on every run, so no specific filename is hardcoded in the
test.

## Dependency files: use the root `pyproject.toml`

Root `pyproject.toml` is the single source of truth for dependencies,
via `[project.dependencies]` plus the optional groups `dev`, `dashboard`,
and `core_credit`. Root `requirements.txt` is a thin convenience wrapper
around `-e .[dev]`, not an independent dependency list.

`GENDSI/requirements.txt` is a separate, unpinned dependency list for the
Gender Study sibling pipeline, not installed as part of the root package.

You will also find a separate `requirements.txt` under each of the 12
`core_credit/agent/*/` submodules. **Do not use these to set up a Core
Credit development environment.** They appear to be stale, redundant
scaffolding: nothing in CI or in the Dockerfile installs from them, and
the actual, correct install path is `pip install ".[dashboard,core_credit]"`
from the repository root, exactly as the Dockerfile does. Treat these
per-submodule files as historical artifacts that may have drifted from the
real dependency set, not as documentation of what to install.

There is no `requirements.txt` or `pyproject.toml` under `dashboard/` at
all; `dashboard.api` and `dashboard.api.routes` are simply packages listed
directly in root `pyproject.toml`'s `[tool.setuptools] packages` list and
installed via the `dashboard` extra.

## Frontend: no tests exist

`dashboard/web/package.json` defines only three scripts: `dev`, `build`
(`tsc -b && vite build`), and `preview`. There is no `test` script, no
test framework listed as a dependency in `package.json`, and no `*.spec.ts`,
`*.test.tsx`, or `e2e/` directory anywhere under `dashboard/web/src`.

The `playwright` and `playwright-core` folders you may notice under
`dashboard/web/node_modules` are not a real project dependency; they do
not appear anywhere in `package-lock.json`, meaning `npm ci` would not
reproduce them. They are leftover install artifacts from some manual local
action, not evidence of an existing end-to-end test suite. Do not document
or assume Playwright coverage exists for the frontend.

## CI: `.github/workflows/ci.yml`

The only workflow file in the repository. On every push and pull request
to `main`, across a matrix of Python 3.11 and 3.12 on Ubuntu, it runs:

1. Checkout and Python setup
2. `pip install -e ".[dev]"`
3. `ruff check .` (lint, across the whole repository)
4. `pytest tests/ -v` (only the root `tests/` tree)

Concrete gaps worth knowing about:

- **The Core Credit test tree never runs in CI.** Since roughly 50 of its
  273 tests already fail locally for the missing-fixture reason described
  above, and CI never touches this tree at all, a genuine regression
  there would currently go completely unnoticed by CI. Treat changes to
  `core_credit/` as requiring a manual `cd core_credit/agent && pytest`
  run before merging.
- **No frontend build, typecheck, or test step runs in CI**, even though
  the Dockerfile's first build stage does run `npm ci && npm run build`.
  A frontend break would only be caught by attempting a Docker build, not
  by CI on a pull request.
- **No Docker build step runs in CI at all.**
- **Deployment to Hugging Face Spaces is entirely manual, not automated.**
  The repository has a second git remote, `space`, pointing at the
  Hugging Face Space; git history shows deploys happening by manually
  pushing squashed history to that remote. Nothing in `.github/` triggers
  a deploy automatically on merge to `main`.
- `ruff check .` does cover the whole repository, including
  `core_credit/`, `GENDSI/`, and `dashboard/api`, even though `pytest`
  does not; lint coverage and test coverage are not the same footprint
  here.

## Linting: ruff

Configuration lives entirely inside root `pyproject.toml`, under
`[tool.ruff]` (`target-version = "py311"`, `line-length = 110`) and
`[tool.ruff.lint]`. There is no separate `ruff.toml` file. The lint
section deliberately does not set an explicit `select`/`extend-select`
list, relying on ruff's defaults only (pyflakes rule `F` plus a slice of
pycodestyle rule `E`), specifically to catch real problems like unused
imports, unused variables, undefined names, and bare `except` clauses,
without forcing a full-repository reformat. Run it manually with
`python -m ruff check .` from the repository root, the same command CI
uses; the `dev` extra in `pyproject.toml` pins `ruff>=0.6`.

## Non-pytest validation tooling: manual, not CI-gated

`coverage_report.py` and `report_spec`'s `load_spec()` are not invoked
directly anywhere in CI. They are exercised only indirectly, as library
code imported by the tests in the root `tests/` tree, which CI does run.
As standalone command-line tools, both are meant to be run manually by a
developer, most often after editing `insurance-report-spec.yaml`:

```
python coverage_report.py insurance-report-spec.yaml --schema insurance-report-spec.schema.json
python inspect_spec.py
```

Both are documented in full in the root [README.md](../../README.md).

## Practical checklist before merging a change

1. If you touched anything under `data_loader/`, `analysis_engine/`,
   `generation/`, `qualitative/`, `report_spec/`, or `dashboard/api/`, run
   `pytest tests/ -v` from the repository root, since CI will do this
   anyway.
2. If you touched anything under `core_credit/`, additionally run
   `cd core_credit/agent && pytest` by hand, since CI will not do this for
   you. Expect roughly 50 pre-existing failures in `benchmark_module` and
   `ppi_module` unless you have obtained the three proprietary workbooks
   described above; do not treat those specific failures as caused by
   your change unless you touched those two submodules directly.
3. If you touched `insurance-report-spec.yaml`, run `python inspect_spec.py`
   for a fast sanity check, and consider running
   `python coverage_report.py insurance-report-spec.yaml --schema insurance-report-spec.schema.json`
   to see the updated automation coverage numbers.
4. If you touched `dashboard/web/`, there is no automated test to run;
   manually exercise the change in a running instance (see the [run
   skill](../../README.md) or start the dev server directly) before
   merging, since neither CI nor the test suite will catch a frontend
   regression.
5. Run `python -m ruff check .` if you are unsure whether your change
   introduced an unused import or undefined name; CI will catch this
   either way, but it is faster to check locally first.
