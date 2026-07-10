"""
analysis_engine/segments.py — single source of truth for all client segment definitions.

Every section calculator imports from here. No other file should define what a segment means.
"""
import logging

import pandas as pd

log = logging.getLogger("analysis_engine.segments")

# --- Column name constants ---
COL_SEX = "q_sex"
COL_CLAIM_SUBMITTED = "q_claim_submitted"
COL_PRIOR_ACCESS = "q_prior_access"
COL_CHILD_WELLBEING_DENOM = "flag_child_wellbeing_denominator"
COL_DISABILITY = "q_disability"

# Non-None children of q_bundled_services_used (option __f is "None", excluded)
COL_BUNDLED_CHILDREN = [
    "q_bundled_services_used__a",
    "q_bundled_services_used__b",
    "q_bundled_services_used__c",
    "q_bundled_services_used__d",
    "q_bundled_services_used__e",
    "q_bundled_services_used__g",
]


def _bundled_mask(df: pd.DataFrame) -> pd.Series:
    # OR across non-None children; missing columns silently skipped
    mask = pd.Series(False, index=df.index)
    for col in COL_BUNDLED_CHILDREN:
        if col in df.columns:
            mask |= df[col] == True  # noqa: E712
    return mask


# ---------------------------------------------------------------------------
# Segment registry
# ---------------------------------------------------------------------------
# Each entry with available=True must have:
#   required_columns: list of column names to pre-check before calling mask_fn
#   mask_fn: callable(df) -> pd.Series[bool]
#
# Adding a new segment: add one entry here. No other function needs to change.

SEGMENT_REGISTRY: dict[str, dict] = {
    "female": {
        "label": "Female",
        "description": "Female respondents",
        "required_columns": [COL_SEX],
        "available": True,
        "mask_fn": lambda df: df[COL_SEX] == "Female",
    },
    "male": {
        "label": "Male",
        "description": "Male respondents",
        "required_columns": [COL_SEX],
        "available": True,
        "mask_fn": lambda df: df[COL_SEX] == "Male",
    },
    "claimant": {
        "label": "Claimant",
        "description": "Submitted an insurance claim",
        "required_columns": [COL_CLAIM_SUBMITTED],
        "available": True,
        "mask_fn": lambda df: df[COL_CLAIM_SUBMITTED] == True,  # noqa: E712
    },
    "non_claimant": {
        "label": "Non-Claimant",
        "description": "Did not submit a claim (includes those with no insured event)",
        "required_columns": [COL_CLAIM_SUBMITTED],
        "available": True,
        "mask_fn": lambda df: df[COL_CLAIM_SUBMITTED] == False,  # noqa: E712
    },
    "first_time_access": {
        "label": "First-Time Access",
        "description": "No insurance before VisionFund",
        "required_columns": [COL_PRIOR_ACCESS],
        "available": True,
        "mask_fn": lambda df: df[COL_PRIOR_ACCESS] == False,  # noqa: E712
    },
    "caregiver": {
        "label": "Caregiver",
        "description": "Supports children (answered child wellbeing question — Yes or No)",
        "required_columns": [COL_CHILD_WELLBEING_DENOM],
        "available": True,
        "mask_fn": lambda df: df[COL_CHILD_WELLBEING_DENOM] == True,  # noqa: E712
    },
    "non_caregiver": {
        "label": "Non-Caregiver",
        "description": "Does not support children (answered 'Do not support any children', or left the child wellbeing question blank)",
        "required_columns": [COL_CHILD_WELLBEING_DENOM],
        "available": True,
        "mask_fn": lambda df: df[COL_CHILD_WELLBEING_DENOM] == False,  # noqa: E712
    },
    "pwd": {
        "label": "PWD",
        "description": "Person with disability in household",
        "required_columns": [COL_DISABILITY],
        "available": True,
        "mask_fn": lambda df: df[COL_DISABILITY] == "Yes",
    },
    "bundled_service_client": {
        "label": "Bundled Service Client",
        "description": "Used at least one non-None bundled service in past 12 months",
        # required_columns is empty: each child column is checked individually inside
        # mask_fn so that a partial set of columns still produces a valid (partial) mask.
        "required_columns": [],
        "available": True,
        "mask_fn": _bundled_mask,
    },
    "female_hh_head": {
        "label": "Female HH Head",
        "description": "Female-headed households",
        "required_columns": [],
        "available": False,
        "skip_reason": "Not applicable to insurance survey — household head status is only captured in the core credit survey",
        "mask_fn": None,
    },
    "climate_shock": {
        "label": "Climate Shock",
        "description": "Experienced a climate-related shock",
        "required_columns": [],
        "available": False,
        "skip_reason": "Vietnam-only segment — activated via country config when --country vietnam is used",
        "mask_fn": None,
    },
}


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _merge_overrides(overrides) -> dict[str, dict]:
    """Build a working copy of SEGMENT_REGISTRY with country overrides applied.

    Never mutates the module-level SEGMENT_REGISTRY.
    `overrides` is a dict[str, SegmentOverride] (from CountryConfig) or None.
    """
    effective = {k: dict(v) for k, v in SEGMENT_REGISTRY.items()}
    if not overrides:
        return effective
    for seg_name, override in overrides.items():
        if seg_name not in effective:
            log.warning(f"segment_overrides: unknown segment '{seg_name}' — ignoring")
            continue
        entry = effective[seg_name]
        entry["available"] = override.available
        if getattr(override, "label", None):
            entry["label"] = override.label
        if getattr(override, "skip_reason", None):
            entry["skip_reason"] = override.skip_reason
        if override.available:
            col = getattr(override, "column", None)
            if not col:
                log.warning(
                    f"segment_overrides: '{seg_name}' is available=True but has no column — skipping"
                )
                entry["available"] = False
                continue
            entry["required_columns"] = [col]
            # Default-argument capture avoids closure capture bug
            entry["mask_fn"] = lambda df, c=col: df[c] == True  # noqa: E712
    return effective


def _mask_from_entry(df: pd.DataFrame, seg_name: str, entry: dict) -> "pd.Series | None":
    """Compute a boolean mask from a registry entry dict.

    Caller is responsible for checking entry["available"] before calling.
    Returns None if a required column is absent or mask_fn is missing.
    """
    for col in entry.get("required_columns", []):
        if col not in df.columns:
            log.warning(
                f"Segment '{seg_name}': required column '{col}' missing from DataFrame — skipping"
            )
            return None
    mask_fn = entry.get("mask_fn")
    if mask_fn is None:
        log.warning(f"Segment '{seg_name}': no mask_fn defined — skipping")
        return None
    return mask_fn(df).fillna(False)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_segment_mask(df: pd.DataFrame, segment_name: str) -> "pd.Series | None":
    """Return a boolean Series (True = in segment) aligned to df.index, or None.

    Returns None — without raising — when the segment is unavailable or a
    required column is absent from df.  Raises KeyError for unknown names.
    """
    entry = SEGMENT_REGISTRY[segment_name]  # KeyError if segment unknown
    if not entry["available"]:
        return None
    return _mask_from_entry(df, segment_name, entry)


def get_all_segment_masks(df: pd.DataFrame, segment_overrides=None) -> dict[str, pd.Series]:
    """Return {segment_name: mask} for every available segment whose columns exist in df.

    `segment_overrides` is an optional dict[str, SegmentOverride] from a CountryConfig;
    it is merged into a local copy of SEGMENT_REGISTRY and never mutates the module-level dict.
    """
    effective = _merge_overrides(segment_overrides)
    n_active  = sum(1 for e in effective.values() if e.get("available", False))
    log.info(f"Computing segment masks: {n_active} active segment(s) in effective registry")
    result: dict[str, pd.Series] = {}
    for name, entry in effective.items():
        if not entry.get("available", False):
            continue
        mask = _mask_from_entry(df, name, entry)
        if mask is not None:
            result[name] = mask
    return result


def describe_segments(df: pd.DataFrame, segment_overrides=None) -> list[dict]:
    """Return one summary dict per registry entry, for logging/debugging.

    `segment_overrides` is an optional dict[str, SegmentOverride] from a CountryConfig.
    """
    effective = _merge_overrides(segment_overrides)
    n_total   = len(df)
    rows: list[dict] = []
    for name, entry in effective.items():
        if not entry.get("available", False):
            rows.append({
                "name":        name,
                "label":       entry["label"],
                "available":   False,
                "n":           None,
                "skip_reason": entry.get("skip_reason", ""),
            })
            continue
        mask = _mask_from_entry(df, name, entry)
        if mask is None:
            rows.append({
                "name":        name,
                "label":       entry["label"],
                "available":   True,
                "n":           None,
                "skip_reason": "Required column missing from DataFrame",
            })
        else:
            n = int(mask.sum())
            rows.append({
                "name":         name,
                "label":        entry["label"],
                "available":    True,
                "n":            n,
                "pct_of_total": round(n / n_total * 100, 1) if n_total > 0 else 0.0,
            })
    return rows
