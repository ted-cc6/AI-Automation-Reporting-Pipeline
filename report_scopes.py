"""report_scopes.py

Named report scopes -- which Region(s) a report run's statistics are
computed over. Distinct from data_loader_screening.py's dataset_schema
(which selects the column-mapping/instrument used to PARSE the raw CSV,
e.g. "africa_vietnam" vs "larco") -- report_scope selects which
ALREADY-PARSED rows a report's numbers cover, on the SAME parsed schema.
The two axes are orthogonal: every current report_scope runs on
dataset_schema="africa_vietnam" data, since that's the only schema the
2026 unified export uses (see project_larco_2026_pivot memory).

Region values are the raw CSV's own Region column content, confirmed
directly against the real 2026 export: "AFRICA", "ASIA", "LACRO" (verified
uppercase, including "LACRO" -- the correct VisionFund regional acronym,
used here as the region VALUE regardless of this codebase's own internal
"LARCO" naming for unrelated symbols/paths -- see project_larco_2026_pivot
memory's naming-decision note: internal code keeps "LARCO", user-facing
strings use "LACRO").

Add a new scope by adding an entry here; no other code should need to
change (data_loader_screening.py's region filter, generation/assembler.py's
report title, and the module manifest in run_analysis.py's build_sections()
all read from this module).
"""

REPORT_SCOPES = {
    "lacro": {
        "label": "LACRO (Latin America and Caribbean Regional Office)",
        "regions": ["LACRO"],
    },
    "africa": {
        "label": "Africa and Asia",
        "regions": ["AFRICA", "ASIA"],
        # Vietnam (ASIA) is bundled into this scope rather than split out on
        # its own -- 154 clients is too small for a standalone report, and
        # this matches the report this bundle has always effectively been
        # (the pre-region-scope "Africa" report already included Vietnam).
        # Split it out later by adding a new "asia" scope entry with
        # regions=["ASIA"] and removing "ASIA" from this one -- no code
        # changes needed elsewhere.
    },
}

# Scopes generated when no --report-scope is given at the CLI/API level.
DEFAULT_REPORT_SCOPES = ["lacro", "africa"]

# Compact acronym form for report titles ("LACRO Regional Portfolio" reads
# better than repeating the full parenthetical expansion in a title). The
# single source of truth for the region's user-facing name is this file --
# REPORT_SCOPES["lacro"]["label"] for the full form, this constant for the
# short form. Every place that renders "LACRO" in a title/subtitle/prose
# must derive from one of these two, not a separately hardcoded string --
# see generation/writer.py's _report_title() and generation/assembler.py's
# assemble(), both previously hardcoded "LARCO" (the codebase's internal
# naming convention, see the module docstring above) directly into
# user-facing text, bypassing this file entirely.
LACRO_SHORT_LABEL = "LACRO"


def get_scope(name: str) -> dict:
    if name not in REPORT_SCOPES:
        raise ValueError(f"Unknown report_scope {name!r} -- expected one of {sorted(REPORT_SCOPES)}")
    return REPORT_SCOPES[name]
