from ppi_module.reference_data import (
    available_line_codes,
    guide_id_for_survey_version,
    load_scorecard,
    parse_option_prefix,
)


def test_parse_option_prefix_variants():
    assert parse_option_prefix("aa) Kayonza") == "AA"
    assert parse_option_prefix("j) Muhanga") == "J"
    assert parse_option_prefix("J. Imbabura") == "J"
    assert parse_option_prefix("A.Quito") == "A"
    assert parse_option_prefix("AE. Kerala") == "AE"
    assert parse_option_prefix("Seis o más") is None  # no letter prefix at all
    assert parse_option_prefix(None) is None
    assert parse_option_prefix("") is None


def test_ecuador_has_three_survey_versions_all_mapped(scorecard_path):
    options = load_scorecard("ECU", scorecard_path)
    versions = {(o.guide_id, o.survey_version) for o in options}
    assert ("ECU2015", 1) in versions
    assert ("ECU2022", 2) in versions
    assert ("ECU2022", 3) in versions


def test_current_ecuador_survey_version_resolves_to_2022_guide(scorecard_path):
    assert guide_id_for_survey_version("ECU", 3, scorecard_path) == "ECU2022"


def test_zambia_two_survey_versions_map_to_same_guide(scorecard_path):
    # This is the exact bug the Impact team hit before: a hardcoded 1:1
    # version->guide table left version 2 unmapped. Both must resolve here.
    v1 = guide_id_for_survey_version("ZMB", 1, scorecard_path)
    v2 = guide_id_for_survey_version("ZMB", 2, scorecard_path)
    assert v1 == "ZMB2017"
    assert v2 == "ZMB2017"


def test_bolivia_and_india_resolve_to_their_current_survey_version_guide(scorecard_path):
    assert guide_id_for_survey_version("BOL", 2, scorecard_path) == "BOL2023"
    assert guide_id_for_survey_version("IND", 2, scorecard_path) == "IND2023"


def test_myanmar_and_malawi_load_despite_differently_named_options_column(scorecard_path):
    # These two tabs name the option-label column "QuestionOptionValues" instead of
    # "OptionValues" like every other country -- confirm the loader tolerates that
    # instead of silently returning zero options.
    for country, expected_guide, expected_version in (("MMR", "MMR2019", 1), ("MWI", "MWI2023", 2)):
        options = load_scorecard(country, scorecard_path)
        assert options, f"{country} scorecard loaded no rows"
        assert guide_id_for_survey_version(country, expected_version, scorecard_path) == expected_guide


def test_kosovo_and_mali_have_no_usable_scorecard(scorecard_path):
    # Rows exist in the sheet but with a null PPI_Guide_Id (malformed placeholder rows),
    # so nothing should resolve for any survey version.
    for country in ("KOS", "MLI"):
        for version in (1, 2, 3):
            assert guide_id_for_survey_version(country, version, scorecard_path) is None


def test_rwanda_option_prefixes_cover_all_thirty_districts(scorecard_path):
    options = [
        o for o in load_scorecard("RWA", scorecard_path) if o.guide_id == "RWA2019" and o.question == 1
    ]
    prefixes = {o.option_prefix for o in options}
    # a..z (26) plus the doubled continuation aa, bb, cc, dd (not the ab/ac/ad continuation
    # a spreadsheet-style scheme would produce) -- confirmed against the real label text.
    expected_tail = {"AA", "BB", "CC", "DD"}
    assert expected_tail.issubset(prefixes)
    assert "AB" not in prefixes
    assert len(options) == 30


def test_ecuador_current_survey_version_line_availability(scorecard_path):
    # Scoped to survey_version=3 -- the version this quarter's clients actually used.
    # Version 2 of the same guide_id does NOT populate the 2017-PPP lines; version 3 does,
    # which is exactly why line availability has to be checked per-version, not per-guide.
    available_v3 = available_line_codes("ECU", "ECU2022", 3, scorecard_path)
    assert "USD190day2011PPP" in available_v3
    assert "USD320day2011PPP" in available_v3
    assert "USD215day2017PPP" in available_v3

    available_v2 = available_line_codes("ECU", "ECU2022", 2, scorecard_path)
    assert "USD215day2017PPP" not in available_v2


def test_vietnam_uses_percentile_lines_not_dollar_lines(scorecard_path):
    options = load_scorecard("VNM", scorecard_path)
    guide_ids = {o.guide_id for o in options}
    assert "VNM2023" in guide_ids
    available = available_line_codes("VNM", "VNM2023", 1, scorecard_path)
    assert "Bottom20thPercentile" in available
    assert "USD190day2011PPP" not in available
