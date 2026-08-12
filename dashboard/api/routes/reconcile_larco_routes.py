"""dashboard/api/routes/reconcile_larco_routes.py"""
import asyncio

from fastapi import APIRouter, HTTPException

from dashboard.api import reconciliation_larco
from dashboard.api.models import (
    ApplyDecisionsRequest,
    ApplyDecisionsResponse,
    ReconcileValidateRequest,
    ValidateDatasetResponse,
)

router = APIRouter(prefix="/api/reconcile-larco/{upload_id}", tags=["reconcile-larco"])


@router.post("/validate", response_model=ValidateDatasetResponse)
async def validate_dataset_route(upload_id: str, req: ReconcileValidateRequest) -> ValidateDatasetResponse:
    if not reconciliation_larco.upload_csv_path(upload_id).exists():
        raise HTTPException(404, f"Upload '{upload_id}' not found -- upload the CSV first.")
    try:
        result = await asyncio.to_thread(reconciliation_larco.validate_dataset, upload_id, req.llm)
    except Exception as exc:
        # Most commonly an invalid/rejected API key surfacing from call_llm()
        # (the deterministic diff itself never raises) -- give the frontend
        # something actionable instead of an opaque 500.
        raise HTTPException(502, f"Dataset validation failed: {exc}") from exc
    return ValidateDatasetResponse(upload_id=upload_id, **result)


@router.post("/apply", response_model=ApplyDecisionsResponse)
async def apply_decisions_route(upload_id: str, req: ApplyDecisionsRequest) -> ApplyDecisionsResponse:
    decisions = {d.id: d.approved for d in req.decisions}
    try:
        result = await asyncio.to_thread(reconciliation_larco.apply_decisions, upload_id, decisions)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return ApplyDecisionsResponse(upload_id=upload_id, **result)
