"""analysis_engine/sections/part_11.py — Part 11: Credit Life Module.

Non-loan-payoff benefits bundled with VisionFund's Enhanced Credit Life
product (help with medical costs, weather-affected income, damaged property,
or "no other benefits") and how much clients value those benefits beyond the
base loan-payoff cover -- distinct from the claims-payout benefits covered
elsewhere in the report. Genuinely new: q_credit_other_benefits and
q_credit_additional_value are mapped in data_loader/column_mapping.csv (cols
92-98) but had no section calculator anywhere before this -- confirmed via a
full-codebase search (see project_region_scoping memory), not a module that
was silently gated wrong.

Base is Enhanced Credit Life clients only (is_credit_life == True), n=285 on
the real 2026 dataset -- Africa-only; Vietnam and LARCO have no Credit Life
product at all (LARCO's insurance_type is 100% Health; see
data_loader_larco/column_mapping.csv). Only run for the "africa" report
scope (see run_analysis.py's build_sections()) -- a LACRO-scoped run would
have zero credit_life clients and every metric below would come back
not_applicable.
"""
import logging

from analysis_engine.stats import ranked_options, share_selecting

log = logging.getLogger("analysis_engine.sections.part_11")

COL_OTHER_BENEFITS = "q_credit_other_benefits"
COL_ADDITIONAL_VALUE = "q_credit_additional_value"

# Children of q_credit_other_benefits excluding option 'd' ("No other
# benefits are included") -- mirrors part_9.py's _SERVICE_CHILDREN pattern.
_BENEFIT_CHILDREN = [
    "q_credit_other_benefits__a",
    "q_credit_other_benefits__b",
    "q_credit_other_benefits__c",
    "q_credit_other_benefits__e",
]

# code_single_select() only strips a leading "x. " prefix -- these are the
# real option TEXT observed in the 2026 data (verified directly against
# runs/*/survey_clean.parquet, not assumed from the raw KoBo option list --
# "Somewhat not valuable" is a genuine 6th value present in the data but
# absent from data_loader/value_coding_map.yaml's q_credit_additional_value
# block, a separate pre-existing data-quality gap this section works around
# by matching on the real observed strings rather than the documented ones).
_AWARE_VALUES = [
    "Very valuable", "Somewhat valuable", "Neither valuable nor not valuable",
    "Somewhat not valuable", "Not valuable at all",
]
_UNAWARE_VALUE = "I am not aware of the additional benefits"
_VALUABLE_VALUES = ["Very valuable", "Somewhat valuable"]


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


def calculate(ds, segment_masks: dict) -> dict:
    """Part 11: Credit Life Module.

    other_benefits_used: which non-loan-payoff benefits credit-life clients
    report having, base = all credit-life clients (most report at least one
    real benefit; very few select "No other benefits are included").

    additional_value: base = credit-life clients who are AWARE of these
    benefits (excludes "I am not aware of the additional benefits" -- that
    response answers a different question, awareness, not value). Reports
    the aware-vs-unaware split first, then the valuable share among only the
    aware subgroup -- same "state the subgroup count before any percentage"
    discipline as part_9.py's services_helped.
    """
    df = ds.credit_life
    log.info(f"Part 11: calculating (n_base={len(df)})")

    if COL_OTHER_BENEFITS not in df.columns:
        log.warning(f"Part 11: column '{COL_OTHER_BENEFITS}' missing — section not applicable to this dataset")
        other_benefits_used = {
            "base": "credit_life_clients", "n_base": len(df),
            "headline": _missing_col(COL_OTHER_BENEFITS),
        }
    else:
        other_benefits_used = {
            "base": "credit_life_clients",
            "n_base": len(df),
            "headline": ranked_options(df[COL_OTHER_BENEFITS]),
        }

    if COL_ADDITIONAL_VALUE not in df.columns:
        log.warning(f"Part 11: column '{COL_ADDITIONAL_VALUE}' missing — section not applicable to this dataset")
        additional_value = {
            "base": "credit_life_clients", "n_base": len(df),
            "awareness": _missing_col(COL_ADDITIONAL_VALUE),
            "valuable_share": _missing_col(COL_ADDITIONAL_VALUE),
        }
    else:
        col = df[COL_ADDITIONAL_VALUE]
        awareness = share_selecting(col, values=_AWARE_VALUES)
        aware_mask = col.isin(_AWARE_VALUES)
        aware_df = df[aware_mask]
        additional_value = {
            "base": "credit_life_clients",
            "n_base": len(df),
            "awareness": awareness,
            "valuable_share": {
                "base": "aware_of_additional_benefits",
                "n_base": int(aware_mask.sum()),
                "result": share_selecting(aware_df[COL_ADDITIONAL_VALUE], values=_VALUABLE_VALUES),
            },
        }

    return {
        "base": "credit_life_clients",
        "n_base": len(df),
        "other_benefits_used": other_benefits_used,
        "additional_value": additional_value,
    }
