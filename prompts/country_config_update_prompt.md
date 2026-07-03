# Developer Prompt — Country Config Update (Steps 1–7)
# Adds country-aware configuration layer to the existing analysis engine

---

## Context

The analysis engine (Steps 1–4) is fully built and working. This prompt delivers a
targeted update across 6 existing files and 3 new files to support:

1. **Female HH Head** — permanently deactivated (confirmed not applicable to insurance survey)
2. **Climate Shock** — activated as `is_crop == True` for Vietnam runs only, via a new
   country config layer
3. **Country config layer** — YAML-driven, zero code changes needed to add future countries

All changes must be backward-compatible. Running `python run_analysis.py --run-id 2026_Q2`
without any country config present must still work (falls back to default config).

---

## What currently exists (do not modify unless specified)

```
analysis_engine/
    __init__.py
    segments.py          ← MODIFY (Steps 1 & 2)
    stats.py             ← do not touch
    country_config.py    ← CREATE (Step 4)
    sections/
        part_1.py … part_7.py   ← do not touch
run_pipeline.py          ← MODIFY (Step 5)
run_analysis.py          ← MODIFY (Step 6)
runs/
    2026_Q2/             ← MODIFY (Step 7 — add run_metadata.yaml manually)
```

### Current state of `segments.py` relevant to this update

The registry currently has these two placeholder entries:

```python
"female_hh_head": {
    "label":            "Female HH Head",
    "available":        False,
    "required_columns": [],
    "skip_reason":      "Column source not yet confirmed",   # ← CHANGE THIS
    "mask_fn":          None,
},
"climate_shock": {
    "label":            "Climate Shock",
    "available":        False,
    "required_columns": [],
    "skip_reason":      "Definition not yet confirmed",      # ← CHANGE THIS
    "mask_fn":          None,
},
```

`get_all_segment_masks(df)` and `describe_segments(df)` both take only `df` right now.

---

## STEP 1 — Update `segments.py` registry entries (text changes only)

Change exactly two strings. No logic changes in this step.

**`female_hh_head`** — update `skip_reason`:
```python
"skip_reason": "Not applicable to insurance survey — household head status is only captured in the core credit survey",
```

**`climate_shock`** — update `skip_reason`:
```python
"skip_reason": "Vietnam-only segment — activated via country config when --country vietnam is used",
```

Both entries keep `available: False`. Vietnam overrides this at runtime in Step 2.

---

## STEP 2 — Add `segment_overrides` to `segments.py` functions

Update two functions. Both are backward-compatible (new parameter defaults to `None`).

### `get_all_segment_masks(df, segment_overrides=None)`

New logic: before computing masks, build a local copy of `SEGMENT_REGISTRY` and merge
any overrides into it. **Never mutate the module-level `SEGMENT_REGISTRY`.**

```python
def get_all_segment_masks(df, segment_overrides=None):
    # Build a shallow copy — dict entries are also copied to allow mutation
    effective = {k: dict(v) for k, v in SEGMENT_REGISTRY.items()}

    if segment_overrides:
        for seg_name, override in segment_overrides.items():
            if seg_name not in effective:
                log.warning(f"segment_overrides: unknown segment '{seg_name}' — ignoring")
                continue
            entry = effective[seg_name]
            entry["available"] = override.available
            if getattr(override, "label", None):
                entry["label"] = override.label
            if getattr(override, "skip_reason", None):
                entry["skip_reason"] = override.skip_reason
            # If activating a segment, build its mask_fn from the specified column
            if override.available:
                col = getattr(override, "column", None)
                if not col:
                    log.warning(f"segment_overrides: '{seg_name}' is available=True but has no column — skipping")
                    entry["available"] = False
                    continue
                entry["required_columns"] = [col]
                # Use default-argument capture to avoid closure capture bug
                entry["mask_fn"] = lambda df, c=col: df[c] == True  # noqa: E712

    # All existing mask-computation logic below uses `effective` instead of SEGMENT_REGISTRY
    # Replace every reference to SEGMENT_REGISTRY in the loop body with `effective`
    masks = {}
    for seg_name, entry in effective.items():
        if not entry.get("available", False):
            continue
        mask = get_segment_mask_from_entry(df, seg_name, entry)   # existing internal call
        if mask is not None:
            masks[seg_name] = mask
    return masks
```

If the existing function uses `SEGMENT_REGISTRY` directly in its loop, replace those
references with `effective`. The rest of the function body is unchanged.

### `describe_segments(df, segment_overrides=None)`

Apply identical override merge at the top of this function, then use `effective` in
place of `SEGMENT_REGISTRY` for the rest of the existing logic:

```python
def describe_segments(df, segment_overrides=None):
    effective = {k: dict(v) for k, v in SEGMENT_REGISTRY.items()}
    if segment_overrides:
        # same merge logic as get_all_segment_masks above
        ...
    # existing loop using `effective`
```

---

## STEP 3 — Create `country_configs/` directory and two YAML files

Create the directory at the project root. Create both files exactly as shown.

### `country_configs/_default.yaml`

```yaml
country: default
label: Default
report_context: ""
segment_overrides: {}
metric_notes: {}
```

### `country_configs/vietnam.yaml`

```yaml
country: vietnam
label: Vietnam
report_context: >
  Crop insurance program is grant-subsidized (zero client premium).
  Typhoon payout was triggered automatically (parametric/index basis) in late 2025 —
  all clients who held a crop policy received a payout.
  MFI is seeking funding to continue the program beyond July 2026.

segment_overrides:
  climate_shock:
    available: true
    column: is_crop
    label: "Climate Shock (Vietnam Crop)"
    description: "Crop insurance clients — all received typhoon-triggered payout"
  female_hh_head:
    available: false
    skip_reason: "Not applicable to insurance survey — household head data is in the core credit survey only"

metric_notes:
  worth_premium:
    note: "Crop insurance was grant-subsidized (zero premium) — interpret climate_shock segment scores with caution"
    applies_to_segments:
      - climate_shock
  confidence_pay:
    note: "Crop insurance was grant-subsidized (zero premium) — interpret climate_shock segment scores with caution"
    applies_to_segments:
      - climate_shock
  claims_funnel:
    note: "Crop payout was index-triggered and automatic — clients did not file individual claims"
    applies_to_segments: []
```

---

## STEP 4 — Create `analysis_engine/country_config.py`

New file. Contains three things only: two dataclasses, one loader function, one constant.

### Module structure

```python
"""country_config.py — Country-specific configuration loader for the analysis engine."""

import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("analysis_engine.country_config")

_CONFIGS_DIR = Path(__file__).parent.parent / "country_configs"
DEFAULT_COUNTRY = "default"
```

### Dataclasses

```python
@dataclass
class SegmentOverride:
    available:   bool
    column:      str | None  = None
    label:       str | None  = None
    description: str | None  = None
    skip_reason: str | None  = None

@dataclass
class MetricNote:
    note:                str
    applies_to_segments: list[str] = field(default_factory=list)

@dataclass
class CountryConfig:
    country:           str
    label:             str
    report_context:    str                          = ""
    segment_overrides: dict[str, SegmentOverride]   = field(default_factory=dict)
    metric_notes:      dict[str, MetricNote]         = field(default_factory=dict)
```

### `load_country_config(country: str) -> CountryConfig`

```python
def load_country_config(country: str) -> CountryConfig:
    yaml_path = _CONFIGS_DIR / f"{country}.yaml"

    if not yaml_path.exists():
        if country != DEFAULT_COUNTRY:
            log.warning(f"No config found for country '{country}' — falling back to default")
        yaml_path = _CONFIGS_DIR / f"{DEFAULT_COUNTRY}.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Default country config not found: {yaml_path}. "
            "Ensure country_configs/_default.yaml exists."
        )

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    log.info(f"Loaded country config: {yaml_path.name}")

    # Parse segment_overrides
    segment_overrides = {}
    for seg_name, raw in (data.get("segment_overrides") or {}).items():
        if not isinstance(raw, dict):
            continue
        override = SegmentOverride(**{k: v for k, v in raw.items()
                                      if k in SegmentOverride.__dataclass_fields__})
        # Validate: available=True requires a column
        if override.available and not override.column:
            raise ValueError(
                f"Country config '{country}': segment_override '{seg_name}' has "
                f"available=true but no column specified."
            )
        segment_overrides[seg_name] = override

    # Parse metric_notes
    metric_notes = {}
    for metric_name, raw in (data.get("metric_notes") or {}).items():
        if not isinstance(raw, dict):
            continue
        metric_notes[metric_name] = MetricNote(
            note=raw.get("note", ""),
            applies_to_segments=raw.get("applies_to_segments") or [],
        )

    return CountryConfig(
        country=data.get("country", country),
        label=data.get("label", country.title()),
        report_context=data.get("report_context", ""),
        segment_overrides=segment_overrides,
        metric_notes=metric_notes,
    )
```

No `__main__` block. No imports from `analysis_engine.segments` (no circular dependency).

---

## STEP 5 — Update `run_pipeline.py`

Two additions only. Do not change any existing pipeline step logic.

### Addition 1: `--country` argument

Add to the argument parser (after existing arguments):

```python
parser.add_argument(
    "--country",
    type=str,
    default=DEFAULT_COUNTRY,
    metavar="COUNTRY",
    help="Country identifier for analysis config (e.g. 'vietnam'). Default: 'default'.",
)
```

Add the import at the top of the file:
```python
from analysis_engine.country_config import DEFAULT_COUNTRY
```

### Addition 2: write `run_metadata.yaml`

Insert immediately after the run directory is created and before the first pipeline step
begins:

```python
import yaml
from datetime import datetime, timezone

run_metadata = {
    "run_id":     args.run_id,
    "country":    args.country,
    "created_at": datetime.now(timezone.utc).isoformat(),
}
run_metadata_path = run_dir / "run_metadata.yaml"
with open(run_metadata_path, "w", encoding="utf-8") as f:
    yaml.dump(run_metadata, f, default_flow_style=False, allow_unicode=True)
log.info(f"Run metadata written → {run_metadata_path}")
```

---

## STEP 6 — Update `run_analysis.py`

Four targeted additions. The section calculator loop, JSON encoder, and console summary
are unchanged.

### Addition 1: read `run_metadata.yaml`

After the run directory is resolved (after `load_survey_data` returns), add:

```python
import yaml
from analysis_engine.country_config import load_country_config, DEFAULT_COUNTRY

metadata_path = run_dir / "run_metadata.yaml"
if metadata_path.exists():
    with open(metadata_path, encoding="utf-8") as f:
        run_metadata = yaml.safe_load(f) or {}
    country = run_metadata.get("country", DEFAULT_COUNTRY)
else:
    log.warning("run_metadata.yaml not found — using default country config")
    country = DEFAULT_COUNTRY
```

### Addition 2: load country config and log it

```python
country_config = load_country_config(country)
if country_config.segment_overrides:
    overridden = list(country_config.segment_overrides.keys())
    log.info(f"Country config '{country}': segment overrides → {overridden}")
if country_config.metric_notes:
    log.info(f"Country config '{country}': metric notes → {list(country_config.metric_notes.keys())}")
```

### Addition 3: pass overrides to segment mask generation

Replace the two existing calls:
```python
# BEFORE:
segment_masks    = get_all_segment_masks(ds.df)
segments_summary = describe_segments(ds.df)

# AFTER:
segment_masks    = get_all_segment_masks(ds.df, country_config.segment_overrides)
segments_summary = describe_segments(ds.df, country_config.segment_overrides)
```

### Addition 4: inject country fields into `meta` block of result dict

In the `_assemble_output` function (or wherever the `meta` dict is built), add these
keys. Insert after the existing `n_total` / `low_n_threshold` keys:

```python
"country":        country_config.country,
"country_label":  country_config.label,
"report_context": country_config.report_context,
"metric_notes":   {
    name: {
        "note":                note.note,
        "applies_to_segments": note.applies_to_segments,
    }
    for name, note in country_config.metric_notes.items()
},
```

Also update the schema version constant:
```python
SCHEMA_VERSION = "1.1"   # was "1.0"
```

Update the console summary to print the country line when it is not "default":
```python
if country_config.country != DEFAULT_COUNTRY:
    print(f"Country         : {country_config.label} ({country_config.country})")
```

---

## STEP 7 — Migrate the existing `runs/2026_Q2/` run

Create `runs/2026_Q2/run_metadata.yaml` manually (do not re-run `run_pipeline.py`):

```yaml
run_id: 2026_Q2
country: vietnam
created_at: "2026-06-30T00:00:00+00:00"
```

Then regenerate the analysis output:
```
python run_analysis.py --run-id 2026_Q2
```

This overwrites `runs/2026_Q2/analysis_results.json` with the Vietnam config applied.

---

## What NOT to do

- Do not mutate `SEGMENT_REGISTRY` — always build `effective = {k: dict(v) for k, v in SEGMENT_REGISTRY.items()}`
- Do not import from `analysis_engine.segments` inside `country_config.py` (circular dependency risk)
- Do not add a `--country` flag to `run_analysis.py` — country is always read from `run_metadata.yaml`
- Do not change any section calculator (`part_1.py` through `part_7.py`)
- Do not change `stats.py`
- Do not add `pytest` tests or `__main__` blocks to `country_config.py`

---

## Acceptance criteria (verify against `runs/2026_Q2/analysis_results.json`)

1. `meta.country` == `"vietnam"`
2. `meta.country_label` == `"Vietnam"`
3. `meta.schema_version` == `"1.1"`
4. `meta.segments_active` includes `"climate_shock"` (n=154 crop clients)
5. `meta.segments_skipped` == `["female_hh_head"]` — climate_shock is no longer skipped
6. `meta.skip_reasons["female_hh_head"]` contains `"core credit survey"` (updated reason)
7. `meta.metric_notes` has entries for `worth_premium`, `confidence_pay`, and `claims_funnel`
8. `parts.part_1.metrics.coverage_understanding.segments` has a `"climate_shock"` key with `n_total == 154`
9. `climate_shock` segment appears in Parts 6 and 7 scorecard metric rows (may be `suppressed=true` for small sub-groups, but the key must be present)
10. Running `python run_analysis.py --run-id 2026_Q2` without any `run_metadata.yaml` (rename it temporarily to test) logs a WARNING and completes successfully using the default config — `climate_shock` absent, no crash
