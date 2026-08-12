"""Subprocess entry point for the dashboard (see dashboard/api/core_credit_runner.py).

Not the same thing as run_orchestrator.py: that one is the interactive CLI (single blocking
.invoke(), human-readable prints, resume-from-checkpoint support). This one drives the same
compiled graph via .stream(stream_mode="updates") instead, and prints exactly one machine-
readable JSON line per real node completion to stdout -- nothing else about the run's shape
changes. The dashboard runs this as a subprocess rather than importing orchestrator.graph
in-process because this pipeline's internal modules use deliberately generic top-level names
(schemas, graph, state, driver, writer, synthesis, ...) that would otherwise permanently shadow
sys.modules entries of the same name for the life of the dashboard's own FastAPI process -- see
dashboard/api/core_credit_runner.py's module docstring for the full rationale.

BYOK: this script does not accept an API key argument. It expects ANTHROPIC_API_KEY to already
be set in its own process environment (the parent process, dashboard/api/core_credit_runner.py,
sets it per-run before spawning this subprocess) -- load_dotenv() below is a no-op fallback for
local/manual runs of this script outside the dashboard, and never overrides an already-set env
var (python-dotenv's default), so it can never clobber the BYOK key.

Every stdout line is a single JSON object, one of:
  {"event": "node", "node": <node_name>}          -- a node produced real (non-empty) output
  {"event": "done", "docx_path": ..., "qa_notes_path": ..., "visuals_missing": [...],
   "completeness_issues": [...]}
  {"event": "failed", "reason": <str>}             -- the data-prep gate rejected the run
  {"event": "error", "reason": <str>}              -- unexpected exception

Anything else written to stdout by a dependency (LangChain/LangGraph warnings, etc.) is left as
plain non-JSON text on the same stream; the parent forwards unparseable lines through as raw log
lines rather than discarding them.

Usage:
    python run_for_dashboard.py <raw_csv_path> --run-id <id> [--benchmarks-path P] [--checkpoint-db P]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
PROJECT_ROOT = AGENT_ROOT.parent  # core_credit/

sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from graph.checkpointing import sqlite_checkpointer  # noqa: E402

from orchestrator.graph import compile_graph  # noqa: E402

QA_NOTES_OUTPUT_DIR = AGENT_ROOT / "orchestrator" / "output"


def _emit(payload: dict) -> None:
    print(json.dumps(payload), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Core Credit orchestrator, emitting JSON progress lines.")
    parser.add_argument("raw_csv_path")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--benchmarks-path", default=str(PROJECT_ROOT / "External Benchmarks.xlsx"))
    parser.add_argument("--checkpoint-db", default=str(Path(__file__).resolve().parent / "checkpoints.db"))
    args = parser.parse_args()

    raw_path = Path(args.raw_csv_path).resolve()
    if not raw_path.exists():
        _emit({"event": "error", "reason": f"file not found: {raw_path}"})
        sys.exit(1)

    graph_config = {
        "configurable": {"thread_id": args.run_id},
        "run_name": f"core_credit_report[{args.run_id}]",
        "tags": ["orchestrator", "core-credit-report", "dashboard"],
        "recursion_limit": 100,
    }

    try:
        with sqlite_checkpointer(args.checkpoint_db) as checkpointer:
            compiled = compile_graph(checkpointer=checkpointer)
            inputs = {
                "raw_csv_path": str(raw_path),
                "run_id": args.run_id,
                "benchmarks_path": args.benchmarks_path,
            }

            for chunk in compiled.stream(inputs, config=graph_config, stream_mode="updates"):
                for node_name, node_output in chunk.items():
                    if node_output:  # skip the defensive no-op {} firings each node documents
                        _emit({"event": "node", "node": node_name})

            final_state = compiled.get_state(graph_config).values
    except Exception as exc:  # noqa: BLE001 -- last-resort: still emit one parseable terminal line
        _emit({"event": "error", "reason": str(exc)})
        sys.exit(1)

    if final_state.get("failure_reason"):
        _emit({"event": "failed", "reason": final_state["failure_reason"]})
        sys.exit(1)

    if not final_state.get("docx_path"):
        _emit({
            "event": "error",
            "reason": "Pipeline finished without producing a docx_path (unexpected -- see node log above).",
        })
        sys.exit(1)

    _emit({
        "event": "done",
        "docx_path": final_state["docx_path"],
        "qa_notes_path": str(QA_NOTES_OUTPUT_DIR / f"qa_notes_{args.run_id}.md"),
        "visuals_missing": final_state.get("visuals_missing", []),
        "completeness_issues": final_state.get("completeness_issues", []),
    })


if __name__ == "__main__":
    main()
