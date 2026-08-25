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
import logging
import sys
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv

from qualitative.prepare_payload import load_config, build_payload, print_payload_stats
from qualitative.llm_call import call_gemini
from qualitative.parse_results import parse_and_save
from data_quality_flags import flagged_countries

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
PARQUET_PATH = ROOT / "data" / "survey_clean.parquet"

# A .env file at the project root is optional -- load_dotenv() silently
# no-ops if it's absent (e.g. a deployed environment that sets
# GEMINI_API_KEY directly). Without this call, qualitative/llm_call.py's
# own os.environ.get("GEMINI_API_KEY") fallback (used when this CLI's
# caller doesn't pass api_key explicitly) never sees a .env file's
# contents at all -- confirmed missing during the session-8 smoke test.
load_dotenv(ROOT / ".env")


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

    log.info(f"Qualitative Pipeline | run_id={run_id}")

    # Load data
    log.info("Loading survey data...")
    df = pd.read_parquet(PARQUET_PATH)
    config = load_config()

    if args.parse_only:
        # Re-parse existing raw response
        if not raw_response_path.exists():
            log.error(f"{raw_response_path} not found. Run without --parse-only first.")
            sys.exit(1)
        log.info(f"Loading raw response from {raw_response_path}...")
        raw_gemini = json.loads(raw_response_path.read_text(encoding="utf-8"))

    else:
        # Phase 1 — Build payload
        log.info("Phase 1 — Building payload...")
        payload = build_payload(df, config)
        print_payload_stats(payload)

        if args.dry_run:
            print("\n[dry-run] Payload built successfully. Exiting without Gemini call.")
            return

        # Reuse the analysis engine's already-computed data_quality_flags
        # (analysis_results.json), if this run has already gone through
        # run_analysis.py -- same lookup dashboard/api/pipeline_runner.py
        # does, best-effort here since this standalone CLI path doesn't
        # otherwise know a run_id's report_scope.
        excluded_countries = []
        analysis_results_path = ROOT / "runs" / run_id / "analysis_results.json"
        if analysis_results_path.exists():
            try:
                stage2_result = json.loads(analysis_results_path.read_text(encoding="utf-8"))
                excluded_countries = flagged_countries(stage2_result.get("data_quality_flags") or [])
            except json.JSONDecodeError as exc:
                log.warning(f"Could not parse analysis_results.json for data quality flags: {exc}")

        # Phase 2 — Call Gemini
        log.info(f"Phase 2 — Calling {config['model']}...")
        raw_gemini = call_gemini(
            payload=payload,
            raw_response_path=raw_response_path,
            model=config["model"],
            excluded_countries=excluded_countries,
        )
        log.info("Gemini call complete.")

    # Phase 3 — Parse and save
    log.info("Phase 3 — Parsing and enriching results...")
    result = parse_and_save(
        raw_gemini=raw_gemini,
        df=df,
        run_id=run_id,
        provider="gemini",
        model=config["model"],
    )

    # Print summary
    print("\n── Results summary ─────────────────────────────────────────────")
    tc = result.get("theme_counts", {})
    for grp in ("promoters", "passives", "detractors"):
        top = list((tc.get(grp) or {}).items())[:3]
        print(f"  {grp} top themes: {top}")

    sv = result.get("section_verbatims", {})
    print(f"  Section verbatim sets: {len(sv)}/7")

    si = result.get("section_insights", {})
    print(f"  Section insight sets: {len(si)}/7")
    for section in sorted(si.keys()):
        entry = si[section]
        summary = entry.get("theme_summary", "")
        drivers = ", ".join(entry.get("top_drivers", []))
        print(f"    {section}: {summary}")
        if drivers:
            print(f"      drivers: {drivers}")
        # sentiment_split is R-006a's uniform nested shape (session-8):
        # {group_label: {positive, negative, neutral, base_n, ...}}, a
        # single-group section under "all" -- print each group on its
        # own line rather than the dict's own repr, which used to work
        # by coincidence when there was only ever one flat split.
        for group_label, split in (entry.get("sentiment_split") or {}).items():
            counts = f"positive={split.get('positive')}, negative={split.get('negative')}, neutral={split.get('neutral')}"
            print(f"      sentiment [{group_label}]: {counts}  (base_n={split.get('base_n')} of source_pool_n={split.get('source_pool_n')})")

    flags = result.get("protection_flags", [])
    print(f"  Protection flags found: {len(flags)}")
    for f in flags:
        print(f"    [{f.get('severity','?').upper()}] {f.get('flag_type')} — {f.get('id')}")

    print(f"\n  Output: runs/{run_id}/qualitative_results.json")
    print("────────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
