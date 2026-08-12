"""dashboard/api/models.py -- Pydantic request/response schemas for the dashboard API."""
from typing import Literal, Optional

from pydantic import BaseModel


DatasetSchema = Literal["africa_vietnam", "larco", "unknown"]


class CsvUploadResponse(BaseModel):
    upload_id: str
    filename: str
    size_bytes: int
    row_count_preview: int
    columns_detected: int
    # Best-guess source-survey schema, from diffing the header row against
    # each known schema's canonical column_mapping.csv (see
    # dashboard/api/schema_detection.py). "unknown" means neither known
    # schema matched well enough to trust -- the frontend should ask the
    # user to pick one explicitly rather than silently default.
    detected_schema: DatasetSchema = "africa_vietnam"


class CountryOption(BaseModel):
    value: str
    label: str
    # Respondent count for this country within a specific upload. Only set
    # by GET /api/csv/{upload_id}/countries (data-driven discovery); the
    # static GET /api/countries (config-file-driven) leaves this None since
    # it isn't scoped to any particular dataset.
    count: Optional[int] = None


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


ReportType = Literal["cupboard_week", "gender_study"]


class StartRunRequest(BaseModel):
    report_type: ReportType = "cupboard_week"
    upload_id: str
    llm: LlmConfig
    run_id: Optional[str] = None
    dry_run: bool = False
    # Cupboard Week only -- required when report_type == "cupboard_week",
    # ignored for gender_study (which has no country/quarter concept).
    country: Optional[str] = None
    year: Optional[int] = None
    quarter: Optional[int] = None
    powerbi: PowerBiConfigRequest = PowerBiConfigRequest()
    # Cupboard Week only, optional -- if unset, run_routes.py resolves it
    # from the upload's own detected_schema (see
    # dashboard/api/schema_detection.py). Explicit override exists for the
    # case where detection came back "unknown" and a human picked one.
    dataset_schema: Optional[DatasetSchema] = None
    # LARCO only, optional -- a prior completed run_id for Part 10's trend
    # comparison (see analysis_engine/sections/part_10.py). Ignored for
    # non-LARCO runs and for gender_study.
    prior_run_id: Optional[str] = None


class StartRunResponse(BaseModel):
    run_id: str
    status: str


class RunSummary(BaseModel):
    run_id: str
    pipeline: ReportType = "cupboard_week"
    status: str
    created_at: Optional[str] = None


class PriorRunCandidate(BaseModel):
    """A completed LARCO run usable as Part 10's --prior-run-id (see
    analysis_engine/sections/part_10.py). Discovered by scanning runs/ on
    disk (run_metadata.yaml + analysis_results.json), not the in-memory
    RUNS job registry -- that registry is cleared on every dashboard
    restart, but a prior wave's actual output survives on disk indefinitely,
    which is exactly the case this picker needs to keep working across
    restarts and even across VisionFund's typical months-later next-wave
    timeline."""
    run_id: str
    country: Optional[str] = None
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


# --- GEDSI (Gender Study) reconciliation ---
# Same rename/new_question/dropped taxonomy as the Cupboard Week models
# above, but "new_question" resolves to GENDSI's own role-typed mapping
# (quant_indicator / qual_supplementary / multiselect_option / unused)
# instead of a response_type. See dashboard/api/gedsi_reconciliation.py.
GedsiNewRoleType = Literal["quant_indicator", "qual_supplementary", "multiselect_option", "unused"]


class GedsiRecommendationOut(BaseModel):
    id: str
    type: RecommendationType
    confidence: float
    rationale: str
    old_raw_index: Optional[int] = None
    old_header: Optional[str] = None
    old_role_type: Optional[str] = None
    old_role_name: Optional[str] = None
    old_group_name: Optional[str] = None
    old_option_label: Optional[str] = None
    new_csv_index: Optional[int] = None
    new_header: Optional[str] = None
    suggested_role_type: Optional[GedsiNewRoleType] = None
    suggested_role_name: Optional[str] = None
    suggested_group_name: Optional[str] = None
    suggested_option_label: Optional[str] = None
    suggested_applies_to: Optional[str] = None
    approved: Optional[bool] = None


class GedsiValidateDatasetResponse(BaseModel):
    upload_id: str
    clean: bool
    recommendations: list[GedsiRecommendationOut] = []
    residual_old_count: int = 0
    residual_new_count: int = 0


class GedsiApplyDecisionsResponse(BaseModel):
    upload_id: str
    validator_passed: bool
    errors: list[str] = []
    warnings: list[str] = []
    renamed_count: int = 0
    new_question_count: int = 0
    dropped_count: int = 0
