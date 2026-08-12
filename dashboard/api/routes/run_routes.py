"""dashboard/api/routes/run_routes.py"""
import asyncio
import json
import uuid

import yaml
from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from dashboard.api import gedsi_runner, pipeline_runner
from dashboard.api.config import RUNS_DIR, UPLOADS_DIR
from dashboard.api.jobs import RunConflictError, get_run, list_runs, start_new_run
from dashboard.api.models import PriorRunCandidate, RunSummary, StartRunRequest, StartRunResponse
from dashboard.api.schema_detection import detect_dataset_schema

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Diagnostic report files a run produces alongside the final .docx. Fixed
# allow-list (not an arbitrary filename param) so this endpoint can never be
# used to read anything else on disk, regardless of what run_id resolves to.
_ALLOWED_REPORT_FILES = frozenset({
    "screening_report.md",
    "data_quality_report.md",
    "profile_report.md",
    "run_summary.txt",
})

# Keep references to fire-and-forget run tasks so they aren't garbage-collected
# mid-flight; there's no cancellation support in this first version, so tasks
# are never removed before completion (they're small in number -- one at a time).
_background_tasks: set[asyncio.Task] = set()


def _default_run_id(req: StartRunRequest) -> str:
    if req.run_id:
        return req.run_id
    if req.report_type == "gender_study":
        return f"gender_study_{uuid.uuid4().hex[:10]}"
    return f"{req.country}_{req.year}_Q{req.quarter}"


@router.post("", response_model=StartRunResponse)
async def start_run(req: StartRunRequest) -> StartRunResponse:
    upload_path = UPLOADS_DIR / f"{req.upload_id}.csv"
    if not upload_path.exists():
        raise HTTPException(404, f"Upload '{req.upload_id}' not found -- upload the CSV first.")

    if req.report_type == "cupboard_week" and (req.country is None or req.year is None or req.quarter is None):
        raise HTTPException(400, "country, year, and quarter are required for cupboard_week runs.")
    if req.report_type == "gender_study" and req.dry_run:
        raise HTTPException(400, "dry_run is not supported for gender_study runs.")

    # gender_study runs GEDSI's own pipeline, which has no dataset_schema
    # concept at all (see gedsi_reconciliation.py) -- this resolution only
    # matters for cupboard_week, and only touches the raw upload's header
    # row (cheap), never re-detects against an already-reconciled mapping.
    dataset_schema = req.dataset_schema
    if req.report_type == "cupboard_week" and dataset_schema is None:
        dataset_schema = detect_dataset_schema(upload_path)
        if dataset_schema == "unknown":
            raise HTTPException(
                400,
                "Could not determine this upload's source-survey schema "
                "(neither Africa/Vietnam nor LARCO matched well). Pass "
                "dataset_schema explicitly once you've confirmed which "
                "schema this file belongs to.",
            )

    run_id = _default_run_id(req)
    try:
        start_new_run(run_id, req.report_type, req.country)
    except RunConflictError as exc:
        raise HTTPException(409, str(exc)) from exc

    if req.report_type == "gender_study":
        task = asyncio.create_task(asyncio.to_thread(gedsi_runner.execute, run_id, upload_path, req.llm))
    else:
        task = asyncio.create_task(
            asyncio.to_thread(
                pipeline_runner.execute, run_id, upload_path, req.country, req.llm, req.dry_run,
                dataset_schema=dataset_schema, prior_run_id=req.prior_run_id,
            )
        )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return StartRunResponse(run_id=run_id, status="queued")


@router.get("", response_model=list[RunSummary])
async def get_all_runs() -> list[RunSummary]:
    return [
        RunSummary(run_id=r.run_id, pipeline=r.pipeline, status=r.status, created_at=r.created_at)
        for r in list_runs()
    ]


@router.get("/larco-prior-candidates", response_model=list[PriorRunCandidate])
async def list_larco_prior_candidates() -> list[PriorRunCandidate]:
    """Completed LARCO runs usable as Part 10's --prior-run-id. Registered
    before GET /{run_id} below -- Starlette matches routes in registration
    order, and {run_id} would otherwise swallow this literal path first.

    Scans runs/ on disk rather than the in-memory RUNS job registry (see
    dashboard/api/jobs.py) deliberately: RUNS is cleared on every dashboard
    restart, but a prior wave's output is exactly the kind of thing that
    needs to stay pickable weeks or months later, long after any restart.
    """
    candidates: list[PriorRunCandidate] = []
    if not RUNS_DIR.exists():
        return candidates

    for run_dir in RUNS_DIR.iterdir():
        if not run_dir.is_dir():
            continue
        metadata_path = run_dir / "run_metadata.yaml"
        results_path = run_dir / "analysis_results.json"
        if not metadata_path.exists() or not results_path.exists():
            continue
        try:
            metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            continue
        if metadata.get("dataset_schema") != "larco":
            continue
        candidates.append(PriorRunCandidate(
            run_id=run_dir.name,
            country=metadata.get("country"),
            created_at=metadata.get("created_at"),
        ))

    candidates.sort(key=lambda c: c.created_at or "", reverse=True)
    return candidates


@router.get("/{run_id}")
async def get_run_state(run_id: str) -> dict:
    state = get_run(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found.")
    return state.snapshot()


@router.get("/{run_id}/logs")
async def get_run_logs(run_id: str) -> dict:
    state = get_run(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found.")
    return {"logs": [line for _, line in state.logs]}


@router.get("/{run_id}/events")
async def stream_run_events(run_id: str, last_event_id: str | None = Header(None, alias="Last-Event-ID")):
    state = get_run(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found.")

    since = int(last_event_id) if last_event_id else 0

    async def event_generator():
        # Replay anything the client hasn't seen yet (e.g. after an auto-reconnect), then live-stream new entries.
        for seq, line in state.logs:
            if seq > since:
                yield f"id: {seq}\ndata: {json.dumps({'seq': seq, 'line': line, 'snapshot': state.snapshot()})}\n\n"

        queue = state.subscribe()
        try:
            while True:
                seq, line = await queue.get()
                yield f"id: {seq}\ndata: {json.dumps({'seq': seq, 'line': line, 'snapshot': state.snapshot()})}\n\n"
                if state.status in ("succeeded", "failed", "partial_failure") and queue.empty():
                    break
        finally:
            state.unsubscribe(queue)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.get("/{run_id}/download")
async def download_report(run_id: str):
    state = get_run(run_id)
    if state is None or state.docx_path is None or not state.docx_path.exists():
        raise HTTPException(404, "Report not ready yet for this run.")
    return FileResponse(
        state.docx_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=state.docx_path.name,
    )


@router.get("/{run_id}/download-xlsx")
async def download_workbook(run_id: str):
    """GEDSI runs also produce a supporting .xlsx workbook alongside the
    .docx report; Cupboard Week runs never populate xlsx_path, so this
    always 404s for them."""
    state = get_run(run_id)
    if state is None or state.xlsx_path is None or not state.xlsx_path.exists():
        raise HTTPException(404, "Workbook not ready yet for this run.")
    return FileResponse(
        state.xlsx_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=state.xlsx_path.name,
    )


@router.get("/{run_id}/report/{filename}")
async def download_report_file(run_id: str, filename: str):
    """Serve one of the intermediate diagnostic reports a run produces
    (screening_report.md, data_quality_report.md, profile_report.md,
    run_summary.txt) -- for auditing what a run actually did, since only the
    final .docx has a download route otherwise.
    """
    if filename not in _ALLOWED_REPORT_FILES:
        raise HTTPException(
            400, f"Unknown report file {filename!r}. Allowed: {sorted(_ALLOWED_REPORT_FILES)}"
        )
    # get_run() only recognises run_ids created through the normal POST /api/runs
    # flow (see jobs.py's RUNS dict) -- this rejects any run_id that isn't a real,
    # tracked run before it ever reaches a filesystem path, regardless of content.
    state = get_run(run_id)
    if state is None:
        raise HTTPException(404, f"Run '{run_id}' not found.")

    file_path = RUNS_DIR / run_id / filename
    if not file_path.exists():
        raise HTTPException(404, f"{filename} not found for run '{run_id}'.")
    return FileResponse(file_path, media_type="text/plain; charset=utf-8", filename=filename)
