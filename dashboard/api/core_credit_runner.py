"""dashboard/api/core_credit_runner.py

Runs the core_credit orchestrator (core_credit/agent/orchestrator/graph.py) as a subprocess,
not an in-process import. Two reasons:

1. Namespace safety: core_credit's own scripts add agent/ and agent/analysis/ to sys.path at
   import time and rely on bare, generic top-level module names inside that tree -- schemas,
   graph, state, driver, writer, synthesis, section_configs, and more (see e.g.
   core_credit/agent/orchestrator/section_nodes.py's `from graph.graph import compile_graph`).
   Importing that package directly into this FastAPI process would permanently shadow
   sys.modules entries of the same name for the life of the server -- a real fragility (`state`
   and `schemas` in particular are dangerously generic), not a hypothetical one.
2. Isolation: this is the heaviest run this dashboard drives -- 9 concurrent LLM-calling
   sections plus a writer chain, a qualitative-tagging pass, and a QA read, commonly 40-90+
   minutes (see agent/orchestrator/render_nodes.py's own docstring). A subprocess crash or hang
   there can't take the API server down with it.

BYOK: the user's Anthropic key is handed to the subprocess purely via its environment
(ANTHROPIC_API_KEY). core_credit's own scripts already read that var (each calls
load_dotenv(PROJECT_ROOT/".env") first, which is a no-op when that file doesn't exist -- it
won't in this container). No source change was needed inside core_credit for this to work; the
key is never written to disk and never touches this process's own os.environ (only the child's).

Progress: the subprocess entry point (agent/orchestrator/run_for_dashboard.py -- NOT the
interactive CLI in run_orchestrator.py) streams the graph via .stream(stream_mode="updates")
and prints one JSON line per real node completion to stdout. This module tails that stream and
turns each line into a RunState.log() call plus a RunState.core_credit_nodes[...] update, the
same live-progress contract pipeline_runner.py gives cupboard_week/gender_study runs.
"""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
from pathlib import Path

from dashboard.api.config import PROJECT_ROOT, RUNS_DIR
from dashboard.api.jobs import RUNS
from dashboard.api.models import LlmConfig

CORE_CREDIT_ROOT = PROJECT_ROOT / "core_credit"
RUNNER_SCRIPT = CORE_CREDIT_ROOT / "agent" / "orchestrator" / "run_for_dashboard.py"
DEFAULT_BENCHMARKS_PATH = CORE_CREDIT_ROOT / "External Benchmarks.xlsx"


async def _drain_stderr(stream: asyncio.StreamReader, buffer: list) -> None:
    async for raw_line in stream:
        buffer.append(raw_line.decode("utf-8", errors="replace").rstrip())


async def execute(run_id: str, csv_path: Path, llm: LlmConfig) -> None:
    """Entry point run as a plain asyncio.Task directly from the /api/runs route -- native
    asyncio subprocess I/O, so (unlike pipeline_runner.execute/gedsi_runner.execute) this does
    NOT go through asyncio.to_thread.
    """
    state = RUNS[run_id]
    state.status = "running"
    state.current_stage = 1

    try:
        state.log("Starting Core Credit Impact Report pipeline (this can take 40-90+ minutes)...")

        run_dir = RUNS_DIR / run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        checkpoint_db = run_dir / "core_credit_checkpoints.db"

        env = dict(os.environ)
        env["ANTHROPIC_API_KEY"] = llm.api_key

        proc = await asyncio.create_subprocess_exec(
            sys.executable, str(RUNNER_SCRIPT),
            str(csv_path),
            "--run-id", run_id,
            "--benchmarks-path", str(DEFAULT_BENCHMARKS_PATH),
            "--checkpoint-db", str(checkpoint_db),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert proc.stdout is not None and proc.stderr is not None

        stderr_lines: list = []
        stderr_task = asyncio.create_task(_drain_stderr(proc.stderr, stderr_lines))

        result: dict = {}
        async for raw_line in proc.stdout:
            line = raw_line.decode("utf-8", errors="replace").rstrip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                state.log(f"  [core_credit] {line}")
                continue

            event = payload.get("event")
            if event == "node":
                node_name = payload["node"]
                state.core_credit_nodes[node_name] = "done"
                state.log(f"  [core_credit] {node_name} complete")
            elif event in ("done", "failed", "error"):
                result = payload

        await proc.wait()
        await stderr_task

        if result.get("event") == "done":
            src_docx = Path(result["docx_path"])
            dest_docx = run_dir / src_docx.name
            shutil.copy2(src_docx, dest_docx)
            state.docx_path = dest_docx

            missing = result.get("visuals_missing", [])
            issues = result.get("completeness_issues", [])
            state.core_credit_result = {"visuals_missing": missing, "completeness_issues": issues}
            state.status = "partial_failure" if (missing or issues) else "succeeded"
            state.log(
                f"Pipeline finished with status: {state.status} "
                f"({len(missing)} dashboard visual(s) missing, {len(issues)} completeness issue(s))."
            )
            return

        reason = result.get("reason") or (
            f"Subprocess exited (code {proc.returncode}) without a recognizable result."
        )
        if stderr_lines:
            reason = f"{reason}\n\n--- subprocess stderr (tail) ---\n" + "\n".join(stderr_lines[-40:])
        state.status = "failed"
        state.error = reason
        state.log(f"Pipeline failed: {reason}")

    except Exception as exc:  # noqa: BLE001 -- last-resort: never leave a run stuck at "running"
        state.status = "failed"
        state.error = f"core_credit_runner crashed: {exc}"
        state.log(f"Pipeline failed: {state.error}")
