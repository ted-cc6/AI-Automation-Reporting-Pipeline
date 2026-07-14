import { useEffect, useMemo, useState } from "react";
import { Header } from "./components/common/Header";
import { LlmKeyPanel } from "./components/LlmKeyPanel/LlmKeyPanel";
import { SetupPanel } from "./components/SetupPanel/SetupPanel";
import { RunPanel } from "./components/RunPanel/RunPanel";
import { LogPanel } from "./components/LogPanel/LogPanel";
import { ResultsPanel } from "./components/ResultsPanel/ResultsPanel";
import { useRunEvents } from "./state/useRunEvents";
import {
  listCountries,
  uploadCsv,
  validateLlmKey,
  startRun,
  getVisualSlots,
  uploadVisual,
} from "./api/client";
import type { CountryOption, CsvUploadResponse, LlmValidateResponse, Provider, VisualSlotInfo } from "./api/client";
import "./App.css";

const CURRENT_YEAR = new Date().getFullYear();

export default function App() {
  const [countries, setCountries] = useState<CountryOption[]>([]);
  const [country, setCountry] = useState("default");
  const [year, setYear] = useState(CURRENT_YEAR);
  const [quarter, setQuarter] = useState(2);
  const [runIdOverride, setRunIdOverride] = useState("");

  const [csvUpload, setCsvUpload] = useState<CsvUploadResponse | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [datasetReady, setDatasetReady] = useState(false);

  const [provider, setProvider] = useState<Provider>("gemini");
  const [apiKey, setApiKey] = useState("");
  const [llmValidation, setLlmValidation] = useState<LlmValidateResponse | null>(null);
  const [validating, setValidating] = useState(false);

  const [powerbiMode, setPowerbiMode] = useState<"manual" | "api">("manual");
  const [visualSlots, setVisualSlots] = useState<VisualSlotInfo[]>([]);

  const [runId, setRunId] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  const { snapshot, logLines } = useRunEvents(runId);

  const computedRunId = useMemo(
    () => runIdOverride.trim() || `${country}_${year}_Q${quarter}`,
    [runIdOverride, country, year, quarter],
  );

  useEffect(() => {
    listCountries().then((opts) => {
      setCountries(opts);
      if (opts.length && !opts.some((o) => o.value === country)) {
        setCountry(opts[0].value);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    getVisualSlots(computedRunId)
      .then(setVisualSlots)
      .catch(() => setVisualSlots([]));
  }, [computedRunId]);

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
      const result = await validateLlmKey(provider, apiKey);
      setLlmValidation(result);
    } catch (err) {
      setLlmValidation({ ok: false, message: err instanceof Error ? err.message : String(err) });
    } finally {
      setValidating(false);
    }
  }

  async function handleUploadVisual(slot: string, file: File) {
    const updated = await uploadVisual(computedRunId, slot, file);
    setVisualSlots((prev) => prev.map((s) => (s.slot === updated.slot ? updated : s)));
  }

  async function handleStart() {
    setStarting(true);
    setStartError(null);
    try {
      const res = await startRun({
        upload_id: csvUpload!.upload_id,
        country,
        year,
        quarter,
        run_id: runIdOverride.trim() || undefined,
        llm: { provider, api_key: apiKey },
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
    <div className="app-shell">
      <Header />
      <main className="app-main">
        <LlmKeyPanel
          provider={provider}
          onProviderChange={setProvider}
          apiKey={apiKey}
          onApiKeyChange={setApiKey}
          llmValidation={llmValidation}
          onValidateKey={handleValidateKey}
          validating={validating}
          disabled={runActive}
        />

        <SetupPanel
          countries={countries}
          country={country}
          onCountryChange={setCountry}
          year={year}
          onYearChange={setYear}
          quarter={quarter}
          onQuarterChange={setQuarter}
          runIdOverride={runIdOverride}
          onRunIdOverrideChange={setRunIdOverride}
          computedRunId={computedRunId}
          csvUpload={csvUpload}
          onCsvSelected={handleCsvSelected}
          csvUploading={csvUploading}
          csvError={csvError}
          provider={provider}
          apiKey={apiKey}
          onDatasetResolved={setDatasetReady}
          powerbiMode={powerbiMode}
          onPowerbiModeChange={setPowerbiMode}
          visualSlots={visualSlots}
          onUploadVisual={handleUploadVisual}
          disabled={setupDisabled}
        />

        <RunPanel canStart={canStart} starting={starting} onStart={handleStart} snapshot={snapshot} startError={startError} />

        {runId && <LogPanel lines={logLines} />}

        {snapshot?.docx_ready && <ResultsPanel snapshot={snapshot} />}
      </main>
    </div>
  );
}
