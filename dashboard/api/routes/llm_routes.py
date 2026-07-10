"""dashboard/api/routes/llm_routes.py"""
import asyncio

from fastapi import APIRouter

from dashboard.api.models import LlmValidateRequest, LlmValidateResponse
from llm_providers import validate_key

router = APIRouter(prefix="/api/llm", tags=["llm"])


@router.post("/validate", response_model=LlmValidateResponse)
async def validate(req: LlmValidateRequest) -> LlmValidateResponse:
    ok, message = await asyncio.to_thread(validate_key, req.provider, req.api_key)
    return LlmValidateResponse(ok=ok, message=message)
