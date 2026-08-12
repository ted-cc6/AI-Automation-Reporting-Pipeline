"""Terminal node. Defensive for the same reason assemble_report and render_docx are: its two
predecessors (render_docx, qa_review) can each fire more than once -- render_docx in
particular has its own mixed-depth predecessors (assemble_report vs. the near-instant
resolve_dashboard_visuals), so it produces an empty {} update before it ever produces the real
one, and every one of those firings triggers `done` too. Only print the final summary once
both real outputs are actually present.
"""

from __future__ import annotations

from .state import OrchestratorState


def done_node(state: OrchestratorState) -> dict:
    if not state.get("docx_path") or not state.get("qa_notes"):
        return {}  # not ready yet -- see module docstring

    missing = state.get("visuals_missing", [])
    issues = state.get("completeness_issues", [])

    print("\n" + "=" * 70)
    print("PIPELINE COMPLETE")
    print(f"Report: {state['docx_path']}")
    print(f"QA notes: {len(state['qa_notes'])} chars (see orchestrator/output/qa_notes_*.md)")
    print(f"Dashboard visuals missing: {len(missing)} of 26 (rendered as template placeholder text)")
    if missing:
        print(f"  {', '.join(missing)}")
    print(f"Completeness issues to review: {len(issues)}")
    for issue in issues:
        print(f"  - {issue}")

    return {}
