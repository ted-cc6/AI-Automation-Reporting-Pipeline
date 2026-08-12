"""analysis_engine/sections/part_10.py — Part 10: Trend Comparison (LARCO).

LARCO's second wave adds a wave-over-wave trend section for 5 named
indicators (first-time access to insurance, access to alternatives, child
wellbeing improvement, client satisfaction, product understanding). Only run
for LARCO (see run_analysis.py's SECTIONS gating).

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
"""
import json
import logging
from pathlib import Path

from analysis_engine.stats import nps_score, share_selecting, share_true, significance_test

log = logging.getLogger("analysis_engine.sections.part_10")

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = PROJECT_ROOT / "runs"

COL_PRIOR_ACCESS = "q_prior_access"
COL_ALTERNATIVE_ACCESS = "q_alternative_access"
COL_CHILD_WELLBEING = "q_child_wellbeing"
COL_NPS_SCORE = "q_nps_score"
COL_PRODUCT_UNDERSTANDING = "q_product_understanding_combined"

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


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}"}


def _current_snapshot(ds) -> dict:
    snapshot = {}

    if COL_PRIOR_ACCESS not in ds.df.columns:
        snapshot["first_time_access"] = _missing_col(COL_PRIOR_ACCESS)
    else:
        snapshot["first_time_access"] = share_true(~ds.df[COL_PRIOR_ACCESS])

    if COL_ALTERNATIVE_ACCESS not in ds.df.columns:
        snapshot["access_to_alternatives"] = _missing_col(COL_ALTERNATIVE_ACCESS)
    else:
        snapshot["access_to_alternatives"] = share_selecting(
            ds.df[COL_ALTERNATIVE_ACCESS], values=_ALTERNATIVE_ACCESS_DIFFICULT
        )

    if COL_CHILD_WELLBEING not in ds.child_wellbeing_base.columns:
        snapshot["child_wellbeing_improvement"] = _missing_col(COL_CHILD_WELLBEING)
    else:
        snapshot["child_wellbeing_improvement"] = share_selecting(
            ds.child_wellbeing_base[COL_CHILD_WELLBEING], values=["Yes"]
        )

    if COL_NPS_SCORE not in ds.df.columns:
        snapshot["client_satisfaction_nps"] = _missing_col(COL_NPS_SCORE)
    else:
        snapshot["client_satisfaction_nps"] = nps_score(ds.df)

    if COL_PRODUCT_UNDERSTANDING not in ds.df.columns:
        snapshot["product_understanding"] = _missing_col(COL_PRODUCT_UNDERSTANDING)
    else:
        snapshot["product_understanding"] = share_selecting(
            ds.df[COL_PRODUCT_UNDERSTANDING], values=_PRODUCT_UNDERSTANDING_GOOD
        )

    return snapshot


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


def _compare_indicator(key: str, label: str, current: dict, prior: dict) -> dict:
    row = {"label": label, "current": current, "prior": prior}

    if key == "client_satisfaction_nps":
        # NPS is a -100..+100 index, not a proportion -- no two-proportion
        # z-test applies (and the prior run's underlying 0-10 scores aren't
        # available from its JSON output to run a Mann-Whitney U test the
        # way nps_scorecard_row() does for same-run segment comparisons).
        # Report the raw point delta only, explicitly unlabelled as tested.
        delta = None
        if current.get("value") is not None and prior.get("value") is not None:
            delta = current["value"] - prior["value"]
        row["delta"] = delta
        row["delta_unit"] = "NPS points"
        row["significance"] = {
            "p_value": None, "significant": False,
            "test": "not computed -- NPS is not a proportion and the prior wave's "
                    "respondent-level scores aren't available from its stored JSON",
        }
        return row

    if current.get("value") is None or prior.get("value") is None:
        row["delta"] = None
        row["significance"] = None
        return row

    row["delta"] = current["value"] - prior["value"]
    row["delta_unit"] = "percentage points"
    current_n_success = round(current["value"] * current["n_valid"])
    prior_n_success = round(prior["value"] * prior["n_valid"])
    row["significance"] = significance_test(
        current_n_success, current["n_valid"], prior_n_success, prior["n_valid"],
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
    current = _current_snapshot(ds)

    prior = _load_prior_snapshot(prior_run_id, runs_dir or RUNS_DIR)
    comparison = None
    if prior is not None:
        comparison = {
            key: _compare_indicator(key, label, current[key], prior.get(key, _missing_col(key)))
            for key, label in _INDICATORS
        }

    return {
        "current": current,
        "prior_run_id": prior_run_id,
        "prior_available": prior is not None,
        "comparison": comparison,
    }
