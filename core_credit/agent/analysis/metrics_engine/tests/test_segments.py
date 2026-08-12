import pandas as pd

from metrics_engine import segments


def _make_df() -> pd.DataFrame:
    # Column names and value formats are copied verbatim from
    # processed_data/2026Q2_20260803_163530_analysis_ready.csv.
    return pd.DataFrame(
        {
            segments.COUNTRY_COL: ["ECU", "RWA", "GHA", ""],
            segments.REGION_COL: ["LACRO", "Eastern Africa", "Western Africa", ""],
            segments.ACCESS01_COL: ["No", "Yes", "No", ""],
            segments.LOAN_CYCLE_COL: ["2", "3", "4", ""],
            segments.GENDER_COL: ["a. Female", "b. Male", "a. Female", ""],
            segments.AGE_COL: ["25", "40", "33", ""],
            segments.HH_HEAD_COL: ["a. Yes", "b. No", "a. Yes", ""],
            segments.PWD_COL: ["a. Yes", "b. No", "c. Don't know", ""],
            segments.CAREGIVER_COL: ["a. Yes", "c. Do not support any children", "b. No", ""],
            "Client Profile/PROFILE07_resp_1_en": ["a. Savings", "f. None", "", ""],
            "Client Profile/PROFILE07_resp_2_en": ["", "", "", ""],
            "Client Profile/PROFILE07_resp_3_en": ["", "", "", ""],
            "Client Profile/PROFILE07_resp_4_en": ["", "", "", ""],
            "Client Profile/PROFILE07_resp_5_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_1_en": ["b. Flooding", "a. None of these", "", ""],
            "Resilience/RESILIENCE03_resp_2_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_3_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_4_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_5_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_6_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_7_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_8_en": ["", "", "", ""],
            "Resilience/RESILIENCE03_resp_9_en": ["", "", "", ""],
        }
    )


def test_clean_normalizes_blanks_to_none():
    s = pd.Series([" Yes ", "", "No"])
    cleaned = segments._clean(s)
    assert cleaned.tolist() == ["Yes", None, "No"]


def test_country_and_region():
    df = _make_df()
    assert segments.country(df).tolist() == ["ECU", "RWA", "GHA", None]
    assert segments.region(df).tolist() == ["LACRO", "Eastern Africa", "Western Africa", None]


def test_gender_maps_codes_to_labels():
    df = _make_df()
    assert segments.gender(df).tolist() == ["Female", "Male", "Female", None]


def test_age_is_numeric():
    df = _make_df()
    result = segments.age(df)
    assert result.tolist()[:3] == [25.0, 40.0, 33.0]
    assert pd.isna(result.iloc[3])


def test_loan_cycle_labels():
    df = _make_df()
    assert segments.loan_cycle(df).tolist() == ["Loan cycle 2", "Loan cycle 3", "Loan cycle 4", None]


def test_first_time_access_mask():
    df = _make_df()
    # ACCESS01 "No" (no prior access elsewhere) => first-time access == True
    assert segments.first_time_access_mask(df).tolist() == [True, False, True, None]


def test_female_hh_head_mask():
    df = _make_df()
    # row0: Female + HH head Yes -> True; row1: Male -> False; row2: Female + HH head Yes -> True; row3: unknown
    assert segments.female_hh_head_mask(df).tolist() == [True, False, True, None]


def test_pwd_household_mask_treats_dont_know_as_unknown():
    df = _make_df()
    assert segments.pwd_household_mask(df).tolist() == [True, False, None, None]


def test_caregiver_status_and_mask():
    df = _make_df()
    assert segments.caregiver_status(df).tolist() == ["Caregiver", "Non-caregiver", "Caregiver", None]
    assert segments.caregiver_mask(df).tolist() == [True, False, True, None]


def test_child_wellbeing_improved_mask_only_meaningful_for_caregivers():
    df = _make_df()
    # row0 "a. Yes" -> improved True; row2 "b. No" -> improved False;
    # row1 is a non-caregiver ("c.") so this mask is None for them (base filtering handles exclusion)
    assert segments.child_wellbeing_improved_mask(df).tolist() == [True, None, False, None]


def test_other_services_mask():
    df = _make_df()
    # row0 selected "a. Savings" -> True; row1 selected only "f. None" -> False; row2/3 no answer -> None
    assert segments.other_services_mask(df).tolist() == [True, False, None, None]


def test_climate_shock_mask():
    df = _make_df()
    # row0 selected flooding -> True; row1 selected "a. None of these" -> False; row2/3 no answer -> None
    assert segments.climate_shock_mask(df).tolist() == [True, False, None, None]


def test_mask_to_category():
    mask = pd.Series([True, False, None])
    result = segments.mask_to_category(mask, "Yes label", "No label")
    assert result.tolist() == ["Yes label", "No label", None]


def test_standard_categorical_segments_has_expected_axes():
    df = _make_df()
    result = segments.standard_categorical_segments(df)
    from schemas.common import SegmentAxis

    assert SegmentAxis.GENDER in result
    assert SegmentAxis.CAREGIVER in result
    assert result[SegmentAxis.GENDER].tolist() == ["Female", "Male", "Female", None]
