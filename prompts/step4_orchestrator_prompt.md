# Developer Prompt — Analysis Engine Step 4: Orchestrator
# File: run_analysis.py (project root)

---

## Context

You are building Step 4 — the final piece of the analysis engine — for the VisionFund
Insurance Client Survey. Steps 1–3 are complete:

| Step | File | Purpose |
|---|---|---|
| 1 | `analysis_engine/segments.py` | Segment registry and mask generation |
| 2 | `analysis_engine/stats.py` | All stat functions (top_two_box, disaggregate, etc.) |
| 3 | `analysis_engine/sections/part_1.py` … `part_7.py` | Section calculators |

Step 4 is `run_analysis.py` at the project root. It is a CLI script that:
1. Loads the validated survey parquet for a given run
2. Computes segment masks once (shared across all sections)
3. Calls each of the 7 section calculators
4. Assembles and writes `analysis_results.json` to the run directory
5. Prints a human-readable summary to stdout

This is the handoff file that feeds the generation layer (Power BI / reports).

---

## Existing project structure

```
d:/Vision Fund International/Project/
    run_pipeline.py                  ← data loader orchestrator (already exists)
    run_analysis.py                  ← YOU CREATE THIS
    data_loader/
        data_loader_api.py           ← load_survey_data(), CleanDataset
    analysis_engine/
        __init__.py
        segments.py                  ← get_all_segment_masks(), describe_segments(), SEGMENT_REGISTRY
        stats.py                     ← LOW_N_THRESHOLD, stat functions
        sections/
            __init__.py
            part_1.py … part_7.py   ← each has calculate(ds, segment_masks) -> dict
    runs/
        2026_Q2/
            survey_clean.parquet
            profile_report.md
            data_quality_report.md
            run_summary.txt
            analysis_results.json    ← YOU WRITE THIS (Step 4 output)
```

### Import paths

```python
# Add project root to sys.path (same pattern as run_pipeline.py)
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_loader.data_loader_api import load_survey_data
from analysis_engine.segments import get_all_segment_masks, describe_segments, SEGMENT_REGISTRY
from analysis_engine.sections import part_1, part_2, part_3, part_4, part_5, part_6, part_7
from analysis_engine.stats import LOW_N_THRESHOLD
```

---

## Known data note from Step 3

`q_medical_cost_change` is Categorical string dtype in Q2 data (not Int8 as originally
specced). Part 4 already handles this with string matching rather than numeric comparison.
`run_analysis.py` does not need any special handling — just call `part_4.calculate()`.

---

## CLI interface

```
python run_analysis.py                          # auto-selects latest run in runs/
python run_analysis.py --run-id 2026_Q2        # specific run
python run_analysis.py --run-id 2026_Q2 --quiet  # suppress per-section console output
```

Arguments:
- `--run-id` (optional str): run folder name under `runs/`. If omitted, auto-selects
  the most recently modified subfolder (same logic as `data_loader_api._find_latest_run`).
- `--quiet` (flag): suppress INFO logging; only print final summary and errors.

---

## Output file

Write `analysis_results.json` to `runs/{run_id}/`. Overwrite if it already exists.
Log a WARNING (not an error) if overwriting.

---

## `analysis_results.json` top-level schema

```json
{
  "meta": {
    "run_id":            "2026_Q2",
    "generated_at":      "2026-06-29T14:23:01+00:00",
    "schema_version":    "1.0",
    "n_total":           2111,
    "low_n_threshold":   30,
    "segments_active":   ["female", "male", "claimant", "non_claimant",
                          "first_time_access", "caregiver", "pwd",
                          "bundled_service_client"],
    "segments_skipped":  ["female_hh_head", "climate_shock"],
    "skip_reasons":      {
      "female_hh_head": "Column source not yet confirmed",
      "climate_shock":  "Definition not yet confirmed"
    },
    "section_timing_seconds": {
      "part_1": 0.12,
      "part_2": 0.08,
      ...
    },
    "section_errors": {}
  },
  "segments_summary": [ ... ],
  "parts": {
    "part_1": { ... },
    "part_2": { ... },
    "part_3": { ... },
    "part_4": { ... },
    "part_5": { ... },
    "part_6": { ... },
    "part_7": { ... }
  }
}
```

`"section_errors"` is populated only for failed sections (see error handling below).
`"segments_summary"` is the output of `describe_segments(ds.df)`.
`"skip_reasons"` is built from `SEGMENT_REGISTRY` entries where `available == False`.

---

## Section registry (module-level constant)

Define sections as a module-level list so adding a new section in the future is a
one-line edit:

```python
SECTIONS = [
    ("part_1", "Client Understanding & Value Perception", part_1),
    ("part_2", "Claims Experience",                       part_2),
    ("part_3", "Financial Resilience",                    part_3),
    ("part_4", "Child Wellbeing Outcomes",                part_4),
    ("part_5", "CWB Drivers",                            part_5),
    ("part_6", "Claimant vs Non-Claimant Scorecard",     part_6),
    ("part_7", "Female vs Male Scorecard",               part_7),
]
```

---

## Error handling

Wrap each section call in try/except. A failure in one section must not abort the others.
Record the error in `meta.section_errors` and continue.

```python
section_errors = {}
section_timing = {}

for key, label, module in SECTIONS:
    t0 = time.perf_counter()
    try:
        parts[key] = module.calculate(ds, segment_masks)
    except Exception as exc:
        log.error(f"  [{key}] FAILED: {exc}")
        section_errors[key] = {
            "error":   str(exc),
            "type":    type(exc).__name__,
        }
        parts[key] = None           # placeholder so key is present in JSON
    finally:
        section_timing[key] = round(time.perf_counter() - t0, 3)
```

If `section_errors` is non-empty at the end, exit with code 1 after writing the JSON
(so the file is still available for debugging). Print a clear message:

```
WARNING: 1 section(s) failed. Check analysis_results.json["meta"]["section_errors"].
```

---

## JSON serialisation — CRITICAL

The stat functions return dicts that may contain `numpy.int64`, `numpy.float64`,
`numpy.bool_`, and `pd.NA`. Standard `json.dumps()` will raise on all of these.

Define a custom encoder **before** the `main()` function:

```python
import numpy as np
import pandas as pd
import math

class _AnalysisEncoder(json.JSONEncoder):
    def default(self, obj):
        # numpy integer types
        if isinstance(obj, np.integer):
            return int(obj)
        # numpy float types (including nan/inf — convert to None)
        if isinstance(obj, np.floating):
            return None if math.isnan(obj) or math.isinf(obj) else float(obj)
        # numpy bool
        if isinstance(obj, np.bool_):
            return bool(obj)
        # numpy array
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # pandas NA / NaT
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
        return super().default(obj)
```

Write JSON with:

```python
json.dump(result, f, indent=2, ensure_ascii=False, cls=_AnalysisEncoder)
```

Also handle Python `float("nan")` and `float("inf")` — these are not valid JSON. The
encoder above covers numpy floats; also patch stdlib float by calling:

```python
# In _AnalysisEncoder.default(), stdlib float nan/inf reach here as plain Python float
# Handle by overriding encode() or by recursively replacing nan before serialisation.
```

Simplest approach: after assembling the `result` dict, do one recursive pass to replace
all `float("nan")` and `float("inf")` with `None` before serialising:

```python
def _sanitise(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitise(v) for v in obj]
    return obj

result = _sanitise(result)
```

Apply `_sanitise()` on the complete `result` dict before passing to `json.dump()`.

---

## Console summary (printed after JSON is written)

Print a table to stdout regardless of `--quiet` flag:

```
VisionFund Insurance Survey — Analysis Run
==========================================
Run ID          : 2026_Q2
Generated at    : 2026-06-29 14:23:01 UTC
Total respondents: 2,111
Low-n threshold : 30
Output          : runs/2026_Q2/analysis_results.json

Segments active : female(1518) male(586) claimant(153) non_claimant(210)
                  first_time_access(1803) caregiver(1928) pwd(477) bundled_service_client(9)
Segments skipped: female_hh_head, climate_shock

Section results:
  part_1  Client Understanding & Value Perception   OK    0.12s
  part_2  Claims Experience                         OK    0.08s
  part_3  Financial Resilience                      OK    0.09s
  part_4  Child Wellbeing Outcomes                  OK    0.11s
  part_5  CWB Drivers                               OK    0.05s
  part_6  Claimant vs Non-Claimant Scorecard        OK    0.07s
  part_7  Female vs Male Scorecard                  OK    0.06s

Status: COMPLETE (0 errors)
```

If sections failed:

```
Status: PARTIAL — 1 section(s) failed:
  part_3: ZeroDivisionError — division by zero
```

Use Python `print()` for this summary (not logging), so it always appears regardless of
log level.

---

## Logging

Logger name: `"run_analysis"`.
Use `logging.basicConfig` with format `"%(levelname)s | %(name)s | %(message)s"`.
`--quiet` sets root level to WARNING; default sets to INFO.

Do NOT use `print()` inside section calls or within the main run loop — only the final
summary table uses `print()`.

---

## Reusability requirements

1. **`SECTIONS` list is the only place to add a new section.** Adding a Part 8 requires
   creating `sections/part_8.py` and adding one entry to `SECTIONS`. Nothing else changes.

2. **`schema_version = "1.0"` as a module-level constant.** Bump it when the JSON shape
   changes so the generation layer can detect incompatible outputs.

3. **Run ID auto-detection is encapsulated.** If no `--run-id` is given, the script
   delegates to `load_survey_data()` (which calls `_find_latest_run()` internally).
   `run_analysis.py` does not implement its own directory search.

4. **Output path is always `{run_dir}/analysis_results.json`.** Resolved from `run_id`
   via `PROJECT_ROOT / "runs" / run_id`. Do not add `--output-dir`.

---

## What NOT to do

- Do not import between section files or duplicate any stats logic here
- Do not implement any stat calculations in this file
- Do not call `get_segment_mask()` directly — use `get_all_segment_masks()`
- Do not `print()` inside the computation loop — only the final summary block
- Do not silently swallow section exceptions — record them in `section_errors`
- Do not use `json.dumps()` without `_AnalysisEncoder` and `_sanitise()`

---

## Acceptance criteria

1. `python run_analysis.py --run-id 2026_Q2` exits with code 0 and writes
   `runs/2026_Q2/analysis_results.json`.

2. The JSON is valid: `json.load(open("runs/2026_Q2/analysis_results.json"))` raises no error.

3. All 7 `parts` keys are present: `part_1` through `part_7`.

4. No value in the entire JSON is `NaN`, `Infinity`, or a non-serialisable type
   (`numpy.int64`, `pd.NA`, etc.).

5. `result["meta"]["segments_skipped"]` contains `["female_hh_head", "climate_shock"]`.

6. `result["meta"]["section_errors"]` is an empty dict `{}` on a clean run.

7. `result["segments_summary"]` is a list of 10 dicts (8 available + 2 skipped),
   each with `"name"`, `"label"`, `"available"`, `"n"` keys.

8. Running the script twice overwrites the existing JSON and logs a WARNING about it.

9. `python run_analysis.py --run-id NONEXISTENT_RUN` exits with code 1 and prints a
   clear error message before any calculation begins.

10. Removing `part_3` from the `SECTIONS` list (simulating a future skip) causes the
    script to produce a JSON with only 6 parts and no error — demonstrating the registry
    is the only place that controls which sections run.
