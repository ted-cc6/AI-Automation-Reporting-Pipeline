"""
Unit tests for data_loader/data_loader_screening.py — duplicate-submission and
test/QA-row detection that runs between the transformer and derived-flags steps.
Run: pytest tests/test_screening.py -v
"""
from __future__ import annotations

import pandas as pd

from data_loader.data_loader_screening import (
    CONTENT_EXCLUDE_COLS,
    SCOPE_COUNTRIES,
    choose_canonical_index,
    content_columns,
    find_client_id_collisions,
    find_duplicate_groups,
    find_non_consenting_rows,
    find_out_of_scope_country_rows,
    find_test_rows,
    screen,
)


def _base_df(**overrides) -> pd.DataFrame:
    base = {
        "client_id":       ["A1", "A2", "A3"],
        "enumerator":      ["alice", "bob", "carol"],
        "branch":          ["Branch 1", "Branch 1", "Branch 2"],
        "kobotoolbox_id":  [101, 102, 103],
        "uuid":            ["u1", "u2", "u3"],
        "submission_time": ["2026-04-01T10:00:00", "2026-04-01T11:00:00", "2026-04-02T09:00:00"],
        "kobotoolbox_index": [1, 2, 3],
        "device_info":     ["dev1", "dev1", "dev2"],
        "interview_start": ["2026-04-01T09:50:00", "2026-04-01T10:50:00", "2026-04-02T08:50:00"],
        "interview_end":   ["2026-04-01T10:05:00", "2026-04-01T11:05:00", "2026-04-02T09:05:00"],
        "q_coverage_understanding": [1, 2, 3],
        "q_nps_score":     [9, 5, 2],
        "q_survey_consent": [True, True, True],
        "country":         ["Kenya", "Kenya", "Kenya"],
    }
    base.update(overrides)
    return pd.DataFrame(base)


# ---------------------------------------------------------------------------
# find_test_rows
# ---------------------------------------------------------------------------

class TestFindTestRows:
    def test_flags_test_keyword_in_client_id(self):
        df = _base_df(client_id=["test rosa", "A2", "A3"])
        mask = find_test_rows(df)
        assert list(mask) == [True, False, False]

    def test_flags_training_keyword_in_branch_case_insensitive(self):
        df = _base_df(branch=["TRAINING branch", "Branch 1", "Branch 2"])
        mask = find_test_rows(df)
        assert bool(mask.iloc[0])
        assert not mask.iloc[1]

    def test_does_not_false_positive_on_substring_inside_real_word(self):
        # "qa" should not match inside unrelated words like "Squattersville"
        df = _base_df(branch=["Squattersville", "Branch 1", "Branch 2"])
        mask = find_test_rows(df)
        assert not mask.any()

    def test_clean_rows_are_never_flagged(self):
        df = _base_df()
        mask = find_test_rows(df)
        assert not mask.any()


# ---------------------------------------------------------------------------
# find_non_consenting_rows
# ---------------------------------------------------------------------------

class TestFindNonConsentingRows:
    def test_flags_rows_that_declined_consent(self):
        df = _base_df(q_survey_consent=[True, False, True])
        mask = find_non_consenting_rows(df)
        assert list(mask) == [False, True, False]

    def test_all_consenting_rows_are_never_flagged(self):
        df = _base_df()
        mask = find_non_consenting_rows(df)
        assert not mask.any()

    def test_missing_column_flags_nothing(self):
        df = _base_df().drop(columns=["q_survey_consent"])
        mask = find_non_consenting_rows(df)
        assert not mask.any()

    def test_unmapped_na_values_are_never_flagged(self):
        # Regression test: an all-NA q_survey_consent column (e.g. every raw
        # answer failed to decode against value_coding_map.yaml) must resolve
        # to an all-False mask, never a mask containing pd.NA. `== False`
        # alone produces NA here (unknown != known-False), and critically
        # `~` of an all-NA mask is ALSO all-NA, not all-True -- which, unless
        # this function neutralises it, makes screen()'s `working[~mask]`
        # silently select zero rows instead of "no one flagged."
        df = _base_df(q_survey_consent=pd.array([pd.NA, pd.NA, pd.NA], dtype=pd.BooleanDtype()))
        mask = find_non_consenting_rows(df)
        assert list(mask) == [False, False, False]
        assert mask.isna().sum() == 0  # no NA slipped through (dtype can stay nullable boolean)

    def test_all_na_consent_column_does_not_empty_the_dataset_via_screen(self):
        # End-to-end version of the regression above, through screen() itself.
        df = _base_df(q_survey_consent=pd.array([pd.NA, pd.NA, pd.NA], dtype=pd.BooleanDtype()))
        result = screen(df)
        assert len(result.df) == 3
        assert len(result.removed_non_consenting) == 0


# ---------------------------------------------------------------------------
# find_out_of_scope_country_rows
# ---------------------------------------------------------------------------

class TestFindOutOfScopeCountryRows:
    def test_flags_countries_outside_the_study_scope(self):
        df = _base_df(country=["Kenya", "Mexico", "Vietnam"])
        mask = find_out_of_scope_country_rows(df)
        assert list(mask) == [False, True, False]

    def test_all_in_scope_countries_are_never_flagged(self):
        df = _base_df(country=list(SCOPE_COUNTRIES)[:1] * 3)
        mask = find_out_of_scope_country_rows(df)
        assert not mask.any()

    def test_missing_column_flags_nothing(self):
        df = _base_df().drop(columns=["country"])
        mask = find_out_of_scope_country_rows(df)
        assert not mask.any()


# ---------------------------------------------------------------------------
# find_duplicate_groups / choose_canonical_index
# ---------------------------------------------------------------------------

class TestFindDuplicateGroups:
    def test_identical_content_with_different_identity_cols_is_a_duplicate(self):
        # Same client_id, same answers, only identity/logistics cols differ --
        # mirrors the real Jm25575010-style resubmission found in production.
        df = _base_df(
            client_id=["A1", "A1", "A3"],
            kobotoolbox_id=[101, 999, 103],
            uuid=["u1", "u1-resync", "u3"],
            submission_time=["2026-04-01T10:00:00", "2026-04-20T08:00:00", "2026-04-02T09:00:00"],
            kobotoolbox_index=[1, 500, 3],
            q_coverage_understanding=[1, 1, 3],
            q_nps_score=[9, 9, 2],
        )
        groups = find_duplicate_groups(df)
        assert len(groups) == 1
        assert set(groups[0]) == {0, 1}

    def test_same_client_id_but_different_answers_is_not_a_duplicate(self):
        # Mirrors the real AP103/AP104 case: same client_id, genuinely
        # different substantive answers -- must NOT be grouped as a duplicate.
        df = _base_df(
            client_id=["A1", "A1", "A3"],
            q_coverage_understanding=[1, 3, 3],   # differs between the pair
            q_nps_score=[9, 2, 2],
        )
        groups = find_duplicate_groups(df)
        assert groups == []

    def test_identical_device_timestamp_but_different_clients_is_not_a_duplicate(self):
        # Mirrors the real ND/M-style coincidence: identical device start
        # timestamp, but different client_id and different answers.
        df = _base_df(
            interview_start=["2026-04-01T09:50:00", "2026-04-01T09:50:00", "2026-04-02T08:50:00"],
            q_coverage_understanding=[1, 4, 3],
            q_nps_score=[9, 1, 2],
        )
        groups = find_duplicate_groups(df)
        assert groups == []

    def test_choose_canonical_index_keeps_earliest_submission_time(self):
        df = _base_df(
            submission_time=["2026-04-20T08:00:00", "2026-04-01T10:00:00", "2026-04-02T09:00:00"],
            kobotoolbox_index=[500, 1, 3],
        )
        keep = choose_canonical_index(df, [0, 1])
        assert keep == 1  # earlier submission_time wins, regardless of row order


class TestMultiSelectListColumns:
    def test_duplicate_detection_handles_numpy_array_list_columns(self):
        # Multi-select "list" columns come back from parquet as numpy ndarrays,
        # not plain Python lists -- these must still compare/hash correctly.
        import numpy as np

        df = _base_df(
            client_id=["A1", "A1", "A3"],
            q_coverage_understanding=[1, 1, 3],
            q_nps_score=[9, 9, 2],
            q_child_improvements=[
                np.array(["a", "b"], dtype=object),
                np.array(["a", "b"], dtype=object),
                np.array(["c"], dtype=object),
            ],
        )
        groups = find_duplicate_groups(df)
        assert len(groups) == 1
        assert set(groups[0]) == {0, 1}

    def test_differing_numpy_array_list_columns_are_not_duplicates(self):
        import numpy as np

        df = _base_df(
            client_id=["A1", "A1", "A3"],
            q_child_improvements=[
                np.array(["a", "b"], dtype=object),
                np.array(["a"], dtype=object),
                np.array(["c"], dtype=object),
            ],
        )
        groups = find_duplicate_groups(df)
        assert groups == []


class TestContentColumns:
    def test_excludes_all_identity_and_logistics_columns(self):
        df = _base_df()
        cols = content_columns(df)
        assert not (set(cols) & CONTENT_EXCLUDE_COLS)
        assert "client_id" in cols          # real content, kept
        assert "q_coverage_understanding" in cols


# ---------------------------------------------------------------------------
# find_client_id_collisions
# ---------------------------------------------------------------------------

class TestFindClientIdCollisions:
    def test_flags_same_client_id_with_differing_content(self):
        df = _base_df(
            client_id=["A1", "A1", "A3"],
            q_coverage_understanding=[1, 3, 3],
        )
        collisions = find_client_id_collisions(df)
        assert list(collisions.keys()) == ["A1"]
        assert set(collisions["A1"]) == {0, 1}

    def test_no_collision_when_client_ids_are_unique(self):
        df = _base_df()
        assert find_client_id_collisions(df) == {}


# ---------------------------------------------------------------------------
# screen() — end-to-end
# ---------------------------------------------------------------------------

class TestScreen:
    def test_removes_test_rows_and_true_duplicates_but_keeps_id_collision_rows(self):
        df = _base_df(
            client_id=["test rosa", "A1", "A1"],
            branch=["Branch 9", "Branch 1", "Branch 1"],
            kobotoolbox_id=[901, 101, 999],
            uuid=["tu1", "u1", "u1-resync"],
            submission_time=["2026-06-25T09:19:00", "2026-04-01T10:00:00", "2026-04-20T08:00:00"],
            kobotoolbox_index=[9999, 1, 500],
            q_coverage_understanding=[2, 1, 1],
            q_nps_score=[5, 9, 9],
        )
        result = screen(df)

        assert len(result.removed_test) == 1
        assert result.removed_test[0]["client_id"] == "test rosa"

        assert len(result.removed_duplicates) == 1
        assert result.removed_duplicates[0]["kept_kobotoolbox_id"] == 101
        assert result.removed_duplicates[0]["dropped_kobotoolbox_id"] == 999

        # Only one real row survives from the A1 duplicate pair; test row gone.
        assert len(result.df) == 1
        assert result.df.iloc[0]["client_id"] == "A1"

    def test_id_collision_rows_are_kept_in_output_not_dropped(self):
        df = _base_df(
            client_id=["A1", "A1", "A3"],
            q_coverage_understanding=[1, 3, 3],   # genuinely different answers
        )
        result = screen(df)

        assert len(result.removed_test) == 0
        assert len(result.removed_duplicates) == 0
        assert len(result.df) == 3  # nothing dropped
        assert "A1" in result.id_collisions

    def test_all_four_removal_checks_compose_correctly(self):
        df = _base_df(
            client_id=["test rosa", "A2", "A3"],
            q_survey_consent=[True, False, True],
            country=["Kenya", "Kenya", "Mexico"],
        )
        result = screen(df)

        assert len(result.removed_test) == 1
        assert result.removed_test[0]["client_id"] == "test rosa"
        assert len(result.removed_non_consenting) == 1
        assert result.removed_non_consenting[0]["client_id"] == "A2"
        assert len(result.removed_out_of_scope) == 1
        assert result.removed_out_of_scope[0]["client_id"] == "A3"
        assert result.removed_out_of_scope[0]["country"] == "Mexico"

        # All three rows were removed for one reason or another -- nothing survives.
        assert len(result.df) == 0
