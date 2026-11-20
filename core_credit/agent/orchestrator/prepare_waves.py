"""CC-093: turn a multi-wave survey export into one analysis-ready CSV per wave, plus a wave
manifest the YoY steps read.

  1. Column Cleaner runs ONCE on the whole export, so both waves keep exactly the same
     columns (it is an LLM agent; two separate runs could keep different ones).
  2. The trimmed CSV is split by submission year (analysis/yoy/waves.py).
  3. Row Checker runs on each wave separately: one QA report per wave, and a client surveyed
     in both years is not flagged as a duplicate of themself.
  4. processed_data/<run_id>_wave_manifest.json records each wave's file and country counts,
     the comparison country set, partial countries, and whether collection is still open.

Usage (from core_credit/agent):
    python orchestrator/prepare_waves.py <raw export> --run-id YoY1 [--collection-closed]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
PROJECT_ROOT = AGENT_ROOT.parent  # core_credit

sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from orchestrator.data_prep_nodes import check_rows_node, clean_columns_node  # noqa: E402
from yoy.waves import SUBMISSION_TIME_COL, build_manifest, country_counts, split_waves, wave_of  # noqa: E402

PROCESSED_DIR = PROJECT_ROOT / "processed_data"


def _fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("raw_csv_path")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collection-closed", action="store_true", help="the latest wave has finished collecting")
    args = parser.parse_args()

    raw = Path(args.raw_csv_path).resolve()
    if not raw.exists():
        _fail(f"file not found: {raw}")

    print("1/4 Column Cleaner on the full export...")
    cleaned = clean_columns_node({"raw_csv_path": str(raw), "run_id": args.run_id})
    if cleaned.get("data_ready") is False:
        _fail(cleaned["failure_reason"])
    trimmed = pd.read_csv(cleaned["trimmed_csv_path"], dtype=str, encoding="utf-8-sig")
    print(f"    trimmed: {cleaned['trimmed_csv_path']} ({len(trimmed)} rows, {trimmed.shape[1]} columns)")

    print("2/4 Splitting by submission year...")
    waves = split_waves(trimmed)
    rows_without_wave = int(wave_of(trimmed[SUBMISSION_TIME_COL]).isna().sum())
    if len(waves) < 2:
        _fail(f"expected at least two waves, found {sorted(waves)}")

    paths, counts, columns = {}, {}, {}
    for year, wave_df in waves.items():
        wave_trimmed = PROCESSED_DIR / f"{args.run_id}_{year}_trimmed.csv"
        wave_df.to_csv(wave_trimmed, index=False)
        print(f"3/4 Row Checker on the {year} wave ({len(wave_df)} rows)...")
        checked = check_rows_node({"trimmed_csv_path": str(wave_trimmed), "run_id": f"{args.run_id}_{year}"})
        if not checked.get("data_ready"):
            _fail(f"{year} wave: {checked.get('failure_reason')}")
        ready = pd.read_csv(checked["csv_path"], dtype=str, encoding="utf-8-sig")
        paths[year], counts[year], columns[year] = checked["csv_path"], country_counts(ready), list(ready.columns)
        print(f"    {year}: {checked['csv_path']} ({len(ready)} rows)")

    first = next(iter(columns.values()))
    if any(cols != first for cols in columns.values()):
        _fail("the waves ended up with different columns; they cannot be compared")

    latest = waves[max(waves)]
    manifest = build_manifest(
        counts,
        paths,
        source_export=str(raw),
        last_submission=str(latest[SUBMISSION_TIME_COL].max()),
        rows_without_wave=rows_without_wave,
        collection_open=not args.collection_closed,
    )
    out = PROCESSED_DIR / f"{args.run_id}_wave_manifest.json"
    out.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"4/4 Manifest: {out}")
    print(f"    comparison countries ({len(manifest['comparison_countries'])}): {', '.join(manifest['comparison_countries'])}")
    print(f"    excluded: {manifest['excluded_countries']}")
    print(f"    partial: {manifest['partial_countries']}; provisional: {manifest['provisional']}")


if __name__ == "__main__":
    main()
