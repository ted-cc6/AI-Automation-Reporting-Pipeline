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
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
PROJECT_ROOT = AGENT_ROOT.parent  # core_peoject

sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from graph.checkpointing import sqlite_checkpointer  # noqa: E402

from orchestrator.graph import compile_graph  # noqa: E402

CHECKPOINT_DB = str(Path(__file__).resolve().parent / "checkpoints.db")


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
        if existing.values:
            print(f"Found an existing checkpoint for run_id={run_id!r} (next steps: {existing.next}) -- resuming.")
            result = compiled.invoke(None, config=graph_config)
        else:
            print(f"Starting fresh run: run_id={run_id!r}, raw_csv={raw_path.name}")
            inputs = {"raw_csv_path": str(raw_path), "run_id": run_id, "benchmarks_path": benchmarks_path}
            result = compiled.invoke(inputs, config=graph_config)

        elapsed = time.monotonic() - started
        print(f"\nOrchestrator run finished in {elapsed / 60:.1f} min.")

        if result.get("failure_reason"):
            print(f"\nPIPELINE FAILED:\n{result['failure_reason']}")
            sys.exit(1)


if __name__ == "__main__":
    main()
