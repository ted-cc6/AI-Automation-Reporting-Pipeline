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

PROJECT_ROOT = Path(__file__).parent
DATA_LOADER  = PROJECT_ROOT / "data_loader"

STEPS = [
    {
        "name": "profiler",
        "script": DATA_LOADER / "data_loader_profiler.py",
        "args": lambda csv, run_dir, country: ["--csv", str(csv), "--output-dir", str(run_dir)],
    },
    {
        "name": "transformer",
        "script": DATA_LOADER / "data_loader_transformer.py",
        "args": lambda csv, run_dir, country: ["--csv", str(csv), "--output-dir", str(run_dir)],
    },
    {
        "name": "screening",
        "script": DATA_LOADER / "data_loader_screening.py",
        # Scopes the report to a single country instead of the full
        # multi-country portfolio.
        "args": lambda csv, run_dir, country: (
            ["--output-dir", str(run_dir)] + (["--country", country] if country else [])
        ),
    },
    {
        "name": "derived",
        "script": DATA_LOADER / "data_loader_derived.py",
        # Also needs to know the scope: a country-scoped run can legitimately
        # have zero severe-coping respondents (relaxes a structural assertion
        # that would otherwise treat that as a coding bug).
        "args": lambda csv, run_dir, country: (
            ["--output-dir", str(run_dir)] + (["--country", country] if country else [])
        ),
    },
    {
        "name": "validator",
        "script": DATA_LOADER / "data_loader_validator.py",
        # Same reason as the "derived" step: its own independent
        # flag_negative_coping check needs the same scope awareness.
        "args": lambda csv, run_dir, country: (
            ["--output-dir", str(run_dir)] + (["--country", country] if country else [])
        ),
    },
]


def run_step(step: dict, csv: Path, run_dir: Path, filter_country: "str | None") -> None:
    cmd = [sys.executable, str(step["script"])] + step["args"](csv, run_dir, filter_country)
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
             "created_at": datetime.now(timezone.utc).isoformat()},
            f, default_flow_style=False, allow_unicode=True,
        )
    print(f"Run metadata written — {run_metadata_path}")

    print(f"Pipeline starting — run_id: {run_id}")
    print(f"CSV     : {args.csv.resolve()}")
    print(f"Run dir : {run_dir.resolve()}")

    for step in STEPS:
        run_step(step, args.csv, run_dir, filter_country)

    write_summary(run_dir, args.csv, run_id)
    print(f"\nAll steps passed. Outputs in: {run_dir}")


if __name__ == "__main__":
    main()
