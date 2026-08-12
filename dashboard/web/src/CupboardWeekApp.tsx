import { useEffect, useMemo, useState } from "react";
import { LlmKeyPanel } from "./components/LlmKeyPanel/LlmKeyPanel";
import { SetupPanel } from "./components/SetupPanel/SetupPanel";
import { RunPanel } from "./components/RunPanel/RunPanel";
import { LogPanel } from "./components/LogPanel/LogPanel";
import { ResultsPanel } from "./components/ResultsPanel/ResultsPanel";
import { useRunEvents } from "./state/useRunEvents";
import {
  listUploadCountries,
  listLarcoPriorCandidates,
  uploadCsv,
  validateLlmKey,
  startRun,
  getVisualSlots,
  uploadVisual,
} from "./api/client";
import type {
  CountryOption,
  CsvUploadResponse,
  DatasetSchema,
  LlmValidateResponse,
  PriorRunCandidate,
  Provider,
  ReportType,
  VisualSlotInfo,
} from "./api/client";
import "./App.css";

const CURRENT_YEAR = new Date().getFullYear();

// "default" is the sentinel meaning "no single country selected" -- the
// full multi-country portfolio rollup (see analysis_engine/country_config.py's
// DEFAULT_COUNTRY). Always the first, permanent option in the country picker;
// listUploadCountries() supplies the rest once a CSV is uploaded.
const DEFAULT_COUNTRY_OPTION: CountryOption = { value: "default", label: "All Countries (Global Portfolio)" };

export function CupboardWeekApp({
  reportType,
  onReportTypeChange,
}: {
  reportType: ReportType;
  onReportTypeChange: (t: ReportType) => void;
}) {
  const [countries, setCountries] = useState<CountryOption[]>([DEFAULT_COUNTRY_OPTION]);
  const [country, setCountry] = useState("default");
  const [year, setYear] = useState(CURRENT_YEAR);
  const [quarter, setQuarter] = useState(2);
  const [runIdOverride, setRunIdOverride] = useState("");

  const [csvUpload, setCsvUpload] = useState<CsvUploadResponse | null>(null);
  const [csvUploading, setCsvUploading] = useState(false);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [datasetReady, setDatasetReady] = useState(false);

  // Only set when detection comes back "unknown" and the user picks one
  // manually (see SetupPanel's schema-override buttons) -- resolvedSchema
  // below is the single source of truth everything else reads from.
  const [schemaOverride, setSchemaOverride] = useState<DatasetSchema | null>(null);
  const [priorRunId, setPriorRunId] = useState("");
  const [priorRunOptions, setPriorRunOptions] = useState<PriorRunCandidate[]>([]);

  const resolvedSchema: DatasetSchema | null = schemaOverride ?? csvUpload?.detected_schema ?? null;

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
    if (!csvUpload) {
      setCountries([DEFAULT_COUNTRY_OPTION]);
      return;
    }
    listUploadCountries(csvUpload.upload_id)
      .then((opts) => {
        const merged = [DEFAULT_COUNTRY_OPTION, ...opts];
        setCountries(merged);
        // If the previously-selected country isn't in this upload's data
        // (e.g. a new file was uploaded), fall back to the full portfolio
        // rather than silently keeping a now-nonexistent selection.
        setCountry((prev) => (merged.some((o) => o.value === prev) ? prev : "default"));
      })
      .catch(() => setCountries([DEFAULT_COUNTRY_OPTION]));
  }, [csvUpload]);

  // A manual override only makes sense for the upload it was picked for --
  // a new file gets a fresh detection, not the previous file's override.
  useEffect(() => {
    setSchemaOverride(null);
  }, [csvUpload?.upload_id]);

  useEffect(() => {
    if (resolvedSchema !== "larco") {
      setPriorRunOptions([]);
      setPriorRunId("");
      return;
    }
    listLarcoPriorCandidates()
      .then(setPriorRunOptions)
      .catch(() => setPriorRunOptions([]));
  }, [resolvedSchema]);

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
        report_type: "cupboard_week",
        upload_id: csvUpload!.upload_id,
        country,
        year,
        quarter,
        run_id: runIdOverride.trim() || undefined,
        llm: { provider, api_key: apiKey },
        dataset_schema: resolvedSchema && resolvedSchema !== "unknown" ? resolvedSchema : undefined,
        prior_run_id: resolvedSchema === "larco" && priorRunId ? priorRunId : undefined,
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
        reportType={reportType}
        onReportTypeChange={onReportTypeChange}
        reportTypeDisabled={runActive}
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
        schemaOverride={schemaOverride}
        onSchemaOverrideChange={setSchemaOverride}
        reconcileEndpointBase={resolvedSchema === "larco" ? "/reconcile-larco" : "/reconcile"}
        showPriorRunPicker={resolvedSchema === "larco"}
        priorRunOptions={priorRunOptions}
        priorRunId={priorRunId}
        onPriorRunIdChange={setPriorRunId}
        powerbiMode={powerbiMode}
        onPowerbiModeChange={setPowerbiMode}
        visualSlots={visualSlots}
        onUploadVisual={handleUploadVisual}
        disabled={setupDisabled}
      />

      <RunPanel canStart={canStart} starting={starting} onStart={handleStart} snapshot={snapshot} startError={startError} />

      {runId && <LogPanel lines={logLines} />}

      {snapshot?.docx_ready && <ResultsPanel snapshot={snapshot} />}
    </>
  );
}
