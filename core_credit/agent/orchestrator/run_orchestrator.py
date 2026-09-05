"""CLI entry point for the top-level orchestrator: raw survey export -> final branded .docx +
QA notes, running every node in orchestrator/graph.py end to end.

Checkpointed to its own SQLite file (checkpoints.db, next to this script -- separate from
graph/checkpoints.db, which is for the section-level graphs' own internal state) so a run
interrupted partway through can be resumed under the same --run-id: sections that already
finished are skipped, not recomputed. Reuses graph.checkpointing.sqlite_checkpointer (the same
pickle_fallback=True serializer already proven against this project's rich state objects)
rather than writing a second one.

LangSmith tracing: automatic via the LANGSMITH_* env vars in .env (same as every other
LLM-calling component in this project) -- every nested call this graph makes (the two data-prep
agents, every section's writer/qualitative-agent calls, the QA review) is traced under one
top-level run, named and tagged below for findability in the LangSmith UI.

Usage:
    python run_orchestrator.py <raw_survey_csv> [--run-id 2026Q3] [--skip-qa]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
PROJECT_ROOT = AGENT_ROOT.parent  # core_credit

sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from graph.checkpointing import sqlite_checkpointer  # noqa: E402
from report_assembly.build_report import CROSS_CUTTING_SECTIONS, THEME_SECTIONS  # noqa: E402

from orchestrator.graph import compile_graph  # noqa: E402

CHECKPOINT_DB = str(Path(__file__).resolve().parent / "checkpoints.db")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
ALL_SECTION_IDS = THEME_SECTIONS + CROSS_CUTTING_SECTIONS


def diagnose_failure(compiled, graph_config: dict, exc: Exception) -> dict:
    """CC-038: best-effort summary of a graph run that raised, built from whatever the
    checkpointer already persisted -- LangGraph writes state after each node that completes
    (a superstep), so a node that raises partway through never gets its own write in, but
    every node that finished before it is already there. This is what makes a "which node
    failed" report possible without the exception itself carrying that information (it
    doesn't -- `exc` is just whatever the failed node's own code raised).

    Kept separate from main() so it's testable against a real (temp-file) checkpointer and a
    deliberately-failing stub node, without needing a real several-minute LLM run to prove the
    diagnosis is accurate. See orchestrator/tests/test_failure_handling.py.
    """
    try:
        state = compiled.get_state(graph_config).values
    except Exception:
        state = {}
    sections_done = sorted((state.get("sections") or {}).keys())
    sections_missing = [s for s in ALL_SECTION_IDS if s not in sections_done]
    return {
        "sections_completed": sections_done,
        "sections_missing": sections_missing,
        "exception_type": type(exc).__name__,
        "exception_message": str(exc),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full Core Credit Impact Report pipeline end to end.")
    parser.add_argument("raw_csv_path", help="Path to the raw quarterly survey export")
    parser.add_argument("--run-id", default=None, help="Unique tag for this run (e.g. 2026Q3) -- also the checkpoint thread_id")
    args = parser.parse_args()

    raw_path = Path(args.raw_csv_path).resolve()
    if not raw_path.exists():
        print(f"ERROR: file not found: {raw_path}", file=sys.stderr)
        sys.exit(1)

    run_id = args.run_id or time.strftime("run-%Y%m%dT%H%M%S")
    benchmarks_path = str(PROJECT_ROOT / "External Benchmarks.xlsx")

    with sqlite_checkpointer(CHECKPOINT_DB) as checkpointer:
        compiled = compile_graph(checkpointer=checkpointer)
        graph_config = {
            "configurable": {"thread_id": run_id},
            "run_name": f"core_credit_report[{run_id}]",
            "tags": ["orchestrator", "core-credit-report"],
            "recursion_limit": 100,
        }

        existing = compiled.get_state(graph_config)
        started = time.monotonic()
        try:
            if existing.values:
                print(f"Found an existing checkpoint for run_id={run_id!r} (next steps: {existing.next}) -- resuming.")
                result = compiled.invoke(None, config=graph_config)
            else:
                print(f"Starting fresh run: run_id={run_id!r}, raw_csv={raw_path.name}")
                inputs = {"raw_csv_path": str(raw_path), "run_id": run_id, "benchmarks_path": benchmarks_path}
                result = compiled.invoke(inputs, config=graph_config)
        except Exception as exc:  # noqa: BLE001 -- CC-038: report which node failed, don't crash bare
            elapsed = time.monotonic() - started
            diagnosis = diagnose_failure(compiled, graph_config, exc)
            OUTPUT_DIR.mkdir(exist_ok=True)
            status_path = OUTPUT_DIR / f"run_status_{run_id}.json"
            status_path.write_text(json.dumps(diagnosis, indent=2), encoding="utf-8")
            print(f"\nPIPELINE CRASHED after {elapsed / 60:.1f} min: {diagnosis['exception_type']}: {diagnosis['exception_message']}")
            print(f"Sections completed before the crash: {diagnosis['sections_completed'] or '(none)'}")
            print(f"Sections not yet built: {diagnosis['sections_missing']}")
            print(f"Wrote {status_path}")
            print(
                f"This run is checkpointed under run_id={run_id!r}. Re-run the identical command "
                f"(same --run-id) to resume: completed sections are skipped, not recomputed -- "
                f"only the failed node and whatever depends on it runs again."
            )
            sys.exit(1)

        elapsed = time.monotonic() - started
        print(f"\nOrchestrator run finished in {elapsed / 60:.1f} min.")

        if result.get("failure_reason"):
            print(f"\nPIPELINE FAILED:\n{result['failure_reason']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
