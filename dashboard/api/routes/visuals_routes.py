"""dashboard/api/routes/visuals_routes.py"""
from fastapi import APIRouter, Form, HTTPException, UploadFile

from dashboard.api.models import PowerBiFetchResult, VisualSlotInfo
from dashboard.api.powerbi_client import PowerBiClient, PowerBiConfig
from dashboard.api.visuals_source import VISUAL_SLOTS, list_slots, write_visual_slot

router = APIRouter(prefix="/api/runs/{run_id}/visuals", tags=["visuals"])


@router.get("", response_model=list[VisualSlotInfo])
async def get_visual_slots(run_id: str) -> list[VisualSlotInfo]:
    return [VisualSlotInfo(**s) for s in list_slots(run_id)]


@router.post("", response_model=VisualSlotInfo)
async def upload_visual(run_id: str, slot: str = Form(...), file: UploadFile = None) -> VisualSlotInfo:
    if file is None:
        raise HTTPException(400, "No file provided.")
    if not file.content_type or "png" not in file.content_type:
        raise HTTPException(400, "Expected a PNG image.")
    try:
        write_visual_slot(run_id, slot, await file.read(), source="manual")
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    updated = next(s for s in list_slots(run_id) if s["slot"] == slot)
    return VisualSlotInfo(**updated)


@router.post("/fetch-powerbi", response_model=list[PowerBiFetchResult])
async def fetch_powerbi_visuals(run_id: str, config: PowerBiConfig) -> list[PowerBiFetchResult]:
    client = PowerBiClient(config)
    slot_map = {s["slot"]: s["filename"] for s in VISUAL_SLOTS}
    try:
        client.export_pages_as_images(slot_map)
        return [PowerBiFetchResult(slot=s, ok=True) for s in slot_map]
    except NotImplementedError as exc:
        return [PowerBiFetchResult(slot=s, ok=False, error=str(exc)) for s in slot_map]
