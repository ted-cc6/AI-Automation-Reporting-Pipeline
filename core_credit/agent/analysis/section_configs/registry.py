"""All section configs in one lookup, keyed by section_id -- what graph/run_graph.py reads
to know which sections it can build.

Status as of this build: all four registered sections are validated=True, each proven against
the real, full dataset (business_household_impact and financial_access from early in the
project; client_protection and agency via graph/run_graph.py real runs, thread_ids "real-run"
and "agency-real-run").

Deliberately NOT in this registry, and why -- these are scope decisions about this config
system's own abstraction, not gaps still to fill:
  - poverty_likelihood: doesn't fit the top-box MetricConfig pattern at all -- it's built from
    ppi_module + benchmark_module.build_national_comparison directly, a genuinely different
    computation path, not a config-driven gap. Built as driver/build_poverty_likelihood.py.
  - client_satisfaction: NPS isn't a top-box MetricResult (see schemas.client_satisfaction.NPSResult)
    -- needs its own node type before it fits this abstraction. Built as driver/build_client_satisfaction.py.
  - client_profile: mostly means and multi-category splits (age, household size, education),
    not top-box shares -- doesn't fit this abstraction either. Built as driver/build_client_profile.py.
  - child_wellbeing, resilience: need ranked multi-select support (metrics_engine.engine.multiselect_distribution,
    since built) for several subsections each, which this config system still doesn't have wired
    in. Both are fully built as bespoke drivers instead (driver/build_child_wellbeing.py,
    driver/build_resilience.py) -- including child_wellbeing's 4.2 caregiver-vs-other table,
    which turned out NOT to need the cross-cutting synthesis step after all: every row's mask is
    re-derived straight from the CSV using box definitions imported from the relevant
    SectionConfig (or driver, for the two rows outside section_configs), not read from another
    section's computed output. (An earlier version of this docstring claimed 4.2 needed the
    synthesis step to exist first -- that was wrong; corrected once actually built.)

Cross-cutting sections (Executive Summary, Gender Scorecard, Client Voices) were never going to
be config-per-section -- they read across every section above. All three are now built in
agent/analysis/synthesis/, which also needed all nine theme sections' real output to exist
first (Executive Summary reads every one of them).
"""

from __future__ import annotations

from .sections.agency import AGENCY_CONFIG
from .sections.business_household_impact import BUSINESS_HOUSEHOLD_IMPACT_CONFIG
from .sections.client_protection import CLIENT_PROTECTION_CONFIG
from .sections.financial_access import FINANCIAL_ACCESS_CONFIG

SECTION_CONFIGS = {
    "business_household_impact": BUSINESS_HOUSEHOLD_IMPACT_CONFIG,
    "financial_access": FINANCIAL_ACCESS_CONFIG,
    "client_protection": CLIENT_PROTECTION_CONFIG,
    "agency": AGENCY_CONFIG,
}
