"""analysis_engine/sections/part_2.py — Part 2: Claims Experience."""
import logging

import pandas as pd

from analysis_engine.stats import claims_funnel, ranked_options, SCOPE_SENTINEL

log = logging.getLogger("analysis_engine.sections.part_2")

# --- Column constants ---
COL_CLAIM_SUBMITTED              = "q_claim_submitted"
COL_CLAIM_CHALLENGES_EXPERIENCED = "q_claim_challenges_experienced"
COL_NO_CLAIM_REASON              = "q_no_claim_reason"
COL_CLAIM_CHALLENGES             = "q_claim_challenges"
COL_CLAIM_RESULT                 = "q_claim_result"
COL_PAYOUT_COST_COVERAGE         = "q_payout_cost_coverage"

# NOTE: q_claim_channel_preferred ("which channel do you prefer for submitting
# claims?") is asked of ALL respondents, not just claimants -- it lives in
# Part 1 (analysis_engine/sections/part_1.py) alongside the other client
# understanding/preference questions, not here.


def _dist(series: pd.Series) -> list:
    """Sorted frequency distribution for a single-select Categorical column."""
    valid = series[series.notna() & (series != SCOPE_SENTINEL)]
    n = len(valid)
    if n == 0:
        return []
    vc = valid.value_counts()
    return [{"value": str(v), "n": int(c), "pct": float(c / n)} for v, c in vc.items()]


def calculate(ds, segment_masks: dict) -> dict:
    """Part 2: Claims Experience (multiple sub-bases)."""
    log.info(f"Part 2: calculating all_respondents (n={len(ds.df)})")

    # 2.1 Claims funnel (structural — no disaggregation)
    funnel = claims_funnel(ds.df)

    # 2.2 No-claim reasons — base: insured event but did NOT submit a claim
    if COL_CLAIM_SUBMITTED in ds.insured_event_base.columns:
        leakage_base = ds.insured_event_base[
            ds.insured_event_base[COL_CLAIM_SUBMITTED] == False  # noqa: E712
        ]
    else:
        log.warning(f"Part 2: column '{COL_CLAIM_SUBMITTED}' missing — leakage base empty")
        leakage_base = ds.insured_event_base.iloc[:0]

    no_claim_dist = (
        _dist(leakage_base[COL_NO_CLAIM_REASON])
        if COL_NO_CLAIM_REASON in leakage_base.columns else []
    )

    # 2.3 Claim challenges — base: claimants who experienced challenges
    if COL_CLAIM_CHALLENGES_EXPERIENCED in ds.claimants.columns:
        challenges_base = ds.claimants[
            ds.claimants[COL_CLAIM_CHALLENGES_EXPERIENCED] == True  # noqa: E712
        ]
    else:
        log.warning(f"Part 2: column '{COL_CLAIM_CHALLENGES_EXPERIENCED}' missing — challenges base empty")
        challenges_base = ds.claimants.iloc[:0]

    if COL_CLAIM_CHALLENGES in challenges_base.columns:
        challenges_ranked = ranked_options(challenges_base[COL_CLAIM_CHALLENGES])
    else:
        log.warning(f"Part 2: column '{COL_CLAIM_CHALLENGES}' missing")
        challenges_ranked = {
            "value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {COL_CLAIM_CHALLENGES}", "ranked": [],
            "not_applicable": True,
        }

    # 2.5 Claim result — base: all claimants
    result_dist = (
        _dist(ds.claimants[COL_CLAIM_RESULT])
        if COL_CLAIM_RESULT in ds.claimants.columns else []
    )

    # 2.6 Payout cost coverage — base: paid claimants
    payout_dist = (
        _dist(ds.paid_claimants[COL_PAYOUT_COST_COVERAGE])
        if COL_PAYOUT_COST_COVERAGE in ds.paid_claimants.columns else []
    )

    return {
        "base": "all_respondents",
        "n_base": len(ds.df),
        "claims_funnel": funnel,
        "no_claim_reasons": {
            "base": "leakage_respondents",
            "n_base": len(leakage_base),
            "distribution": no_claim_dist,
        },
        "claim_challenges": {
            "base": "claimants_with_challenges",
            "n_base": len(challenges_base),
            "ranked": challenges_ranked,
        },
        "claim_result": {
            "base": "claimants",
            "n_base": len(ds.claimants),
            "distribution": result_dist,
        },
        "payout_cost_coverage": {
            "base": "paid_claimants",
            "n_base": len(ds.paid_claimants),
            "distribution": payout_dist,
        },
    }
