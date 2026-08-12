"""Tier 0: the 9 theme sections. No edges between them -- LangGraph runs them concurrently
once the data-ready gate opens.

6 call a bespoke driver's build_section(df) directly. business_household_impact uses its
driver (not the config-driven graph version) deliberately: synthesis/loader.py's
CANONICAL_OUTPUTS has always pointed at the driver's output as the blessed source for this
section, so the orchestrator matches that rather than introducing a second, parallel
implementation path for the same section.

3 (financial_access, client_protection, agency) have no bespoke driver and go through the
config-driven section_configs/graph system instead -- compiled WITHOUT a checkpointer, since
the orchestrator's own checkpoint (one level up) is what provides resumability; if this node
is interrupted, it's redone whole on resume, not resumed mid-way.

Every node returns {"sections": {section_id: <built Section>}}, merged into state via
operator.or_. Each also still writes its own JSON to the usual output/ folder, matching every
other driver/graph run in this project -- the orchestrator just doesn't read it back from disk.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from driver.build_business_household_impact import build_section as _build_business_household_impact
from driver.build_child_wellbeing import build_section as _build_child_wellbeing
from driver.build_client_profile import build_section as _build_client_profile
from driver.build_client_satisfaction import build_section as _build_client_satisfaction
from driver.build_poverty_likelihood import build_section as _build_poverty_likelihood
from driver.build_resilience import build_section as _build_resilience
from graph.graph import compile_graph
from section_configs.registry import SECTION_CONFIGS

from .state import OrchestratorState

ANALYSIS_ROOT = Path(__file__).resolve().parents[1] / "analysis"
DRIVER_OUTPUT_DIR = ANALYSIS_ROOT / "driver" / "output"
GRAPH_OUTPUT_DIR = ANALYSIS_ROOT / "graph" / "output"

_DRIVER_BUILDERS = {
    "client_profile": _build_client_profile,
    "poverty_likelihood": _build_poverty_likelihood,
    "business_household_impact": _build_business_household_impact,
    "child_wellbeing": _build_child_wellbeing,
    "resilience": _build_resilience,
    "client_satisfaction": _build_client_satisfaction,
}
_CONFIG_DRIVEN_SECTION_IDS = ("financial_access", "client_protection", "agency")


def _load_df(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False)


def _save_section_json(output_dir: Path, section_id: str, run_id: str, section) -> None:
    output_dir.mkdir(exist_ok=True)
    out_path = output_dir / f"{section_id}_{run_id}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")


def _make_driver_node(section_id: str):
    build = _DRIVER_BUILDERS[section_id]

    def node(state: OrchestratorState) -> dict:
        df = _load_df(state["csv_path"])
        section = build(df)
        _save_section_json(DRIVER_OUTPUT_DIR, section_id, state.get("run_id", "orchestrator"), section)
        return {"sections": {section_id: section}}

    return node


def _make_config_driven_node(section_id: str):
    def node(state: OrchestratorState) -> dict:
        config = SECTION_CONFIGS[section_id]
        compiled = compile_graph()  # no checkpointer -- see module docstring
        inputs = {
            "section_config": config,
            "csv_path": state["csv_path"],
            "benchmarks_path": state["benchmarks_path"],
            "batch_size": 200,
            "reasoning_effort": "high",
            "sample": None,
        }
        run_id = state.get("run_id", "orchestrator")
        result = compiled.invoke(
            inputs, config={"configurable": {"thread_id": f"{run_id}-{section_id}"}, "run_name": f"build_{section_id}"}
        )
        section = result["section"]
        _save_section_json(GRAPH_OUTPUT_DIR, section_id, run_id, section)
        return {"sections": {section_id: section}}

    return node


build_client_profile_node = _make_driver_node("client_profile")
build_poverty_likelihood_node = _make_driver_node("poverty_likelihood")
build_business_household_impact_node = _make_driver_node("business_household_impact")
build_child_wellbeing_node = _make_driver_node("child_wellbeing")
build_resilience_node = _make_driver_node("resilience")
build_client_satisfaction_node = _make_driver_node("client_satisfaction")

build_financial_access_node = _make_config_driven_node("financial_access")
build_client_protection_node = _make_config_driven_node("client_protection")
build_agency_node = _make_config_driven_node("agency")
