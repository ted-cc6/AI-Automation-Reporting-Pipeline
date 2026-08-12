import { useState } from "react";
import { LlmKeyPanel } from "./components/LlmKeyPanel/LlmKeyPanel";
import { CoreCreditSetupPanel } from "./components/CoreCreditSetupPanel/CoreCreditSetupPanel";
import { CoreCreditRunPanel } from "./components/CoreCreditRunPanel/CoreCreditRunPanel";
import { LogPanel } from "./components/LogPanel/LogPanel";
import { CoreCreditResultsPanel } from "./components/CoreCreditResultsPanel/CoreCreditResultsPanel";
import { useRunEvents } from "./state/useRunEvents";
import { uploadCsv, validateLlmKey, startRun } from "./api/client";
import type { CsvUploadResponse, LlmValidateResponse } from "./api/client";
import "./App.css";

// core_credit's pipeline is Anthropic-only end to end (Sonnet 5 + Haiku 4.5) -- see
// core_credit/agent/analysis/llm_client.py and the backend's own provider gate in
// dashboard/api/routes/run_routes.py, which rejects any other provider for this report_type.
const PROVIDER = "anthropic" as const;

export function CoreCreditApp() {
  const [runLabel, setRunLabel] = useState("");

  const [csvUpload, setCsvUpload] = useState<CsvUploadResponse | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);

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
        report_type: "core_credit",
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
  const canStart = csvUpload != null && llmValidation?.ok === true && (runId == null || runFinished);
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

      <CoreCreditSetupPanel
        csvUpload={csvUpload}
        onCsvSelected={handleCsvSelected}
        csvUploading={csvUploading}
        csvError={csvError}
        runLabel={runLabel}
        onRunLabelChange={setRunLabel}
        disabled={setupDisabled}
      />

      <CoreCreditRunPanel canStart={canStart} starting={starting} onStart={handleStart} snapshot={snapshot} startError={startError} />

      {runId && <LogPanel lines={logLines} />}

      {snapshot?.docx_ready && <CoreCreditResultsPanel snapshot={snapshot} />}
    </>
  );
}
