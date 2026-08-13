"""
Unit tests for data_loader/data_loader_screening.py — duplicate-submission and
test/QA-row detection that runs between the transformer and derived-flags steps.
Run: pytest tests/test_screening.py -v
"""
from __future__ import annotations

import pandas as pd

from data_loader.data_loader_screening import (
    CONTENT_EXCLUDE_COLS,
    DATASET_SCHEMAS,
    SCOPE_COUNTRIES_AFRICA_VIETNAM,
    SCOPE_COUNTRIES_LARCO,
    build_screening_summary,
    choose_canonical_index,
    content_columns,
    find_client_id_collisions,
    find_duplicate_groups,
    find_duration_outliers,
    find_non_consenting_rows,
    find_out_of_scope_country_rows,
    find_test_rows,
    find_unselected_country_rows,
    find_unselected_region_rows,
    find_uuid_duplicate_pairs,
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
        # Nigeria: a real country that is nonetheless outside both schemas'
        # scope -- Mexico used to serve this role until the 2026 wave folded
        # LARCO's countries into SCOPE_COUNTRIES_AFRICA_VIETNAM (see
        # test_dataset_schemas_registry_intentionally_overlaps_on_larco_countries).
        df = _base_df(country=["Kenya", "Nigeria", "Vietnam"])
        mask = find_out_of_scope_country_rows(df, SCOPE_COUNTRIES_AFRICA_VIETNAM)
        assert list(mask) == [False, True, False]

    def test_all_in_scope_countries_are_never_flagged(self):
        df = _base_df(country=list(SCOPE_COUNTRIES_AFRICA_VIETNAM)[:1] * 3)
        mask = find_out_of_scope_country_rows(df, SCOPE_COUNTRIES_AFRICA_VIETNAM)
        assert not mask.any()

    def test_missing_column_flags_nothing(self):
        df = _base_df().drop(columns=["country"])
        mask = find_out_of_scope_country_rows(df, SCOPE_COUNTRIES_AFRICA_VIETNAM)
        assert not mask.any()

    def test_larco_scope_flags_africa_countries_and_vice_versa(self):
        df = _base_df(country=["Ecuador", "Kenya", "Bolivia"])
        mask = find_out_of_scope_country_rows(df, SCOPE_COUNTRIES_LARCO)
        assert list(mask) == [False, True, False]

    def test_dataset_schemas_registry_intentionally_overlaps_on_larco_countries(self):
        # 2026-08-13: LARCO's countries were folded into the africa_vietnam
        # schema for the 2026 wave (same unified instrument), while
        # SCOPE_COUNTRIES_LARCO is kept unchanged so the older 2025
        # LARCO-instrument export can still be reprocessed as a Part 10
        # trend-comparison baseline. So every LARCO-schema country must also
        # be in scope for africa_vietnam -- overlap here is intentional, not
        # a regression of the pre-2026 disjointness this test used to assert.
        assert SCOPE_COUNTRIES_LARCO <= SCOPE_COUNTRIES_AFRICA_VIETNAM
        assert set(DATASET_SCHEMAS) == {"africa_vietnam", "larco"}


# ---------------------------------------------------------------------------
# find_unselected_country_rows
# ---------------------------------------------------------------------------

class TestFindUnselectedCountryRows:
    def test_flags_every_row_not_matching_the_target_country(self):
        df = _base_df(country=["Kenya", "Vietnam", "Kenya"])
        mask = find_unselected_country_rows(df, "Vietnam")
        assert list(mask) == [True, False, True]

    def test_comparison_is_case_insensitive(self):
        df = _base_df(country=["Vietnam", "vietnam", "VIETNAM"])
        mask = find_unselected_country_rows(df, "vietnam")
        assert not mask.any()

    def test_target_country_with_surrounding_whitespace_still_matches(self):
        df = _base_df(country=[" Vietnam ", "Kenya", "Vietnam"])
        mask = find_unselected_country_rows(df, "  Vietnam  ")
        assert list(mask) == [False, True, False]

    def test_missing_column_flags_nothing(self):
        df = _base_df().drop(columns=["country"])
        mask = find_unselected_country_rows(df, "Vietnam")
        assert not mask.any()


# ---------------------------------------------------------------------------
# find_unselected_region_rows -- report_scope filter (see report_scopes.py)
# ---------------------------------------------------------------------------

class TestFindUnselectedRegionRows:
    def test_flags_every_row_outside_the_given_regions(self):
        df = _base_df(region=["LACRO", "AFRICA", "ASIA"])
        mask = find_unselected_region_rows(df, ["LACRO"])
        assert list(mask) == [False, True, True]

    def test_multiple_regions_are_all_kept(self):
        df = _base_df(region=["AFRICA", "ASIA", "LACRO"])
        mask = find_unselected_region_rows(df, ["AFRICA", "ASIA"])
        assert list(mask) == [False, False, True]

    def test_comparison_is_case_insensitive(self):
        df = _base_df(region=["lacro", "LACRO", "Lacro"])
        mask = find_unselected_region_rows(df, ["LACRO"])
        assert not mask.any()

    def test_missing_column_flags_nothing(self):
        df = _base_df()  # no region column
        mask = find_unselected_region_rows(df, ["LACRO"])
        assert not mask.any()


# ---------------------------------------------------------------------------
# screen() -- report_scope wiring end to end
# ---------------------------------------------------------------------------

class TestScreenReportScope:
    def test_report_scope_narrows_to_the_named_regions(self):
        df = _base_df(
            client_id=["A1", "A2", "A3"],
            region=["LACRO", "AFRICA", "LACRO"],
        )
        result = screen(df, report_scope="lacro")
        assert len(result.df) == 2
        assert list(result.df["client_id"]) == ["A1", "A3"]
        assert len(result.removed_unselected_region) == 1
        assert result.removed_unselected_region[0]["client_id"] == "A2"

    def test_report_scope_runs_after_other_screens_not_instead_of_them(self):
        df = _base_df(
            client_id=["test rosa", "A2", "A3"],
            region=["LACRO", "LACRO", "AFRICA"],
        )
        result = screen(df, report_scope="lacro")
        assert len(result.removed_test) == 1
        assert len(result.removed_unselected_region) == 1
        assert result.removed_unselected_region[0]["client_id"] == "A3"
        assert len(result.df) == 1
        assert result.df.iloc[0]["client_id"] == "A2"

    def test_no_report_scope_leaves_every_region_in_place(self):
        df = _base_df(region=["LACRO", "AFRICA", "ASIA"])
        result = screen(df)
        assert len(result.df) == 3
        assert result.removed_unselected_region == []


# ---------------------------------------------------------------------------
# build_screening_summary
# ---------------------------------------------------------------------------

class TestBuildScreeningSummary:
    def test_summary_reports_report_scope_removals(self):
        df = _base_df(region=["LACRO", "AFRICA", "LACRO"])
        result = screen(df, report_scope="lacro")
        summary = build_screening_summary(result, n_start=3, report_scope="lacro")
        assert summary["report_scope"] == "lacro"
        assert summary["removed"]["unselected_region"] == 1
        assert summary["n_end"] == 2
        assert "rules" in summary


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
            country=["Kenya", "Kenya", "Nigeria"],
        )
        result = screen(df)

        assert len(result.removed_test) == 1
        assert result.removed_test[0]["client_id"] == "test rosa"
        assert len(result.removed_non_consenting) == 1
        assert result.removed_non_consenting[0]["client_id"] == "A2"
        assert len(result.removed_out_of_scope) == 1
        assert result.removed_out_of_scope[0]["client_id"] == "A3"
        assert result.removed_out_of_scope[0]["country"] == "Nigeria"

        # All three rows were removed for one reason or another -- nothing survives.
        assert len(result.df) == 0

    def test_target_country_scopes_the_run_to_just_that_country(self):
        df = _base_df(country=["Kenya", "Vietnam", "Vietnam"])
        result = screen(df, target_country="Vietnam")

        assert len(result.df) == 2
        assert set(result.df["country"]) == {"Vietnam"}
        assert len(result.removed_unselected_country) == 1
        assert result.removed_unselected_country[0]["client_id"] == "A1"
        assert result.removed_unselected_country[0]["country"] == "Kenya"

    def test_no_target_country_leaves_removed_unselected_country_empty(self):
        df = _base_df(country=["Kenya", "Vietnam", "Vietnam"])
        result = screen(df)

        assert len(result.df) == 3  # nothing removed by country selection
        assert result.removed_unselected_country == []

    def test_target_country_runs_after_other_screens_not_instead_of_them(self):
        # A test-QA row and an out-of-scope-country row should still be
        # removed by their own screens even when a target_country is set --
        # country selection is an additional narrowing, not a replacement.
        df = _base_df(
            client_id=["test rosa", "A2", "A3"],
            country=["Vietnam", "Vietnam", "Nigeria"],
        )
        result = screen(df, target_country="Vietnam")

        assert len(result.removed_test) == 1
        assert len(result.removed_out_of_scope) == 1
        assert result.removed_out_of_scope[0]["client_id"] == "A3"
        assert len(result.df) == 1
        assert result.df.iloc[0]["client_id"] == "A2"


# ---------------------------------------------------------------------------
# find_uuid_duplicate_pairs -- a THIRD independent signal from exact-content
# duplicates and client-ID collisions (see the function's own docstring)
# ---------------------------------------------------------------------------

class TestFindUuidDuplicatePairs:
    def test_shared_uuid_different_client_id_partial_overlap_is_a_pair(self):
        df = _base_df(
            client_id=["A1", "A2", "A3"],
            uuid=["dup-uuid", "dup-uuid", "u3"],
            q_coverage_understanding=[1, 1, 3],  # matches between A1/A2
            q_nps_score=[9, 2, 2],                # differs between A1/A2
        )
        pairs = find_uuid_duplicate_pairs(df)
        assert len(pairs) == 1
        p = pairs[0]
        assert {p["client_id_a"], p["client_id_b"]} == {"A1", "A2"}
        assert 0.0 < p["similarity"] < 1.0

    def test_fully_matching_content_gets_a_pair_at_100_percent(self):
        # client_id IS a content column (not in CONTENT_EXCLUDE_COLS), so a
        # true 100%-similarity pair needs a matching client_id too -- this
        # is the ceiling case, not the real-world shape (find_duplicate_
        # groups() would already catch a same-client_id, fully-identical
        # pair as an exact duplicate; this function doesn't care and would
        # still score it, confirming the similarity math itself).
        df = _base_df(
            client_id=["A1", "A1", "A3"], uuid=["dup-uuid", "dup-uuid", "u3"],
            q_coverage_understanding=[1, 1, 3], q_nps_score=[9, 9, 2],
        )
        pairs = find_uuid_duplicate_pairs(df)
        assert len(pairs) == 1
        assert pairs[0]["similarity"] == 1.0
        assert pairs[0]["severity"] == "high"

    def test_severity_bands_follow_similarity(self):
        assert find_uuid_duplicate_pairs(
            _base_df(uuid=["u", "u", "x"], q_coverage_understanding=[1, 1, 3], q_nps_score=[9, 5, 2])
        )[0]["severity"] in ("high", "medium", "low")  # sanity: always one of the three

    def test_unique_uuids_produce_no_pairs(self):
        df = _base_df()  # default fixture already has 3 distinct uuids
        assert find_uuid_duplicate_pairs(df) == []

    def test_missing_uuid_column_returns_empty(self):
        df = _base_df().drop(columns=["uuid"])
        assert find_uuid_duplicate_pairs(df) == []

    def test_never_drops_rows_report_only(self):
        df = _base_df(uuid=["dup-uuid", "dup-uuid", "u3"])
        result = screen(df)
        assert len(result.df) == 3  # nothing removed
        assert len(result.uuid_duplicate_pairs) == 1


# ---------------------------------------------------------------------------
# find_duration_outliers -- derivable data-quality signal (see
# data_quality_flags.py for how a "concentrated" finding becomes a flag)
# ---------------------------------------------------------------------------

def _duration_df(n_normal=100, n_fast=40, fast_country="Bolivia",
                  fast_enumerator_share=1.0) -> pd.DataFrame:
    """n_normal respondents at ~13 minutes across a few countries, plus
    n_fast respondents from fast_country at ~2 minutes -- mirrors the real
    Bolivia scenario (n=278, 213 outliers, one enumerator)."""
    rows = []
    countries = ["Ecuador", "Mexico", "Guatemala"]
    for i in range(n_normal):
        rows.append({
            "country": countries[i % len(countries)],
            "enumerator": f"enum_{i % 5}",
            "interview_start": "2026-04-01T09:00:00",
            "interview_end": "2026-04-01T09:13:00",  # 13 min
        })
    n_from_top_enum = int(n_fast * fast_enumerator_share)
    for i in range(n_fast):
        enumerator = "rosa_cardenas" if i < n_from_top_enum else f"other_enum_{i}"
        rows.append({
            "country": fast_country,
            "enumerator": enumerator,
            "interview_start": "2026-04-01T09:00:00",
            "interview_end": "2026-04-01T09:02:00",  # 2 min
        })
    df = pd.DataFrame(rows)
    df["client_id"] = [f"C{i}" for i in range(len(df))]
    return df


class TestFindDurationOutliers:
    def test_concentrated_fast_country_is_flagged(self):
        df = _duration_df()
        findings = find_duration_outliers(df)
        assert len(findings) == 1
        f = findings[0]
        assert f["country"] == "Bolivia"
        assert f["n_outliers"] == 40
        assert f["concentrated"] is True
        assert f["top_enumerator"] == "rosa_cardenas"
        assert f["top_enumerator_share_of_outliers"] == 1.0

    def test_spread_out_fast_interviews_are_not_concentrated(self):
        df = _duration_df(fast_enumerator_share=0.1)  # only 10% from one enumerator
        findings = find_duration_outliers(df)
        assert len(findings) == 1
        assert findings[0]["concentrated"] is False

    def test_no_elevated_country_produces_no_findings(self):
        df = _duration_df(n_fast=0)
        assert find_duration_outliers(df) == []

    def test_small_country_below_min_n_is_ignored(self):
        df = _duration_df(n_fast=5)  # below _DURATION_OUTLIER_MIN_N (30)
        assert find_duration_outliers(df) == []

    def test_missing_required_columns_returns_empty(self):
        assert find_duration_outliers(pd.DataFrame({"country": ["Kenya"]})) == []

    def test_never_drops_rows_report_only(self):
        df = _duration_df()
        result = screen(df)
        assert len(result.df) == len(df)  # nothing removed
        assert len(result.duration_outliers) == 1
