"""generation/run_generation.py

CLI entrypoint for the report generation pipeline.

Usage:
    python generation/run_generation.py --run-id 2026_Q2
    python generation/run_generation.py --run-id 2026_Q2 --dry-run
    python generation/run_generation.py --run-id 2026_Q2 --parts 1,4,5
    python generation/run_generation.py --run-id 2026_Q2 --parts 1 --skip-assembly
"""
import argparse
import json
import logging
import sys
from pathlib import Path

import yaml

from generation.orchestrator import preflight_check, orchestrate
from generation.writer import write_all_parts
from generation.assembler import assemble

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent


def parse_args():
    parser = argparse.ArgumentParser(description="VisionFund Report Generation Pipeline")
    parser.add_argument("--run-id", default="2026_Q2",
                        help="Run directory name (default: 2026_Q2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build packages and print data summary; do not call Gemini")
    parser.add_argument("--parts",
                        help="Comma-separated part numbers to generate (e.g. '1,4,5')")
    parser.add_argument("--skip-assembly", action="store_true",
                        help="Run Gemini writer but skip .docx assembly")
    return parser.parse_args()


def main():
    args     = parse_args()
    run_id   = args.run_id

    spec_path = ROOT / "generation" / "report_spec.yaml"
    spec      = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    if args.parts:
        parts_filter = [f"part_{p.strip()}" for p in args.parts.split(",")]
    else:
        # report_spec.yaml lists Parts 9/10 (LARCO-only, see run_analysis.py's
        # build_sections()) alongside the shared Parts 1-8 -- default to
        # excluding them unless this run's own metadata says dataset_schema
        # is "larco", so a plain `--run-id ... ` (no --parts) on Africa/
        # Vietnam data doesn't render two all-SUPPRESSED sections. An
        # explicit --parts always wins over this default.
        run_metadata_path = ROOT / "runs" / run_id / "run_metadata.yaml"
        dataset_schema = "africa_vietnam"
        if run_metadata_path.exists():
            with open(run_metadata_path, encoding="utf-8") as f:
                dataset_schema = (yaml.safe_load(f) or {}).get("dataset_schema", "africa_vietnam")
        parts_filter = None if dataset_schema == "larco" else [
            k for k in spec.get("parts", {}) if k not in ("part_9", "part_10")
        ]

    log.info(f"Generation Pipeline | run_id={run_id}")

    # Phase 1: Preflight
    log.info("Phase 1 — Preflight check...")
    result = preflight_check(run_id)
    if not result["ok"]:
        sys.exit(1)

    # Phase 2: Orchestrate
    log.info("Phase 2 — Extracting data packages...")
    packages = orchestrate(run_id, parts_filter)
    log.info(f"Packages built: {[p['part'] for p in packages]}")

    if args.dry_run:
        out = ROOT / "runs" / run_id / "dry_run_packages.json"
        out.write_text(
            json.dumps(packages, indent=2, default=str),
            encoding="utf-8"
        )
        print(f"\n[dry-run] Packages saved to {out}. Exiting without Gemini call.")
        for pkg in packages:
            print(f"\n  {pkg['part']} — {pkg['title']}")
            for s_key, s_data in pkg.get("sections", {}).items():
                if isinstance(s_data, dict):
                    n_metrics   = len(s_data.get("metrics", {}))
                    n_verbatims = len(s_data.get("verbatims", []))
                    wl          = s_data.get("word_limit", "?")
                    n_drivers   = len(s_data.get("drivers_data", []))
                    extras = f", {n_drivers} drivers" if n_drivers else ""
                    print(f"    {s_key}: {n_metrics} metrics, {n_verbatims} verbatims, word_limit={wl}{extras}")
            n_sc = len(pkg.get("scorecard", []))
            if n_sc:
                print(f"    scorecard: {n_sc} rows")
        return

    # Phase 3: Write (Gemini calls)
    log.info(f"Phase 3 — Writing report sections (Gemini {spec['model']})...")
    written_texts = write_all_parts(packages, run_id, model=spec["model"])
    failed_parts = [
        part_key for part_key, texts in written_texts.items()
        if isinstance(texts, dict) and texts.get("_generation_failed")
    ]
    log.info(f"{len(packages) - len(failed_parts)}/{len(packages)} parts written successfully.")

    if args.skip_assembly:
        print("\n[skip-assembly] Exiting before .docx build.")
        sys.exit(2 if failed_parts else 0)

    # Phase 4: Assemble
    log.info("Phase 4 — Assembling .docx...")
    output_filename = spec.get("output_filename", f"report_{run_id}.docx")
    output_path     = ROOT / "runs" / run_id / output_filename
    assemble(packages, written_texts, run_id, output_path)

    print("\n── Report complete ──────────────────────────────────────────────")
    print(f"  Output: {output_path}")
    if failed_parts:
        print(f"  WARNING: {len(failed_parts)} part(s) need manual write-up: {', '.join(failed_parts)}")
    print("────────────────────────────────────────────────────────────────\n")

    if failed_parts:
        sys.exit(2)


if __name__ == "__main__":
    main()
