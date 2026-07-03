# Developer Prompt — Analysis Engine Step 4 (Revised): Orchestrator + Country Config
# Supersedes: step4_orchestrator_prompt.md

---

## Context

You are building Step 4 of the analysis engine for the VisionFund Insurance Client Survey.
Steps 1–3 are complete. Step 4 was originally scoped as just the orchestrator, but the
scope has expanded to include a country configuration layer before implementation began.
Build everything in this prompt together — do not implement the orchestrator first and
retrofit country config later.

**New requirement:** Future survey runs may cover different countries. Most countries share
the same analysis structure. Vietnam is the only country with special configuration right
now (climate shock segment, zero-premium caveats). When the dataset is identified as
Vietnam, the system must automatically apply Vietnam-specific config — no code changes,
only config files.

---

## Complete picture of what exists

```
analysis_engine/
    __init__.py
    segments.py          ← Step 1: SEGMENT_REGISTRY, get_all_segment_masks(df)
    stats.py             ← Step 2: stat functions, disaggregate(), LOW_N_THRESHOLD
    sections/
        part_1.py … part_7.py   ← Step 3: calculate(ds, segment_masks) → dict
runs/
    Vietnam_2026_Q2/
        survey_clean.parquet
        profile_report.md
        data_quality_report.md
        run_summary.txt
```

---

## What you must build

### New files

```
country_configs/
    _default.yaml                    ← baseline for all countries
    vietnam.yaml                     ← Vietnam-specific overrides
analysis_engine/
    country_config.py                ← loader + CountryConfig dataclass
run_analysis.py                      ← orchestrator (project root)
```

### Modified files

```
run_pipeline.py                      ← add --country arg; write run_metadata.yaml
analysis_engine/segments.py          ← add segment_overrides param to get_all_segment_masks()
```

---

## Part 1: Country config YAML files

### `country_configs/_default.yaml`

Baseline for every country that has no special arrangements.
Empty overrides — all keys present but empty:

```yaml
country: default
label:   Default
report_context: ""

segment_overrides: {}

metric_notes: {}
```

### `country_configs/vietnam.yaml`

Vietnam-specific configuration. Two concerns:
1. **Climate shock segment** — defined as all crop insurance clients (parametric payout triggered by typhoon)
2. **Zero-premium caveats** — crop insurance was grant-subsidized; worth_premium and confidence_pay questions are conceptually N/A for crop clients

```yaml
country: vietnam
label:   Vietnam
report_context: >
  Crop insurance program is grant-subsidized (zero client premium).
  Typhoon payout was triggered automatically (parametric/index basis) in late 2025 —
  all clients who held a crop policy received a payout.
  MFI is seeking funding to continue the program beyond July 2026 and is using
  this survey to support that fundraising effort.

segment_overrides:
  climate_shock:
    available:   true
    column:      is_crop
    label:       "Climate Shock (Vietnam Crop)"
    description: "Crop insurance clients — all received typhoon-triggered payout"
  female_hh_head:
    available:   false
    skip_reason: "Not applicable to insurance survey — household head data is in the core credit survey only"

metric_notes:
  worth_premium:
    note:                "Crop insurance was grant-subsidized (zero premium) — interpret scores for climate_shock segment with caution"
    applies_to_segments: [climate_shock]
  confidence_pay:
    note:                "Crop insurance was grant-subsidized (zero premium) — interpret scores for climate_shock segment with caution"
    applies_to_segments: [climate_shock]
  claims_funnel:
    note:                "Crop payout was index-triggered and automatic — clients did not file individual claims; funnel steps reflect this"
    applies_to_segments: []
```

---

## Part 2: `analysis_engine/country_config.py`

### Purpose

Loads and validates country YAML files. Returns a typed `CountryConfig` object that the
orchestrator passes to segment mask generation and injects into the JSON output.

### Dataclasses

```python
from dataclasses import dataclass, field

@dataclass
class SegmentOverride:
    available:   bool
    column:      str | None  = None     # required if available=True
    label:       str | None  = None
    description: str | None  = None
    skip_reason: str | None  = None     # required if available=False

@dataclass
class MetricNote:
    note:                str
    applies_to_segments: list[str] = field(default_factory=list)  # empty = applies globally

@dataclass
class CountryConfig:
    country:           str
    label:             str
    report_context:    str                         = ""
    segment_overrides: dict[str, SegmentOverride]  = field(default_factory=dict)
    metric_notes:      dict[str, MetricNote]        = field(default_factory=dict)
```

### `load_country_config(country: str) -> CountryConfig`

- Look for `country_configs/{country}.yaml`
- If not found and `country != "default"`: log WARNING, fall back to `_default.yaml`
- If `_default.yaml` not found: raise `FileNotFoundError` with a clear message
- Parse YAML → build dataclasses
- Validate: for each `SegmentOverride` where `available=True`, `column` must be present; raise `ValueError` if missing

```python
_CONFIGS_DIR = Path(__file__).parent.parent / "country_configs"

def load_country_config(country: str) -> CountryConfig:
    ...
```

### Module-level constants

```python
DEFAULT_COUNTRY = "default"
```

### Logging

Logger name: `"analysis_engine.country_config"`.
Log at INFO: which config file was loaded.
Log at WARNING: country not found, falling back to default.

### Dependencies

`pyyaml` — available in the Anaconda environment. No other new dependencies.

---

## Part 3: Modify `analysis_engine/segments.py`

Add an optional `segment_overrides` parameter to `get_all_segment_masks()`.
This is a backward-compatible change — existing callers with no override continue to work.

### New signature

```python
def get_all_segment_masks(
    df: pd.DataFrame,
    segment_overrides: "dict[str, SegmentOverride] | None" = None,
) -> dict[str, pd.Series]:
```

### Override logic

Before computing masks, build an effective registry by merging overrides into a copy
of `SEGMENT_REGISTRY`. Do not mutate the module-level `SEGMENT_REGISTRY`:

```python
def get_all_segment_masks(df, segment_overrides=None):
    # 1. Deep-copy registry entries that will be overridden
    effective = {k: dict(v) for k, v in SEGMENT_REGISTRY.items()}

    if segment_overrides:
        for seg_name, override in segment_overrides.items():
            if seg_name not in effective:
                log.warning(f"Override for unknown segment '{seg_name}' — ignoring")
                continue
            entry = effective[seg_name]
            entry["available"] = override.available
            if override.label:
                entry["label"] = override.label
            if override.skip_reason:
                entry["skip_reason"] = override.skip_reason
            # If activating a previously-unavailable segment, build its mask_fn
            if override.available and override.column:
                col = override.column
                entry["required_columns"] = [col]
                entry["mask_fn"] = (lambda df, c=col: df[c] == True)  # noqa: E712

    # 2. Compute masks using effective registry (existing logic unchanged)
    masks = {}
    for seg_name, entry in effective.items():
        if not entry.get("available", False):
            continue
        mask = _compute_mask(df, seg_name, entry)   # existing internal logic
        if mask is not None:
            masks[seg_name] = mask
    return masks
```

The `describe_segments()` function also needs the same optional parameter so the
segments summary in the JSON output reflects the active overrides:

```python
def describe_segments(df, segment_overrides=None) -> list[dict]:
    ...
```

---

## Part 4: Modify `run_pipeline.py`

### Add `--country` argument

```python
parser.add_argument(
    "--country",
    type=str,
    default="default",
    help="Country identifier (e.g. 'vietnam'). Determines which country config is applied during analysis. Default: 'default'.",
)
```

### Write `run_metadata.yaml` after run directory is created

After the run directory is created (before any pipeline steps run):

```python
import yaml
from datetime import datetime, timezone

metadata = {
    "run_id":       args.run_id,
    "country":      args.country,
    "created_at":   datetime.now(timezone.utc).isoformat(),
}
run_metadata_path = run_dir / "run_metadata.yaml"
with open(run_metadata_path, "w", encoding="utf-8") as f:
    yaml.dump(metadata, f, default_flow_style=False)
log.info(f"Run metadata written to {run_metadata_path}")
```

---

## Part 5: `run_analysis.py` (project root)

### CLI

```
python run_analysis.py                        # auto-selects latest run
python run_analysis.py --run-id Vietnam_2026_Q2   # specific run
python run_analysis.py --quiet                # suppress INFO logging
```

No `--country` flag here — the country is read from `run_metadata.yaml` that
`run_pipeline.py` already wrote. This ensures the analysis always uses the same
country that was declared when the data was loaded.

### Full implementation spec

```python
PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_loader.data_loader_api       import load_survey_data
from analysis_engine.segments          import get_all_segment_masks, describe_segments, SEGMENT_REGISTRY
from analysis_engine.stats             import LOW_N_THRESHOLD
from analysis_engine.country_config    import load_country_config, DEFAULT_COUNTRY
from analysis_engine.sections          import part_1, part_2, part_3, part_4, part_5, part_6, part_7

SCHEMA_VERSION = "1.1"   # bumped from 1.0 to reflect country config addition

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

### Startup sequence

```python
def main():
    args = _parse_args()

    # 1. Load data (resolves run_dir internally)
    ds = load_survey_data(run_id=args.run_id)
    run_dir = PROJECT_ROOT / "runs" / (args.run_id or _latest_run_id())

    # 2. Read run_metadata.yaml → determine country
    metadata_path = run_dir / "run_metadata.yaml"
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            run_metadata = yaml.safe_load(f) or {}
        country = run_metadata.get("country", DEFAULT_COUNTRY)
    else:
        country = DEFAULT_COUNTRY
        log.warning("run_metadata.yaml not found — using default country config")

    # 3. Load country config
    country_config = load_country_config(country)
    log.info(f"Country config: {country_config.label} ({country})")
    if country_config.segment_overrides:
        log.info(f"  Segment overrides: {list(country_config.segment_overrides.keys())}")
    if country_config.metric_notes:
        log.info(f"  Metric notes: {list(country_config.metric_notes.keys())}")

    # 4. Compute segment masks (with country overrides applied)
    segment_masks = get_all_segment_masks(ds.df, country_config.segment_overrides)
    segments_summary = describe_segments(ds.df, country_config.segment_overrides)

    # 5. Run section calculators
    parts, section_errors, section_timing = _run_sections(ds, segment_masks)

    # 6. Assemble output
    result = _assemble_output(
        ds, run_metadata, country_config,
        segment_masks, segments_summary,
        parts, section_errors, section_timing,
    )

    # 7. Write JSON
    out_path = run_dir / "analysis_results.json"
    if out_path.exists():
        log.warning(f"Overwriting existing {out_path.name}")
    result = _sanitise(result)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, cls=_AnalysisEncoder)
    log.info(f"Written: {out_path}")

    # 8. Print summary
    _print_summary(result, out_path, section_errors)

    sys.exit(1 if section_errors else 0)
```

### `_run_sections()` — error isolation

```python
def _run_sections(ds, segment_masks):
    parts, errors, timing = {}, {}, {}
    for key, label, module in SECTIONS:
        t0 = time.perf_counter()
        try:
            parts[key] = module.calculate(ds, segment_masks)
        except Exception as exc:
            log.error(f"  [{key}] FAILED: {exc}")
            errors[key] = {"error": str(exc), "type": type(exc).__name__}
            parts[key] = None
        finally:
            timing[key] = round(time.perf_counter() - t0, 3)
    return parts, errors, timing
```

### `analysis_results.json` schema (version 1.1)

```json
{
  "meta": {
    "run_id":                "Vietnam_2026_Q2",
    "schema_version":        "1.1",
    "generated_at":          "2026-06-29T14:23:01+00:00",
    "country":               "vietnam",
    "country_label":         "Vietnam",
    "report_context":        "Crop insurance program is grant-subsidized...",
    "n_total":               2111,
    "low_n_threshold":       30,
    "segments_active":       ["female", "male", "claimant", "non_claimant",
                              "first_time_access", "caregiver", "pwd",
                              "bundled_service_client", "climate_shock"],
    "segments_skipped":      ["female_hh_head"],
    "skip_reasons":          {
      "female_hh_head": "Not applicable to insurance survey — household head data is in the core credit survey only"
    },
    "metric_notes":          {
      "worth_premium":   {
        "note":                "Crop insurance was grant-subsidized (zero premium) — interpret scores for climate_shock segment with caution",
        "applies_to_segments": ["climate_shock"]
      },
      "confidence_pay":  { ... },
      "claims_funnel":   { ... }
    },
    "section_timing_seconds": { "part_1": 0.12, ... },
    "section_errors":         {}
  },
  "segments_summary": [ ... ],
  "parts": {
    "part_1": { ... },
    ...
    "part_7": { ... }
  }
}
```

For a default-country run, `"country": "default"`, `"report_context": ""`,
`"metric_notes": {}`. The `climate_shock` segment is absent from `segments_active`
and does not appear in any disaggregation output.

### JSON serialisation — `_AnalysisEncoder` and `_sanitise()`

Same as originally specced:

```python
class _AnalysisEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.integer): return int(obj)
        if isinstance(obj, np.floating):
            return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
        if isinstance(obj, np.bool_): return bool(obj)
        if isinstance(obj, np.ndarray): return obj.tolist()
        try:
            if pd.isna(obj): return None
        except (TypeError, ValueError): pass
        return super().default(obj)

def _sanitise(obj):
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict): return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list): return [_sanitise(v) for v in obj]
    return obj
```

### Console summary

```
VisionFund Insurance Survey — Analysis Run
==========================================
Run ID          : Vietnam_2026_Q2
Country         : Vietnam
Generated at    : 2026-06-29 14:23:01 UTC
Total respondents: 2,111
Output          : runs/Vietnam_2026_Q2/analysis_results.json

Country config  : vietnam.yaml loaded
  Segments overridden : climate_shock (activated), female_hh_head (deactivated)
  Metric notes        : worth_premium, confidence_pay, claims_funnel

Segments active : female(1518) male(586) claimant(153) non_claimant(210)
                  first_time_access(1803) caregiver(1928) pwd(477)
                  bundled_service_client(9) climate_shock(154)
Segments skipped: female_hh_head

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

---

## Run naming convention

Suggested format: `{Country}_{Year}_{Quarter}`

Examples:
```
Vietnam_2026_Q2
Kenya_2026_Q1
Cambodia_2026_Q2
```

For a combined/global dataset if one ever occurs: `Global_2026_Q2` with `--country default`.

---

## Reusability requirements

1. **Adding a new country** = create one YAML in `country_configs/`. No Python changes.
2. **Adding a Vietnam-specific segment override** = edit `vietnam.yaml`. No Python changes.
3. **`SECTIONS` list is the only place to add a new section.** Adding Part 8 = new file in `sections/` + one entry in `SECTIONS`.
4. **`SCHEMA_VERSION = "1.1"` as a module-level constant.** Bump when JSON shape changes.
5. **`get_all_segment_masks()` remains backward-compatible.** Callers that pass only `df` still work.

---

## What NOT to do

- Do not hardcode `"vietnam"` anywhere in Python — all Vietnam-specific logic lives in `vietnam.yaml`
- Do not add a `--country` argument to `run_analysis.py` — country comes from `run_metadata.yaml`
- Do not add a `--country` argument to `run_analysis.py` — read from `run_metadata.yaml` only
- Do not mutate `SEGMENT_REGISTRY` — build `effective` as a local copy inside the function
- Do not add `pytest` tests or `__main__` blocks to `country_config.py`

---

## Acceptance criteria

1. **Default run:**
   `python run_pipeline.py --csv export.csv --run-id Test_2026_Q2` (no `--country`)
   → `run_metadata.yaml` contains `country: default`
   → `run_analysis.py` loads `_default.yaml`
   → `climate_shock` absent from `segments_active`
   → `female_hh_head` in `segments_skipped` with original skip reason

2. **Vietnam run:**
   `python run_pipeline.py --csv export.csv --run-id Vietnam_2026_Q2 --country vietnam`
   → `run_metadata.yaml` contains `country: vietnam`
   → `run_analysis.py` loads `vietnam.yaml`
   → `climate_shock` present in `segments_active` with n=154
   → `female_hh_head` in `segments_skipped` with updated Vietnam-specific reason
   → `meta.metric_notes` contains entries for `worth_premium`, `confidence_pay`, `claims_funnel`
   → `meta.report_context` contains the fundraising/grant context string

3. All 7 `parts` keys present; JSON is valid (`json.load()` raises no error).

4. No `numpy`, `pd.NA`, `NaN`, or `Infinity` values in the JSON.

5. `get_all_segment_masks(ds.df)` (no overrides) returns the same result as before Step 4
   — backward compatibility confirmed.

6. `get_all_segment_masks(ds.df, overrides)` with Vietnam overrides returns `climate_shock`
   in the result dict with `n=154` (all crop clients).

7. Unknown country (`--country zimbabwe` with no `zimbabwe.yaml`) falls back to
   `_default.yaml` and logs a WARNING — does not crash.

8. Missing `run_metadata.yaml` → falls back to default country, logs a WARNING — does not crash.

9. A section calculator failure is recorded in `meta.section_errors`; the other 6 sections
   still complete; the JSON is still written; exit code is 1.

10. Removing a section from `SECTIONS` list produces a JSON with one fewer `parts` key
    and no error — confirming the registry is the single control point.
