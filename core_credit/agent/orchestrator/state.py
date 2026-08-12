"""Shared state for the top-level orchestrator graph.

`sections` is the one field every Tier 0/1 node writes into, merged via operator.or_ (same
reducer pattern used for metric_results in the section-level graphs) -- this is what replaces
the file-registry hop (synthesis.loader.CANONICAL_OUTPUTS) for an orchestrated run. Downstream
nodes (the three Tier 1 synthesis nodes, and assemble_report) read already-built Section
objects straight out of `sections`, never from disk. Every node still also writes its own JSON
to the usual output/ folder as a side effect, for the audit trail and for standalone/manual
reruns -- the orchestrator just doesn't depend on reading that back.

Everything else here is single-writer (exactly one node ever sets it), so no reducer is needed.
"""

from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict


class OrchestratorState(TypedDict, total=False):
    # Inputs
    raw_csv_path: str
    run_id: str
    benchmarks_path: str

    # Tier -1: data prep (clean_columns, check_rows)
    trimmed_csv_path: str
    column_manifest_path: str
    csv_path: str  # analysis_ready.csv -- what every Tier 0 node reads
    qa_report_path: str
    data_ready: bool
    failure_reason: Optional[str]

    # Tier 0/1: section outputs, keyed by section_id
    sections: Annotated[dict, operator.or_]

    # Independent branch: dashboard visuals (no dependency on sections at all)
    dashboard_visuals: dict  # subsection_id -> dashboard_visuals.lookup.DashboardVisual
    visuals_missing: list  # subsection_ids with no real screenshot on disk

    # Tier 2: assembly
    report: object  # schemas.report.CoreCreditImpactReport
    completeness_issues: list

    # Tier 3: render + QA
    docx_path: str
    qa_notes: str
