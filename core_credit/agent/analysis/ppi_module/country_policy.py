"""Per-country reporting decisions that are policy, not something derivable from the reference data.

These came out of a direct discussion with VisionFund's Impact team about
this quarter's report (2026Q2): India's PPI stays excluded (a standing
policy carried over from the FY25 AIM dataset work, confirmed as still
applicable here), Vietnam is reported on national percentiles rather than
$-a-day lines, and Kosovo/Mali/Montenegro/Mongolia are NA this wave with a
footnote -- consistent with the same four countries being NA in last year's
figures too, so this is an established pattern, not a new gap.

Everyone not listed here falls through to the default: score whichever of
the template's three headline lines ($1.90/2011 PPP, $2.15/2017 PPP,
$3.20/2011 PPP) their guide actually has points for -- "show whatever line
they do have," per that same discussion.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, Optional

TARGET_LINES = ["USD190day2011PPP", "USD215day2017PPP", "USD320day2011PPP"]


@dataclass(frozen=True)
class CountryPPIPolicy:
    status: Literal["ok", "not_available"] = "ok"
    reason: Optional[str] = None
    metric_type: Literal["dollar_line", "percentile"] = "dollar_line"
    lines: Optional[list] = None  # explicit override; None => auto-detect from TARGET_LINES


NOT_AVAILABLE: dict = {
    "IND": CountryPPIPolicy(
        status="not_available",
        reason="Excluded by VisionFund policy this wave (carried over from the FY25 AIM dataset decision).",
    ),
    "KOS": CountryPPIPolicy(
        status="not_available",
        reason="No PPI responses collected and no usable scorecard this wave (consistent with prior waves).",
    ),
    "MLI": CountryPPIPolicy(
        status="not_available",
        reason="No PPI responses collected and no usable scorecard this wave (consistent with prior waves).",
    ),
    "MNE": CountryPPIPolicy(
        status="not_available",
        reason="No PPI responses collected this wave (consistent with prior waves).",
    ),
    "MNG": CountryPPIPolicy(
        status="not_available",
        reason=(
            "No PPI responses collected this wave -- every client's PPI answer fields are "
            "blank, so none could be scored. The MNG scorecard itself is valid (guide MNG2016, "
            "the one 12-question guide in the workbook). The response data is simply absent."
        ),
    ),
}

OVERRIDES: dict = {
    "VNM": CountryPPIPolicy(
        metric_type="percentile",
        lines=["Bottom20thPercentile", "Bottom40thPercentile", "Bottom60thPercentile", "Bottom80thPercentile"],
    ),
}


def policy_for(country_code: str) -> CountryPPIPolicy:
    if country_code in NOT_AVAILABLE:
        return NOT_AVAILABLE[country_code]
    if country_code in OVERRIDES:
        return OVERRIDES[country_code]
    return CountryPPIPolicy()


# pipeline.py::score_country builds the KEN/ZMB partial-status reason as one sentence that
# bundles a fixable scorecard label typo with ordinary incomplete responses, reading as though
# the typo drove the whole exclusion (a reviewer misread it exactly that way). CC-025 put the
# real per-cause counts on CountryPovertyResult (n_unscored_label_conflict / _incomplete); this
# rewrites the footnote entry to use them. The regex only pulls the question number(s) out of
# that sentence -- coupled to its wording, keep in sync if pipeline.py changes it.
_LABEL_CONFLICT_RE = re.compile(r"Questions?\s+([\d,\s]+?)\s+of the PPI scorecard")


def _footnote_entry(r) -> str:
    if not (r.n_unscored_label_conflict or r.n_unscored_incomplete):
        return f"{r.country_code}: {r.status_reason}"
    m = _LABEL_CONFLICT_RE.search(r.status_reason or "")
    questions = m.group(1).strip().rstrip(",") if m else "the affected question"
    total = r.n_unscored_label_conflict + r.n_unscored_incomplete
    return (
        f"{r.country_code}: {total} of {r.n_total} clients unscored this wave, from two separate "
        f"and unrelated problems. (1) {r.n_unscored_label_conflict} from a source-workbook label "
        f"typo on PPI question {questions}: two answer options were given the same letter, so a "
        f"client who chose it cannot be scored -- fixable upstream in PPI_scorecards.xlsx. "
        f"(2) {r.n_unscored_incomplete} from incomplete PPI responses on other questions, a "
        f"data-collection gap unrelated to the typo"
    )


def na_footnote(results) -> Optional[str]:
    """The single PPI-coverage footnote the template asks for: one entry per country carrying a
    status_reason. That spans four situations -- not collected, no usable scorecard, excluded by
    policy, and scored but only partially (Kenya, Zambia, Myanmar this wave) -- so the opening is
    neutral coverage language, not "not available". Kenya/Zambia get their two causes split out
    (see _footnote_entry).
    """
    entries = [_footnote_entry(r) for r in results if r.status_reason]
    if not entries:
        return None
    return "PPI scoring coverage by country this wave -- " + "; ".join(entries)
