const BASE = "/api";

export type Provider = "gemini" | "anthropic" | "openai";

export interface CountryOption {
  value: string;
  label: string;
}

export interface CsvUploadResponse {
  upload_id: string;
  filename: string;
  size_bytes: number;
  row_count_preview: number;
  columns_detected: number;
}

export interface LlmValidateResponse {
  ok: boolean;
  message: string;
}

export interface StartRunResponse {
  run_id: string;
  status: string;
}

export interface RunSummary {
  run_id: string;
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
  country: string;
  created_at: string;
  status: string;
  current_stage: number;
  stage1: StageInfo;
  stage2: StageInfo;
  stage3: StageInfo;
  stage4: StageInfo & { parts: Record<string, PartStatus> };
  error?: string | null;
  docx_ready: boolean;
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

export function validateLlmKey(provider: Provider, api_key: string): Promise<LlmValidateResponse> {
  return req("/llm/validate", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ provider, api_key }),
  });
}

export interface StartRunRequest {
  upload_id: string;
  country: string;
  year: number;
  quarter: number;
  run_id?: string;
  llm: { provider: Provider; api_key: string; model?: string };
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
