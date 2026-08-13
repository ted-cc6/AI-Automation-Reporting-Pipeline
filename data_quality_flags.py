"""data_quality_flags.py

Data quality flags -- footnote specific findings and exclude them from
headline claims and quote selection, WITHOUT dropping the underlying data.
Whether a flagged country's records are actually invalid is a decision for
a human reviewer, not a pipeline default (see Requirement 7(a) in
project_region_scoping memory) -- the pipeline's job is to make the flag
impossible to miss, not to act on it unilaterally.

Two sources of flags, both returned by get_flags():
  1. Hand-entered overrides in DATA_QUALITY_FLAGS below -- for a flag that
     needs a note or action an automated check can't phrase on its own
     (e.g. "escalated to the field team on 2026-08-20", or a flag for
     something that isn't duration/uuid-shaped at all).
  2. Auto-derived from data_loader_screening.py's find_duration_outliers()
     -- see auto_derive_duration_flags(). This is the actual point of this
     module: a flag whose only path into existence is someone remembering
     to hand-type a config entry will not exist next wave (Requirement
     7(b)). Only concentrated findings (see that function's docstring)
     auto-promote to a flag -- a spread-out fast-interview pattern across
     many enumerators is more likely a genuinely quick population/
     instrument than a data-quality problem, and shouldn't page anyone.

A flag's effect, applied by the generation layer (see generation/
orchestrator.py and qualitative/llm_call.py):
  - Stated explicitly in the "Data Notes" section of the generated report
    (see generation/assembler.py's _add_data_notes_subsection()).
  - The flagged country is excluded from top_findings/executive_summary
    headline evidence -- a prompt-level instruction to the synthesis call,
    since the underlying pooled arithmetic still legitimately includes the
    country's real respondents (per Requirement 7(a), figures are NOT
    adjusted or excluded).
  - The flagged country's records are excluded from the verbatim-quote
    candidate pool entirely -- no quote from a flagged country can be
    selected, unlike headline figures.
"""

# Hand-entered override flags, keyed by report_scope. Empty by default --
# every flag currently active on the real 2026 LACRO data (Bolivia) is
# auto-derived below, not hand-entered; add an entry here only for a flag
# an automated check can't produce on its own.
DATA_QUALITY_FLAGS: dict = {}

# Only a duration-outlier finding with enumerator concentration at or above
# this share auto-promotes to an actual report flag -- matches
# data_loader_screening.py's _DURATION_OUTLIER_ENUMERATOR_CONCENTRATION
# (find_duration_outliers() already filters on this; kept as its own
# constant here too since "which findings become a flag" is a decision
# this module owns, not the screening layer -- they're allowed to diverge
# if a future wave needs a different bar for one than the other).
_MIN_CONCENTRATION_FOR_AUTO_FLAG = 0.5


def auto_derive_duration_flags(duration_outlier_findings: list) -> list:
    """Convert data_loader_screening.find_duration_outliers() findings into
    report-facing data quality flags. Only concentrated findings promote --
    see module docstring."""
    flags = []
    for f in duration_outlier_findings:
        if f.get("top_enumerator_share_of_outliers", 0) < _MIN_CONCENTRATION_FOR_AUTO_FLAG:
            continue
        country = f["country"]
        flags.append({
            "id": f"{country.lower().replace(' ', '_')}_duration_outlier",
            "country": country,
            "note": (
                f"{f['n_outliers']} of {country}'s {f['n_total']} interviews completed in "
                f"under {f['threshold_minutes']:.1f} minutes, against this run's own median "
                f"of {f['scope_median_minutes']:.1f} minutes ({f['outlier_share']:.1%} of "
                f"{country}'s sample). {f['top_enumerator_share_of_outliers']:.1%} of those "
                f"fast interviews are attributable to a single enumerator "
                f"({f['top_enumerator']}). This is a data quality flag, not evidence the "
                f"records are invalid -- {country}'s data remains in every figure in this "
                "report; it is excluded only from headline claims and quoted verbatims "
                "pending human review."
            ),
            "source": "auto_derived",
        })
    return flags


def get_flags(report_scope: "str | None", duration_outlier_findings: "list | None" = None) -> list:
    """All active flags for this report_scope: hand-entered overrides plus
    whatever auto-derives from this run's own duration_outlier_findings
    (see data_loader_screening.find_duration_outliers(), threaded through
    via screening_summary.json)."""
    flags = list(DATA_QUALITY_FLAGS.get(report_scope, []))
    if duration_outlier_findings:
        flags.extend(auto_derive_duration_flags(duration_outlier_findings))
    return flags


def flagged_countries(flags: list) -> list:
    """Just the country names, for callers that only need the exclusion
    list (quote-candidate filtering, the synthesis prompt's do-not-cite
    instruction) and don't need each flag's own note text."""
    return sorted({f["country"] for f in flags if f.get("country")})
