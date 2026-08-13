"""analysis_engine/sections/part_12.py — Part 12: Crop Module.

Weather-shock recovery speed and farming-approach change since having crop
insurance -- distinct from the claims-payout benefits covered elsewhere in
the report. Genuinely new: q_crop_recovery_speed and q_crop_farming_change
are mapped in data_loader/column_mapping.csv (cols 89-90) but had no section
calculator anywhere before this -- confirmed via a full-codebase search (see
project_region_scoping memory), not a module that was silently gated wrong.

Base is crop-insurance clients only (is_crop == True), n=147 on the real
2026 dataset -- 100% Vietnam (crop insurance is a Vietnam-only product; see
project_analysis_engine memory's "climate shock: is_crop == True (Vietnam
only)"). Africa and LARCO have no crop-insurance product at all. Every
metric here MUST be labelled "Vietnam crop clients only" wherever it
appears in the generated report (see report_spec.yaml's population: field)
-- the same rule renewal_intent/worth_premium already follow for the same
reason. Only run for the "africa" report scope (see run_analysis.py's
build_sections()) -- a LACRO-scoped run would have zero crop clients and
every metric below would come back not_applicable.
"""
import logging

from analysis_engine.stats import share_selecting

log = logging.getLogger("analysis_engine.sections.part_12")

COL_RECOVERY_SPEED = "q_crop_recovery_speed"
COL_FARMING_CHANGE = "q_crop_farming_change"

# code_single_select() only strips a leading "x. " prefix -- these are the
# real option TEXT observed in the 2026 data (verified directly against
# runs/*/survey_clean.parquet). q_crop_recovery_speed: 3 options (fastest
# to slowest). q_crop_farming_change: 4 options observed in the real data
# (data_loader/value_coding_map.yaml notes "a-d, all options present").
_RECOVERY_FAST_VALUES = ["Immediately or within 1 month", "After 1–3 months"]
_FARMING_IMPROVED_VALUES = ["Very much improved", "Slightly improved"]

_VIETNAM_CROP_ONLY_POPULATION = (
    "Vietnam's crop-insurance clients only -- crop insurance is not sold in any "
    "other country in this report's scope"
)


def _missing_col(col: str) -> dict:
    return {"value": None, "n_valid": 0, "n_total": 0, "suppressed": True,
            "suppress_reason": f"column missing: {col}", "not_applicable": True}


def calculate(ds, segment_masks: dict) -> dict:
    """Part 12: Crop Module.

    recovery_speed: share who recovered and continued earning income within
    3 months of the weather shock (fastest two of three options), base =
    all crop clients.

    farming_change: share whose farming approach improved (choice of crops,
    input investment, or planting practices) since having crop insurance
    (top two of four options), base = all crop clients.
    """
    df = ds.crop
    log.info(f"Part 12: calculating (n_base={len(df)})")

    if COL_RECOVERY_SPEED not in df.columns:
        log.warning(f"Part 12: column '{COL_RECOVERY_SPEED}' missing — section not applicable to this dataset")
        recovery_speed = _missing_col(COL_RECOVERY_SPEED)
    else:
        recovery_speed = share_selecting(df[COL_RECOVERY_SPEED], values=_RECOVERY_FAST_VALUES)

    if COL_FARMING_CHANGE not in df.columns:
        log.warning(f"Part 12: column '{COL_FARMING_CHANGE}' missing — section not applicable to this dataset")
        farming_change = _missing_col(COL_FARMING_CHANGE)
    else:
        farming_change = share_selecting(df[COL_FARMING_CHANGE], values=_FARMING_IMPROVED_VALUES)

    return {
        "base": "crop_clients",
        "n_base": len(df),
        "population": _VIETNAM_CROP_ONLY_POPULATION,
        "recovery_speed": recovery_speed,
        "farming_change": farming_change,
    }
