const BASE = "/api";

export type Provider = "gemini" | "anthropic" | "openai";

export interface CountryOption {
  value: string;
  label: string;
  // Respondent count within a specific upload. Only set by
  // listUploadCountries() (data-driven discovery); the static
  // listCountries() (config-file-driven) leaves this undefined.
  count?: number;
}

// A named region group (see report_scopes.py) a run can be scoped to instead
// of a single country or the full multi-region portfolio, e.g. "lacro".
export interface ReportScopeOption {
  value: string;
  label: string;
}

// Which source-survey schema an upload matches, from diffing its header row
// against each known schema's canonical column mapping (see
// dashboard/api/schema_detection.py). "unknown" means neither matched well
// enough to trust -- the user should be asked to confirm before starting a run.
export type DatasetSchema = "africa_vietnam" | "larco" | "unknown";

export interface CsvUploadResponse {
  upload_id: string;
  filename: string;
  size_bytes: number;
  row_count_preview: number;
  columns_detected: number;
  detected_schema: DatasetSchema;
}

export interface LlmValidateResponse {
  ok: boolean;
  message: string;
}

export type RecommendationType = "rename" | "new_question" | "dropped";
export type NewQuestionResponseType = "open_text" | "single_select" | "likert5" | "nps_score" | "age";
export type GedsiNewRoleType = "quant_indicator" | "qual_supplementary" | "multiselect_option" | "unused";

export interface LikertValueEntry {
  int: number;
  label: string;
}

// Covers both reconciliation backends' recommendation shape (Cupboard
// Week's question_ref/response_type taxonomy and GEDSI's role-typed
// mapping) so DatasetValidation.tsx's card UI can render either without
// forking the component -- see endpointBase on DatasetValidation.
export interface Recommendation {
  id: string;
  type: RecommendationType;
  confidence: number;
  rationale: string;
  old_raw_index?: number | null;
  old_header?: string | null;
  new_csv_index?: number | null;
  new_header?: string | null;
  approved?: boolean | null;
  // Cupboard Week fields:
  old_question_ref?: string | null;
  old_category?: string | null;
  suggested_question_ref?: string | null;
  suggested_response_type?: NewQuestionResponseType | null;
  suggested_value_map?: Record<string, LikertValueEntry> | null;
  // GEDSI fields:
  old_role_type?: string | null;
  old_role_name?: string | null;
  old_group_name?: string | null;
  old_option_label?: string | null;
  suggested_role_type?: GedsiNewRoleType | null;
  suggested_role_name?: string | null;
  suggested_group_name?: string | null;
  suggested_option_label?: string | null;
  suggested_applies_to?: string | null;
}

export interface ValidateDatasetResponse {
  upload_id: string;
  clean: boolean;
  recommendations: Recommendation[];
  residual_old_count: number;
  residual_new_count: number;
}

export interface ApplyDecisionsResponse {
  upload_id: string;
  validator_passed: boolean;
  errors: string[];
  warnings: string[];
  renamed_count: number;
  new_question_count: number;
  dropped_count: number;
}

export interface StartRunResponse {
  run_id: string;
  status: string;
}

export type ReportType = "cupboard_week" | "gender_study" | "core_credit";

// Top-level space the landing page offers -- one level above ReportType, since Insurance
// itself still offers a choice between two report types (cupboard_week/gender_study) once
// inside, while Core Credit is a single report type with no sibling variant.
export type Product = "insurance" | "core_credit";

export interface RunSummary {
  run_id: string;
  pipeline: ReportType;
  status: string;
  created_at?: string;
}

export interface VisualSlotInfo {
  slot: string;
  filename: string;
  part: string;
  has_generator: boolean;
  exists: boolean;
  source?: { source: string; written_at: string } | null;
}

export interface StageInfo {
  status: string;
  [key: string]: unknown;
}

export interface PartStatus {
  status: string;
  error?: string;
}

export interface RunSnapshot {
  run_id: string;
  pipeline: ReportType;
  country: string | null;
  created_at: string;
  status: string;
  current_stage: number;
  stage1: StageInfo;
  stage2: StageInfo;
  stage3: StageInfo;
  stage4: StageInfo & { parts: Record<string, PartStatus> };
  // Only meaningful for gender_study runs (GEDSI's 6-stage pipeline);
  // present but always "pending" on cupboard_week runs.
  stage5: StageInfo;
  stage6: StageInfo;
  // core_credit only -- its graph has a genuinely parallel middle tier (9
  // sections at once), which doesn't fit the linear stage1..stage6 shape
  // above. node_name -> "done", populated as each orchestrator node
  // produces real output; core_credit_result carries its two run-level
  // summaries once the run finishes. Both are always present (default {})
  // on every run, just empty for cupboard_week/gender_study.
  core_credit_nodes: Record<string, string>;
  core_credit_result: { visuals_missing?: string[]; completeness_issues?: string[] };
  error?: string | null;
  docx_ready: boolean;
  xlsx_ready: boolean;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, init);
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new Error(`${res.status} ${res.statusText}${body ? `: ${body}` : ""}`);
  }
  return res.json() as Promise<T>;
}

const jsonHeaders = { "Content-Type": "application/json" };

export function uploadCsv(file: File): Promise<CsvUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  return req("/csv/upload", { method: "POST", body: form });
}

export function listCountries(): Promise<CountryOption[]> {
  return req("/countries");
}

// report_scopes.py's REPORT_SCOPES, for the report-scope picker -- lets a
// run be scoped to a named region group (e.g. LACRO) instead of a single
// country or the full portfolio.
export function listReportScopes(): Promise<ReportScopeOption[]> {
  return req("/report-scopes");
}

// Countries actually present in a specific upload (with respondent counts),
// discovered from the raw CSV -- lets the country picker reflect this
// dataset's real population instead of only the statically-configured
// country_configs/*.yaml options.
export function listUploadCountries(uploadId: string): Promise<CountryOption[]> {
  return req(`/csv/${uploadId}/countries`);
}

export function validateLlmKey(provider: Provider, api_key: string): Promise<LlmValidateResponse> {
  return req("/llm/validate", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ provider, api_key }),
  });
}

// endpointBase points at either reconciliation backend's route prefix, e.g.
// "/reconcile" (Cupboard Week) or "/gedsi-reconcile" (Gender Study) -- both
// mounted under the shared /api prefix already baked into req().
export function validateDataset(
  endpointBase: string,
  uploadId: string,
  provider: Provider,
  api_key: string,
): Promise<ValidateDatasetResponse> {
  return req(`${endpointBase}/${uploadId}/validate`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ llm: { provider, api_key } }),
  });
}

export function applyDecisions(
  endpointBase: string,
  uploadId: string,
  decisions: { id: string; approved: boolean }[],
): Promise<ApplyDecisionsResponse> {
  return req(`${endpointBase}/${uploadId}/apply`, {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ decisions }),
  });
}

export interface StartRunRequest {
  report_type: ReportType;
  upload_id: string;
  run_id?: string;
  llm: { provider: Provider; api_key: string; model?: string };
  // Cupboard Week only -- required when report_type is "cupboard_week".
  country?: string;
  year?: number;
  quarter?: number;
  // Cupboard Week only, optional -- if omitted, the backend resolves it from
  // the upload's own detected_schema. Only needs to be sent explicitly when
  // detection came back "unknown" and the user picked one manually.
  dataset_schema?: DatasetSchema;
  // LARCO only, optional -- a prior completed run_id for Part 10's trend
  // comparison. See listLarcoPriorCandidates().
  prior_run_id?: string;
  // Optional -- a named region group (see report_scopes.py, e.g. "lacro" or
  // "africa") to scope this run to. Sent alongside country="default" when
  // set (see CupboardWeekApp.tsx's handleStart()).
  report_scope?: string;
  // Cupboard Week only, optional -- runs stages 1-2 (data cleaning +
  // analysis) only, producing analysis_results.json without spending any
  // LLM calls on qualitative tagging or report writing (stages 3-4 are
  // skipped). Used to build a prior-wave baseline for Part 10's trend
  // comparison from a standalone prior-wave CSV (e.g. a 2025 LARCO export)
  // without generating a full report for it. Not supported for
  // gender_study/core_credit (see run_routes.py).
  dry_run?: boolean;
}

export interface PriorRunCandidate {
  run_id: string;
  country?: string | null;
  created_at?: string | null;
}

export function startRun(payload: StartRunRequest): Promise<StartRunResponse> {
  return req("/runs", { method: "POST", headers: jsonHeaders, body: JSON.stringify(payload) });
}

export function getRun(runId: string): Promise<RunSnapshot> {
  return req(`/runs/${runId}`);
}

export function listRuns(): Promise<RunSummary[]> {
  return req("/runs");
}

// Completed LARCO runs usable as StartRunRequest.prior_run_id, for Part 10's
// trend comparison -- only meaningful once a LARCO upload is detected.
export function listLarcoPriorCandidates(): Promise<PriorRunCandidate[]> {
  return req("/runs/larco-prior-candidates");
}

export function getVisualSlots(runId: string): Promise<VisualSlotInfo[]> {
  return req(`/runs/${runId}/visuals`);
}

export function uploadVisual(runId: string, slot: string, file: File): Promise<VisualSlotInfo> {
  const form = new FormData();
  form.append("slot", slot);
  form.append("file", file);
  return req(`/runs/${runId}/visuals`, { method: "POST", body: form });
}

export function downloadUrl(runId: string): string {
  return `${BASE}/runs/${runId}/download`;
}

export function downloadXlsxUrl(runId: string): string {
  return `${BASE}/runs/${runId}/download-xlsx`;
}
