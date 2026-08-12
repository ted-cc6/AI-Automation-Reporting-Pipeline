"""Resolves every dashboard visual up front, independent of the rest of the pipeline -- it's a
pure filesystem check against a fixed, known list of subsection ids (report_render's
ALL_SUBSECTION_IDS), so it doesn't need the CSV, any section built, or the report assembled.
Runs from START, in parallel with the whole data pipeline, rather than waiting until right
before rendering.

Also surfaces what's missing, not just what's found -- previously a missing screenshot just
quietly became placeholder text with nothing else recording that it happened.
"""

from __future__ import annotations

from dashboard_visuals.lookup import find_dashboard_visuals, missing_dashboard_visuals
from report_render.section_layout import ALL_SUBSECTION_IDS

from .state import OrchestratorState


def resolve_dashboard_visuals_node(state: OrchestratorState) -> dict:
    results = find_dashboard_visuals(list(ALL_SUBSECTION_IDS))
    missing = missing_dashboard_visuals(results)
    return {"dashboard_visuals": results, "visuals_missing": missing}
