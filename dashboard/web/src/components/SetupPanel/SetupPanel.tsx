import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { Card } from "../common/Card";
import { Button } from "../common/Button";
import { DatasetValidation } from "../DatasetValidation/DatasetValidation";
import type {
  CountryOption,
  CsvUploadResponse,
  DatasetSchema,
  Provider,
  ReportType,
  VisualSlotInfo,
} from "../../api/client";
import "./SetupPanel.css";

function slotLabel(filename: string): string {
  return filename
    .replace(".png", "")
    .replace(/^part(\d)_/, "Part $1 — ")
    .replace(/_/g, " ");
}

export function SetupPanel(props: {
  reportType: ReportType;
  onReportTypeChange: (v: ReportType) => void;
  reportTypeDisabled: boolean;

  countries: CountryOption[];
  country: string;
  onCountryChange: (v: string) => void;
  year: number;
  onYearChange: (v: number) => void;
  quarter: number;
  onQuarterChange: (v: number) => void;
  runIdOverride: string;
  onRunIdOverrideChange: (v: string) => void;
  computedRunId: string;

  csvUpload: CsvUploadResponse | null;
  onCsvSelected: (file: File) => void;
  csvUploading: boolean;
  csvError: string | null;

  provider: Provider;
  apiKey: string;
  onDatasetResolved: (ready: boolean) => void;

  // Schema detection (see dashboard/api/schema_detection.py). schemaOverride
  // is only used when detection comes back "unknown" -- the user picks one
  // manually, which also determines which reconcile endpoint validates
  // against and what dataset_schema is eventually sent to /api/runs.
  schemaOverride: DatasetSchema | null;
  onSchemaOverrideChange: (v: DatasetSchema | null) => void;
  reconcileEndpointBase: string;

  // LARCO only -- Part 10's optional trend-comparison baseline. Uploading a
  // second, standalone prior-wave CSV here is enough; the backend analyzes
  // it and wires it in as the baseline automatically when this run starts,
  // with no separate "build a baseline first" run or run-picking involved.
  showPriorCsvUpload: boolean;
  priorCsvFile: File | null;
  onPriorCsvSelected: (file: File) => void;
  onPriorCsvCleared: () => void;

  // Cupboard Week only -- runs data cleaning + analysis without spending
  // any LLM calls, producing analysis_results.json without a report.
  dryRun: boolean;
  onDryRunChange: (v: boolean) => void;

  powerbiMode: "manual" | "api";
  onPowerbiModeChange: (m: "manual" | "api") => void;

  visualSlots: VisualSlotInfo[];
  onUploadVisual: (slot: string, file: File) => void;

  disabled: boolean;
}) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  function handleFiles(files: FileList | null) {
    if (files && files[0]) props.onCsvSelected(files[0]);
  }

  return (
    <>
      <Card
        title="1. Survey data"
        subtitle="Upload the raw KoBoToolbox CSV export for this quarter."
      >
        <div
          className={`dropzone ${dragOver ? "dropzone--over" : ""} ${props.disabled ? "dropzone--disabled" : ""}`}
          onClick={() => !props.disabled && fileInputRef.current?.click()}
          onDragOver={(e: DragEvent) => {
            e.preventDefault();
            if (!props.disabled) setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e: DragEvent) => {
            e.preventDefault();
            setDragOver(false);
            if (!props.disabled) handleFiles(e.dataTransfer.files);
          }}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".csv"
            hidden
            disabled={props.disabled}
            onChange={(e: ChangeEvent<HTMLInputElement>) => handleFiles(e.target.files)}
          />
          {props.csvUploading ? (
            <p>Uploading and parsing CSV…</p>
          ) : props.csvUpload ? (
            <div className="dropzone__result">
              <strong>{props.csvUpload.filename}</strong>
              <span>
                {props.csvUpload.row_count_preview.toLocaleString()} rows ·{" "}
                {props.csvUpload.columns_detected} columns detected
              </span>
            </div>
          ) : (
            <p>Drag a CSV here, or click to browse.</p>
          )}
        </div>
        {props.csvError && <p className="field-error">{props.csvError}</p>}

        {props.csvUpload && (
          <>
            {props.csvUpload.detected_schema === "unknown" && !props.schemaOverride && (
              <div className="schema-override">
                <p className="field-error">
                  This file didn't clearly match a known schema. Confirm which one it actually is before
                  validating:
                </p>
                <div className="schema-override__choices">
                  <Button variant="secondary" onClick={() => props.onSchemaOverrideChange("africa_vietnam")}>
                    It's Africa / Vietnam
                  </Button>
                  <Button variant="secondary" onClick={() => props.onSchemaOverrideChange("larco")}>
                    It's LARCO
                  </Button>
                </div>
              </div>
            )}

            {(props.csvUpload.detected_schema !== "unknown" || props.schemaOverride) && (
              <DatasetValidation
                key={`${props.csvUpload.upload_id}:${props.reconcileEndpointBase}`}
                endpointBase={props.reconcileEndpointBase}
                uploadId={props.csvUpload.upload_id}
                provider={props.provider}
                apiKey={props.apiKey}
                disabled={props.disabled}
                onResolved={props.onDatasetResolved}
              />
            )}
          </>
        )}
      </Card>

      <Card
        title="2. Report type & period"
        subtitle="Choose which report to generate, then set the run identifier. Selecting a country or region scopes the analysis to those respondents only, instead of the full multi-country portfolio."
      >
        <label className="field field--grow">
          <span>Report type</span>
          <select
            value={props.reportType}
            disabled={props.reportTypeDisabled}
            onChange={(e) => props.onReportTypeChange(e.target.value as ReportType)}
          >
            <option value="cupboard_week">Insurance Cupboard Week Report</option>
            <option value="gender_study">Insurance Gender Study Report</option>
          </select>
        </label>
        <div className="field-row">
          <label className="field">
            <span>Country / Region</span>
            <select
              value={props.country}
              disabled={props.disabled}
              onChange={(e) => props.onCountryChange(e.target.value)}
            >
              {props.countries.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
                  {typeof c.count === "number" ? ` (${c.count.toLocaleString()})` : ""}
                </option>
              ))}
            </select>
          </label>
          <label className="field field--narrow">
            <span>Year</span>
            <input
              type="number"
              value={props.year}
              disabled={props.disabled}
              onChange={(e) => props.onYearChange(Number(e.target.value))}
            />
          </label>
          <label className="field field--narrow">
            <span>Quarter</span>
            <select
              value={props.quarter}
              disabled={props.disabled}
              onChange={(e) => props.onQuarterChange(Number(e.target.value))}
            >
              {[1, 2, 3, 4].map((q) => (
                <option key={q} value={q}>
                  Q{q}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="field field--grow">
          <span>Run ID override (optional)</span>
          <input
            type="text"
            placeholder={props.computedRunId}
            value={props.runIdOverride}
            disabled={props.disabled}
            onChange={(e) => props.onRunIdOverrideChange(e.target.value)}
          />
        </label>
        <p className="run-id-preview">
          Run ID: <span className="mono">{props.computedRunId}</span>
        </p>

        {props.showPriorCsvUpload && (
          <div className="field field--grow">
            <span>Prior year's data for trend comparison (optional)</span>
            <PriorCsvPicker
              file={props.priorCsvFile}
              onSelected={props.onPriorCsvSelected}
              onCleared={props.onPriorCsvCleared}
              disabled={props.disabled}
            />
            <p className="field-hint">
              Upload last year's raw CSV here and this report will include a wave-over-wave trend
              comparison automatically -- no separate step needed. Leave this empty for a
              first-wave report with no trend comparison.
            </p>
          </div>
        )}

        {props.reportType === "cupboard_week" && (
          <label className="field field--checkbox">
            <input
              type="checkbox"
              checked={props.dryRun}
              disabled={props.disabled}
              onChange={(e) => props.onDryRunChange(e.target.checked)}
            />
            <span>
              Analysis only (skip report generation) -- cleans and analyzes this upload without
              spending any LLM calls, producing no .docx.
            </span>
          </label>
        )}
      </Card>

      <Card title="3. Report visuals" subtitle="Power BI API access is pending approval — upload screenshots manually for now.">
        <div className="powerbi-mode-row">
          <label className={`provider-choice ${props.powerbiMode === "manual" ? "provider-choice--selected" : ""}`}>
            <input
              type="radio"
              name="powerbi-mode"
              checked={props.powerbiMode === "manual"}
              onChange={() => props.onPowerbiModeChange("manual")}
            />
            Manual upload
          </label>
          <label className={`provider-choice ${props.powerbiMode === "api" ? "provider-choice--selected" : ""}`}>
            <input
              type="radio"
              name="powerbi-mode"
              checked={props.powerbiMode === "api"}
              onChange={() => props.onPowerbiModeChange("api")}
            />
            Power BI API <span className="badge badge--pending">not yet available</span>
          </label>
        </div>

        {props.powerbiMode === "manual" && (
          <div className="visual-grid">
            {props.visualSlots.map((slot) => (
              <VisualSlotRow key={slot.slot} slot={slot} onUpload={(f) => props.onUploadVisual(slot.slot, f)} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}

function PriorCsvPicker({
  file,
  onSelected,
  onCleared,
  disabled,
}: {
  file: File | null;
  onSelected: (f: File) => void;
  onCleared: () => void;
  disabled: boolean;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="prior-csv-picker">
      <input
        ref={inputRef}
        type="file"
        accept=".csv"
        hidden
        disabled={disabled}
        onChange={(e: ChangeEvent<HTMLInputElement>) => {
          const f = e.target.files?.[0];
          if (f) onSelected(f);
          e.target.value = "";
        }}
      />
      {file ? (
        <div className="prior-csv-picker__result">
          <span className="badge badge--success">selected</span>
          <strong>{file.name}</strong>
          <Button variant="ghost" disabled={disabled} onClick={onCleared}>
            Remove
          </Button>
        </div>
      ) : (
        <Button variant="secondary" disabled={disabled} onClick={() => inputRef.current?.click()}>
          Choose prior-year CSV…
        </Button>
      )}
    </div>
  );
}

function VisualSlotRow({ slot, onUpload }: { slot: VisualSlotInfo; onUpload: (f: File) => void }) {
  const inputRef = useRef<HTMLInputElement>(null);
  return (
    <div className="visual-slot">
      <div className="visual-slot__label">
        <span>{slotLabel(slot.filename)}</span>
        {!slot.has_generator && <span className="badge badge--pending">no generator yet</span>}
      </div>
      <div className="visual-slot__status">
        {slot.exists ? (
          <span className="badge badge--success">uploaded</span>
        ) : (
          <span className="badge badge--neutral">missing</span>
        )}
        <input
          ref={inputRef}
          type="file"
          accept="image/png"
          hidden
          onChange={(e) => e.target.files?.[0] && onUpload(e.target.files[0])}
        />
        <Button variant="ghost" onClick={() => inputRef.current?.click()}>
          {slot.exists ? "Replace" : "Upload"}
        </Button>
      </div>
    </div>
  );
}
