"""Tier 3: render_docx and qa_review, both downstream of assemble_report only -- they don't
depend on each other, so they run in parallel.

render_docx also depends on resolve_dashboard_visuals, which finishes almost immediately (it's
a filesystem check with no dependency on the rest of the pipeline) while assemble_report is the
very end of a 45-90 minute chain -- another case of predecessors at different depths, so this
node needs the same defensive no-op pattern as assemble_report itself.
"""

from __future__ import annotations

import json
from pathlib import Path

from docx import Document

from report_render.qa_review import review_report
from report_render.section_layout import render_report

from .state import OrchestratorState

OUTPUT_DIR = Path(__file__).resolve().parents[1] / "orchestrator" / "output"


def render_docx_node(state: OrchestratorState) -> dict:
    report = state.get("report")
    dashboard_visuals = state.get("dashboard_visuals")
    if report is None or dashboard_visuals is None:
        return {}  # not ready yet -- see module docstring

    doc = Document()
    render_report(doc, report, dashboard_visuals=dashboard_visuals)

    OUTPUT_DIR.mkdir(exist_ok=True)
    run_id = state.get("run_id", "orchestrator")
    docx_path = OUTPUT_DIR / f"Core_Credit_Impact_Report_{run_id}.docx"
    doc.save(str(docx_path))

    return {"docx_path": str(docx_path)}


def qa_review_node(state: OrchestratorState) -> dict:
    report = state.get("report")
    if report is None:
        return {}  # not ready yet

    qa_notes = review_report(report)

    OUTPUT_DIR.mkdir(exist_ok=True)
    run_id = state.get("run_id", "orchestrator")
    qa_path = OUTPUT_DIR / f"qa_notes_{run_id}.md"
    qa_path.write_text(qa_notes, encoding="utf-8")

    return {"qa_notes": qa_notes}
