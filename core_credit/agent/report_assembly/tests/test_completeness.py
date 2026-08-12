from typing import Optional

import pytest
from pydantic import BaseModel, Field

from report_assembly.completeness import MetaTextLeakError, completeness_report, find_meta_text_leaks, raise_on_meta_text_leaks
from schemas.common import WrittenText


def _wt(subsection_id: str, within_cap: bool = True, ungrounded=None) -> WrittenText:
    return WrittenText(
        subsection_id=subsection_id, text="text", word_count=10, within_cap=within_cap,
        ungrounded_percentages=ungrounded or [],
    )


class _Sub(BaseModel):
    a: Optional[WrittenText] = None


class _Fake(BaseModel):
    direct: Optional[WrittenText] = None
    nested: Optional[_Sub] = None
    listed: list[_Sub] = Field(default_factory=list)


def test_clean_report_has_no_issues():
    report = _Fake(direct=_wt("1"), nested=_Sub(a=_wt("2")), listed=[_Sub(a=_wt("3"))])
    assert completeness_report(report) == []


def test_missing_written_text_field_is_flagged():
    report = _Fake(direct=None, nested=_Sub(a=_wt("2")))
    issues = completeness_report(report)
    assert any("direct" in i and "MISSING" in i for i in issues)


def test_over_cap_is_flagged_with_word_count():
    report = _Fake(direct=_wt("1", within_cap=False))
    issues = completeness_report(report)
    assert any("direct" in i and "10 words" in i for i in issues)


def test_ungrounded_percentages_are_flagged():
    report = _Fake(direct=_wt("1", ungrounded=["99%"]))
    issues = completeness_report(report)
    assert any("direct" in i and "99%" in i for i in issues)


def test_finds_issues_nested_inside_a_list():
    report = _Fake(listed=[_Sub(a=_wt("1", within_cap=True)), _Sub(a=None)])
    issues = completeness_report(report)
    assert any("listed[1].a" in i and "MISSING" in i for i in issues)


def test_within_cap_and_grounded_written_text_produces_nothing():
    report = _Fake(direct=_wt("1"))
    assert completeness_report(report) == []


def _wt_text(subsection_id: str, text: str) -> WrittenText:
    return WrittenText(subsection_id=subsection_id, text=text, word_count=len(text.split()), within_cap=True)


def test_find_meta_text_leaks_clean_report_returns_empty():
    report = _Fake(direct=_wt_text("1", "Clean, finished analytical prose with no issues."))
    assert find_meta_text_leaks(report) == []


def test_find_meta_text_leaks_flags_a_real_incident():
    # Regression test for the real incident: this exact sentence shipped into a production
    # report's Agency insight.
    text = 'A female client from Ghana said "[quote placeholder removed]" -- actually omitting fabricated text.'
    report = _Fake(direct=_wt_text("1", text))
    leaks = find_meta_text_leaks(report)
    assert len(leaks) >= 1
    assert any("placeholder" in leak for leak in leaks)


def test_find_meta_text_leaks_checks_nested_and_listed_fields():
    report = _Fake(
        nested=_Sub(a=_wt_text("2", "This section discusses fabricated evidence tampering.")),
        listed=[_Sub(a=_wt_text("3", "Clean prose."))],
    )
    leaks = find_meta_text_leaks(report)
    assert any("nested.a" in leak for leak in leaks)


def test_raise_on_meta_text_leaks_raises_when_dirty():
    report = _Fake(direct=_wt_text("1", "This response includes a placeholder value."))
    with pytest.raises(MetaTextLeakError):
        raise_on_meta_text_leaks(report)


def test_raise_on_meta_text_leaks_passes_when_clean():
    report = _Fake(direct=_wt_text("1", "Clean, finished analytical prose."))
    raise_on_meta_text_leaks(report)  # must not raise
