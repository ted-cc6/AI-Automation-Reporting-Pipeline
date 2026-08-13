"""
run_pipeline.py — VisionFund Insurance Survey Pipeline Orchestrator

Runs all 5 data loader steps in sequence for a given CSV export, writing
all outputs to a versioned run folder under runs/.

Usage:
    python run_pipeline.py --csv path/to/export.csv
    python run_pipeline.py --csv path/to/export.csv --run-id 2026_Q3
"""

import argparse
import subprocess
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import yaml

from analysis_engine.country_config import DEFAULT_COUNTRY
from report_scopes import REPORT_SCOPES

PROJECT_ROOT = Path(__file__).parent
DATA_LOADER  = PROJECT_ROOT / "data_loader"
DATA_LOADER_LARCO = PROJECT_ROOT / "data_loader_larco"

# Which column_mapping.csv/value_coding_map.yaml pair the profiler/
# transformer read, keyed by the same dataset_schema strings used
# throughout the pipeline (data_loader_screening.py's SCOPE_COUNTRIES,
# data_loader_derived.py's VALID_INSURANCE_SLUGS, run_metadata.yaml).
DATASET_SCHEMA_PATHS = {
    "africa_vietnam": (DATA_LOADER / "column_mapping.csv", DATA_LOADER / "value_coding_map.yaml"),
    "larco":          (DATA_LOADER_LARCO / "column_mapping.csv", DATA_LOADER_LARCO / "value_coding_map.yaml"),
}
DEFAULT_DATASET_SCHEMA = "africa_vietnam"

STEPS = [
    {
        "name": "profiler",
        "script": DATA_LOADER / "data_loader_profiler.py",
        "args": lambda csv, run_dir, country, schema, report_scope: (
            ["--csv", str(csv), "--output-dir", str(run_dir),
             "--mapping", str(DATASET_SCHEMA_PATHS[schema][0])]
        ),
    },
    {
        "name": "transformer",
        "script": DATA_LOADER / "data_loader_transformer.py",
        "args": lambda csv, run_dir, country, schema, report_scope: (
            ["--csv", str(csv), "--output-dir", str(run_dir),
             "--mapping", str(DATASET_SCHEMA_PATHS[schema][0]),
             "--yaml", str(DATASET_SCHEMA_PATHS[schema][1])]
        ),
    },
    {
        "name": "screening",
        "script": DATA_LOADER / "data_loader_screening.py",
        # Scopes the report to a single country and/or a named region group
        # instead of the full multi-region portfolio; dataset_schema picks
        # the right SCOPE_COUNTRIES allow-list (see data_loader_screening.py).
        "args": lambda csv, run_dir, country, schema, report_scope: (
            ["--output-dir", str(run_dir), "--dataset-schema", schema]
            + (["--country", country] if country else [])
            + (["--report-scope", report_scope] if report_scope else [])
        ),
    },
    {
        "name": "derived",
        "script": DATA_LOADER / "data_loader_derived.py",
        # Also needs to know the scope: a country- or region-scoped run can
        # legitimately have zero severe-coping respondents (relaxes a
        # structural assertion that would otherwise treat that as a coding
        # bug). dataset_schema controls the insurance_type valid-slug
        # allow-list and which flags are expected to exist at all.
        "args": lambda csv, run_dir, country, schema, report_scope: (
            ["--output-dir", str(run_dir), "--dataset-schema", schema]
            + (["--country", country] if country else [])
            + (["--report-scope", report_scope] if report_scope else [])
        ),
    },
    {
        "name": "validator",
        "script": DATA_LOADER / "data_loader_validator.py",
        # Same reason as the "derived" step: its own independent
        # flag_negative_coping check needs the same scope awareness, and
        # dataset_schema picks which checks/range/slug lists apply.
        "args": lambda csv, run_dir, country, schema, report_scope: (
            ["--output-dir", str(run_dir), "--dataset-schema", schema]
            + (["--country", country] if country else [])
            + (["--report-scope", report_scope] if report_scope else [])
        ),
    },
]


def run_step(step: dict, csv: Path, run_dir: Path, filter_country: "str | None",
             dataset_schema: str, report_scope: "str | None" = None) -> None:
    cmd = [sys.executable, str(step["script"])] + step["args"](csv, run_dir, filter_country, dataset_schema, report_scope)
    print(f"\n{'='*60}")
    print(f"  Step: {step['name']}")
    print(f"  Cmd : {' '.join(cmd)}")
    print(f"{'='*60}\n")
    result = subprocess.run(cmd, check=False)
    if result.returncode != 0:
        print(
            f"\nERROR: step '{step['name']}' exited with code {result.returncode}. "
            "Pipeline halted.",
            file=sys.stderr,
        )
        sys.exit(result.returncode)


def write_summary(run_dir: Path, csv: Path, run_id: str) -> None:
    parquet = run_dir / "survey_clean.parquet"
    row_count = "unknown"
    if parquet.exists():
        try:
            import pandas as pd
            row_count = str(len(pd.read_parquet(parquet, columns=["insurance_type"])))
        except Exception:
            pass

    from datetime import datetime
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    summary = "\n".join([
        "VisionFund Insurance Survey — Run Summary",
        "=" * 44,
        f"run_id     : {run_id}",
        f"csv_file   : {csv.name}",
        f"csv_path   : {csv.resolve()}",
        f"row_count  : {row_count}",
        f"timestamp  : {ts}",
        f"run_dir    : {run_dir.resolve()}",
        "",
        "Artifacts:",
        f"  profile_report.md      : {(run_dir / 'profile_report.md').exists()}",
        f"  survey_clean.parquet   : {(run_dir / 'survey_clean.parquet').exists()}",
        f"  screening_report.md    : {(run_dir / 'screening_report.md').exists()}",
        f"  data_quality_report.md : {(run_dir / 'data_quality_report.md').exists()}",
    ])
    summary_path = run_dir / "run_summary.txt"
    summary_path.write_text(summary, encoding="utf-8")
    print(f"\nRun summary written: {summary_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VisionFund Survey Pipeline Orchestrator")
    parser.add_argument("--csv",    type=Path, required=True,
                        help="Path to the KoBoToolbox CSV export (semicolon-delimited, UTF-8)")
    parser.add_argument("--run-id", type=str,  default=None,
                        help="Run identifier for the output folder under runs/ (default: YYYY-MM-DD)")
    parser.add_argument("--country", type=str, default=DEFAULT_COUNTRY, metavar="COUNTRY",
                        help="Country identifier for analysis config (e.g. 'vietnam'). Default: 'default'.")
    parser.add_argument("--dataset-schema", type=str, default=DEFAULT_DATASET_SCHEMA,
                        choices=sorted(DATASET_SCHEMA_PATHS), metavar="SCHEMA",
                        help=f"Which source-survey schema this CSV export uses -- selects the "
                             f"column_mapping.csv/value_coding_map.yaml pair and every downstream "
                             f"step's schema-specific checks. Default: {DEFAULT_DATASET_SCHEMA!r}.")
    parser.add_argument("--report-scope", type=str, default=None,
                        choices=sorted(REPORT_SCOPES), metavar="SCOPE",
                        help="If given, scope this run to a named region group (see "
                             "report_scopes.py, e.g. 'lacro' or 'africa') instead of the full "
                             "multi-region portfolio. Independent of --country -- normal usage "
                             "picks one or the other, not both.")
    args = parser.parse_args()

    if not args.csv.exists():
        print(f"ERROR: CSV not found: {args.csv}", file=sys.stderr)
        sys.exit(1)

    run_id  = args.run_id or date.today().strftime("%Y-%m-%d")
    run_dir = PROJECT_ROOT / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    # "default" is the sentinel for "no single country selected" (see
    # analysis_engine/country_config.py) -- it means "use
    # country_configs/default.yaml", not an actual country to filter to.
    filter_country = args.country if args.country and args.country != DEFAULT_COUNTRY else None

    run_metadata_path = run_dir / "run_metadata.yaml"
    with open(run_metadata_path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"run_id": run_id, "country": args.country,
             "country_filter_applied": filter_country is not None,
             "dataset_schema": args.dataset_schema,
             "report_scope": args.report_scope,
             "created_at": datetime.now(timezone.utc).isoformat()},
            f, default_flow_style=False, allow_unicode=True,
        )
    print(f"Run metadata written — {run_metadata_path}")

    print(f"Pipeline starting — run_id: {run_id}")
    print(f"CSV     : {args.csv.resolve()}")
    print(f"Run dir : {run_dir.resolve()}")
    print(f"Schema  : {args.dataset_schema}")
    if args.report_scope:
        print(f"Scope   : {args.report_scope} ({REPORT_SCOPES[args.report_scope]['label']})")

    for step in STEPS:
        run_step(step, args.csv, run_dir, filter_country, args.dataset_schema, args.report_scope)

    write_summary(run_dir, args.csv, run_id)
    print(f"\nAll steps passed. Outputs in: {run_dir}")


if __name__ == "__main__":
    main()
