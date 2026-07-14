"""dashboard/api/models.py -- Pydantic request/response schemas for the dashboard API."""
from typing import Literal, Optional

from pydantic import BaseModel


class CsvUploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    row_count_preview: int
    columns_detected: int


class CountryOption(BaseModel):
    value: str
    label: str


class LlmValidateRequest(BaseModel):
    provider: Literal["gemini", "anthropic", "openai"]
    api_key: str


class LlmValidateResponse(BaseModel):
    ok: bool
    message: str


class LlmConfig(BaseModel):
    provider: Literal["gemini", "anthropic", "openai"]
    api_key: str
    model: Optional[str] = None


class PowerBiConfigRequest(BaseModel):
    mode: Literal["manual", "api"] = "manual"
    tenant_id: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    workspace_id: Optional[str] = None
    report_id: Optional[str] = None


class StartRunRequest(BaseModel):
    upload_id: str
    country: str
    year: int
    quarter: int
    run_id: Optional[str] = None
    llm: LlmConfig
    powerbi: PowerBiConfigRequest = PowerBiConfigRequest()
    dry_run: bool = False


class StartRunResponse(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    status: str
    created_at: Optional[str] = None


class VisualSlotInfo(BaseModel):
    slot: str
    filename: str
    part: str
    has_generator: bool
    exists: bool
    source: Optional[dict] = None


class PowerBiFetchResult(BaseModel):
    slot: str
    ok: bool
    error: Optional[str] = None


RecommendationType = Literal["rename", "new_question", "dropped"]
NewQuestionResponseType = Literal["open_text", "single_select", "likert5", "nps_score", "age"]


class LikertValueEntry(BaseModel):
    int: int
    label: str


class RecommendationOut(BaseModel):
    id: str
    type: RecommendationType
    confidence: float
    rationale: str
    old_raw_index: Optional[int] = None
    old_header: Optional[str] = None
    old_question_ref: Optional[str] = None
    old_category: Optional[str] = None
    new_csv_index: Optional[int] = None
    new_header: Optional[str] = None
    suggested_question_ref: Optional[str] = None
    suggested_response_type: Optional[NewQuestionResponseType] = None
    suggested_value_map: Optional[dict[str, LikertValueEntry]] = None
    approved: Optional[bool] = None


class ReconcileValidateRequest(BaseModel):
    llm: LlmConfig


class ValidateDatasetResponse(BaseModel):
    upload_id: str
    clean: bool
    recommendations: list[RecommendationOut] = []
    residual_old_count: int = 0
    residual_new_count: int = 0


class DecisionInput(BaseModel):
    id: str
    approved: bool


class ApplyDecisionsRequest(BaseModel):
    decisions: list[DecisionInput]


class ApplyDecisionsResponse(BaseModel):
    upload_id: str
    validator_passed: bool
    errors: list[str] = []
    warnings: list[str] = []
    renamed_count: int = 0
    new_question_count: int = 0
    dropped_count: int = 0
