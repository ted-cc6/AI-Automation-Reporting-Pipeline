"""dashboard/api/visuals_source.py

Canonical manifest of the report's visual slots, and the one writer function
that both the manual-upload endpoint and the (future) Power BI export path
call to populate them. Both write to the exact `runs/{run_id}/visuals/{filename}`
path generation/orchestrator.py's check_visual() already reads -- one code
path, two entry points.

The 12 slots below are copied from generation/report_spec.yaml's `file:`
entries. Only 11 of them have a working generator today: generate_visuals.py
(the standalone matplotlib script) never produces `part4_themes.png`, so that
slot always renders as "[VISUAL PENDING]" in the assembled .docx. This is a
pre-existing spec/generator mismatch, not something introduced here -- the UI
should surface it as "no generator available yet", not as a failure.
"""
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

log = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parent.parent.parent

VISUAL_SLOTS = [
    {"slot": "part1_coverage_bar",         "filename": "part1_coverage_bar.png",         "part": "part_1", "has_generator": True},
    {"slot": "part1_claims_process_bar",   "filename": "part1_claims_process_bar.png",   "part": "part_1", "has_generator": True},
    {"slot": "part2_funnel",               "filename": "part2_funnel.png",               "part": "part_2", "has_generator": True},
    {"slot": "part2_no_claim_reasons",     "filename": "part2_no_claim_reasons.png",     "part": "part_2", "has_generator": True},
    {"slot": "part2_claim_challenges",     "filename": "part2_claim_challenges.png",     "part": "part_2", "has_generator": True},
    {"slot": "part3_financial_protection", "filename": "part3_financial_protection.png", "part": "part_3", "has_generator": True},
    {"slot": "part4_nps",                  "filename": "part4_nps.png",                  "part": "part_4", "has_generator": True},
    {"slot": "part4_themes",               "filename": "part4_themes.png",               "part": "part_4", "has_generator": False},
    {"slot": "part5_drivers",              "filename": "part5_drivers.png",              "part": "part_5", "has_generator": True},
    {"slot": "part5_healthcare",           "filename": "part5_healthcare.png",           "part": "part_5", "has_generator": True},
    {"slot": "part6_scorecard",            "filename": "part6_scorecard.png",            "part": "part_6", "has_generator": True},
    {"slot": "part7_scorecard",            "filename": "part7_scorecard.png",            "part": "part_7", "has_generator": True},
]

_SLOT_BY_NAME = {s["slot"]: s for s in VISUAL_SLOTS}


def visuals_dir(run_id: str) -> Path:
    return PROJECT_ROOT / "runs" / run_id / "visuals"


def _sources_path(run_id: str) -> Path:
    return visuals_dir(run_id) / ".sources.json"


def list_slots(run_id: str) -> list[dict]:
    """Slot manifest annotated with per-run exists/source info for the UI."""
    vdir = visuals_dir(run_id)
    sources = {}
    sp = _sources_path(run_id)
    if sp.exists():
        sources = json.loads(sp.read_text(encoding="utf-8"))

    out = []
    for slot in VISUAL_SLOTS:
        fpath = vdir / slot["filename"]
        out.append({
            **slot,
            "exists": fpath.exists(),
            "source": sources.get(slot["slot"]),
        })
    return out


def write_visual_slot(run_id: str, slot: str, png_bytes: bytes, source: Literal["manual", "powerbi"]) -> Path:
    """Write PNG bytes into a named slot for this run. Called by both the
    manual-upload endpoint and the Power BI fetch path -- the only difference
    between them is where png_bytes comes from."""
    if slot not in _SLOT_BY_NAME:
        raise ValueError(f"Unknown visual slot: {slot!r}. Known slots: {list(_SLOT_BY_NAME)}")

    vdir = visuals_dir(run_id)
    vdir.mkdir(parents=True, exist_ok=True)
    filename = _SLOT_BY_NAME[slot]["filename"]
    out_path = vdir / filename
    out_path.write_bytes(png_bytes)

    sp = _sources_path(run_id)
    sources = json.loads(sp.read_text(encoding="utf-8")) if sp.exists() else {}
    sources[slot] = {"source": source, "written_at": datetime.now(timezone.utc).isoformat()}
    sp.write_text(json.dumps(sources, indent=2), encoding="utf-8")

    log.info(f"Visual slot '{slot}' written from {source} -> {out_path}")
    return out_path
