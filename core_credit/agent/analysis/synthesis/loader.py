"""Loads a previously-built section's finished output back into its Pydantic schema.

This is the first place in the project that reads another section's FINISHED output rather
than recomputing from the raw CSV -- the cross-cutting synthesis stage (Client Voices, Gender
Scorecard, Executive Summary) needs exactly that.

CANONICAL_OUTPUTS is an explicit path per section_id, not "most recently modified file matching
this section_id" auto-discovery. That auto-discovery approach was tried and rejected: driver/
and graph/output/ both accumulate multiple runs per section (smoke tests, regression tests,
sampled dry runs), and by plain file-modified-time, the most recent business_household_impact
file on disk turned out to be a regression test run with `sample=40` -- its deterministic
metrics were still computed on the full dataset (compute_metric_node never respects `sample`,
only the qualitative pass does), so this particular case wasn't actually wrong, but a future
sampled run easily could be, and nothing about "most recent" distinguishes the two. Pointing at
one explicit, hand-verified file per section is the safe version of the same idea.

Update CANONICAL_OUTPUTS by hand whenever a section is re-run for real and should replace what
synthesis reads.
"""

from __future__ import annotations

import importlib
from pathlib import Path
from typing import Optional

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
DRIVER_OUTPUT = ANALYSIS_ROOT / "driver" / "output"
GRAPH_OUTPUT = ANALYSIS_ROOT / "graph" / "output"

SYNTHESIS_OUTPUT = ANALYSIS_ROOT / "synthesis" / "output"

# section_id -> (module, class_name) for parsing its saved JSON back into the right schema.
SCHEMA_CLASSES: dict[str, tuple] = {
    "client_profile": ("schemas.client_profile", "ClientProfileSection"),
    "financial_access": ("schemas.financial_access", "FinancialAccessSection"),
    "poverty_likelihood": ("schemas.poverty_likelihood", "PovertyLikelihoodSection"),
    "business_household_impact": ("schemas.business_household_impact", "BusinessHouseholdImpactSection"),
    "child_wellbeing": ("schemas.child_wellbeing", "ChildWellbeingSection"),
    "client_protection": ("schemas.client_protection", "ClientProtectionSection"),
    "agency": ("schemas.agency", "AgencySection"),
    "resilience": ("schemas.resilience", "ResilienceSection"),
    "client_satisfaction": ("schemas.client_satisfaction", "ClientSatisfactionSection"),
    "executive_summary": ("schemas.executive_summary", "ExecutiveSummarySection"),
    "gender_scorecard": ("schemas.gender_scorecard", "GenderScorecardSection"),
    "client_voices": ("schemas.client_voices", "ClientVoicesSection"),
}

# section_id -> the one hand-verified real run to treat as canonical.
CANONICAL_OUTPUTS: dict[str, Path] = {
    "client_profile": DRIVER_OUTPUT / "client_profile_20260805T205330Z.json",
    "financial_access": GRAPH_OUTPUT / "financial_access_fa-test.json",
    "poverty_likelihood": DRIVER_OUTPUT / "poverty_likelihood_20260805T204249Z.json",
    "business_household_impact": DRIVER_OUTPUT / "business_household_impact_20260805T161931Z.json",
    "child_wellbeing": DRIVER_OUTPUT / "child_wellbeing_20260805T213107Z.json",
    "resilience": DRIVER_OUTPUT / "resilience_20260805T212255Z.json",
    "client_satisfaction": DRIVER_OUTPUT / "client_satisfaction_20260805T211244Z.json",
    "client_protection": GRAPH_OUTPUT / "client_protection_protection-signals-v2.json",
    "agency": GRAPH_OUTPUT / "agency_agency-real-run.json",
    "executive_summary": SYNTHESIS_OUTPUT / "executive_summary_20260805T215941Z.json",
    "gender_scorecard": SYNTHESIS_OUTPUT / "gender_scorecard_20260805T214939Z.json",
    "client_voices": SYNTHESIS_OUTPUT / "client_voices_20260805T214459Z.json",
}


def _schema_class(section_id: str) -> type:
    module_name, class_name = SCHEMA_CLASSES[section_id]
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def canonical_output_path(section_id: str) -> Path:
    path = CANONICAL_OUTPUTS.get(section_id)
    if path is None:
        raise FileNotFoundError(
            f"No canonical real-run output registered for section_id={section_id!r} -- "
            "run it for real and add its path to CANONICAL_OUTPUTS in synthesis/loader.py."
        )
    if not path.exists():
        raise FileNotFoundError(f"Registered output for {section_id!r} no longer exists: {path}")
    return path


def load_section(section_id: str, path: Optional[Path] = None):
    """Loads a section's saved output, parsed back into its Pydantic schema. Defaults to the
    registered canonical run; pass `path` explicitly to load a specific file instead (e.g. right
    after producing a fresh one, before updating the registry).
    """
    schema_class = _schema_class(section_id)
    resolved = path if path is not None else canonical_output_path(section_id)
    return schema_class.model_validate_json(resolved.read_text(encoding="utf-8"))
