import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { Card } from "../common/Card";
import { Button } from "../common/Button";
import type { CountryOption, CsvUploadResponse, LlmValidateResponse, Provider, VisualSlotInfo } from "../../api/client";
import "./SetupPanel.css";

const PROVIDER_LABELS: Record<Provider, string> = {
  gemini: "Gemini",
  anthropic: "Anthropic Claude",
  openai: "OpenAI",
};

function slotLabel(filename: string): string {
  return filename
    .replace(".png", "")
    .replace(/^part(\d)_/, "Part $1 — ")
    .replace(/_/g, " ");
}

export function SetupPanel(props: {
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
  onProviderChange: (p: Provider) => void;
  apiKey: string;
  onApiKeyChange: (v: string) => void;
  llmValidation: LlmValidateResponse | null;
  onValidateKey: () => void;
  validating: boolean;

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
      </Card>

      <Card title="2. Report period" subtitle="Determines the run identifier and country-specific analysis config.">
        <div className="field-row">
          <label className="field">
            <span>Country</span>
            <select
              value={props.country}
              disabled={props.disabled}
              onChange={(e) => props.onCountryChange(e.target.value)}
            >
              {props.countries.map((c) => (
                <option key={c.value} value={c.value}>
                  {c.label}
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
      </Card>

      <Card title="3. Language model" subtitle="Used for qualitative tagging and report writing. Your key stays in this browser session only.">
        <div className="provider-row">
          {(Object.keys(PROVIDER_LABELS) as Provider[]).map((p) => (
            <label key={p} className={`provider-choice ${props.provider === p ? "provider-choice--selected" : ""}`}>
              <input
                type="radio"
                name="provider"
                checked={props.provider === p}
                disabled={props.disabled}
                onChange={() => props.onProviderChange(p)}
              />
              {PROVIDER_LABELS[p]}
            </label>
          ))}
        </div>
        <div className="field-row">
          <label className="field field--grow">
            <span>API key</span>
            <input
              type="password"
              autoComplete="off"
              placeholder={`Paste your ${PROVIDER_LABELS[props.provider]} API key`}
              value={props.apiKey}
              disabled={props.disabled}
              onChange={(e) => props.onApiKeyChange(e.target.value)}
            />
          </label>
          <Button
            variant="secondary"
            disabled={props.disabled || !props.apiKey || props.validating}
            onClick={props.onValidateKey}
          >
            {props.validating ? "Checking…" : "Validate key"}
          </Button>
        </div>
        {props.llmValidation && (
          <p className={props.llmValidation.ok ? "field-success" : "field-error"}>
            {props.llmValidation.message}
          </p>
        )}
      </Card>

      <Card title="4. Report visuals" subtitle="Power BI API access is pending approval — upload screenshots manually for now.">
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
