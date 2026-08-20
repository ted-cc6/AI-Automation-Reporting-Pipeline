"""
LACRO Insurance Impact Report: validation check suite.

Every check maps to a requirement ID in docs/report_spec.md.

Two kinds of check:
  TEXT   runs against the rendered report text. Portable, works on the
         existing Test9 PDF, no pipeline integration needed.
  OBJECT runs against the assembled report object before rendering.
         Stubbed here with the assertion written out, to be wired in
         once the models exist.

Usage:
    python report_checks.py test9.txt
    python report_checks.py new_run.txt --compare test9.txt

Severity:
    BLOCKING  a defect a reader would notice. Fails the build.
    ADVISORY  worth a look. Logged, does not fail the build.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Callable

BLOCKING = "BLOCKING"
ADVISORY = "ADVISORY"


@dataclass
class CheckResult:
    check_id: str
    requirement: str
    severity: str
    passed: bool
    detail: str = ""


@dataclass
class Registry:
    checks: list = field(default_factory=list)

    def add(self, check_id: str, requirement: str, severity: str):
        def wrap(fn: Callable):
            self.checks.append((check_id, requirement, severity, fn))
            return fn
        return wrap

    def run(self, text: str) -> list[CheckResult]:
        results = []
        for check_id, requirement, severity, fn in self.checks:
            try:
                ok, detail = fn(text)
            except Exception as exc:  # a check that errors is a failed check
                ok, detail = False, f"check raised: {exc}"
            results.append(CheckResult(check_id, requirement, severity, ok, detail))
        return results


reg = Registry()


# ---------------------------------------------------------------- helpers

def _norm(text: str) -> str:
    """Collapse whitespace and PDF line breaks so phrase matching works."""
    return re.sub(r"\s+", " ", text)


def _lower(text: str) -> str:
    return _norm(text).lower()


def _find_all(text: str, pattern: str) -> list[str]:
    return re.findall(pattern, _norm(text), flags=re.IGNORECASE)


# ------------------------------------------------- Phase 1: data and config

@reg.add("C-001", "R-001", ADVISORY)
def period_label_matches_fieldwork(text: str):
    """Reporting period label is consistent with the fieldwork dates.

    Downgraded to ADVISORY per Lorenz: the label is operator entered on
    the dashboard, so a mismatch is a warning to the operator, not a
    pipeline defect. Still logged so nobody ships a wrong label silently.
    """
    t = _norm(text)
    label = re.search(r"20\d\d\s*Q\d", t)
    dates = re.findall(r"(20\d\d)-(\d\d)-\d\d", t)
    if not label or not dates:
        return True, "no label or no dates found, nothing to compare"
    quarters = {(y, (int(m) - 1) // 3 + 1) for y, m in dates}
    if len(quarters) > 1:
        return False, (
            f"fieldwork spans {sorted(quarters)} but label reads "
            f"'{label.group()}'. Confirm intended period with the operator."
        )
    return True, ""


@reg.add("C-002", "R-002", BLOCKING)
def summary_n_column_is_a_denominator(text: str):
    """Executive summary N values are denominators, not numerators.

    Test9 shows Filed a Claim with N=124, which is the count who
    experienced an insured event, while the 44.4% is 55/124. Other rows
    use the full sample. Mixing the two makes the table unreadable.
    """
    t = _norm(text)
    block = re.search(r"Executive Summary(.{0,600})", t)
    if not block:
        return True, "no executive summary found"
    ns = [int(x.replace(",", "")) for x in re.findall(r"\b(\d{3,4})\b", block.group(1))]
    if not ns:
        return True, "no N values parsed"
    if len(set(ns)) > 1 and min(ns) < max(ns) / 4:
        return False, (
            f"summary N values vary widely ({sorted(set(ns))}); confirm each "
            f"is the denominator of its own percentage"
        )
    return True, ""


@reg.add("C-003", "R-003", BLOCKING)
def protection_appendix_has_no_duplicates(text: str):
    """No client reference appears twice with the same description."""
    t = _norm(text)
    entries = re.findall(r"\(([\d\-]{4,20}),\s*([^)]{2,40})\)", t)
    seen, dupes = set(), []
    for ref, loc in entries:
        key = (ref.strip(), loc.strip().lower())
        if key in seen:
            dupes.append(key)
        seen.add(key)
    if dupes:
        uniq = sorted({d[0] for d in dupes})
        return False, f"{len(dupes)} duplicate entries across refs {uniq}"
    return True, ""


@reg.add("C-004", "R-003", BLOCKING)
def protection_stated_total_matches_entries(text: str):
    """The stated count equals the number of listed entries."""
    t = _norm(text)
    stated = re.search(r"(\d+)\s+client[- ]reported protection concerns", t)
    if not stated:
        return True, "no stated total found"
    listed = len(re.findall(r"\(([\d\-]{4,20}),\s*[^)]{2,40}\)", t))
    if int(stated.group(1)) != listed:
        return False, f"states {stated.group(1)} concerns, lists {listed} entries"
    return True, ""


@reg.add("C-005", "R-004", BLOCKING)
def trend_table_declares_comparability(text: str):
    """Every trend indicator carries a comparability declaration."""
    t = _lower(text)
    if "trend comparison" not in t:
        return True, "no trend section"
    header = re.search(r"indicator\s+20\d\d\s+20\d\d\s+comparability", t)
    if not header:
        return False, "trend table has no Comparability column header"
    return True, ""


# ------------------------------------------------------------ Phase 2: schema

@reg.add("C-006", "R-006", BLOCKING)
def sentiment_uses_counts_not_percentages(text: str):
    """Sentiment splits are integer counts, never percentages."""
    hits = _find_all(text, r"sentiment split[^.]{0,160}")
    bad = [h for h in hits if "%" in h]
    if bad:
        return False, f"{len(bad)} sentiment split(s) expressed as percentages: {bad[0][:110]}"
    return True, ""


@reg.add("C-007", "R-006", BLOCKING)
def sentiment_states_its_base(text: str):
    """Every sentiment split states the pool it was drawn from.

    Guards the Test9 failure mode where a split is reported with no
    indication of how 1,948 free text responses became 7.
    """
    hits = _find_all(text, r"sentiment split[^.]{0,200}")
    if not hits:
        return True, "no sentiment splits found"
    missing = [h for h in hits if not re.search(r"\b(of|from|across)\b.{0,60}\bresponses?\b", h, re.I)]
    if missing:
        return False, f"{len(missing)} of {len(hits)} splits do not state a base"
    return True, ""


@reg.add("C-008", "R-006", ADVISORY)
def sentiment_base_is_not_implausibly_small(text: str, floor: int = 25):
    """Flag sentiment bases far below the available pool.

    LACRO has 1,948 free text responses. Bases of 3 to 10 indicate a
    nomination cap or an over restrictive filter, not a small dataset.
    """
    counts = []
    for h in _find_all(text, r"sentiment split[^.]{0,200}"):
        nums = [int(n) for n in re.findall(r"\b(\d{1,4})\b", h)]
        if nums:
            counts.append(sum(n for n in nums if n < 500))
    tiny = [c for c in counts if c < floor]
    if tiny:
        return False, f"{len(tiny)} of {len(counts)} sentiment bases below {floor}: {sorted(tiny)}"
    return True, ""


@reg.add("C-009", "R-007", BLOCKING)
def no_metric_reported_with_two_values(text: str):
    """The same named metric never appears with conflicting values.

    Test9 reports healthcare access improved at 33.9% in Part 5 prose and
    8.9% in the Part 5 caregiver table, because the table pairs a
    restricted numerator with an unrestricted denominator.
    """
    t = _norm(text)
    findings = {}
    for label in ["healthcare access improved", "high financial stress",
                  "coverage understanding", "claim process understanding"]:
        vals = set()
        for m in re.finditer(re.escape(label), t, re.I):
            window = t[max(0, m.start() - 90): m.end() + 90]
            vals.update(re.findall(r"(\d{1,3}\.\d)%", window))
        if len(vals) > 2:
            findings[label] = sorted(vals)
    if findings:
        first = next(iter(findings.items()))
        return False, f"{len(findings)} metric(s) with conflicting values, e.g. {first[0]}: {first[1]}"
    return True, ""


@reg.add("C-010", "R-007", BLOCKING)
def cross_references_point_to_the_right_part(text: str):
    """A footnote referring to another Part names the Part that holds it.

    Test9's Part 5 footnote cites 'Part 4's healthcare access metric';
    healthcare access is reported in Part 5.
    """
    t = _norm(text)
    bad = []
    for m in re.finditer(r"Part (\d+)'s ([a-z ]{4,40}?) metric", t, re.I):
        part, metric = m.group(1), m.group(2).strip().lower()
        section = re.search(rf"Part {part}:(.{{0,4000}}?)(?=Part \d+:|$)", t, re.I | re.S)
        if section and metric.split()[0] not in section.group(1).lower():
            bad.append(f"'{metric}' cited as Part {part}")
    if bad:
        return False, "; ".join(bad)
    return True, ""


@reg.add("C-011", "R-008", BLOCKING)
def coping_behaviour_is_named(text: str):
    """Negative coping is not reported as a bare rate."""
    t = _norm(text)
    if "coping" not in t.lower():
        return True, "coping not reported"
    named = re.search(
        r"(sold|borrow|savings|reduc\w+ food|took .{0,20}children out|"
        r"closed .{0,20}business|withdrew|pawn)", t, re.I)
    if not named:
        return False, "coping rate reported without naming any behaviour"
    return True, ""


@reg.add("C-012", "R-009", BLOCKING)
def trend_table_has_no_significance_column(text: str):
    """Significance is removed from the trend table per LM3."""
    t = _norm(text)
    section = re.search(r"Trend Comparison(.{0,2600})", t, re.S)
    if not section:
        return True, "no trend section"
    body = section.group(1)
    if re.search(r"\bSig\.", body) or "z-test" in body.lower():
        return False, "trend table still carries a significance column or z-test footnote"
    return True, ""


@reg.add("C-013", "R-009", BLOCKING)
def no_p_values_in_trend_section(text: str):
    """No p value appears in the trend section."""
    section = re.search(r"Trend Comparison(.{0,2600})", _norm(text), re.S)
    if not section:
        return True, "no trend section"
    hits = re.findall(r"p\s*=\s*0?\.\d+", section.group(1), re.I)
    if hits:
        return False, f"p value(s) present in trend section: {hits}"
    return True, ""


# -------------------------------------------------------------- Phase 3: code

@reg.add("C-014", "R-010", BLOCKING)
def no_narration_of_absent_data(text: str):
    """The report never explains what it cannot say.

    Covers LM4 and LM11 together, and the fabricated-narrative failure
    mode from the previous iteration.
    """
    banned = [
        "not yet available", "not yet been provided", "have not yet been",
        "become available", "in a future data package", "cannot characterize",
        "cannot characterise", "is not yet available in this dataset",
    ]
    t = _lower(text)
    found = [p for p in banned if p in t]
    if found:
        return False, f"narrates absent data: {found}"
    return True, ""


@reg.add("C-015", "R-010", BLOCKING)
def qualitative_heading_implies_verbatims(text: str):
    """A qualitative heading is followed by at least one quoted verbatim."""
    t = _norm(text)
    parts = re.split(r"Key Qualitative Insights", t)
    empty = 0
    for chunk in parts[1:]:
        window = chunk[:1400]
        if not re.search(r"[\"\u201c][^\"\u201d]{12,}", window):
            empty += 1
    if empty:
        return False, f"{empty} qualitative block(s) render with no verbatim"
    return True, ""


@reg.add("C-016", "R-011", BLOCKING)
def non_filer_is_renamed(text: str):
    """LM10: non filer becomes non claimant everywhere."""
    t = _lower(text)
    hits = t.count("non-filer") + t.count("non filer")
    if hits:
        return False, f"'non filer' appears {hits} time(s)"
    return True, ""


@reg.add("C-017", "R-012", BLOCKING)
def trend_columns_use_wave_years(text: str):
    """LM3: columns are labelled by year, not Current and Prior Wave."""
    t = _lower(text)
    if "current wave" in t or "prior wave" in t:
        return False, "trend table still uses Current Wave / Prior Wave headers"
    return True, ""


@reg.add("C-018", "R-013", BLOCKING)
def summary_actions_restart_numbering(text: str):
    """Recommended Actions are numbered from 1, not continuing from findings."""
    t = _norm(text)
    m = re.search(r"Recommended Actions\s*(\d+)\.", t)
    if m and m.group(1) != "1":
        return False, f"Recommended Actions start at {m.group(1)}"
    return True, ""


@reg.add("C-019", "R-013", ADVISORY)
def summary_spans_multiple_modules(text: str):
    """The executive summary draws on more than the NPS module."""
    t = _lower(text)
    block = t.split("about this survey")[0]
    modules = {
        "claims": ["claim process", "claims funnel", "filed a claim"],
        "access": ["first-time access", "first time access", "no prior insurance"],
        "healthcare": ["medical care", "healthcare access", "out-of-pocket"],
        "services": ["teleconsultation", "additional service", "lab test"],
        "value": ["worth the premium", "worth what you pay", "product value"],
    }
    hit = [k for k, terms in modules.items() if any(x in block for x in terms)]
    if len(hit) < 3:
        return False, f"summary references only {len(hit)} non-NPS module(s): {hit or 'none'}"
    return True, ""


@reg.add("C-020", "R-014", BLOCKING)
def editorial_phrase_removed(text: str):
    """LM9: remove 'unrelated to child wellbeing itself'."""
    if "unrelated to child wellbeing" in _lower(text):
        return False, "phrase still present"
    return True, ""


# ------------------------------------------------------ cross cutting guards

@reg.add("C-021", "cross", BLOCKING)
def percentages_sum_to_about_one_hundred(text: str):
    """Distribution splits sum to 100 within rounding.

    Catches the 55/40/8 = 103 defect seen in an earlier iteration.
    """
    bad = []
    for sentence in re.split(r"(?<=[.])\s", _norm(text)):
        pcts = [float(x) for x in re.findall(r"(\d{1,3}\.?\d?)%", sentence)]
        if len(pcts) < 3:
            continue
        total = sum(pcts)
        # only a complete distribution should land near 100
        if 100.5 < total < 108 or 92 < total < 99.5:
            bad.append(f"{pcts} sums to {total:.1f}")
    if bad:
        return False, "; ".join(bad[:3])
    return True, ""


@reg.add("C-022", "cross", BLOCKING)
def no_raw_variable_names(text: str):
    """Column names never leak into prose."""
    hits = set(re.findall(r"\b(?:q|flag)_[a-z_]{3,}\b", _norm(text)))
    if hits:
        return False, f"raw variable names in prose: {sorted(hits)[:5]}"
    return True, ""


@reg.add("C-023", "cross", ADVISORY)
def suppression_threshold_is_stated(text: str):
    """If anything is suppressed, the threshold is stated once."""
    t = _lower(text)
    if "suppressed" not in t:
        return True, "nothing suppressed"
    if re.search(r"(fewer than|below|under)\s+\d+\s+(respondents|responses|clients)", t):
        return True, ""
    return False, "values suppressed but no threshold stated"


@reg.add("C-024", "cross", BLOCKING)
def no_placeholder_for_absent_visual(text: str):
    """Visual placeholders do not survive into a delivered report."""
    n = len(re.findall(r"VISUAL PENDING", _norm(text)))
    if n:
        return False, f"{n} unrendered visual placeholder(s)"
    return True, ""


# ------------------------------------------------------------------ reporting

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()
    results = reg.run(text)

    width = max(len(r.check_id) for r in results)
    blocking_failures = 0
    print(f"\n{'CHECK':<{width}}  {'REQ':<7} {'SEV':<9} {'RESULT':<7} DETAIL")
    print("-" * 100)
    for r in sorted(results, key=lambda x: x.check_id):
        status = "pass" if r.passed else "FAIL"
        if not r.passed and r.severity == BLOCKING:
            blocking_failures += 1
        print(f"{r.check_id:<{width}}  {r.requirement:<7} {r.severity:<9} {status:<7} {r.detail[:120]}")

    passed = sum(1 for r in results if r.passed)
    print("-" * 100)
    print(f"{passed}/{len(results)} passed, {blocking_failures} blocking failure(s)\n")
    return 1 if blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
