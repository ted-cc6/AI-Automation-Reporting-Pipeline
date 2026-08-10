"""dashboard/api/gedsi_runner.py

Runs the GEDSI (Gender Study) pipeline's 6 stages in-process, mirroring
pipeline_runner.py's shape for the Cupboard Week pipeline: same
RunState.log()/stage-snapshot mechanism, same "call execute() via
asyncio.to_thread()" entry point from run_routes.py.

Unlike Cupboard Week's stages, GEDSI's own modules (ingest, quant_engine,
qual_engine, triangulate, draft_writer, assemble) have no built-in
per-section partial-failure handling -- draft_writer.run_draft_writer(), for
instance, raises straight through the moment one section's LLM call fails
after retries, rather than isolating that one section the way Cupboard
Week's write_all_parts() does. This runner is honest about that rather than
inventing resilience the underlying code doesn't have: each stage is
all-or-nothing, matching what would actually happen if you ran it stage by
stage from RUNBOOK.md. Stage 4 (qualitative coding) is the one exception
where per-question progress is tracked in real time as the loop it already
naturally runs -- see _run_stage4.

Progress visibility: gedsi_pipeline's stage modules already print useful
progress (row counts, "Wrote ...", "Drafting: ..."), just via plain print()
rather than a callback parameter. _tee_stdout captures that output for the
duration of each stage and forwards every line to state.log(), so the SSE
log stream gets real granularity without adding progress_cb plumbing to
gedsi_pipeline itself. Caveat: sys.stdout is process-global, not
thread-local, so this relies on the one-run-at-a-time lock in jobs.py to
avoid interleaving with another run's output -- acceptable for this
dashboard's single-operator scope, called out here rather than left
implicit.

Codebook policy: every run seeds its own work/codebooks/ from this
project's own approved codebooks and never regenerates them from the
uploaded dataset -- a stable analytical framework maintained across survey
waves, not a shortcut. See _seed_codebooks.
"""
from __future__ import annotations

import contextlib
import logging
import shutil
import sys
from pathlib import Path

from dashboard.api.config import GENDSI_ROOT, RUNS_DIR, UPLOADS_DIR
from dashboard.api.jobs import RUNS
from dashboard.api.models import LlmConfig

from gedsi_pipeline import assemble as gedsi_assemble
from gedsi_pipeline import config as gedsi_config
from gedsi_pipeline import draft_writer as gedsi_draft_writer
from gedsi_pipeline import ingest as gedsi_ingest
from gedsi_pipeline import mapping as gedsi_mapping
from gedsi_pipeline import qual_engine as gedsi_qual_engine
from gedsi_pipeline import quant_engine as gedsi_quant_engine
from gedsi_pipeline import triangulate as gedsi_triangulate

log = logging.getLogger(__name__)


class _LogTee:
    """File-like object that forwards each printed line to state.log()
    while still writing through to the real stream, so gedsi_pipeline's
    existing print() progress becomes live SSE log lines with no changes
    to that code."""

    def __init__(self, state, real_stream):
        self._state = state
        self._real = real_stream
        self._buffer = ""

    def write(self, s: str) -> int:
        self._real.write(s)
        self._buffer += s
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._state.log(f"    {line}")
        return len(s)

    def flush(self) -> None:
        self._real.flush()


@contextlib.contextmanager
def _tee_stdout(state):
    tee = _LogTee(state, sys.stdout)
    with contextlib.redirect_stdout(tee):
        yield
    if tee._buffer.strip():
        state.log(f"    {tee._buffer}")


def _seed_codebooks(state, work_dir: Path) -> None:
    """Copies this repo's own approved codebooks into the run's isolated
    work dir. Per product decision, codebooks are a stable analytical
    framework maintained across survey waves -- never re-induced from
    whatever the user just uploaded. If a question is missing an approved
    codebook in the repo, that's a setup problem worth failing loudly on,
    not something to silently paper over by inducing an unreviewed one."""
    canonical_dir = gedsi_config.WORK_DIR / "codebooks"
    dest_dir = work_dir / "codebooks"
    dest_dir.mkdir(parents=True, exist_ok=True)

    questions = list(gedsi_config.DEFAULT_ROLE_MAP.qual_primary)
    missing = []
    for question in questions:
        src = canonical_dir / f"{question}_approved.json"
        if not src.exists():
            missing.append(question)
            continue
        shutil.copy2(src, dest_dir / f"{question}_approved.json")

    if missing:
        raise RuntimeError(
            "No approved codebook checked into the repo for: " + ", ".join(missing) + ". "
            "Gender Study runs always reuse this project's reviewed codebooks and never "
            "induce new ones from an uploaded dataset -- add an approved codebook file "
            "before running."
        )
    state.log(
        f"  [stage 3] seeded {len(questions)} approved codebook(s) from the repo "
        "(reused as-is, not regenerated from this upload)."
    )


def _resolve_role_map(state, run_dir: Path, upload_id: str):
    """Uses the upload's reconciled mapping if one exists (see
    dashboard/api/gedsi_reconciliation.py), falling back to the canonical
    mapping otherwise -- same pattern as pipeline_runner.py's
    reconciled-vs-canonical column_mapping.csv resolution. Copies whichever
    was actually used into run_dir as this run's own audit artifact."""
    reconciled_mapping_path = UPLOADS_DIR / f"{upload_id}_gedsi_column_mapping.csv"
    if reconciled_mapping_path.exists():
        state.log(f"  [stage 1] using reconciled column mapping for upload {upload_id}")
        mapping_path = reconciled_mapping_path
    else:
        mapping_path = gedsi_config.COLUMN_MAPPING_PATH

    shutil.copy2(mapping_path, run_dir / "column_mapping_used.csv")
    return gedsi_mapping.load_role_map(mapping_path)


def _run_stage1(state, csv_path: Path, run_dir: Path, work_dir: Path, upload_id: str) -> None:
    state.current_stage = 1
    state.stage1 = {"status": "running"}
    state.log("Stage 1/6 -- Ingest & clean...")

    role_map = _resolve_role_map(state, run_dir, upload_id)
    with _tee_stdout(state):
        gedsi_ingest.main(csv_path=csv_path, role_map=role_map, work_dir=work_dir)

    state.stage1 = {"status": "succeeded"}
    state.log("Stage 1/6 complete.")


def _run_stage2(state, work_dir: Path) -> None:
    state.current_stage = 2
    state.stage2 = {"status": "running"}
    state.log("Stage 2/6 -- Quantitative engine...")

    with _tee_stdout(state):
        gedsi_quant_engine.main(work_dir=work_dir)

    state.stage2 = {"status": "succeeded"}
    state.log("Stage 2/6 complete.")


def _run_stage3(state, work_dir: Path) -> None:
    state.current_stage = 3
    state.stage3 = {"status": "running"}
    state.log("Stage 3/6 -- Codebook check (reusing this project's approved codebooks)...")

    _seed_codebooks(state, work_dir)

    state.stage3 = {"status": "succeeded"}
    state.log("Stage 3/6 complete.")


def _run_stage4(state, work_dir: Path, api_key: str) -> None:
    state.current_stage = 4
    state.stage4 = {"status": "running", "parts": {}}
    state.log("Stage 4/6 -- Qualitative coding...")

    for question in gedsi_config.DEFAULT_ROLE_MAP.qual_primary:
        state.stage4["parts"][question] = {"status": "running"}
        state.log(f"  [stage 4] coding {question}...")
        with _tee_stdout(state):
            gedsi_qual_engine.run_coding(question, api_key, work_dir=work_dir)
        state.stage4["parts"][question] = {"status": "succeeded"}

    state.stage4["status"] = "succeeded"
    state.log("Stage 4/6 complete.")


def _run_stage5(state, work_dir: Path) -> None:
    state.current_stage = 5
    state.stage5 = {"status": "running"}
    state.log("Stage 5/6 -- Triangulation...")

    with _tee_stdout(state):
        gedsi_triangulate.main(work_dir=work_dir)

    state.stage5 = {"status": "succeeded"}
    state.log("Stage 5/6 complete.")


def _run_stage6(state, csv_path: Path, work_dir: Path, output_dir: Path, api_key: str) -> None:
    state.current_stage = 6
    state.stage6 = {"status": "running"}
    state.log("Stage 6/6 -- Draft writing + assembly...")

    with _tee_stdout(state):
        gedsi_draft_writer.run_draft_writer(api_key, work_dir=work_dir)

    state.log("  [stage 6] drafts complete, assembling report...")
    with _tee_stdout(state):
        outputs = gedsi_assemble.main(csv_path=csv_path, work_dir=work_dir, output_dir=output_dir)

    state.docx_path = outputs["docx_path"]
    state.xlsx_path = outputs["xlsx_path"]
    state.stage6["status"] = "succeeded"
    state.log(f"Stage 6/6 complete -- report at {state.docx_path.name}")


def execute(run_id: str, csv_path: Path, llm: LlmConfig, dry_run: bool = False) -> None:
    """Entry point run via asyncio.to_thread() from the /api/runs route."""
    state = RUNS[run_id]
    run_dir = RUNS_DIR / run_id
    work_dir = run_dir / "work"
    output_dir = run_dir / "outputs"
    run_dir.mkdir(parents=True, exist_ok=True)
    upload_id = csv_path.stem
    state.status = "running"

    if dry_run:
        # GEDSI has no dry-run concept anywhere in its own pipeline (unlike
        # Cupboard Week's stage3/4, which can skip the LLM calls and dump
        # intermediate payloads); the route layer should reject dry_run
        # for gender_study before ever reaching here, but log plainly if
        # it somehow got through rather than silently ignoring the flag.
        state.log("dry_run was requested but is not supported for Gender Study runs -- running normally.")

    try:
        _run_stage1(state, csv_path, run_dir, work_dir, upload_id)
        _run_stage2(state, work_dir)
        _run_stage3(state, work_dir)
        _run_stage4(state, work_dir, llm.api_key)
        _run_stage5(state, work_dir)
        _run_stage6(state, csv_path, work_dir, output_dir, llm.api_key)
    except Exception as exc:
        stage_field = f"stage{state.current_stage}"
        current = dict(getattr(state, stage_field, {}) or {})
        current["status"] = "failed"
        current["error"] = str(exc)
        setattr(state, stage_field, current)
        state.status = "failed"
        state.error = f"Stage {state.current_stage} failed: {exc}"
        state.log(f"Pipeline halted: {exc}")
        return

    state.status = "succeeded"
    state.log(f"Pipeline finished with status: {state.status}")
