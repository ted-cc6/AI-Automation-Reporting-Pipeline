"""qualitative/run_qualitative.py

Orchestrator for the qualitative analysis pipeline.

Usage:
    python qualitative/run_qualitative.py --run-id 2026_Q2
    python qualitative/run_qualitative.py --run-id 2026_Q2 --dry-run
    python qualitative/run_qualitative.py --run-id 2026_Q2 --parse-only

Options:
    --dry-run:    Build and print payload stats; do NOT call Gemini.
    --parse-only: Skip payload build and Gemini call; re-parse the existing
                  raw response from runs/{run_id}/gemini_raw_response.json.
                  Useful if the API call succeeded but parsing failed.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

from qualitative.prepare_payload import load_config, build_payload, print_payload_stats
from qualitative.gemini_call import call_gemini
from qualitative.parse_results import parse_and_save

ROOT = Path(__file__).parent.parent
PARQUET_PATH = ROOT / "data" / "survey_clean.parquet"


def main():
    parser = argparse.ArgumentParser(description="Run qualitative analysis pipeline")
    parser.add_argument("--run-id", default="2026_Q2",
                        help="Run identifier (default: 2026_Q2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build payload and print stats; do not call Gemini")
    parser.add_argument("--parse-only", action="store_true",
                        help="Re-parse existing raw response without calling Gemini")
    args = parser.parse_args()

    run_id = args.run_id
    raw_response_path = ROOT / "runs" / run_id / "gemini_raw_response.json"

    print(f"\n── Qualitative Pipeline | run_id={run_id} ──────────────────────")

    # Load data
    print("Loading survey data...")
    df = pd.read_parquet(PARQUET_PATH)
    config = load_config()

    if args.parse_only:
        # Re-parse existing raw response
        if not raw_response_path.exists():
            print(f"ERROR: {raw_response_path} not found. Run without --parse-only first.")
            sys.exit(1)
        print(f"Loading raw response from {raw_response_path}...")
        raw_gemini = json.loads(raw_response_path.read_text(encoding="utf-8"))

    else:
        # Phase 1 — Build payload
        print("\nPhase 1 — Building payload...")
        payload = build_payload(df, config)
        print_payload_stats(payload)

        if args.dry_run:
            print("\n[dry-run] Payload built successfully. Exiting without Gemini call.")
            return

        # Phase 2 — Call Gemini
        print(f"\nPhase 2 — Calling {config['model']}...")
        raw_gemini = call_gemini(
            payload=payload,
            raw_response_path=raw_response_path,
            model=config["model"],
        )
        print("  Gemini call complete.")

    # Phase 3 — Parse and save
    print("\nPhase 3 — Parsing and enriching results...")
    result = parse_and_save(
        raw_gemini=raw_gemini,
        df=df,
        run_id=run_id,
    )

    # Print summary
    print("\n── Results summary ─────────────────────────────────────────────")
    tc = result.get("theme_counts", {})
    for grp in ("promoters", "passives", "detractors"):
        top = list((tc.get(grp) or {}).items())[:3]
        print(f"  {grp} top themes: {top}")

    sv = result.get("section_verbatims", {})
    print(f"  Section verbatim sets: {len(sv)}/7")

    flags = result.get("protection_flags", [])
    print(f"  Protection flags found: {len(flags)}")
    for f in flags:
        print(f"    [{f.get('severity','?').upper()}] {f.get('flag_type')} — {f.get('id')}")

    print(f"\n  Output: runs/{run_id}/qualitative_results.json")
    print("────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
