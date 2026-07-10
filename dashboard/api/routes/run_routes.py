"""dashboard/api/routes/run_routes.py"""
import asyncio
import json

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse, StreamingResponse

from dashboard.api import pipeline_runner
from dashboard.api.config import UPLOADS_DIR
from dashboard.api.jobs import RunConflictError, get_run, list_runs, start_new_run
from dashboard.api.models import RunSummary, StartRunRequest, StartRunResponse

router = APIRouter(prefix="/api/runs", tags=["runs"])

# Keep references to fire-and-forget run tasks so they aren't garbage-collected
# mid-flight; there's no cancellation support in this first version, so tasks
# are never removed before completion (they're small in number -- one at a time).
_background_tasks: set[asyncio.Task] = set()


def _default_run_id(req: StartRunRequest) -> str:
    return req.run_id or f"{req.country}_{req.year}_Q{req.quarter}"


@router.post("", response_model=StartRunResponse)
async def start_run(req: StartRunRequest) -> StartRunResponse:
    upload_path = UPLOADS_DIR / f"{req.upload_id}.csv"
    if not upload_path.exists():
        raise HTTPException(404, f"Upload '{req.upload_id}' not found -- upload the CSV first.")

    run_id = _default_run_id(req)
    try:
        start_new_run(run_id, req.country)
    except RunConflictError as exc:
        raise HTTPException(409, str(exc)) from exc

    task = asyncio.create_task(
        asyncio.to_thread(pipeline_runner.execute, run_id, upload_path, req.country, req.llm, req.dry_run)
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return StartRunResponse(run_id=run_id, status="queued")


@router.get("", response_model=list[RunSummary])
async def get_all_runs() -> list[RunSummary]:
    return [RunSummary(run_id=r.run_id, status=r.status, created_at=r.created_at) for r in list_runs()]


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
