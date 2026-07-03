"""
run_analysis.py — VisionFund Insurance Survey Analysis Orchestrator

Usage:
    python run_analysis.py                         # auto-selects latest run in runs/
    python run_analysis.py --run-id 2026_Q2        # specific run
    python run_analysis.py --run-id 2026_Q2 --quiet
"""
import argparse
import json
import logging
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from data_loader.data_loader_api import load_survey_data
from analysis_engine.country_config import load_country_config, DEFAULT_COUNTRY
from analysis_engine.segments import describe_segments, get_all_segment_masks
from analysis_engine.sections import part_1, part_2, part_3, part_4, part_5, part_6, part_7, part_8
from analysis_engine.stats import LOW_N_THRESHOLD

log = logging.getLogger("run_analysis")

SCHEMA_VERSION = "1.5"   # was "1.4" — inverted Likert scale corrected:
                          # bottom_two_box replaces top_two_box for all
                          # positive-outcome Likert metrics (Track D scale fix)

# Registry of section calculators — add a new section here only; nothing else changes.
SECTIONS = [
    ("part_1", "Client Understanding & Value Perception", part_1),
    ("part_2", "Claims Experience",                       part_2),
    ("part_3", "Financial Resilience",                    part_3),
    ("part_4", "Child Wellbeing Outcomes",                part_4),
    ("part_5", "CWB Drivers",                            part_5),
    ("part_6", "Claimant vs Non-Claimant Scorecard",     part_6),
    ("part_7", "Female vs Male Scorecard",               part_7),
    ("part_8", "Kling Index — Product Outcomes",         part_8),
]


# ---------------------------------------------------------------------------
# JSON serialisation helpers
# ---------------------------------------------------------------------------

class _AnalysisEncoder(json.JSONEncoder):
    """Handle numpy scalars, numpy arrays, and pd.NA in JSON output."""

    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return None if (math.isnan(obj) or math.isinf(obj)) else float(obj)
        if isinstance(obj, np.bool_):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
        return super().default(obj)


def _sanitise(obj):
    """Recursively replace Python float nan/inf with None (not valid JSON)."""
    if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
        return None
    if isinstance(obj, dict):
        return {k: _sanitise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitise(v) for v in obj]
    return obj


# ---------------------------------------------------------------------------
# Run resolution
# ---------------------------------------------------------------------------

def _resolve_run(run_id_arg):
    """Return (run_id, CleanDataset); auto-selects latest run when run_id_arg is None."""
    if run_id_arg:
        return run_id_arg, load_survey_data(run_id=run_id_arg)
    runs_dir = PROJECT_ROOT / "runs"
    if not runs_dir.exists():
        raise FileNotFoundError(f"Runs directory not found: {runs_dir}")
    subdirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not subdirs:
        raise FileNotFoundError(f"No run subdirectories found in {runs_dir}")
    latest = max(subdirs, key=lambda d: d.stat().st_mtime)
    return latest.name, load_survey_data(run_id=latest.name)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="VisionFund Insurance Survey Analysis Engine"
    )
    parser.add_argument(
        "--run-id", help="Run folder name under runs/ (default: latest)"
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress INFO logging; show only summary"
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.WARNING if args.quiet else logging.INFO,
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # 1. Load survey data (exits early with code 1 on failure)
    try:
        run_id, ds = _resolve_run(args.run_id)
    except (FileNotFoundError, ValueError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    run_dir     = PROJECT_ROOT / "runs" / run_id
    output_path = run_dir / "analysis_results.json"

    # 2. Read run metadata to determine country config
    metadata_path = run_dir / "run_metadata.yaml"
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            run_metadata = yaml.safe_load(f) or {}
        country = run_metadata.get("country", DEFAULT_COUNTRY)
    else:
        log.warning("run_metadata.yaml not found — using default country config")
        country = DEFAULT_COUNTRY

    country_config = load_country_config(country)
    if country_config.segment_overrides:
        log.info(f"Country config '{country}': segment overrides — {list(country_config.segment_overrides.keys())}")
    if country_config.metric_notes:
        log.info(f"Country config '{country}': metric notes — {list(country_config.metric_notes.keys())}")

    # 3. Compute segment masks once — shared across all section calculators
    log.info("Computing segment masks…")
    segment_masks = get_all_segment_masks(ds.df, country_config.segment_overrides)
    seg_desc      = describe_segments(ds.df, country_config.segment_overrides)

    # Derive skipped segments from the effective (override-applied) state
    segments_skipped = [d["name"] for d in seg_desc if not d.get("available", True)]
    skip_reasons     = {d["name"]: d.get("skip_reason", "") for d in seg_desc
                        if not d.get("available", True)}

    # 4. Run section calculators with per-section error isolation
    now             = datetime.now(timezone.utc)
    parts: dict     = {}
    section_errors: dict  = {}
    section_timing: dict  = {}

    log.info(f"Running {len(SECTIONS)} section(s) for run '{run_id}'…")
    for key, label, module in SECTIONS:
        t0 = time.perf_counter()
        try:
            parts[key] = module.calculate(ds, segment_masks)
        except Exception as exc:
            log.error(f"  [{key}] FAILED: {type(exc).__name__}: {exc}")
            section_errors[key] = {"error": str(exc), "type": type(exc).__name__}
            parts[key] = None
        finally:
            section_timing[key] = round(time.perf_counter() - t0, 3)

    # 5. Assemble result dict
    result = {
        "meta": {
            "run_id":                 run_id,
            "generated_at":           now.isoformat(timespec="seconds"),
            "schema_version":         SCHEMA_VERSION,
            "n_total":                ds.n,
            "low_n_threshold":        LOW_N_THRESHOLD,
            "country":                country_config.country,
            "country_label":          country_config.label,
            "report_context":         country_config.report_context,
            "metric_notes": {
                name: {
                    "note":                note.note,
                    "applies_to_segments": note.applies_to_segments,
                }
                for name, note in country_config.metric_notes.items()
            },
            "segments_active":        list(segment_masks.keys()),
            "segments_skipped":       segments_skipped,
            "skip_reasons":           skip_reasons,
            "section_timing_seconds": section_timing,
            "section_errors":         section_errors,
        },
        "segments_summary": seg_desc,
        "parts": parts,
    }

    # 6. Sanitise (replace float nan/inf → None) and write JSON
    result = _sanitise(result)

    if output_path.exists():
        log.warning(f"Overwriting existing file: {output_path}")

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, cls=_AnalysisEncoder)

    log.info(f"Wrote {output_path}")

    # 7. Console summary (always shown, regardless of --quiet)
    generated_display = now.strftime("%Y-%m-%d %H:%M:%S UTC")
    active_counts = {
        d["name"]: d["n"]
        for d in seg_desc
        if d.get("available") and d.get("n") is not None
    }
    seg_active_parts = [f"{k}({v:,})" for k, v in active_counts.items()]

    print()
    print("VisionFund Insurance Survey — Analysis Run")
    print("==========================================")
    print(f"Run ID            : {run_id}")
    if country_config.country != DEFAULT_COUNTRY:
        print(f"Country           : {country_config.label} ({country_config.country})")
    print(f"Generated at      : {generated_display}")
    print(f"Total respondents : {ds.n:,}")
    print(f"Low-n threshold   : {LOW_N_THRESHOLD}")
    print(f"Output            : {output_path}")
    print()
    # Wrap active segments across lines at ~80 chars
    seg_line, seg_lines = "", []
    prefix_w = len("Segments active   : ")
    for part in seg_active_parts:
        candidate = (seg_line + "  " + part).lstrip("  ") if seg_line else part
        if len(candidate) > 80 - prefix_w and seg_line:
            seg_lines.append(seg_line)
            seg_line = part
        else:
            seg_line = candidate
    if seg_line:
        seg_lines.append(seg_line)
    indent = " " * prefix_w
    print(f"Segments active   : {seg_lines[0]}")
    for extra in seg_lines[1:]:
        print(f"{indent}{extra}")
    print(f"Segments skipped  : {', '.join(segments_skipped) if segments_skipped else '(none)'}")
    print()
    print("Section results:")
    for key, label, _ in SECTIONS:
        timing  = section_timing.get(key, 0.0)
        status  = "FAILED" if key in section_errors else "OK"
        print(f"  {key:<8}  {label:<50}  {status:<6}  {timing:.2f}s")
        if key in section_errors:
            err = section_errors[key]
            print(f"           ! {err['type']}: {err['error']}")
    print()
    if section_errors:
        print(f"Status: PARTIAL — {len(section_errors)} section(s) failed:")
        for key, err in section_errors.items():
            print(f"  {key}: {err['type']} — {err['error']}")
    else:
        print("Status: COMPLETE (0 errors)")
    print()

    return 1 if section_errors else 0


if __name__ == "__main__":
    sys.exit(main())
