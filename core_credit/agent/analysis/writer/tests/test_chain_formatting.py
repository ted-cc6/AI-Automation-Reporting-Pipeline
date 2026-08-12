from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim
from writer.chain import _format_verbatim_pool, _format_verbatim_profile, _pool_verbatims, _writer_violations


def test_format_verbatim_profile_includes_country_and_segment_tags():
    v = Verbatim(
        quote="test quote",
        gender="Female",
        age=34,
        country="ECU",
        loan_cycle=2,
        branch="Quito Branch",
        segment_tags=["Caregiver", "Climate-shock-affected"],
        source_field="test_field",
    )
    profile = _format_verbatim_profile(v)
    assert "Female" in profile
    assert "ECU" in profile
    assert "age 34" in profile
    assert "loan cycle 2" in profile
    assert "Quito Branch" in profile
    assert "Caregiver" in profile
    assert "Climate-shock-affected" in profile


def test_format_verbatim_profile_handles_missing_fields_gracefully():
    v = Verbatim(quote="test quote", source_field="test_field")
    profile = _format_verbatim_profile(v)
    assert "unknown gender" in profile
    assert "unknown country" in profile
    assert "unknown branch" in profile


def _qualitative_with_two_themes() -> QualitativeSynthesis:
    return QualitativeSynthesis(
        source_field="test",
        base_n=10,
        themes=[
            ThemeFinding(
                theme="Theme A",
                frequency=5,
                share_of_respondents=0.5,
                representative_verbatims=[
                    Verbatim(quote="quote one", country="ECU", source_field="f"),
                    Verbatim(quote="quote two", country="RWA", source_field="f"),
                ],
            ),
            ThemeFinding(
                theme="Theme B",
                frequency=3,
                share_of_respondents=0.3,
                representative_verbatims=[Verbatim(quote="quote three", country="KEN", source_field="f")],
            ),
        ],
    )


def test_pool_verbatims_flattens_across_themes_preserving_order():
    pool = _pool_verbatims(_qualitative_with_two_themes())
    assert [v.quote for v in pool] == ["quote one", "quote two", "quote three"]


def test_pool_verbatims_empty_when_no_themes():
    empty = QualitativeSynthesis(source_field="test", base_n=0, themes=[])
    assert _pool_verbatims(empty) == []


def test_format_verbatim_pool_numbers_entries_matching_pool_order():
    pool = _pool_verbatims(_qualitative_with_two_themes())
    text = _format_verbatim_pool(pool)
    assert "[0]" in text and "quote one" in text
    assert "[1]" in text and "quote two" in text
    assert "[2]" in text and "quote three" in text
    # ID order in the text must match pool index order, so ID resolution stays correct
    assert text.index("[0]") < text.index("[1]") < text.index("[2]")


def test_writer_violations_clean_text_passes():
    assert _writer_violations("A short, clean sentence with no issues.", word_cap=10, pool=[]) == []


def test_writer_violations_flags_over_cap():
    text = "one two three four five six seven eight nine ten eleven"
    violations = _writer_violations(text, word_cap=10, pool=[])
    assert any("11 words" in v and "10-word cap" in v for v in violations)


def test_writer_violations_flags_em_dash_and_semicolon():
    # Regression test for a real incident: a production report carried 297 em dashes and 15
    # semicolons across its insight paragraphs with nothing ever checking for either.
    text = "Clients improved significantly — especially women; the gap narrowed."
    violations = _writer_violations(text, word_cap=100, pool=[])
    assert any("1 em dash" in v and "1 semicolon" in v for v in violations)


def test_writer_violations_reports_cap_and_punctuation_together():
    text = "one two three four — five; six"
    violations = _writer_violations(text, word_cap=3, pool=[])
    assert len(violations) == 2


def test_writer_violations_flags_a_fabricated_quote_for_deletion():
    # Regression test for a real incident: a production report shipped "A female client from
    # Ghana said \"[quote placeholder removed]\" -- actually omitting fabricated text" straight
    # into the deliverable. Detection existed (ungrounded_quotes) but nothing acted on it.
    text = 'A female client from Ghana said "this is a fabricated quote nobody actually said."'
    violations = _writer_violations(text, word_cap=100, pool=[])
    assert any("must be deleted entirely" in v for v in violations)


def test_writer_violations_flags_a_real_quote_with_wrong_country():
    v = Verbatim(quote="I would not recommend them because rates are too high for my needs.", country="MWI", source_field="f")
    text = 'A female Ugandan client in Malawi said, "I would not recommend them because rates are too high for my needs."'
    violations = _writer_violations(text, word_cap=100, pool=[v])
    assert any("wrong country" in v for v in violations)


def test_writer_violations_passes_a_correctly_attributed_real_quote():
    v = Verbatim(quote="I would not recommend them because rates are too high for my needs.", country="MWI", source_field="f")
    text = 'A female client in Malawi said, "I would not recommend them because rates are too high for my needs."'
    assert _writer_violations(text, word_cap=100, pool=[v]) == []
