import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { Card } from "../common/Card";
import type { CsvUploadResponse } from "../../api/client";
import "./CoreCreditSetupPanel.css";

// Core Credit has no reconciliation/validate step in this UI: the raw export
// is cleaned and quality-checked by two LLM agents (Column Cleaner, Row
// Checker) that run automatically as the first tier of the pipeline itself
// (see core_credit/agent/orchestrator/data_prep_nodes.py) -- there's nothing
// for the user to review or approve before a run can start, unlike Cupboard
// Week/Gender Study's separate column-mapping reconciliation flow.
export function CoreCreditSetupPanel(props: {
  csvUpload: CsvUploadResponse | null;
  onCsvSelected: (file: File) => void;
  csvUploading: boolean;
  csvError: string | null;

  runLabel: string;
  onRunLabelChange: (v: string) => void;

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
        subtitle="Upload the raw quarterly Core Credit Impact Survey export -- the full, multi-country portfolio in one file."
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
          <p className="core-credit-note">
            Column cleaning and row-level quality checks run automatically as the first step of
            the pipeline below -- no manual review needed before starting.
          </p>
        )}
      </Card>

      <Card
        title="2. Run label"
        subtitle="Optional. Leave blank to have one generated automatically."
      >
        <label className="field field--grow">
          <span>Run label</span>
          <input
            type="text"
            placeholder="e.g. 2026-Q3-global"
            value={props.runLabel}
            disabled={props.disabled}
            onChange={(e) => props.onRunLabelChange(e.target.value)}
          />
        </label>
      </Card>
    </>
  );
}
