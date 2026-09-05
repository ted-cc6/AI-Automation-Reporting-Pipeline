"""Assembles the final CoreCreditImpactReport from all 12 sections' already-built, already-
validated output. Plain deterministic module -- no LLM call, no agent, no judgment to make.

Every number in this report was computed by a deterministic engine (metrics_engine, ppi_module,
benchmark_module); every sentence of prose was already written and grounding-checked by the
writer chain in earlier steps (agent/analysis/driver/, agent/analysis/graph/,
agent/analysis/synthesis/). This script's only job is combining 12 already-finished JSON files
into one validated object -- reusing agent/analysis/synthesis/loader.py's canonical-output
registry (the same explicit-path-per-section registry the cross-cutting sections already read
from) rather than inventing a second one.

Pydantic validation on CoreCreditImpactReport construction already guarantees every section is
present and correctly shaped; completeness.py adds the one thing Pydantic can't check --
whether any subsection's prose was left unwritten, ran over its template word cap, or contains
a percentage that never traced back to real data.

Usage: python build_report.py
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))

from llm_client import MODEL  # noqa: E402
from report_assembly.completeness import completeness_report  # noqa: E402
from schemas.report import CoreCreditImpactReport  # noqa: E402
from synthesis.loader import load_section  # noqa: E402

THEME_SECTIONS = [
    "client_profile",
    "financial_access",
    "poverty_likelihood",
    "business_household_impact",
    "child_wellbeing",
    "client_protection",
    "agency",
    "resilience",
    "client_satisfaction",
]
CROSS_CUTTING_SECTIONS = ["executive_summary", "gender_scorecard", "client_voices"]

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _data_availability_note() -> Optional[str]:
    """CC-033: run_for_dashboard.py sets these two env vars (and only these two, and only when
    the corresponding reference workbook is absent) before the graph runs, so reading them here
    is the exact, direct signal for what this run actually degraded -- not a re-derivation from
    section output shape, which would have to guess at the no-PPI-data stub's structure instead
    of reading the one flag that caused it. Also fires for a CLI run an operator deliberately
    started with the flag set, which is correct: the run is degraded either way.
    """
    ppi_missing = bool(os.environ.get("CORE_CREDIT_ALLOW_MISSING_PPI"))
    benchmarks_missing = bool(os.environ.get("CORE_CREDIT_ALLOW_MISSING_BENCHMARKS"))
    if not ppi_missing and not benchmarks_missing:
        return None
    parts = []
    if ppi_missing:
        parts.append(
            "the PPI reference workbooks (PPI_scorecards.xlsx, PPI_lookups.xlsx) were not "
            "available, so no client could be scored and Part 2 (Poverty Likelihood) is omitted"
        )
    if benchmarks_missing:
        parts.append(
            "the External Benchmarks.xlsx workbook was not available, so no MFI Index "
            "comparison appears anywhere in this report"
        )
    return (
        "This run is missing reference data VisionFund normally provides server-side: "
        + "; and ".join(parts)
        + ". This is an infrastructure gap for this run, not a data quality issue with the "
        "survey responses -- every other section reflects the full submitted dataset."
    )


def build_report(sections: Optional[dict] = None, run_id: Optional[str] = None) -> CoreCreditImpactReport:
    """`sections`, when given, is an already-built {section_id: Section} map covering all 12
    section_ids (e.g. from the orchestrator's graph state) -- used instead of re-reading every
    section's canonical output file. Standalone/CLI usage (sections=None) is unchanged: falls
    back to loading all 12 via synthesis.loader.load_section(), same as before this was wired
    into the orchestrator.

    `run_id`, when given, is stamped onto the report alongside the model version actually used
    for every LLM call in this pipeline (llm_client.MODEL) -- see CoreCreditImpactReport's own
    docstring for why: LLM-tagged qualitative findings aren't reproducible run to run, so
    traceability (which run and model produced this exact document) is the honest substitute.
    """
    if sections is None:
        sections = {section_id: load_section(section_id) for section_id in THEME_SECTIONS + CROSS_CUTTING_SECTIONS}

    # Executive Summary already computed the report's own reporting_period from the same CSV
    # every other section was built from -- reused here rather than re-derived a second time.
    reporting_period = sections["executive_summary"].reporting_period

    return CoreCreditImpactReport(
        reporting_period=reporting_period,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        run_id=run_id,
        model_version=MODEL,
        data_availability_note=_data_availability_note(),
        **sections,
    )


def main() -> None:
    report = build_report()
    print(f"Assembled CoreCreditImpactReport for {report.reporting_period} "
          f"({report.client_profile.n_respondents} respondents, {report.client_profile.n_countries} countries).")

    issues = completeness_report(report)

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"core_credit_impact_report_{timestamp}.json"
    out_path.write_text(json.dumps(report.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")

    if issues:
        print(f"\n{len(issues)} completeness issue(s) to review before publishing:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nNo completeness issues found -- every subsection is written, within its "
              "template cap, and free of ungrounded percentages.")


if __name__ == "__main__":
    main()
