# Extension Guide: Adding a New Region Scope or Report Family

This is a recipe document. It answers a question that has already come up
twice in this codebase's history: how do you add a new region scope to an
existing report family (as was done for LACRO and Africa), and, a much
bigger question, how do you add a genuinely new report family (as Core
Credit was)? Read [known-issues-log.md](known-issues-log.md) first for the
concrete history this guide generalizes from.

## Adding a new region scope to an existing report family

The single source of truth for a region scope is the `REPORT_SCOPES`
dictionary in the root `report_scopes.py`:

```python
REPORT_SCOPES = {
    "lacro": {"label": "LACRO (Latin America and Caribbean)", "regions": ["LACRO"]},
    "africa": {"label": "Africa and Asia", "regions": ["AFRICA", "ASIA"]},
}
DEFAULT_REPORT_SCOPES = ["lacro", "africa"]
```

Each entry is just a label and a list of raw region values, matched
case-insensitively against the uploaded CSV's own region column. The
module's own docstring makes an explicit claim that adding a new scope is
just adding an entry here and nothing else needs to change. **That claim
is true for consumption** (every reader of this dictionary pulls from it
dynamically, so a new key is picked up everywhere automatically) **but not
true end to end.** There are real additional steps, listed below, that the
module's own claim does not cover.

### Step 1: Add the entry to `REPORT_SCOPES`

This alone makes the new scope appear in `GET /api/report-scopes`, which
is what populates the dashboard's country and region picker, and makes it
a valid `--report-scope` CLI argument.

### Step 2: Make sure the scope's countries are allowed through Stage 1's screening filter

This is the step that is easiest to miss, because nothing fails loudly if
you skip it; rows are simply dropped silently as "out of scope." Before
the region-scope filter ever runs, `data_loader/data_loader_screening.py`
applies an earlier, separate allow-list keyed on the dataset schema, not
the report scope (`SCOPE_COUNTRIES_AFRICA_VIETNAM`). If your new scope's
countries are not already present in that allow-list, every row from those
countries gets removed before the region-scope filter ever sees them. This
is exactly the first of the four concrete bugs found when LACRO's
countries were folded into the unified schema: without this fix, zero of
1,721 real LARCO rows would have survived. Add the new scope's countries
to this allow-list as part of the same change that adds the
`REPORT_SCOPES` entry.

### Step 3: Add the scope to the "module manifest" if it needs its own report sections

There is no separate manifest file. The gating logic lives directly inside
`run_analysis.py`'s `build_sections()` function, and it decides which
report-part calculators even run for a given combination of dataset
schema and report scope:

```python
def build_sections(dataset_schema="africa_vietnam", prior_run_id=None, report_scope=None):
    is_lacro_report = report_scope == "lacro" or dataset_schema == "larco"
    sections = [(key, label, module.calculate) for key, label, module in SECTIONS]
    if is_lacro_report:
        sections.append(("part_9", "Additional Services", part_9.calculate))
    if is_lacro_report or prior_run_id:
        sections.append(("part_10", "Trend Comparison", functools.partial(part_10.calculate, prior_run_id=prior_run_id)))
    if report_scope == "africa":
        sections.append(("part_11", "Credit Life Module", part_11.calculate))
        sections.append(("part_12", "Crop Module", part_12.calculate))
    return sections
```

The rule this encodes: do not compute or emit a report section whose
underlying survey questions were never asked of that scope's respondents.
If your new scope needs a section that does not apply to every existing
scope, add an `if report_scope == "<new>":` branch here. This is
imperative Python gating on scope-name string literals, not a declarative
list inside `report_scopes.py` itself; there is currently no
config-driven alternative, so this is genuinely hand-written logic every
new scope with special sections needs to add.

If your new scope reuses only the eight base sections with no additions,
you can skip this step entirely; that is what most scopes will need.

### Step 4: `country_configs/` almost certainly does not need to change

Per-country configuration files (`country_configs/bolivia.yaml`, and so
on) are keyed on the individual country, loaded from the run's `country`
field, not from `report_scope`. When a user selects a region scope in the
dashboard rather than a single country, the `country` field is explicitly
reset to `"default"`, so every scoped run loads `country_configs/default.yaml`
(empty overrides) regardless of which scope was chosen. There is no
`lacro.yaml` or `africa.yaml`, and you should not create one; segment
overrides and metric notes are deliberately orthogonal to region scope.

### Step 5: Do not forget the Dockerfile

`report_scopes.py` itself has to be copied into the Docker image. This was
missed on the first region-scoping rollout and caused an import-time
failure on the deployed Space that did not show up in local development,
fixed in its own dedicated commit. If you add a new top-level file or
directory as part of a new scope, check the Dockerfile's `COPY` lines
before assuming it will be present on the deployed Space.

### Step 6: Data quality flags and the protection-signals appendix need no changes

Both of these shipped alongside the original region-scoping rollout, which
is likely why they are sometimes remembered as scope-specific features,
but neither actually is. `data_quality_flags.py`'s flag dictionary is
keyed by report scope only as an optional extension point for a hand-typed
override; every currently active flag is derived automatically from a
purely statistical, scope-agnostic check on interview durations. The
client-protection-signals appendix is sourced from the qualitative LLM
pass scanning every scope's open-text responses the same way; nothing in
that path branches on region scope at all. A new scope inherits both
features automatically, with zero code changes required.

### Step 7: Decide whether the new scope should support trend comparison

The backend side of trend comparison is already scope-agnostic: Part 10
activates whenever a prior run ID is supplied, for any scope, or
unconditionally on a LARCO-schema run. The actual bottleneck is a single
hardcoded check in the frontend, `CupboardWeekApp.tsx`'s `isLacroRun`
constant, which decides whether to show the prior-year CSV upload field at
all:

```ts
const isLacroRun = resolvedSchema === "larco" || country === "lacro";
```

This is a literal string comparison, not a generic "this scope supports
trend comparison" flag; no such flag currently exists in `REPORT_SCOPES`
or the `ReportScopeOption` type. Enabling the prior-year upload field for
a new scope is a genuinely shallow, one-line change: add the new scope's
value to this comparison. If you want to harden this properly rather than
accumulate more special-cased string comparisons over time, consider
adding a real `supports_trend_comparison` flag to each `REPORT_SCOPES`
entry and deriving `isLacroRun` from that instead. Before finalizing
either approach, read `analysis_engine/sections/part_10.py`'s body
directly; it was not fully verified whether it does its own additional
internal scope-specific comparability logic beyond what `build_sections()`
already gates.

### Checklist summary for a new region scope

1. Add the entry to `report_scopes.py`'s `REPORT_SCOPES`.
2. Add the new scope's countries to `SCOPE_COUNTRIES_AFRICA_VIETNAM` in
   `data_loader/data_loader_screening.py`.
3. If the scope needs report sections that do not apply to every scope,
   add a branch inside `run_analysis.py`'s `build_sections()`.
4. Leave `country_configs/` alone unless an individual country within the
   new scope needs its own overrides.
5. Confirm any new files are actually copied by the Dockerfile.
6. Leave data quality flags and the protection-signals appendix alone;
   they work automatically.
7. Decide whether trend comparison should be available for the new scope,
   and update the frontend's `isLacroRun` check if so.

## Adding a wholly new report family

This is a much bigger lift than a new region scope, and this codebase
already contains two precedents at very different levels of cost.

**Gender Study is the cheap precedent.** It clones Cupboard Week's overall
pipeline shape (a data-loading stage, an analysis stage, a qualitative
tagging stage, a writing and assembly stage) into a self-contained sibling
package (`GENDSI/gedsi_pipeline/`), and wires in only two dispatch points:
a new report-type branch in the frontend's `App.tsx` state machine, and a
new dispatch branch in the backend's `run_routes.py`.

**Core Credit is the expensive precedent.** It uses an entirely different
orchestration paradigm (a LangGraph multi-agent node graph instead of a
linear stage script), an entirely different report-spec mechanism (a
Python configuration registry instead of a YAML file), its own rendering
path, and its own qualitative synthesis, sharing almost no code with
Cupboard Week or Gender Study beyond the outer FastAPI app and React
shell.

Before starting, decide honestly which of these two shapes your new
family is closer to: does it reuse the same kind of tabular survey
structure and reporting logic as Cupboard Week, or does it need a genuinely
different computation and orchestration model? That decision determines
which of the following pieces you need to build from scratch versus adapt
from an existing sibling.

### The load-bearing pieces every new report family needs

1. **Frontend product or report-type branching.** `dashboard/web/src/App.tsx`
   holds a top-level `product` state that picks an entire `*App.tsx`
   component, and, within the `insurance` product, a second-level
   `reportType` state that picks between `CupboardWeekApp` and
   `GenderStudyApp`. A new family needs either a new top-level `Product`
   value with its own new branch (the Core Credit pattern), or a new
   `ReportType` value reusing the existing `insurance` product's
   sub-branch (the Gender Study pattern). Also update the corresponding
   type definitions and the `StartRunRequest` shape in
   `dashboard/web/src/api/client.ts`.
2. **Backend request validation and dispatch.** `dashboard/api/routes/run_routes.py`
   needs a branch for your new report type's required-field validation,
   and a branch in its runner dispatch that calls your new runner module.
3. **A dedicated runner module**, one of `pipeline_runner.py` (subprocess-style
   staged execution, in-process), `gedsi_runner.py` (a thin wrapper calling
   directly into a sibling package's stage functions), or
   `core_credit_runner.py` (an async wrapper that spawns a genuine
   subprocess and streams its progress) as a model, depending on which
   execution shape your new family needs.
4. **The analysis and generation pipeline itself.** This is the largest
   piece of work by far, and the two precedents diverge completely here:
   Gender Study reimplements Cupboard Week's linear stage shape
   self-contained inside its own package with no shared code; Core Credit
   uses a LangGraph node graph with a declarative section-configuration
   registry for some sections and hand-built driver modules for others.
   There is no shared, generic pipeline engine in this codebase that a
   new family gets for free; you are building or adapting this stage by
   stage regardless of which shape you choose.
5. **A report spec, in whichever form your new family's pipeline
   consumes.** Cupboard Week's live generation step reads
   `generation/report_spec.yaml`, a flat, declarative file mapping report
   sections to metric paths, validated informally by the separate
   `report_spec/` governance package. Core Credit has no equivalent single
   YAML file at all; its "spec" is the Python `SECTION_CONFIGS` registry
   plus external PDF design documents. Decide which pattern fits your new
   family; nothing forces you toward either one.
6. **A column mapping or ingestion definition specific to the new
   family's raw data.** Every existing family has its own answer here:
   `data_loader/column_mapping.csv` for Africa/Vietnam,
   `data_loader_larco/column_mapping.csv` for the legacy LARCO instrument,
   `GENDSI/gedsi_pipeline/column_mapping.csv` for Gender Study, and Core
   Credit's own LLM-driven column-cleaning agent instead of a static
   mapping file at all. A new family needs its own answer here too; none
   of the existing ones are directly reusable for a structurally
   different survey instrument.
7. **A dashboard reconciliation route**, if your new family's raw data
   needs a diff-and-approve step before generation, following the pattern
   of `reconcile_routes.py`, `reconcile_larco_routes.py`, or
   `gedsi_reconcile_routes.py`. Note that Core Credit deliberately does
   not have an equivalent route; its column-cleaning agent handles this
   automatically with an LLM rather than presenting the user with
   renamed/dropped-column decisions to approve. This is a genuine fork in
   approach, not just one more routes file to write in the same style as
   the other three.
8. **Dockerfile `COPY` lines** for every new top-level package or
   directory your new family introduces, following the pattern already
   used for `GENDSI`, `core_credit`, and `dashboard_alignment`.
9. **Tests.** Follow whichever precedent's test layout matches your
   family's structure: the root `tests/` tree's flat-file-per-module
   layout for a Cupboard-Week-shaped family, or Core Credit's
   colocated-per-submodule `tests/` directories for a more modular one.
   Either way, read [testing-guide.md](testing-guide.md) first so your
   new suite is actually reachable by the right `pytest` invocation, and
   consider whether it should be added to CI, since neither existing
   precedent's test tree is fully covered by CI today.

### A realistic cost estimate

If your new report family can be described as "the same kind of survey,
different questions and different countries," follow the Gender Study
precedent; expect to write a self-contained sibling package plus two
frontend and backend dispatch points, largely mechanical work once the
underlying computation logic is settled.

If your new report family needs meaningfully different orchestration, for
example genuinely parallel or conditional computation stages, long-running
work that should not block the main server process, or a fundamentally
different report structure, budget for something closer to Core Credit's
scope: a new orchestration engine, a new spec mechanism, and little to no
code reuse from the existing pipelines beyond the outer web application
shell.
