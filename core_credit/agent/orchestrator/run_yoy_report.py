"""CC-100: the year-over-year report in one command, for the final run once 2026 collection closes.

Runs, in order, each as its own process so a failure stops the chain:
  1. orchestrator/prepare_waves.py   export -> one analysis-ready CSV per wave + wave manifest
  2. analysis: python -m yoy.run_deltas   metric and theme changes (codes only answers not yet cached)
  3. orchestrator/run_orchestrator.py --prepared-csv <latest wave> --yoy <deltas>

Usage (from core_credit/agent):
    python orchestrator/run_yoy_report.py <multi-wave export> --run-id YoYFinal --collection-closed

Leave out --collection-closed for a provisional run: the report then marks every 2026 figure
provisional and names the countries still being surveyed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
PROCESSED_DIR = AGENT_ROOT.parent / "processed_data"


def _run(args: list, cwd: Path) -> None:
    print(f"\n>>> {' '.join(str(a) for a in args)}\n", flush=True)
    done = subprocess.run([sys.executable, *args], cwd=cwd)
    if done.returncode != 0:
        sys.exit(f"stopped: step exited with {done.returncode}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("raw_csv_path")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--collection-closed", action="store_true")
    args = parser.parse_args()

    prep = ["orchestrator/prepare_waves.py", args.raw_csv_path, "--run-id", args.run_id]
    _run(prep + (["--collection-closed"] if args.collection_closed else []), AGENT_ROOT)

    manifest_path = PROCESSED_DIR / f"{args.run_id}_wave_manifest.json"
    _run(["-m", "yoy.run_deltas", str(manifest_path)], AGENT_ROOT / "analysis")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    latest = next(w for w in manifest["waves"] if w["year"] == manifest["report_wave"])
    deltas_path = PROCESSED_DIR / f"{args.run_id}_yoy_deltas.json"
    _run(
        ["orchestrator/run_orchestrator.py", "--prepared-csv", latest["analysis_ready_csv"], "--yoy", str(deltas_path), "--run-id", args.run_id],
        AGENT_ROOT,
    )


if __name__ == "__main__":
    main()
