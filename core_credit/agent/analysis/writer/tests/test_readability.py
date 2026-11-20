"""Test7 QA readability fixes: country names, quote marks, R8 shape rotation, 2.2 coverage fact."""

from benchmark_module.mapping import country_display_name
from schemas.common import SegmentAxis, SegmentedValue, Verbatim
from schemas.poverty_likelihood import CountryVsNationalRate
from writer import chain
from writer.formatting import _segment_line, format_national_comparison
from writer.grounding import check_profile_grounding


def test_every_survey_country_has_a_name():
    codes = "BOL DOM ECU GHA GTM HND IND KEN KOS MEX MLI MMR MNE MNG MWI RWA SEN TZA UGA VNM ZMB".split()
    assert all(country_display_name(c) != c for c in codes)
    assert country_display_name("XYZ") == "XYZ"


def test_country_segment_lines_use_names():
    seg = SegmentedValue(axis=SegmentAxis.COUNTRY, value_label="MNE", share=0.015, n=262)
    assert "Montenegro: 1.5%" in _segment_line("all clients", seg)
    gender = SegmentedValue(axis=SegmentAxis.GENDER, value_label="Female", share=0.5, n=10)
    assert "Female: 50.0%" in _segment_line("all clients", gender)


def test_codes_expand_outside_quotes_only():
    text = 'Scores range from MLI to MNE. A client wrote "KEN office was far".'
    assert chain._clean_output(text) == 'Scores range from Mali to Montenegro. A client wrote "KEN office was far".'


def test_doubled_closing_quote_mark_collapses():
    assert chain._clean_output('He said "it helped a lot.”" Then more.') == 'He said "it helped a lot." Then more.'


def test_profile_check_knows_kosovo_and_montenegro():
    v = Verbatim(quote="The loan officers were always kind to me here", country="KOS", source_field="f")
    ok = 'A client in Kosovo said "The loan officers were always kind to me here".'
    bad = 'A client in Montenegro said "The loan officers were always kind to me here".'
    assert check_profile_grounding(ok, [v]) == []
    assert check_profile_grounding(bad, [v])


def test_r8_shapes_rotate_across_insights_and_analysis_blocks_get_none():
    notes = [chain._forward_looking_note(f"{p}-insight") for p in ["1", "2", "3", "4", "5", "6", "7", "8", "gender"]]
    for shape in chain._R8_SHAPES:
        assert sum(shape in n for n in notes) == 3
    assert "no forward-looking sentence" in chain._forward_looking_note("7.3")


def test_national_comparison_states_how_many_countries_are_compared():
    rows = [
        CountryVsNationalRate(country_code="KEN", portfolio_poverty_likelihood=30.0, national_poverty_rate=36.0, poorer_than_national=False),
        CountryVsNationalRate(country_code="MNE", portfolio_poverty_likelihood=5.0, national_poverty_rate=None),
    ]
    out = format_national_comparison(rows, ("IND", "KOS"))
    assert "4 survey countries" in out and "1 of the 4" in out
    assert "2 have no PPI-scored clients this wave (India, Kosovo)" in out
    assert "1 scored countries have no national poverty rate" in out
    assert "  - Kenya:" in out and "  - Montenegro:" in out
