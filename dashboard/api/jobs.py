"""dashboard/api/jobs.py

In-memory run-as-a-job model. No database -- justified by the single-operator,
local-only scope: losing in-flight state on a process restart is acceptable.

One RunState shape serves both pipelines this dashboard drives: Cupboard
Week (4 stages, one .docx) and the GEDSI Gender Study (6 stages, a .docx
plus a supporting .xlsx workbook) -- see pipeline_runner.py and
gedsi_runner.py respectively. Every RunState always carries all 6 stage
slots and both output paths regardless of which pipeline produced it;
Cupboard Week runs just never touch stage5/stage6 or xlsx_path, and its own
frontend only ever reads the 4 keys it knows about, so the unused slots are
harmless rather than a fork of this module per pipeline.

RunState.log() is safe to call from the worker thread pipeline_runner.execute()
actually runs on (via asyncio.to_thread): it appends to a plain list (atomic
enough under the GIL) and, if an event loop was captured at creation time,
hands delivery to subscriber queues back to that loop via
call_soon_threadsafe -- asyncio.Queue.put_nowait is not safe to call directly
from a non-loop thread.
"""
import asyncio
import itertools
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional

RunStatus = Literal["queued", "running", "succeeded", "partial_failure", "failed"]
ReportType = Literal["cupboard_week", "gender_study", "core_credit"]


class RunConflictError(Exception):
    """Raised when a run is requested while another is already active."""


@dataclass
class RunState:
    run_id: str
    pipeline: ReportType = "cupboard_week"
    country: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    status: RunStatus = "queued"
    current_stage: int = 0
    stage1: dict = field(default_factory=lambda: {"status": "pending"})
    stage2: dict = field(default_factory=lambda: {"status": "pending"})
    stage3: dict = field(default_factory=lambda: {"status": "pending"})
    stage4: dict = field(default_factory=lambda: {"status": "pending", "parts": {}})
    stage5: dict = field(default_factory=lambda: {"status": "pending"})
    stage6: dict = field(default_factory=lambda: {"status": "pending"})
    # core_credit only -- its graph has a genuinely parallel middle tier (9 sections at once),
    # which doesn't fit the linear stage1..stage6 shape above. node_name -> "done", populated as
    # core_credit_runner.py tails the subprocess's progress stream; core_credit_result carries
    # its two run-level summaries (visuals_missing, completeness_issues) once the run finishes.
    core_credit_nodes: dict = field(default_factory=dict)
    core_credit_result: dict = field(default_factory=dict)
    logs: list = field(default_factory=list)
    docx_path: Optional[Path] = None
    xlsx_path: Optional[Path] = None
    error: Optional[str] = None

    def __post_init__(self) -> None:
        self._subscribers: list[asyncio.Queue] = []
        self._seq = itertools.count(1)
        try:
            self._loop: Optional[asyncio.AbstractEventLoop] = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None

    def log(self, message: str) -> None:
        entry = (next(self._seq), message)
        self.logs.append(entry)
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._deliver, entry)
        else:
            self._deliver(entry)

    def _deliver(self, entry: tuple) -> None:
        for q in list(self._subscribers):
            q.put_nowait(entry)

    def subscribe(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self._subscribers.append(q)
        return q

    def unsubscribe(self, q: asyncio.Queue) -> None:
        if q in self._subscribers:
            self._subscribers.remove(q)

    def snapshot(self) -> dict:
        return {
            "run_id": self.run_id,
            "pipeline": self.pipeline,
            "country": self.country,
            "created_at": self.created_at,
            "status": self.status,
            "current_stage": self.current_stage,
            "stage1": self.stage1,
            "stage2": self.stage2,
            "stage3": self.stage3,
            "stage4": self.stage4,
            "stage5": self.stage5,
            "stage6": self.stage6,
            "core_credit_nodes": self.core_credit_nodes,
            "core_credit_result": self.core_credit_result,
            "error": self.error,
            "docx_ready": self.docx_path is not None,
            "xlsx_ready": self.xlsx_path is not None,
        }


RUNS: dict[str, RunState] = {}
_active_run_id: Optional[str] = None


def start_new_run(run_id: str, pipeline: ReportType = "cupboard_week", country: Optional[str] = None) -> RunState:
    global _active_run_id
    active = RUNS.get(_active_run_id) if _active_run_id else None
    if active is not None and active.status in ("queued", "running"):
        raise RunConflictError(
            f"Run '{active.run_id}' is already {active.status}. "
            "Only one run can be active at a time."
        )
    state = RunState(run_id=run_id, pipeline=pipeline, country=country)
    RUNS[run_id] = state
    _active_run_id = run_id
    return state


def get_run(run_id: str) -> Optional[RunState]:
    return RUNS.get(run_id)


def list_runs() -> list[RunState]:
    return sorted(RUNS.values(), key=lambda r: r.created_at, reverse=True)
