"""dashboard/api/routes/gedsi_reconcile_routes.py

GEDSI (Gender Study) equivalent of reconcile_routes.py -- same
validate/apply shape, pointed at gedsi_reconciliation.py instead of
reconciliation.py. Kept on a separate prefix (/api/gedsi-reconcile) rather
than branching inside reconcile_routes.py so the two pipelines' reconcile
logic never share a request path, even though the upload_id namespace
(dashboard/api/uploads/) is shared.
"""
import asyncio

from fastapi import APIRouter, HTTPException

from dashboard.api import gedsi_reconciliation
from dashboard.api.models import (
    ApplyDecisionsRequest,
    GedsiApplyDecisionsResponse,
    GedsiValidateDatasetResponse,
    ReconcileValidateRequest,
)

router = APIRouter(prefix="/api/gedsi-reconcile/{upload_id}", tags=["gedsi-reconcile"])


@router.post("/validate", response_model=GedsiValidateDatasetResponse)
async def validate_dataset_route(upload_id: str, req: ReconcileValidateRequest) -> GedsiValidateDatasetResponse:
    if not gedsi_reconciliation.upload_csv_path(upload_id).exists():
        raise HTTPException(404, f"Upload '{upload_id}' not found -- upload the CSV first.")
    try:
        result = await asyncio.to_thread(gedsi_reconciliation.validate_dataset, upload_id, req.llm)
    except Exception as exc:
        # Most commonly an invalid/rejected API key surfacing from call_llm()
        # (the deterministic diff itself never raises) -- give the frontend
        # something actionable instead of an opaque 500.
        raise HTTPException(502, f"Dataset validation failed: {exc}") from exc
    return GedsiValidateDatasetResponse(upload_id=upload_id, **result)


@router.post("/apply", response_model=GedsiApplyDecisionsResponse)
async def apply_decisions_route(upload_id: str, req: ApplyDecisionsRequest) -> GedsiApplyDecisionsResponse:
    decisions = {d.id: d.approved for d in req.decisions}
    try:
        result = await asyncio.to_thread(gedsi_reconciliation.apply_decisions, upload_id, decisions)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return GedsiApplyDecisionsResponse(upload_id=upload_id, **result)
