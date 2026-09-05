from typing import Optional

import pytest
from pydantic import BaseModel, Field

from report_assembly.completeness import (
    MetaTextLeakError,
    MissingCaregiverScopeError,
    UnknownThemeNameError,
    completeness_report,
    find_dangling_attributions,
    find_meta_text_leaks,
    find_missing_caregiver_scope,
    find_unknown_theme_references,
    raise_on_meta_text_leaks,
    raise_on_missing_caregiver_scope,
    raise_on_unknown_theme_references,
)
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


# CC-044: the phrase list alone missed this real second incident -- none of the four original
# patterns match any word of it.

_SIX_INSIGHT_DEFECT = (
    "A female client in Kenya, Caregiver, described this kind of standing shift directly. A "
    "male client in India, Caregiver, and a female client in Ghana each pointed to household "
    "and community-level changes tied to their loan use, though the exact phrasing should be "
    "drawn from the verbatim pool rather than summarized here without quotation."
)


def test_find_meta_text_leaks_catches_the_six_insight_defect_by_phrase():
    report = _Fake(direct=_wt_text("1", _SIX_INSIGHT_DEFECT))
    leaks = find_meta_text_leaks(report)
    assert any("should be drawn from" in leak for leak in leaks)
    assert any("verbatim pool" in leak for leak in leaks)


def test_raise_on_meta_text_leaks_still_raises_on_the_six_insight_defect():
    # CC-058: the structural check moved out of this gate, but the six-insight text must still
    # fail the build overall -- it does, via the phrase list alone (sentence 2 contains four
    # separate hits), independent of what the dangling-attribution check does with sentence 1.
    report = _Fake(direct=_wt_text("1", _SIX_INSIGHT_DEFECT))
    with pytest.raises(MetaTextLeakError):
        raise_on_meta_text_leaks(report)


# CC-058: find_dangling_attributions replaces the old "no quote nearby" structural check --
# see its own docstring in completeness.py for why. Downgraded to a soft completeness issue,
# so these test find_dangling_attributions and completeness_report directly, not the raise gate.

def test_find_dangling_attributions_flags_the_guatemala_incident():
    # Confirmed real, live: this shipped during a real regeneration. No content at all after
    # the reporting verb beyond a bare "this" and one adverb.
    text = "A female client in Guatemala described this directly."
    report = _Fake(direct=_wt_text("1", text))
    issues = find_dangling_attributions(report)
    assert any("Guatemala" in i or "dangling" in i for i in issues)


def test_find_dangling_attributions_does_not_fire_on_the_rwanda_paraphrase():
    # Confirmed real, live, same regeneration batch as Guatemala above: legitimate, specific,
    # sanctioned paraphrase with no quote at all -- "client"+"in" (the rule's own intended
    # matching scope), but real content (a gerund-headed action), so not dangling.
    text = (
        "A male client in Rwanda, Climate-shock-affected, reported selling land as a coping "
        "route, a reminder that asset sales remain part of the reported response even where "
        "savings behavior looks broadly positive."
    )
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_find_dangling_attributions_does_not_fire_on_a_real_citation():
    text = (
        'A Female client in KEN, a Caregiver and Female HH head, described "Harassment from '
        'Agents and Branch Managers, don\'t have patience and they don\'t listen when you have '
        'a problem."'
    )
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_find_dangling_attributions_does_not_fire_on_generic_country_mention():
    text = "Kenya's 35.0% rests on only 90 of 271 clients scored, well below the low-N threshold."
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_find_dangling_attributions_does_not_fire_when_the_quote_follows_two_sentences_later():
    text = (
        "A female client in Kenya, Caregiver, described her experience with the loan officer. "
        "She has run a small tailoring shop for six years now. "
        'She said, "Business has really picked up since the loan."'
    )
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_find_dangling_attributions_does_not_fire_when_the_quote_precedes_the_attribution():
    text = (
        '"Harassment from Agents and Branch Managers, they don\'t listen," said a female '
        "client in Kenya, Caregiver."
    )
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_find_dangling_attributions_does_not_fire_on_unquoted_paraphrase_of_a_caregiver():
    # "caregiver"/"from", not "client"/"in" -- outside _CLIENT_ATTRIBUTION_RE's scope entirely,
    # so never reaches the dangling check at all.
    text = (
        "A female caregiver from Malawi, affected by a climate shock, described planting "
        "drought-resistant crops as her way of adapting to the strain, a frequently reported "
        "reason clients gave for managing shocks without resorting to more severe cuts."
    )
    report = _Fake(direct=_wt_text("1", text))
    assert find_dangling_attributions(report) == []


def test_completeness_report_includes_dangling_attributions():
    # CC-058: recorded alongside the other soft/residual completeness flags, not raised.
    text = "A female client in Guatemala described this directly."
    report = _Fake(direct=_wt_text("1", text))
    issues = completeness_report(report)
    assert any("dangling attribution" in i for i in issues)


def test_raise_on_meta_text_leaks_does_not_raise_on_a_dangling_attribution_alone():
    # CC-058: downgraded from a hard gate -- a dangling attribution with no phrase-list hit
    # must not stop the build.
    text = "A female client in Guatemala described this directly."
    report = _Fake(direct=_wt_text("1", text))
    raise_on_meta_text_leaks(report)  # must not raise


class _ThemeScoreFake(BaseModel):
    theme_name: str


class _ExecSummaryFake(BaseModel):
    analysis_text: Optional[WrittenText] = None


class _ReportWithExecSummary(BaseModel):
    executive_summary: Optional[_ExecSummaryFake] = None


def test_find_unknown_theme_references_flags_the_real_incident():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Client Wellbeing outcomes anchor this year's results.")
        )
    )
    issues = find_unknown_theme_references(report)
    assert any("Client Wellbeing" in i and "Child Wellbeing" in i for i in issues)


def test_find_unknown_theme_references_passes_for_the_real_theme_name():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Child Wellbeing outcomes anchor this year's results.")
        )
    )
    assert find_unknown_theme_references(report) == []


def test_find_unknown_theme_references_handles_missing_executive_summary():
    report = _ReportWithExecSummary(executive_summary=None)
    assert find_unknown_theme_references(report) == []


def test_raise_on_unknown_theme_references_raises_when_fabricated():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Client Wellbeing outcomes anchor this year's results.")
        )
    )
    with pytest.raises(UnknownThemeNameError):
        raise_on_unknown_theme_references(report)


def test_find_missing_caregiver_scope_flags_the_real_incident():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Child Wellbeing is strong at 93.5%.")
        )
    )
    issues = find_missing_caregiver_scope(report)
    assert any("Child Wellbeing" in i for i in issues)


def test_find_missing_caregiver_scope_passes_when_scope_is_stated():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Child Wellbeing is strong at 93.5% among caregivers.")
        )
    )
    assert find_missing_caregiver_scope(report) == []


def test_find_missing_caregiver_scope_does_not_fire_on_other_themes():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Financial Access sits at 43.9%. Agency reads solidly at 85.1%.")
        )
    )
    assert find_missing_caregiver_scope(report) == []


def test_raise_on_missing_caregiver_scope_raises_when_unscoped():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Child Wellbeing is strong at 93.5%.")
        )
    )
    with pytest.raises(MissingCaregiverScopeError):
        raise_on_missing_caregiver_scope(report)


def test_raise_on_missing_caregiver_scope_passes_when_clean():
    report = _ReportWithExecSummary(
        executive_summary=_ExecSummaryFake(
            analysis_text=_wt_text("executive-summary", "Among caregivers, Child Wellbeing is strong at 93.5%.")
        )
    )
    raise_on_missing_caregiver_scope(report)  # must not raise
