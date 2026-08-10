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
from analysis_engine.segments import describe_segments, get_all_segment_masks
from qualitative.llm_call import call_gemini
from qualitative.parse_results import parse_and_save
from qualitative.prepare_payload import build_payload, load_config as load_qual_config, print_payload_stats
from generation.assembler import assemble
from generation.orchestrator import orchestrate, preflight_check
from generation.writer import write_all_parts

from dashboard.api.config import PROJECT_ROOT, RUNS_DIR, UPLOADS_DIR
from dashboard.api.jobs import RUNS
from dashboard.api.models import LlmConfig

log = logging.getLogger(__name__)

DATA_LOADER_DIR = PROJECT_ROOT / "data_loader"
COLUMN_MAPPING_PATH = DATA_LOADER_DIR / "column_mapping.csv"
VALUE_CODING_MAP_PATH = DATA_LOADER_DIR / "value_coding_map.yaml"


def _run_stage1(state, csv_path: Path, run_dir: Path, country: str) -> None:
    state.current_stage = 1
    state.stage1 = {"status": "running"}
    state.log("Stage 1/4 -- Loading and cleaning survey data...")

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
            {"run_id": state.run_id, "country": country,
             "country_filter_applied": filter_country is not None,
             "created_at": datetime.now(timezone.utc).isoformat()},
            f, default_flow_style=False, allow_unicode=True,
        )

    # Uploads are always saved as UPLOADS_DIR/{upload_id}.csv (see csv_routes.py),
    # so the upload_id is recoverable from the path alone -- no signature change
    # needed to thread it through from the /api/runs route. If the dataset
    # reconciliation flow (dashboard/api/reconciliation.py) produced and
    # validator-passed a per-upload mapping, use it instead of canonical; either
    # way, copy whichever pair was actually used into run_dir as this run's own
    # audit artifact.
    upload_id = csv_path.stem
    reconciled_mapping = UPLOADS_DIR / f"{upload_id}_column_mapping.csv"
    reconciled_value_map = UPLOADS_DIR / f"{upload_id}_value_coding_map.yaml"

    mapping_path = reconciled_mapping if reconciled_mapping.exists() else COLUMN_MAPPING_PATH
    value_map_path = reconciled_value_map if reconciled_value_map.exists() else VALUE_CODING_MAP_PATH
    if mapping_path == reconciled_mapping:
        state.log(f"  [stage 1] using reconciled column mapping for upload {upload_id}")

    shutil.copy2(mapping_path, run_dir / "column_mapping_used.csv")
    shutil.copy2(value_map_path, run_dir / "value_coding_map_used.yaml")

    steps = [
        ("profiler", lambda: data_loader_profiler.main(csv_path, mapping_path, run_dir)),
        ("transformer", lambda: data_loader_transformer.main(
            csv_path, mapping_path, value_map_path, run_dir)),
        ("screening", lambda: data_loader_screening.main(run_dir, target_country=filter_country)),
        ("derived", lambda: data_loader_derived.main(run_dir, target_country=filter_country)),
        ("validator", lambda: data_loader_validator.main(run_dir, target_country=filter_country)),
    ]
    for name, fn in steps:
        state.log(f"  [stage 1] running {name}...")
        try:
            fn()
        except SystemExit as exc:
            # data_loader_derived/validator call sys.exit() internally; both
            # success (code None or 0) and failure use this path.
            code = exc.code
            if code not in (None, 0):
                raise RuntimeError(f"data_loader step '{name}' failed (exit code {code})") from exc
        state.log(f"  [stage 1] {name} complete.")

    state.stage1 = {"status": "succeeded"}
    state.log("Stage 1/4 complete.")


def _run_stage2(state, run_dir: Path, country: str) -> None:
    state.current_stage = 2
    state.stage2 = {"status": "running", "section_timing": {}, "section_errors": {}}
    state.log("Stage 2/4 -- Running analysis engine...")

    ds = load_survey_data(run_id=state.run_id)
    country_config = load_country_config(country)
    segment_masks = get_all_segment_masks(ds.df, country_config.segment_overrides)
    seg_desc = describe_segments(ds.df, country_config.segment_overrides)
    segments_skipped = [d["name"] for d in seg_desc if not d.get("available", True)]
    skip_reasons = {d["name"]: d.get("skip_reason", "") for d in seg_desc if not d.get("available", True)}

    now = datetime.now(timezone.utc)
    parts: dict = {}
    section_errors: dict = {}
    section_timing: dict = {}

    for key, label, module in ra.SECTIONS:
        t0 = time.perf_counter()
        try:
            parts[key] = module.calculate(ds, segment_masks)
            state.log(f"  [stage 2] {key} ({label}) OK")
        except Exception as exc:
            section_errors[key] = {"error": str(exc), "type": type(exc).__name__}
            parts[key] = None
            state.log(f"  [stage 2] {key} ({label}) FAILED: {exc}")
        finally:
            section_timing[key] = round(time.perf_counter() - t0, 3)
        state.stage2["section_timing"] = dict(section_timing)
        state.stage2["section_errors"] = dict(section_errors)

    result = {
        "meta": {
            "run_id": state.run_id,
            "generated_at": now.isoformat(timespec="seconds"),
            "schema_version": ra.SCHEMA_VERSION,
            "n_total": ds.n,
            "low_n_threshold": ra.LOW_N_THRESHOLD,
            "country": country_config.country,
            "country_label": country_config.label,
            "report_context": country_config.report_context,
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
        "parts": parts,
    }
    result = ra._sanitise(result)
    output_path = run_dir / "analysis_results.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False, cls=ra._AnalysisEncoder)

    state.stage2["status"] = "partial_failure" if section_errors else "succeeded"
    state.log(f"Stage 2/4 complete ({len(section_errors)} section error(s)).")


def _run_stage3(state, run_dir: Path, llm: LlmConfig, dry_run: bool) -> None:
    state.current_stage = 3
    state.stage3 = {"status": "running"}
    state.log("Stage 3/4 -- Qualitative tagging (1 LLM call)...")

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
        raw_result = call_gemini(
            payload=payload,
            raw_response_path=raw_response_path,
            model=model,
            provider=llm.provider,
            api_key=llm.api_key,
        )
        parse_and_save(raw_gemini=raw_result, df=df, run_id=state.run_id)
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

    # report_spec.yaml's output_filename is a static string left over from a
    # specific quarter, not templated by run_id -- name the file explicitly
    # here instead so successive runs don't collide or overwrite each other.
    output_path = run_dir / f"VFI_Insurance_Impact_Report_{state.run_id}.docx"
    assemble(packages, written_texts, state.run_id, output_path)
    state.docx_path = output_path

    state.stage4["status"] = "partial_failure" if failed_parts else "succeeded"
    note = f" ({len(failed_parts)} part(s) need manual write-up)" if failed_parts else ""
    state.log(f"Stage 4/4 complete -- report at {output_path.name}{note}")


def execute(run_id: str, csv_path: Path, country: str, llm: LlmConfig, dry_run: bool = False) -> None:
    """Entry point run via asyncio.to_thread() from the /api/runs route."""
    state = RUNS[run_id]
    run_dir = RUNS_DIR / run_id
    state.status = "running"

    try:
        _run_stage1(state, csv_path, run_dir, country)
    except Exception as exc:
        state.stage1 = {"status": "failed", "error": str(exc)}
        state.status = "failed"
        state.error = f"Stage 1 failed: {exc}"
        state.log(f"Pipeline halted: {exc}")
        return

    try:
        _run_stage2(state, run_dir, country)
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
