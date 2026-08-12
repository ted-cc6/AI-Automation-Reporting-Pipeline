import pandas as pd

from metrics_engine import segments
from qualitative_agent.data_prep import (
    BRANCH_COL,
    CLIENT_ID_COL,
    QUALITY_OF_LIFE_DRIVER_COLS,
    load_free_text_responses,
    load_quality_of_life_drivers,
)


def _make_df() -> pd.DataFrame:
    other_services_blank = {c: ["", "", ""] for c in segments.OTHER_SERVICES_COLS}
    shock_blank = {c: ["", "", ""] for c in segments.SHOCK_COLS}
    return pd.DataFrame(
        {
            segments.GENDER_COL: ["a. Female", "b. Male", ""],
            segments.AGE_COL: ["25", "40", ""],
            segments.LOAN_CYCLE_COL: ["2", "3", ""],
            segments.COUNTRY_COL: ["ECU", "RWA", ""],
            segments.ACCESS01_COL: ["No", "Yes", ""],
            segments.HH_HEAD_COL: ["a. Yes", "b. No", ""],
            segments.PWD_COL: ["a. Yes", "b. No", ""],
            segments.CAREGIVER_COL: ["a. Yes", "c. Do not support any children", ""],
            BRANCH_COL: ["Quito Branch", "", ""],
            CLIENT_ID_COL: ["ECU_001", "RWA_002", ""],
            QUALITY_OF_LIFE_DRIVER_COLS[0]: ["Tengo mas ingresos", "", ""],
            QUALITY_OF_LIFE_DRIVER_COLS[1]: ["", "No change because loan was small", ""],
            QUALITY_OF_LIFE_DRIVER_COLS[2]: ["", "", ""],
            **{**other_services_blank, segments.OTHER_SERVICES_COLS[0]: ["a. Savings", "f. None", ""]},
            **{**shock_blank, segments.SHOCK_COLS[0]: ["b. Flooding", "a. None of these", ""]},
        }
    )


def test_load_free_text_responses_skips_blanks():
    df = _make_df()
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[0])
    assert len(responses) == 1
    assert responses[0].text == "Tengo mas ingresos"


def test_load_free_text_responses_attaches_profile():
    df = _make_df()
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[0])
    r = responses[0]
    assert r.gender == "Female"
    assert r.age == 25
    assert r.loan_cycle == 2
    assert r.country == "ECU"
    assert r.branch == "Quito Branch"
    assert r.client_id == "ECU_001"
    assert r.source_field == QUALITY_OF_LIFE_DRIVER_COLS[0]


def test_load_free_text_responses_populates_segment_tags():
    df = _make_df()
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[0])
    r = responses[0]
    # row 0: Female HH head, PWD household, Caregiver, first-time access, other services, climate shock
    assert "Caregiver" in r.segment_tags
    assert "Female HH head" in r.segment_tags
    assert "PWD household" in r.segment_tags
    assert "Climate-shock-affected" in r.segment_tags
    assert "First-time access" in r.segment_tags
    assert "Receives other services" in r.segment_tags


def test_load_free_text_responses_segment_tags_reflect_non_caregiver_and_no_shock():
    df = _make_df()
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[1])
    r = responses[0]  # row 1: Male, not HH... wait HH_HEAD_COL row1 = "b. No" -> not female hh head anyway (Male)
    assert "Non-caregiver" in r.segment_tags
    assert "Climate-shock-affected" not in r.segment_tags
    assert "Receives other services" not in r.segment_tags


def test_load_free_text_responses_missing_profile_fields_are_none():
    df = _make_df()
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[1])
    r = responses[0]
    assert r.text == "No change because loan was small"
    assert r.branch is None  # row 1's branch column is blank


def test_load_free_text_responses_respects_max_n():
    df = pd.DataFrame(
        {
            segments.GENDER_COL: ["a. Female"] * 5,
            segments.AGE_COL: ["30"] * 5,
            segments.LOAN_CYCLE_COL: ["2"] * 5,
            segments.COUNTRY_COL: ["ECU"] * 5,
            segments.ACCESS01_COL: ["No"] * 5,
            segments.HH_HEAD_COL: ["a. Yes"] * 5,
            segments.PWD_COL: ["b. No"] * 5,
            segments.CAREGIVER_COL: ["a. Yes"] * 5,
            BRANCH_COL: ["Branch"] * 5,
            CLIENT_ID_COL: [f"ECU_{i}" for i in range(5)],
            QUALITY_OF_LIFE_DRIVER_COLS[0]: [f"response {i}" for i in range(5)],
            **{c: [""] * 5 for c in segments.OTHER_SERVICES_COLS},
            **{c: [""] * 5 for c in segments.SHOCK_COLS},
        }
    )
    responses = load_free_text_responses(df, QUALITY_OF_LIFE_DRIVER_COLS[0], max_n=2)
    assert len(responses) == 2


def test_load_quality_of_life_drivers_loads_full_dataset_by_default():
    df = _make_df()
    combined = load_quality_of_life_drivers(df)  # no max_per_field -- full dataset
    assert len(combined) == 2  # one from field 0 (row 0), one from field 1 (row 1)
    source_fields = {r.source_field for r in combined}
    assert source_fields == {QUALITY_OF_LIFE_DRIVER_COLS[0], QUALITY_OF_LIFE_DRIVER_COLS[1]}
