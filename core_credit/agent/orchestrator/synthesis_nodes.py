"""Tier 1: the 3 cross-cutting sections, each declaring only its REAL dependencies rather than
waiting on a blanket barrier after all 9 Tier 0 nodes:

  build_client_voices      <- client_satisfaction only
  build_gender_scorecard   <- business_household_impact, resilience, child_wellbeing,
                               client_satisfaction (verbatim pool) + the CSV directly (its own
                               15-row table is recomputed fresh, not read from any section's
                               output)
  build_executive_summary  <- all 9 (reads a headline value from each)

All three now read their sibling sections from `state["sections"]` (the in-memory map every
Tier 0 node writes into) rather than synthesis.loader.load_section()'s file registry -- see the
sections=... parameter added to each build_section() for the orchestrator specifically.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from synthesis.build_client_voices import build_section as _build_client_voices
from synthesis.build_executive_summary import build_section as _build_executive_summary
from synthesis.build_gender_scorecard import build_section as _build_gender_scorecard

from .state import OrchestratorState

ANALYSIS_ROOT = Path(__file__).resolve().parents[1] / "analysis"
SYNTHESIS_OUTPUT_DIR = ANALYSIS_ROOT / "synthesis" / "output"


def _load_df(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False)


def _save_section_json(section_id: str, run_id: str, section) -> None:
    SYNTHESIS_OUTPUT_DIR.mkdir(exist_ok=True)
    out_path = SYNTHESIS_OUTPUT_DIR / f"{section_id}_{run_id}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")


def build_client_voices_node(state: OrchestratorState) -> dict:
    section = _build_client_voices(sections=state["sections"])
    _save_section_json("client_voices", state.get("run_id", "orchestrator"), section)
    return {"sections": {"client_voices": section}}


def build_gender_scorecard_node(state: OrchestratorState) -> dict:
    df = _load_df(state["csv_path"])
    section = _build_gender_scorecard(df, sections=state["sections"])
    _save_section_json("gender_scorecard", state.get("run_id", "orchestrator"), section)
    return {"sections": {"gender_scorecard": section}}


def build_executive_summary_node(state: OrchestratorState) -> dict:
    section = _build_executive_summary(sections=state["sections"])
    _save_section_json("executive_summary", state.get("run_id", "orchestrator"), section)
    return {"sections": {"executive_summary": section}}
