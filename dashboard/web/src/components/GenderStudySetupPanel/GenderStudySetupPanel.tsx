import { useRef, useState } from "react";
import type { ChangeEvent, DragEvent } from "react";
import { Card } from "../common/Card";
import { DatasetValidation } from "../DatasetValidation/DatasetValidation";
import type { CsvUploadResponse, Provider } from "../../api/client";
import "./GenderStudySetupPanel.css";

export function GenderStudySetupPanel(props: {
  csvUpload: CsvUploadResponse | null;
  onCsvSelected: (file: File) => void;
  csvUploading: boolean;
  csvError: string | null;

  provider: Provider;
  apiKey: string;
  onDatasetResolved: (ready: boolean) => void;

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
        subtitle="Upload the raw insurance client survey CSV export."
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
          <DatasetValidation
            key={props.csvUpload.upload_id}
            endpointBase="/gedsi-reconcile"
            uploadId={props.csvUpload.upload_id}
            provider={props.provider}
            apiKey={props.apiKey}
            disabled={props.disabled}
            onResolved={props.onDatasetResolved}
          />
        )}
      </Card>

      <Card
        title="2. Report label"
        subtitle="Used to name this run. Leave blank to have one generated automatically."
      >
        <label className="field field--grow">
          <span>Run label (optional)</span>
          <input
            type="text"
            placeholder="e.g. 2026-Q3-refresh"
            value={props.runLabel}
            disabled={props.disabled}
            onChange={(e) => props.onRunLabelChange(e.target.value)}
          />
        </label>
      </Card>

      <Card title="Qualitative theming" subtitle="How the NPS driver questions are coded.">
        <p className="gedsi-note">
          This report reuses this project's already-reviewed theme codebooks for the three
          Net Promoter Score driver questions. Every new response is coded against those
          themes, but the themes themselves are not re-generated from your upload — a human
          only ever reviews a codebook once, not on every run.
        </p>
      </Card>
    </>
  );
}
