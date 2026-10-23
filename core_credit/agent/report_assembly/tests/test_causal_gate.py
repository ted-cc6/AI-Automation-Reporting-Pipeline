"""CC-086: the causal-language lint as an enforcing gate -- a single writer rewrite, then a
hard stop at assembly. Fixture sentences are real generated text: the three hard-tier hits in
local-cc066, and the Part 8 insight sentence the Step 6 regeneration produced."""
from typing import Optional

import pytest
from pydantic import BaseModel

from report_assembly.completeness import (
    CausalLanguageError,
    completeness_report,
    find_causal_language,
    raise_on_causal_language,
)
from schemas.common import WrittenText
from writer.chain import _writer_violations

CC066_HARD_HITS = {
    "2.2": "Stronger-than-national poverty targeting appears in Honduras (11.8% vs. 9.2%) and Senegal (16.7% vs. 3.6%).",
    "6.1": 'Our 70.1% figure is far above the MFI Index benchmark of 32.0%, which uses a stricter "all financial goals" definition.',
    "7.4": "This can be read as realized preparedness among those who actually faced a shock.",
}
STEP6_SHAPING = (
    "These reported reasons show that staff conduct and pricing sit on both sides of the ledger, "
    "shaping whether clients lean toward recommending or not."
)


class _Report(BaseModel):
    a: Optional[WrittenText] = None
    b: Optional[WrittenText] = None
    c: Optional[WrittenText] = None


def _wt(subsection_id: str, text: str) -> WrittenText:
    return WrittenText(subsection_id=subsection_id, text=text, word_count=len(text.split()), within_cap=True)


def _cc066_report() -> _Report:
    return _Report(**{field: _wt(sid, text) for field, (sid, text) in zip("abc", CC066_HARD_HITS.items())})


def test_the_three_real_cc066_hits_fail_the_gate():
    issues = find_causal_language(_cc066_report())
    # 7.4's sentence carries two hard phrases since "realized preparedness" joined the list (Step 8).
    assert len(issues) == 4
    assert any("[poverty targeting]" in i and "(2.2)" in i for i in issues)
    assert any("[far above the mfi index]" in i and "(6.1)" in i for i in issues)
    assert any("[can be read as]" in i and "(7.4)" in i for i in issues)
    assert any("[realized preparedness]" in i and "(7.4)" in i for i in issues)
    with pytest.raises(CausalLanguageError, match="4 causal or overclaiming phrase"):
        raise_on_causal_language(_cc066_report())


def test_approved_wording_passes_the_gate():
    report = _Report(
        a=_wt("2.2", "Client poverty likelihood is higher than the national rate in Honduras, consistent with relatively pro-poor client reach."),
        b=_wt("6.1", "Our 70.1% figure is higher than the MFI Index benchmark of 32.0%."),
        c=_wt("8.2", 'Good service is a commonly cited reason, and one client said "the loan drives my business".'),
    )
    raise_on_causal_language(report)  # must not raise -- the quoted client words are not counted


def test_review_tier_goes_to_completeness_report_and_never_raises():
    report = _Report(a=_wt("gender-scorecard", "Women face an easier alternative-lender landscape."))
    raise_on_causal_language(report)
    issues = completeness_report(report)
    assert any("review wording [landscape]" in i for i in issues)


def test_writer_rewrite_is_triggered_and_names_the_phrase():
    violations = _writer_violations(STEP6_SHAPING, word_cap=200, pool=[])
    assert len(violations) == 1
    assert '"shaping" in:' in violations[0]
    assert "approved wording" in violations[0]


def test_writer_rewrite_not_triggered_by_review_tier_or_quotes():
    assert _writer_violations("Low clarity is signaling a need to review client understanding.", word_cap=200, pool=[]) == []
    # (With no verbatim pool the quote itself is flagged as ungrounded -- a separate check.)
    violations = _writer_violations('One client said "this loan lifts my family".', word_cap=200, pool=[])
    assert not any("causal" in v for v in violations)
