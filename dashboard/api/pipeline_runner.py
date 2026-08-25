"""dashboard/api/pipeline_runner.py

Runs the 4 pipeline stages in-process (not via subprocess/CLI) so the
dashboard gets real per-stage/per-section/per-part progress and errors,
matching the fine-grained failure semantics each stage already implements:
  - Stage 1 (data_loader): any step failing halts the whole run.
  - Stage 2 (analysis_engine): per-section failures are recorded but don't
    abort the run -- already built into run_analysis.py, reused here.
  - Stage 3 (qualitative): a failure is non-fatal to the overall run --
    generation/orchestrator.py already treats a missing
    qualitative_results.json as a soft warning, not an error.
  - Stage 4 (generation): a single part failing all retries doesn't abort
    the run either -- already built into generation/writer.py, reused here.

This module intentionally imports run_analysis.py directly to reuse its
SECTIONS registry, SCHEMA_VERSION, and JSON-sanitising helpers rather than
duplicating them -- importing it has no side effects since its own
orchestration only runs inside `if __name__ == "__main__"`.
"""
import json
import logging
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

# A .env file at the project root is optional -- load_dotenv() silently
# no-ops if it's absent (e.g. a deployed environment that sets
# GEMINI_API_KEY directly). Without this call, qualitative/llm_call.py's
# own os.environ.get("GEMINI_API_KEY") fallback (used whenever this
# module's own LlmConfig doesn't carry an explicit api_key) never sees a
# .env file's contents at all -- confirmed missing during the session-8
# smoke test. dashboard/api/pipeline_runner.py is two directories below
# the project root (dashboard/api/), hence parents[2].
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

import run_analysis as ra
from data_loader import (
    data_loader_derived,
    data_loader_profiler,
    data_loader_screening,
    data_loader_transformer,
    data_loader_validator,
)
from data_loader.data_loader_api import load_survey_data
from analysis_engine.country_config import DEFAULT_COUNTRY, load_country_config
from report_scopes import REPORT_SCOPES
from data_quality_flags import get_flags as get_data_quality_flags, flagged_countries
from utils import parse_period
from analysis_engine.segments import describe_segments, get_all_segment_masks
from qualitative import llm_call
from qualitative.llm_call import call_gemini
from qualitative.parse_results import parse_and_save
from qualitative.prepare_payload import build_payload, load_config as load_qual_config, print_payload_stats
from generation.assembler import assemble
from generation.orchestrator import orchestrate, preflight_check
from generation.writer import write_all_parts
from generation.validate_output import load_in_scope_countries, load_product_mix, validate_report

from dashboard.api.config import PROJECT_ROOT, RUNS_DIR, UPLOADS_DIR
from dashboard.api.jobs import RUNS
from dashboard.api.models import LlmConfig

log = logging.getLogger(__name__)

DATA_LOADER_DIR = PROJECT_ROOT / "data_loader"
COLUMN_MAPPING_PATH = DATA_LOADER_DIR / "column_mapping.csv"
VALUE_CODING_MAP_PATH = DATA_LOADER_DIR / "value_coding_map.yaml"

DATA_LOADER_LARCO_DIR = PROJECT_ROOT / "data_loader_larco"
LARCO_COLUMN_MAPPING_PATH = DATA_LOADER_LARCO_DIR / "column_mapping.csv"
LARCO_VALUE_CODING_MAP_PATH = DATA_LOADER_LARCO_DIR / "value_coding_map.yaml"

# Which canonical column_mapping.csv/value_coding_map.yaml pair to start
# from, keyed by the same dataset_schema strings used throughout the
# pipeline (data_loader_screening.py's SCOPE_COUNTRIES, run_pipeline.py's
# DATASET_SCHEMA_PATHS, run_metadata.yaml's "dataset_schema" field). A
# per-upload reconciled mapping (see below) still overrides this base pair
# when one exists, regardless of schema.
DATASET_SCHEMA_PATHS = {
    "africa_vietnam": (COLUMN_MAPPING_PATH, VALUE_CODING_MAP_PATH),
    "larco":          (LARCO_COLUMN_MAPPING_PATH, LARCO_VALUE_CODING_MAP_PATH),
}
DEFAULT_DATASET_SCHEMA = "africa_vietnam"


def _load_and_clean(run_id: str, csv_path: Path, run_dir: Path, country: str,
                     dataset_schema: str, report_scope: "str | None", log) -> None:
    """Core data-cleaning logic (stage 1's actual work), parameterized by an
    explicit run_id and a plain log callback instead of a shared RunState --
    lets this run both for the tracked main run (via _run_stage1, which also
    updates state.stage1 for the frontend's stage pills) and for an
    untracked prior-wave baseline build (via _build_prior_baseline, which
    only needs the resulting files on disk, not its own stage tracking)."""
    # "default" (DEFAULT_COUNTRY) is the sentinel for "no single country
    # selected" -- it means "use country_configs/default.yaml" (no segment
    # overrides), not an actual country to filter survey_clean.parquet down
    # to. Any other value scopes stage 1's screening step to just that
    # country; None here means "don't filter, analyze the full portfolio."
    filter_country = country if country and country != DEFAULT_COUNTRY else None

    run_dir.mkdir(parents=True, exist_ok=True)
    run_metadata_path = run_dir / "run_metadata.yaml"
    with open(run_metadata_path, "w", encoding="utf-8") as f:
        yaml.dump(
            {"run_id": run_id, "country": country,
             "country_filter_applied": filter_country is not None,
             "dataset_schema": dataset_schema,
             "report_scope": report_scope,
             "created_at": datetime.now(timezone.utc).isoformat()},
            f, default_flow_style=False, allow_unicode=True,
        )

    # Uploads are always saved as UPLOADS_DIR/{upload_id}.csv (see csv_routes.py),
    # so the upload_id is recoverable from the path alone -- no signature change
    # needed to thread it through from the /api/runs route. If the dataset
    # reconciliation flow (dashboard/api/reconciliation.py, or its LARCO
    # counterpart) produced and validator-passed a per-upload mapping, use it
    # instead of the schema's canonical pair; either way, copy whichever pair
    # was actually used into run_dir as this run's own audit artifact.
    canonical_mapping_path, canonical_value_map_path = DATASET_SCHEMA_PATHS[dataset_schema]
    upload_id = csv_path.stem
    reconciled_mapping = UPLOADS_DIR / f"{upload_id}_column_mapping.csv"
    reconciled_value_map = UPLOADS_DIR / f"{upload_id}_value_coding_map.yaml"

    mapping_path = reconciled_mapping if reconciled_mapping.exists() else canonical_mapping_path
    value_map_path = reconciled_value_map if reconciled_value_map.exists() else canonical_value_map_path
    if mapping_path == reconciled_mapping:
        log(f"using reconciled column mapping for upload {upload_id}")

    shutil.copy2(mapping_path, run_dir / "column_mapping_used.csv")
    shutil.copy2(value_map_path, run_dir / "value_coding_map_used.yaml")

    steps = [
        ("profiler", lambda: data_loader_profiler.main(csv_path, mapping_path, run_dir)),
        ("transformer", lambda: data_loader_transformer.main(
            csv_path, mapping_path, value_map_path, run_dir)),
        ("screening", lambda: data_loader_screening.main(
            run_dir, target_country=filter_country, dataset_schema=dataset_schema,
            report_scope=report_scope)),
        ("derived", lambda: data_loader_derived.main(
            run_dir, target_country=filter_country, dataset_schema=dataset_schema,
            report_scope=report_scope)),
        ("validator", lambda: data_loader_validator.main(
            run_dir, target_country=filter_country, dataset_schema=dataset_schema,
            report_scope=report_scope)),
    ]
    for name, fn in steps:
        log(f"running {name}...")
        try:
            fn()
        except SystemExit as exc:
            # data_loader_derived/validator call sys.exit() internally; both
            # success (code None or 0) and failure use this path.
            code = exc.code
            if code not in (None, 0):
                raise RuntimeError(f"data_loader step '{name}' failed (exit code {code})") from exc
        log(f"{name} complete.")


def _analyze(run_id: str, run_dir: Path, country: str, dataset_schema: str,
             prior_run_id: "str | None", report_scope: "str | None", log,
             on_section=None) -> dict:
    """Core analysis logic (stage 2's actual work) -- see _load_and_clean()'s
    docstring for why this is split out from _run_stage2. on_section, if
    given, is called after each section with (section_timing, section_errors)
    so far, letting _run_stage2 mirror live per-section progress into
    state.stage2 the same way it always has. Returns a small summary dict
    (not the full analysis_results.json, which is written to disk either
    way) so the caller can decide its own stage status."""
    ds = load_survey_data(run_id=run_id)
    country_config = load_country_config(country)
    segment_masks = get_all_segment_masks(ds.df, country_config.segment_overrides)
    seg_desc = describe_segments(ds.df, country_config.segment_overrides)
    segments_skipped = [d["name"] for d in seg_desc if not d.get("available", True)]
    skip_reasons = {d["name"]: d.get("skip_reason", "") for d in seg_desc if not d.get("available", True)}

    report_scope_label = REPORT_SCOPES[report_scope]["label"] if report_scope else None
    data_notes = None
    screening_summary_path = run_dir / "screening_summary.json"
    if screening_summary_path.exists():
        try:
            data_notes = json.loads(screening_summary_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            log(f"warning: could not parse {screening_summary_path.name}: {exc}")

    # quality_flags' duration-outlier input is ready now; the period-mismatch
    # input (fieldwork) isn't computed until about_survey's section runs
    # below, so the actual get_data_quality_flags() call happens after that
    # loop -- see run_analysis.py's CLI path for the same split.
    duration_outliers = (data_notes or {}).get("duration_outliers") or []

    now = datetime.now(timezone.utc)
    parts: dict = {}
    section_errors: dict = {}
    section_timing: dict = {}

    sections = ra.build_sections(dataset_schema, prior_run_id=prior_run_id, report_scope=report_scope)
    for key, label, calculate_fn in sections:
        t0 = time.perf_counter()
        try:
            parts[key] = calculate_fn(ds, segment_masks)
            log(f"{key} ({label}) OK")
        except Exception as exc:
            section_errors[key] = {"error": str(exc), "type": type(exc).__name__}
            parts[key] = None
            log(f"{key} ({label}) FAILED: {exc}")
        finally:
            section_timing[key] = round(time.perf_counter() - t0, 3)
        if on_section:
            on_section(dict(section_timing), dict(section_errors))

    entered_year, entered_quarter = parse_period(run_id)
    fieldwork = (parts.get("about_survey") or {}).get("fieldwork")
    quality_flags = get_data_quality_flags(report_scope, duration_outliers,
                                            entered_year=entered_year, entered_quarter=entered_quarter,
                                            fieldwork=fieldwork)
    if quality_flags:
        log(f"data quality flags active: {[f['id'] for f in quality_flags]}")

    result = {
        "meta": {
            "run_id": run_id,
            "generated_at": now.isoformat(timespec="seconds"),
            "schema_version": ra.SCHEMA_VERSION,
            "n_total": ds.n,
            "low_n_threshold": ra.LOW_N_THRESHOLD,
            "country": country_config.country,
            "country_label": country_config.label,
            "report_context": country_config.report_context,
            "dataset_schema": dataset_schema,
            "report_scope": report_scope,
            "report_scope_label": report_scope_label,
            "metric_notes": {
                name: {"note": note.note, "applies_to_segments": note.applies_to_segments}
                for name, note in country_config.metric_notes.items()
            },
            "segments_active": list(segment_masks.keys()),
            "segments_skipped": segments_skipped,
            "skip_reasons": skip_reasons,
            "section_timing_seconds": section_timing,
            "section_errors": section_errors,
        },
        "segments_summary": seg_desc,
        "data_notes": data_notes,
        "data_quality_flags": quality_flags,
        "parts": parts,
    }
    result = ra._sanitise(result)
    output_path = run_dir / "analysis_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, cls=ra._AnalysisEncoder)

    return {"section_errors": section_errors, "section_timing": section_timing, "n_total": ds.n}


def _run_stage1(state, csv_path: Path, run_dir: Path, country: str,
                 dataset_schema: str = DEFAULT_DATASET_SCHEMA,
                 report_scope: "str | None" = None) -> None:
    state.current_stage = 1
    state.stage1 = {"status": "running"}
    state.log("Stage 1/4 -- Loading and cleaning survey data...")
    _load_and_clean(state.run_id, csv_path, run_dir, country, dataset_schema, report_scope,
                     log=lambda msg: state.log(f"  [stage 1] {msg}"))
    state.stage1 = {"status": "succeeded"}
    state.log("Stage 1/4 complete.")


def _run_stage2(state, run_dir: Path, country: str, dataset_schema: str = DEFAULT_DATASET_SCHEMA,
                 prior_run_id: "str | None" = None, report_scope: "str | None" = None) -> None:
    state.current_stage = 2
    state.stage2 = {"status": "running", "section_timing": {}, "section_errors": {}}
    state.log("Stage 2/4 -- Running analysis engine...")

    def on_section(timing, errors):
        state.stage2["section_timing"] = timing
        state.stage2["section_errors"] = errors

    summary = _analyze(state.run_id, run_dir, country, dataset_schema, prior_run_id, report_scope,
                        log=lambda msg: state.log(f"  [stage 2] {msg}"), on_section=on_section)
    state.stage2["status"] = "partial_failure" if summary["section_errors"] else "succeeded"
    state.log(f"Stage 2/4 complete ({len(summary['section_errors'])} section error(s)).")


def _build_prior_baseline(state, prior_csv_path: Path, prior_run_id: str,
                           prior_dataset_schema: str) -> bool:
    """Runs stages 1-2 (data cleaning + analysis) for a standalone prior-wave
    CSV (e.g. a 2025 LARCO export), producing analysis_results.json at
    RUNS_DIR/prior_run_id -- used as Part 10's trend-comparison baseline for
    the MAIN run this precedes (see execute()). Logged into the same run's
    log stream, prefixed distinctly, but deliberately does NOT touch
    state.stage1/state.stage2 -- those reflect the MAIN run's own progress,
    and this preliminary step has no stage pill of its own.

    Never raises: a failure here (a malformed prior CSV, an undetectable
    schema, a genuine data error) should not block the main report from
    generating -- it should just generate without a trend comparison,
    exactly as if no prior CSV had been given at all. Returns True/False so
    execute() knows whether to pass this run_id through as prior_run_id.
    """
    prior_run_dir = RUNS_DIR / prior_run_id
    state.log(f"Building prior-wave baseline from the uploaded prior-year CSV ({prior_dataset_schema} schema)...")
    try:
        _load_and_clean(prior_run_id, prior_csv_path, prior_run_dir, country="default",
                         dataset_schema=prior_dataset_schema, report_scope=None,
                         log=lambda msg: state.log(f"  [prior baseline] {msg}"))
        _analyze(prior_run_id, prior_run_dir, country="default", dataset_schema=prior_dataset_schema,
                 prior_run_id=None, report_scope=None,
                 log=lambda msg: state.log(f"  [prior baseline] {msg}"))
        state.log("Prior-wave baseline ready -- this run's trend comparison will use it.")
        return True
    except Exception as exc:
        state.log(
            f"Could not build a prior-wave baseline from the uploaded CSV ({exc}) -- "
            "continuing without a trend comparison for this run."
        )
        return False


def _run_stage3(state, run_dir: Path, llm: LlmConfig, dry_run: bool) -> None:
    state.current_stage = 3
    state.stage3 = {"status": "running"}
    state.log("Stage 3/4 -- Qualitative tagging (batched NPS tagging + synthesis)...")

    try:
        df = pd.read_parquet(run_dir / "survey_clean.parquet")
        qual_config = load_qual_config()
        payload = build_payload(df, qual_config)

        if dry_run:
            print_payload_stats(payload)
            state.stage3 = {"status": "skipped_dry_run"}
            state.log("Stage 3/4 skipped (dry run).")
            return

        model = qual_config["model"] if llm.provider == "gemini" else llm.model
        raw_response_path = run_dir / "gemini_raw_response.json"
        nps_total = len(payload.get("nps_promoters", [])) + len(payload.get("nps_passives", [])) \
            + len(payload.get("nps_detractors", []))
        n_batches = -(-nps_total // llm_call._NPS_BATCH_SIZE)  # ceil division
        state.log(
            f"  [stage 3] tagging {nps_total} NPS responses in {n_batches} batch(es), "
            "then one synthesis call -- see container logs for per-batch progress."
        )

        # Reuse stage 2's already-computed data_quality_flags (analysis_
        # results.json, written before stage 3 ever runs) rather than
        # recomputing from screening_summary.json a second time here.
        excluded_countries = []
        analysis_results_path = run_dir / "analysis_results.json"
        if analysis_results_path.exists():
            try:
                stage2_result = json.loads(analysis_results_path.read_text(encoding="utf-8"))
                excluded_countries = flagged_countries(stage2_result.get("data_quality_flags") or [])
            except json.JSONDecodeError as exc:
                state.log(f"  [stage 3] warning: could not parse analysis_results.json for data quality flags: {exc}")

        raw_result = call_gemini(
            payload=payload,
            raw_response_path=raw_response_path,
            model=model,
            provider=llm.provider,
            api_key=llm.api_key,
            excluded_countries=excluded_countries,
        )
        parse_and_save(raw_gemini=raw_result, df=df, run_id=state.run_id,
                        provider=llm.provider, model=model, payload=payload)
        state.stage3 = {"status": "succeeded"}
        state.log("Stage 3/4 complete.")
    except Exception as exc:
        # Non-fatal: generation/orchestrator.py treats a missing
        # qualitative_results.json as a soft warning, so the run continues.
        state.stage3 = {"status": "failed", "error": str(exc)}
        state.log(f"Stage 3/4 FAILED (continuing without qualitative data): {exc}")


def _run_stage4(state, run_dir: Path, llm: LlmConfig, dry_run: bool) -> None:
    state.current_stage = 4
    state.stage4 = {"status": "running", "parts": {}}
    state.log("Stage 4/4 -- Generating report narrative + assembling .docx...")

    spec_path = PROJECT_ROOT / "generation" / "report_spec.yaml"
    spec = yaml.safe_load(spec_path.read_text(encoding="utf-8"))

    preflight = preflight_check(state.run_id)
    for w in preflight["warnings"]:
        state.log(f"  [stage 4] warning: {w}")
    if not preflight["ok"]:
        raise RuntimeError("Preflight failed: " + "; ".join(preflight["errors"]))

    # Parts 9/10 are only rendered when analysis_results.json actually has
    # data for them -- orchestrate()'s default parts_filter (parts_filter=
    # None) derives that straight from the run's own output, so no
    # dataset_schema lookup is needed here (see generation/orchestrator.py's
    # orchestrate() for the full rationale).
    packages = orchestrate(state.run_id)

    if dry_run:
        out = run_dir / "dry_run_packages.json"
        out.write_text(json.dumps(packages, indent=2, default=str), encoding="utf-8")
        state.stage4["status"] = "skipped_dry_run"
        state.log(f"Stage 4/4 skipped (dry run) -- packages written to {out.name}.")
        return

    model = spec.get("model") if llm.provider == "gemini" else llm.model

    def progress_cb(part_key: str, status: dict) -> None:
        state.stage4["parts"][part_key] = status
        suffix = f" -- {status['error']}" if status.get("error") else ""
        state.log(f"  [stage 4] {part_key}: {status['status']}{suffix}")

    written_texts = write_all_parts(
        packages, state.run_id, model=model,
        provider=llm.provider, api_key=llm.api_key,
        progress_cb=progress_cb,
    )
    failed_parts = [k for k, v in written_texts.items() if isinstance(v, dict) and v.get("_generation_failed")]

    # Advisory validation pass (never blocks assembly; see
    # generation/validate_output.py's module docstring) -- surfaced in the
    # run log and saved to disk for review, same as the CLI path in
    # generation/run_generation.py.
    in_scope_countries = load_in_scope_countries(state.run_id, runs_dir=RUNS_DIR)
    product_mix = load_product_mix(state.run_id, runs_dir=RUNS_DIR)
    validation_findings = validate_report(written_texts, packages, in_scope_countries, product_mix)
    (run_dir / "validation_report.json").write_text(
        json.dumps(validation_findings, indent=2), encoding="utf-8"
    )
    state.stage4["validation"] = {
        "n_reject": sum(1 for f in validation_findings if f["severity"] == "reject"),
        "n_warn": sum(1 for f in validation_findings if f["severity"] == "warn"),
    }
    if validation_findings:
        state.log(
            f"  [stage 4] validation: {state.stage4['validation']['n_reject']} reject, "
            f"{state.stage4['validation']['n_warn']} warn (see validation_report.json)"
        )

    # report_spec.yaml's output_filename is a static string left over from a
    # specific quarter, not templated by run_id -- name the file explicitly
    # here instead so successive runs don't collide or overwrite each other.
    output_path = run_dir / f"VFI_Insurance_Impact_Report_{state.run_id}.docx"
    assemble(packages, written_texts, state.run_id, output_path)
    state.docx_path = output_path

    state.stage4["status"] = "partial_failure" if failed_parts else "succeeded"
    note = f" ({len(failed_parts)} part(s) need manual write-up)" if failed_parts else ""
    state.log(f"Stage 4/4 complete -- report at {output_path.name}{note}")


def execute(run_id: str, csv_path: Path, country: str, llm: LlmConfig, dry_run: bool = False,
            dataset_schema: str = DEFAULT_DATASET_SCHEMA, prior_run_id: "str | None" = None,
            report_scope: "str | None" = None, prior_csv_path: "Path | None" = None,
            prior_dataset_schema: "str | None" = None) -> None:
    """Entry point run via asyncio.to_thread() from the /api/runs route.

    prior_run_id: a prior run_id for Part 10's trend comparison (see
    analysis_engine/sections/part_10.py) -- activates Part 10 on this run
    regardless of dataset_schema (e.g. a 2026 africa_vietnam-schema run for
    a LARCO country, compared against its 2025 larco-schema baseline).
    report_scope: a named region group (see report_scopes.py, e.g. "lacro"
    or "africa") to scope this run to, instead of the full multi-region
    portfolio. Exposed via StartRunRequest.report_scope / the dashboard's
    report-scope picker (see CupboardWeekApp.tsx), which sends country=
    "default" alongside it -- the frontend treats the two as mutually
    exclusive, though this function itself just applies whichever filters
    are non-default.
    prior_csv_path/prior_dataset_schema: an alternative to prior_run_id --
    a standalone prior-wave CSV (e.g. a 2025 LARCO export) uploaded
    alongside the main CSV in the same request. When given, this run first
    builds a baseline from it (see _build_prior_baseline()) and uses THAT
    as the effective prior_run_id, overriding any literal prior_run_id also
    passed. A failure building the baseline degrades to no trend comparison
    rather than failing the whole run -- see _build_prior_baseline()'s
    docstring.
    """
    state = RUNS[run_id]
    run_dir = RUNS_DIR / run_id
    state.status = "running"

    effective_prior_run_id = prior_run_id
    if prior_csv_path is not None:
        candidate_prior_run_id = f"{run_id}__prior"
        if _build_prior_baseline(state, prior_csv_path, candidate_prior_run_id,
                                  prior_dataset_schema or "unknown"):
            effective_prior_run_id = candidate_prior_run_id

    try:
        _run_stage1(state, csv_path, run_dir, country, dataset_schema=dataset_schema,
                    report_scope=report_scope)
    except Exception as exc:
        state.stage1 = {"status": "failed", "error": str(exc)}
        state.status = "failed"
        state.error = f"Stage 1 failed: {exc}"
        state.log(f"Pipeline halted: {exc}")
        return

    try:
        _run_stage2(state, run_dir, country, dataset_schema=dataset_schema, prior_run_id=effective_prior_run_id,
                    report_scope=report_scope)
    except Exception as exc:
        state.stage2 = {"status": "failed", "error": str(exc)}
        state.status = "failed"
        state.error = f"Stage 2 failed: {exc}"
        state.log(f"Pipeline halted: {exc}")
        return

    _run_stage3(state, run_dir, llm, dry_run)  # never raises; failure is non-fatal

    try:
        _run_stage4(state, run_dir, llm, dry_run)
    except Exception as exc:
        state.stage4["status"] = "failed"
        state.status = "failed"
        state.error = f"Stage 4 failed: {exc}"
        state.log(f"Pipeline halted: {exc}")
        return

    statuses = [state.stage1["status"], state.stage2["status"], state.stage3["status"], state.stage4["status"]]
    if any(s == "failed" for s in statuses):
        state.status = "partial_failure"
    elif any(s == "partial_failure" for s in statuses):
        state.status = "partial_failure"
    else:
        state.status = "succeeded"
    state.log(f"Pipeline finished with status: {state.status}")
