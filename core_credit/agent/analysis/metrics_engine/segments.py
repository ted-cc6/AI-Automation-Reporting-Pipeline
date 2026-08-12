"""Derives the template's standard client segments from the analysis-ready CSV.

Column names and value sets here are grounded in
processed_data/2026Q2_20260803_163530_analysis_ready.csv -- they were
verified against the actual data, not guessed from the survey instrument
text alone. If a future quarter's cleaned export renames or reshapes any of
these columns, this is the one place that needs to change.

Every function here builds its result as a plain Python list and wraps it
with `_obj_series(...)` rather than pandas' `.map()` / `.where()` / `.apply()`.
That's deliberate, not a style preference: on the pandas version this
project runs (3.x), `.map()` and `.apply()` silently turn a returned `None`
into `float('nan')` when the output happens to infer a string dtype, which
breaks `is None` checks downstream. Building lists in plain Python and
wrapping them in an explicit `dtype=object` Series sidesteps that dtype
inference entirely and keeps `None` really `None`.
"""

from __future__ import annotations

import pandas as pd

from schemas.common import SegmentAxis

COUNTRY_COL = "Introduction/${Country_question}"
REGION_COL = "Introduction/Which region do you work in?"
ACCESS01_COL = "Financial Access/ACCESS01_resp_en"
LOAN_CYCLE_COL = "Demographics/DEMOG04_resp_en"
GENDER_COL = "Demographics/DEMOG05_resp_en"
AGE_COL = "Demographics/DEMOG03_resp_en"
HH_HEAD_COL = "Client Profile/PROFILE02_resp_en"
PWD_COL = "Client Profile/PROFILE05_resp_en"
OTHER_SERVICES_COLS = [f"Client Profile/PROFILE07_resp_{i}_en" for i in range(1, 6)]
CAREGIVER_COL = "Impacts on Business, Household, and Children/IMPACT04_resp_en"
SHOCK_COLS = [f"Resilience/RESILIENCE03_resp_{i}_en" for i in range(1, 10)]


def _obj_series(values: list, index) -> pd.Series:
    return pd.Series(values, index=index, dtype=object)


def _clean_value(v) -> str | None:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    s = str(v).strip()
    return None if s in ("", "nan", "None") else s


def _clean(series: pd.Series) -> pd.Series:
    """Strip whitespace and normalize blanks/NaN to real None, without going through .map()."""
    return _obj_series([_clean_value(v) for v in series.tolist()], series.index)


def clean_blank_strings(series: pd.Series) -> pd.Series:
    """Public entry point to the same blank/NaN-to-None normalization other modules need
    before handing a raw CSV column to top_box_mask()/isin() -- reused outside this module
    because analysis-ready CSVs are loaded with keep_default_na=False, so blanks are "" not NaN.
    """
    return _clean(series)


def _and(a: pd.Series, b: pd.Series) -> pd.Series:
    """Elementwise AND of two True/False/None object Series, None if either side is unknown."""
    out = []
    for x, y in zip(a.tolist(), b.tolist()):
        out.append(None if (x is None or y is None) else bool(x) and bool(y))
    return _obj_series(out, a.index)


def mask_to_category(mask: pd.Series, true_label: str, false_label: str) -> pd.Series:
    """Turns a boolean mask into a two-value categorical Series, for use as a crosstab segment axis."""
    out = [true_label if v is True else (false_label if v is False else None) for v in mask.tolist()]
    return _obj_series(out, mask.index)


# --- Client identity / geography -------------------------------------------------


def country(df: pd.DataFrame) -> pd.Series:
    return _clean(df[COUNTRY_COL])


def region(df: pd.DataFrame) -> pd.Series:
    return _clean(df[REGION_COL])


def gender(df: pd.DataFrame) -> pd.Series:
    out = []
    for v in _clean(df[GENDER_COL]).tolist():
        out.append("Female" if v == "a. Female" else ("Male" if v == "b. Male" else None))
    return _obj_series(out, df.index)


def age(df: pd.DataFrame) -> pd.Series:
    return pd.to_numeric(df[AGE_COL], errors="coerce")


def loan_cycle(df: pd.DataFrame) -> pd.Series:
    out = []
    for v in _clean(df[LOAN_CYCLE_COL]).tolist():
        out.append(f"Loan cycle {v}" if v in {"2", "3", "4"} else None)
    return _obj_series(out, df.index)


# --- Standard disaggregation segments ---------------------------------------------


def first_time_access_mask(df: pd.DataFrame) -> pd.Series:
    """ACCESS01: prior access to a comparable loan before VisionFund. 'No' == first-time access."""
    out = []
    for v in _clean(df[ACCESS01_COL]).tolist():
        out.append((v == "No") if v in {"Yes", "No"} else None)
    return _obj_series(out, df.index)


def household_head_mask(df: pd.DataFrame) -> pd.Series:
    out = []
    for v in _clean(df[HH_HEAD_COL]).tolist():
        out.append((v == "a. Yes") if v in {"a. Yes", "b. No"} else None)
    return _obj_series(out, df.index)


def female_hh_head_mask(df: pd.DataFrame) -> pd.Series:
    is_female = gender(df)
    out = [v == "Female" if v is not None else None for v in is_female.tolist()]
    is_female = _obj_series(out, df.index)
    return _and(is_female, household_head_mask(df))


def pwd_household_mask(df: pd.DataFrame) -> pd.Series:
    """PROFILE05. 'c. Don't know' is treated as unknown, not as 'no'."""
    out = []
    for v in _clean(df[PWD_COL]).tolist():
        out.append((v == "a. Yes") if v in {"a. Yes", "b. No"} else None)
    return _obj_series(out, df.index)


def caregiver_status(df: pd.DataFrame) -> pd.Series:
    """IMPACT04. 'c. Do not support any children' => Non-caregiver; 'a./b.' => Caregiver."""

    def classify(v):
        if v == "c. Do not support any children":
            return "Non-caregiver"
        if v in {"a. Yes", "b. No"}:
            return "Caregiver"
        return None

    out = [classify(v) for v in _clean(df[CAREGIVER_COL]).tolist()]
    return _obj_series(out, df.index)


def caregiver_mask(df: pd.DataFrame) -> pd.Series:
    out = [(v == "Caregiver") if v is not None else None for v in caregiver_status(df).tolist()]
    return _obj_series(out, df.index)


def child_wellbeing_improved_mask(df: pd.DataFrame) -> pd.Series:
    """IMPACT04 restricted to caregivers: 'a. Yes' == improved. Use with base=caregiver_mask(df)."""
    out = []
    for v in _clean(df[CAREGIVER_COL]).tolist():
        out.append((v == "a. Yes") if v in {"a. Yes", "b. No"} else None)
    return _obj_series(out, df.index)


def _any_selected(df: pd.DataFrame, cols: list[str], none_value: str) -> pd.Series:
    cleaned_cols = [_clean(df[c]).tolist() for c in cols]
    out = []
    for row_values in zip(*cleaned_cols):
        answered = [v for v in row_values if v is not None]
        if not answered:
            out.append(None)
        else:
            out.append(any(v != none_value for v in answered))
    return _obj_series(out, df.index)


def other_services_mask(df: pd.DataFrame) -> pd.Series:
    """PROFILE07 multi-select. 'f. None' selected alone == no other services."""
    return _any_selected(df, OTHER_SERVICES_COLS, none_value="f. None")


def climate_shock_mask(df: pd.DataFrame) -> pd.Series:
    """RESILIENCE03 multi-select. Every listed option is a climate event; 'a. None of these' == unaffected."""
    return _any_selected(df, SHOCK_COLS, none_value="a. None of these")


def standard_categorical_segments(df: pd.DataFrame) -> dict[SegmentAxis, pd.Series]:
    """Ready-made segment columns for crosstab_by_segment, covering every axis with >2 natural values
    plus the boolean segments recast as two-value categories.
    """
    return {
        SegmentAxis.GENDER: gender(df),
        SegmentAxis.LOAN_CYCLE: loan_cycle(df),
        SegmentAxis.COUNTRY: country(df),
        SegmentAxis.REGION: region(df),
        SegmentAxis.FIRST_TIME_ACCESS: mask_to_category(
            first_time_access_mask(df), "First-time access", "Prior access"
        ),
        SegmentAxis.CAREGIVER: caregiver_status(df),
        SegmentAxis.FEMALE_HH_HEAD: mask_to_category(
            female_hh_head_mask(df), "Female HH head", "Not female HH head"
        ),
        SegmentAxis.PWD_HOUSEHOLD: mask_to_category(pwd_household_mask(df), "PWD household", "Non-PWD household"),
        SegmentAxis.CLIMATE_SHOCK: mask_to_category(
            climate_shock_mask(df), "Climate-shock-affected", "Not climate-shock-affected"
        ),
        SegmentAxis.OTHER_SERVICES: mask_to_category(
            other_services_mask(df), "Receives other services", "Loan only"
        ),
    }
