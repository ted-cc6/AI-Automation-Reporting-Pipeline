"""Pulls one subsection's free-text responses, plus each respondent's profile tags, out of the
analysis-ready CSV -- the data the qualitative agent classifies and the Verbatim objects it's
allowed to build are both sourced from here, never from the model's own output.

Loads every non-blank response by default (no sampling) -- theme frequencies need to reflect
the real dataset, not a slice of it. `max_n` exists only as a debugging knob for quick iteration.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import pandas as pd

from metrics_engine.segments import (
    age,
    caregiver_status,
    climate_shock_mask,
    clean_blank_strings,
    country,
    female_hh_head_mask,
    first_time_access_mask,
    gender,
    loan_cycle,
    other_services_mask,
    pwd_household_mask,
)

BRANCH_COL = "Introduction/INTR02_resp_en"
CLIENT_ID_COL = "Introduction/Global unique client id"

QUALITY_OF_LIFE_DRIVER_COLS = [
    "Impacts on Business, Household, and Children/IMPACT03a_resp_en",  # how it improved
    "Impacts on Business, Household, and Children/IMPACT03b_resp_en",  # why it didn't change
    "Impacts on Business, Household, and Children/IMPACT03c_resp_en",  # how it got worse
]


@dataclass(frozen=True)
class FreeTextResponse:
    client_id: Optional[str]
    text: str
    source_field: str
    gender: Optional[str]
    age: Optional[int]
    branch: Optional[str]
    country: Optional[str]
    loan_cycle: Optional[int]
    segment_tags: list = field(default_factory=list)


def _segment_tags_for_row(
    idx,
    caregiver_series: pd.Series,
    female_hh_head_series: pd.Series,
    pwd_series: pd.Series,
    climate_series: pd.Series,
    first_time_series: pd.Series,
    other_services_series: pd.Series,
) -> list:
    tags = []
    caregiver_value = caregiver_series.loc[idx]
    if caregiver_value is not None:
        tags.append(caregiver_value)  # "Caregiver" or "Non-caregiver"
    if female_hh_head_series.loc[idx] is True:
        tags.append("Female HH head")
    if pwd_series.loc[idx] is True:
        tags.append("PWD household")
    if climate_series.loc[idx] is True:
        tags.append("Climate-shock-affected")
    if first_time_series.loc[idx] is True:
        tags.append("First-time access")
    if other_services_series.loc[idx] is True:
        tags.append("Receives other services")
    return tags


def load_free_text_responses(df: pd.DataFrame, source_field: str, max_n: Optional[int] = None) -> list:
    """Every non-blank response in `source_field`, tagged with that respondent's full profile."""
    texts = clean_blank_strings(df[source_field])
    branches = clean_blank_strings(df[BRANCH_COL])
    client_ids = clean_blank_strings(df[CLIENT_ID_COL])
    genders = gender(df)
    ages = age(df)
    countries = country(df)
    cycles = loan_cycle(df)
    caregivers = caregiver_status(df)
    female_hh_heads = female_hh_head_mask(df)
    pwd_households = pwd_household_mask(df)
    climate_shocks = climate_shock_mask(df)
    first_time_accesses = first_time_access_mask(df)
    other_services = other_services_mask(df)

    out = []
    for idx in df.index:
        text = texts.loc[idx]
        if text is None:
            continue
        cycle_label = cycles.loc[idx]
        cycle_num = int(cycle_label.rsplit(" ", 1)[-1]) if cycle_label else None
        age_val = ages.loc[idx]

        out.append(
            FreeTextResponse(
                client_id=client_ids.loc[idx],
                text=text,
                source_field=source_field,
                gender=genders.loc[idx],
                age=(int(age_val) if pd.notna(age_val) else None),
                branch=branches.loc[idx],
                country=countries.loc[idx],
                loan_cycle=cycle_num,
                segment_tags=_segment_tags_for_row(
                    idx, caregivers, female_hh_heads, pwd_households, climate_shocks, first_time_accesses, other_services
                ),
            )
        )
        if max_n is not None and len(out) >= max_n:
            break
    return out


def load_quality_of_life_drivers(df: pd.DataFrame, max_per_field: Optional[int] = None) -> list:
    """Combines IMPACT03a/b/c -- the template asks for these to be theme-tagged together,
    covering how life improved, why it didn't change, and how it got worse. Loads every
    non-blank response across all three fields by default (max_per_field is a debug-only knob).
    """
    return load_free_text_responses_multi(df, QUALITY_OF_LIFE_DRIVER_COLS, max_per_field=max_per_field)


def load_free_text_responses_multi(df: pd.DataFrame, source_columns, max_per_field: Optional[int] = None) -> list:
    """Generic version of load_quality_of_life_drivers -- combines any tuple of free-text
    columns into one response list, for sections whose qualitative pass spans more than one
    survey question (or just one, in which case this is equivalent to load_free_text_responses).
    """
    combined: list = []
    for col in source_columns:
        combined.extend(load_free_text_responses(df, col, max_n=max_per_field))
    return combined
