"""Tier 2: assemble_report -- the one node in this graph with predecessors at genuinely
different depths (9 Tier 0 sections directly, plus 3 Tier 1 sections that themselves depend on
Tier 0). LangGraph invokes a node like this once per predecessor's completion, not once after
all of them -- exactly the situation write_insight_node/assemble_section_node already handle in
every section-level graph this project has built, so this needs the same defensive no-op
pattern: check whether state actually has everything yet, return {} if not.
"""

from __future__ import annotations

import json
from pathlib import Path

from report_assembly.build_report import CROSS_CUTTING_SECTIONS, THEME_SECTIONS, build_report
from report_assembly.completeness import completeness_report, raise_on_meta_text_leaks
from report_assembly.translate_verbatims import translate_report_verbatims

from .state import OrchestratorState

ALL_SECTION_IDS = THEME_SECTIONS + CROSS_CUTTING_SECTIONS
OUTPUT_DIR = Path(__file__).resolve().parents[1] / "report_assembly" / "output"


def assemble_report_node(state: OrchestratorState) -> dict:
    sections = state.get("sections", {})
    if not all(section_id in sections for section_id in ALL_SECTION_IDS):
        return {}  # not ready yet -- see module docstring

    run_id = state.get("run_id", "orchestrator")
    report = build_report(sections=sections, run_id=run_id)
    raise_on_meta_text_leaks(report)  # hard gate -- stops the run before spending on translation/render
    translate_report_verbatims(report)  # in place -- every Verbatim gets .language/.english_gloss
    issues = completeness_report(report)

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = OUTPUT_DIR / f"core_credit_impact_report_{run_id}.json"
    out_path.write_text(json.dumps(report.model_dump(), indent=2, default=str), encoding="utf-8")

    return {"report": report, "completeness_issues": issues}
