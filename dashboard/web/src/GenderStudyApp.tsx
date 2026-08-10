import { useState } from "react";
import { LlmKeyPanel } from "./components/LlmKeyPanel/LlmKeyPanel";
import { GenderStudySetupPanel } from "./components/GenderStudySetupPanel/GenderStudySetupPanel";
import { GenderStudyRunPanel } from "./components/GenderStudyRunPanel/GenderStudyRunPanel";
import { LogPanel } from "./components/LogPanel/LogPanel";
import { GenderStudyResultsPanel } from "./components/GenderStudyResultsPanel/GenderStudyResultsPanel";
import { useRunEvents } from "./state/useRunEvents";
import { uploadCsv, validateLlmKey, startRun } from "./api/client";
import type { CsvUploadResponse, LlmValidateResponse, ReportType } from "./api/client";
import "./App.css";

const PROVIDER = "anthropic" as const;

export function GenderStudyApp({
  reportType,
  onReportTypeChange,
}: {
  reportType: ReportType;
  onReportTypeChange: (t: ReportType) => void;
}) {
  const [runLabel, setRunLabel] = useState("");

  const [csvUpload, setCsvUpload] = useState<CsvUploadResponse | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [datasetReady, setDatasetReady] = useState(false);

  const [apiKey, setApiKey] = useState("");
  const [llmValidation, setLlmValidation] = useState<LlmValidateResponse | null>(null);
  const [validating, setValidating] = useState(false);

  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { snapshot, logLines } = useRunEvents(runId);

  async function handleCsvSelected(file: File) {
    setCsvUploading(true);
    setCsvError(null);
    setDatasetReady(false);
    try {
      const result = await uploadCsv(file);
      setCsvUpload(result);
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : String(err));
    } finally {
      setCsvUploading(false);
    }
  }

  async function handleValidateKey() {
    setValidating(true);
    setLlmValidation(null);
    try {
      const result = await validateLlmKey(PROVIDER, apiKey);
      setLlmValidation(result);
    } catch (err) {
      setLlmValidation({ ok: false, message: err instanceof Error ? err.message : String(err) });
    } finally {
      setValidating(false);
    }
  }

  async function handleStart() {
    setStarting(true);
    setStartError(null);
    try {
      const res = await startRun({
        report_type: "gender_study",
        upload_id: csvUpload!.upload_id,
        run_id: runLabel.trim() || undefined,
        llm: { provider: PROVIDER, api_key: apiKey },
      });
      setRunId(res.run_id);
    } catch (err) {
      setStartError(err instanceof Error ? err.message : String(err));
    } finally {
      setStarting(false);
    }
  }

  const runFinished = snapshot != null && ["succeeded", "failed", "partial_failure"].includes(snapshot.status);
  const canStart =
    csvUpload != null && llmValidation?.ok === true && datasetReady && (runId == null || runFinished);
  const runActive = runId != null && !runFinished;
  const setupDisabled = runActive || llmValidation?.ok !== true;

  return (
    <>
      <LlmKeyPanel
        provider={PROVIDER}
        onProviderChange={() => {}}
        lockedProvider={PROVIDER}
        apiKey={apiKey}
        onApiKeyChange={setApiKey}
        llmValidation={llmValidation}
        onValidateKey={handleValidateKey}
        validating={validating}
        disabled={runActive}
      />

      <GenderStudySetupPanel
        reportType={reportType}
        onReportTypeChange={onReportTypeChange}
        reportTypeDisabled={runActive}
        csvUpload={csvUpload}
        onCsvSelected={handleCsvSelected}
        csvUploading={csvUploading}
        csvError={csvError}
        provider={PROVIDER}
        apiKey={apiKey}
        onDatasetResolved={setDatasetReady}
        runLabel={runLabel}
        onRunLabelChange={setRunLabel}
        disabled={setupDisabled}
      />

      <GenderStudyRunPanel canStart={canStart} starting={starting} onStart={handleStart} snapshot={snapshot} startError={startError} />

      {runId && <LogPanel lines={logLines} />}

      {snapshot?.docx_ready && <GenderStudyResultsPanel snapshot={snapshot} />}
    </>
  );
}
