"""analysis_engine/sections/part_10.py — Part 10: Trend Comparison (LARCO).

LARCO's second wave adds a wave-over-wave trend section for 5 named
indicators (first-time access to insurance, access to alternatives, child
wellbeing improvement, client satisfaction, product understanding). Only run
for a LACRO-scoped report (see run_analysis.py's build_sections()).

Design: every run of this section computes and stores a self-contained
"current" snapshot of all 5 indicators (independent of Parts 1-8's own JSON
structure, which may change shape over time). When a prior_run_id is given,
it reads *that run's own part_10.current snapshot* -- not the prior run's
Part 1/3/4/6 output -- so the comparison chain is self-referential: wave 3
compares against wave 2's part_10.current, wave 2 against wave 1's, and so
on, with no dependency on any other section's JSON paths staying stable.

This also means every LARCO run always produces a usable "current" snapshot
for some future wave to compare against, even when *this* run has no prior
itself (a first-wave LARCO run, or a run started without --prior-run-id) --
the comparison block is simply omitted, not treated as a failure.

COMPARABILITY (2025 vs 2026, added when the 2026 wave moved LARCO onto the
unified schema -- see project_region_scoping memory's Requirement 5): the
survey instrument changed between waves for 3 of the 5 indicators (a
different option set for access_to_alternatives, a different scale for
child_wellbeing, and product_understanding split from one combined question
into two separate ones). Only first_time_access and client_satisfaction_nps
are genuinely comparable -- implemented as DATA (the _COMPARABLE table
below), not a prompt instruction, so a non-comparable indicator's prior-wave
value is structurally never computed or exposed to the writer at all.

SAMPLE COMPOSITION (also Requirement 5): Dominican Republic is new in the
2026 wave and has no 2025-wave data at all (data_loader_larco/
column_mapping.csv's 2025 export only covers Ecuador/Mexico/Guatemala/
Honduras/Bolivia). Including DR in a wave-over-wave delta would inflate the
apparent movement, since DR's first 2026 responses have no counterpart to
move "from". Only the two comparable indicators' DELTA/significance test
narrow to the five common countries -- current_full_scope (the headline
figure shown everywhere else in the report, and every non-comparable
indicator) always covers all six LACRO countries including DR.
"""
import json
import logging
from pathlib import Path

import pandas as pd

from analysis_engine.stats import nps_score, share_selecting, share_true, significance_test

log = logging.getLogger("analysis_engine.sections.part_10")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "runs"

COL_PRIOR_ACCESS = "q_prior_access"
COL_ALTERNATIVE_ACCESS = "q_alternative_access"
COL_CHILD_WELLBEING = "q_child_wellbeing"
COL_NPS_SCORE = "q_nps_score"
COL_PRODUCT_UNDERSTANDING = "q_product_understanding_combined"
COL_COUNTRY = "country"

_ALTERNATIVE_ACCESS_DIFFICULT = ["Very difficult", "Slightly difficult"]
# Judgment call, pending survey-team confirmation (see
# data_loader_larco/column_mapping.csv's notes on raw col 33): "good
# understanding" is defined as the single most positive option only, not a
# top-2-box -- the remaining 5 options don't have an unambiguous ordering
# agreed with the survey team yet, so a top-2-box would be arbitrary.
_PRODUCT_UNDERSTANDING_GOOD = ["I know everything"]

_INDICATORS = [
    # (key, label, requires_child_wellbeing_base)
    ("first_time_access", "First-Time Access to Insurance"),
    ("access_to_alternatives", "Access to Alternatives (difficult)"),
    ("child_wellbeing_improvement", "Child Wellbeing Improvement"),
    ("client_satisfaction_nps", "Client Satisfaction (NPS)"),
    ("product_understanding", "Product Understanding"),
]

# Verified against the actual 2025/2026 instruments (see module docstring).
# The reason each non-comparable indicator changed is carried alongside the
# flag, since the writer must state it in one sentence, not just omit the
# comparison silently.
_COMPARABLE = {
    "first_time_access": True,
    "access_to_alternatives": False,
    "child_wellbeing_improvement": False,
    "client_satisfaction_nps": True,
    "product_understanding": False,
}
_INCOMPARABILITY_REASON = {
    "access_to_alternatives": (
        "the 2025 instrument offered 4 forced-choice options; 2026 adds a neutral "
        "midpoint and \"I don't know\" (selected by 17.7% in 2026), which the 2025 "
        "wave could not select at all"
    ),
    "child_wellbeing_improvement": (
        "the 2025 instrument used a 5-point scale; 2026 uses a binary yes/no question"
    ),
    "product_understanding": (
        "the 2025 instrument used one combined 6-option question; 2026 splits it into "
        "two separate 4-point questions"
    ),
}

# The five LACRO countries present in BOTH the 2025 (data_loader_larco/) and
# 2026 waves. Dominican Republic is 2026-only (new client base, no 2025
# counterpart) -- see module docstring. Restricted to trend-comparison
# ARITHMETIC only (the delta/significance test for the two comparable
# indicators); current_full_scope always covers all six countries.
COMMON_LACRO_COUNTRIES = ["Bolivia", "Ecuador", "Guatemala", "Honduras", "Mexico"]
NEW_COUNTRY_2026 = "Dominican Republic"

# Definition fingerprint per indicator (column/rule/base) -- stored alongside
# every wave's snapshot and diffed wave-over-wave in _compare_indicator(), so
# a definition change between waves (a different column, a different top-box
# rule, a different population base -- e.g. this codebase's own logic
# changing, or the underlying survey question being reworded) surfaces as an
# explicit flagged mismatch instead of a silent, possibly apples-to-oranges
# comparison. A prior wave generated before this fingerprint existed has no
# "definition" key at all, which _compare_indicator() treats as "unknown",
# not "mismatch" -- there's no false positive against older runs.
_INDICATOR_DEFINITIONS = {
    "first_time_access": {
        "column": "q_prior_access", "rule": "share_true(NOT prior_access)",
        "base": "all_respondents",
    },
    "access_to_alternatives": {
        "column": "q_alternative_access",
        "rule": f"share_selecting(values={_ALTERNATIVE_ACCESS_DIFFICULT!r})",
        "base": "all_respondents",
    },
    "child_wellbeing_improvement": {
        "column": "q_child_wellbeing", "rule": "share_selecting(values=['Yes'])",
        "base": "child_wellbeing_base",
    },
    "client_satisfaction_nps": {
        "column": "q_nps_score", "rule": "nps_score: (promoters - detractors) / n_valid * 100",
        "base": "all_respondents",
    },
    "product_understanding": {
        "column": "q_product_understanding_combined",
        "rule": f"share_selecting(values={_PRODUCT_UNDERSTANDING_GOOD!r})",
        "base": "all_respondents",
    },
}


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


def _current_snapshot(df: pd.DataFrame, cwb_base: pd.DataFrame) -> dict:
    """Compute all 5 indicators over an EXPLICIT population, rather than
    inheriting whatever scope ds/ds.df happens to represent -- this is what
    lets calculate() below compute the same 5 indicators twice, once on the
    full report scope (the headline figures shown everywhere) and once on
    just the 5 countries common to both waves (used only for the two
    comparable indicators' delta/significance test), from the same code
    path instead of two hand-duplicated ones.
    """
    snapshot = {}

    if COL_PRIOR_ACCESS not in df.columns:
        snapshot["first_time_access"] = _missing_col(COL_PRIOR_ACCESS)
    else:
        snapshot["first_time_access"] = share_true(~df[COL_PRIOR_ACCESS])

    if COL_ALTERNATIVE_ACCESS not in df.columns:
        snapshot["access_to_alternatives"] = _missing_col(COL_ALTERNATIVE_ACCESS)
    else:
        snapshot["access_to_alternatives"] = share_selecting(
            df[COL_ALTERNATIVE_ACCESS], values=_ALTERNATIVE_ACCESS_DIFFICULT
        )

    if COL_CHILD_WELLBEING not in cwb_base.columns:
        snapshot["child_wellbeing_improvement"] = _missing_col(COL_CHILD_WELLBEING)
    else:
        snapshot["child_wellbeing_improvement"] = share_selecting(
            cwb_base[COL_CHILD_WELLBEING], values=["Yes"]
        )

    if COL_NPS_SCORE not in df.columns:
        snapshot["client_satisfaction_nps"] = _missing_col(COL_NPS_SCORE)
    else:
        snapshot["client_satisfaction_nps"] = nps_score(df)

    if COL_PRODUCT_UNDERSTANDING not in df.columns:
        snapshot["product_understanding"] = _missing_col(COL_PRODUCT_UNDERSTANDING)
    else:
        snapshot["product_understanding"] = share_selecting(
            df[COL_PRODUCT_UNDERSTANDING], values=_PRODUCT_UNDERSTANDING_GOOD
        )

    # Attach each indicator's definition fingerprint uniformly (even when the
    # column was missing -- that's still useful to know what WOULD have been
    # computed) rather than repeating it in each of the 5 branches above.
    for key in snapshot:
        snapshot[key]["definition"] = _INDICATOR_DEFINITIONS[key]

    return snapshot


def _filter_to_common_countries(df: pd.DataFrame) -> pd.DataFrame:
    if COL_COUNTRY not in df.columns:
        return df
    return df[df[COL_COUNTRY].isin(COMMON_LACRO_COUNTRIES)]


def _load_prior_snapshot(prior_run_id: "str | None", runs_dir: Path) -> "dict | None":
    if not prior_run_id:
        return None
    prior_path = runs_dir / prior_run_id / "analysis_results.json"
    if not prior_path.exists():
        log.warning(f"Part 10: prior_run_id={prior_run_id!r} has no analysis_results.json at {prior_path}")
        return None
    try:
        with open(prior_path, encoding="utf-8") as f:
            prior_results = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        log.warning(f"Part 10: could not read prior run {prior_run_id!r}: {exc}")
        return None

    prior_part_10 = (prior_results.get("parts") or {}).get("part_10")
    if not prior_part_10 or "current" not in prior_part_10:
        log.warning(
            f"Part 10: prior_run_id={prior_run_id!r} has no part_10.current snapshot "
            "(it was likely run before trend comparison existed, or wasn't a LARCO run)"
        )
        return None
    return prior_part_10["current"]


def _compare_indicator(key: str, label: str, current_full: dict, current_common: dict,
                        prior: "dict | None", comparable: bool) -> dict:
    row = {
        "label": label,
        "comparable": comparable,
        "current_full_scope": current_full,
    }

    if not comparable:
        # No comparison attempted at all, on either base -- a non-comparable
        # indicator gets a fresh-baseline snapshot only (Requirement 5:
        # never pass a 2025 figure for these, so the writer has no prior
        # number available to misuse). current_common_scope/prior/delta
        # stay None/absent rather than a misleading zero or suppressed
        # marker -- there is nothing to suppress, the comparison was never
        # attempted by design.
        row["incomparability_reason"] = _INCOMPARABILITY_REASON.get(key)
        row["current_common_scope"] = None
        row["prior"] = None
        row["delta"] = None
        row["delta_unit"] = None
        row["significance"] = None
        row["definition_match"] = None
        return row

    row["current_common_scope"] = current_common
    prior = prior or _missing_col(_INDICATOR_DEFINITIONS[key]["column"])
    row["prior"] = prior

    # Definition-match check: None (unknown) when either side lacks a
    # fingerprint (e.g. prior wave predates this feature) -- never treated as
    # a mismatch just because it can't be verified. False only when both
    # sides HAVE a fingerprint and they genuinely differ.
    current_def = current_common.get("definition")
    prior_def = prior.get("definition")
    if current_def is not None and prior_def is not None:
        row["definition_match"] = (current_def == prior_def)
    else:
        row["definition_match"] = None

    if key == "client_satisfaction_nps":
        # NPS is a -100..+100 index, not a proportion -- no two-proportion
        # z-test applies (and the prior run's underlying 0-10 scores aren't
        # available from its JSON output to run a Mann-Whitney U test the
        # way nps_scorecard_row() does for same-run segment comparisons).
        # Report the raw point delta only, explicitly unlabelled as tested.
        delta = None
        if current_common.get("value") is not None and prior.get("value") is not None:
            delta = current_common["value"] - prior["value"]
        row["delta"] = delta
        row["delta_unit"] = "NPS points"
        row["significance"] = {
            "p_value": None, "significant": False,
            "test": "not computed -- NPS is not a proportion, and the prior wave's "
                    "individual respondent-level scores were never retained, only its "
                    "aggregate value.",
        }
        return row

    if current_common.get("value") is None or prior.get("value") is None:
        row["delta"] = None
        row["significance"] = None
        return row

    row["delta"] = current_common["value"] - prior["value"]
    row["delta_unit"] = "percentage points"
    current_n_success = round(current_common["value"] * current_common["n_valid"])
    prior_n_success = round(prior["value"] * prior["n_valid"])
    row["significance"] = significance_test(
        current_n_success, current_common["n_valid"], prior_n_success, prior["n_valid"],
    )
    return row


def calculate(ds, segment_masks: dict, prior_run_id: "str | None" = None,
              runs_dir: "Path | None" = None) -> dict:
    """Part 10: Trend Comparison.

    segment_masks is accepted for signature-compatibility with every other
    section calculator (see run_analysis.py's SECTIONS loop) but unused --
    the 5 named trend indicators are headline-only, not disaggregated by
    segment, matching how the manager's email described this section.
    """
    log.info(f"Part 10: calculating current-wave snapshot (n_total={len(ds.df)})")
    current_full = _current_snapshot(ds.df, ds.child_wellbeing_base)

    # Common-country snapshot -- only meaningfully used for the 2 comparable
    # indicators (see _compare_indicator()), but computed uniformly for all
    # 5 here since it's the same cheap call either way.
    common_df = _filter_to_common_countries(ds.df)
    common_cwb_base = _filter_to_common_countries(ds.child_wellbeing_base)
    current_common = _current_snapshot(common_df, common_cwb_base)

    n_total = len(ds.df)
    n_new_country = int((ds.df[COL_COUNTRY] == NEW_COUNTRY_2026).sum()) if COL_COUNTRY in ds.df.columns else 0
    sample_composition = {
        "common_countries": COMMON_LACRO_COUNTRIES,
        "new_country": NEW_COUNTRY_2026,
        "n_new_country": n_new_country,
        "n_total": n_total,
        "new_country_share": (n_new_country / n_total) if n_total > 0 else None,
    }

    prior = _load_prior_snapshot(prior_run_id, runs_dir or RUNS_DIR)
    comparison = None
    if prior is not None:
        comparison = {
            key: _compare_indicator(
                key, label, current_full[key], current_common[key],
                prior.get(key), comparable=_COMPARABLE[key],
            )
            for key, label in _INDICATORS
        }

    return {
        "current": current_full,
        "sample_composition": sample_composition,
        "prior_run_id": prior_run_id,
        "prior_available": prior is not None,
        "comparison": comparison,
    }
