"""
LACRO Insurance Impact Report: validation check suite.

Every check maps to a requirement ID in docs/report_spec.md.

Two kinds of check:
  TEXT   runs against the rendered report text. Portable, works on the
         existing Test9 PDF, no pipeline integration needed.
  OBJECT runs against the assembled report object before rendering.
         Stubbed here with the assertion written out, to be wired in
         once the models exist.

One exception to the TEXT/OBJECT split: C-002 (R-002) also reads
generation/report_spec.yaml directly, not just rendered text. That
requirement is about a config-driven metric list matching what actually
renders, so the check needs the config to know what "matching" means --
see C-002's own docstring.

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
from pathlib import Path
from typing import Callable

import yaml

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


def _norm_keep_lines(text: str) -> str:
    """Like _norm(), but preserves line breaks -- collapses runs of spaces
    and tabs only. A newline is a far more robust, source-format-
    independent row-boundary signal than any label or heading text this
    file could otherwise guess at; see _summary_table_row_spans(), the one
    place that needs this instead of _norm()."""
    return re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n").replace("\r", "\n"))


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


_SPEC_PATH = Path(__file__).resolve().parent.parent / "generation" / "report_spec.yaml"


def _resolve_base_label(base_label, report_scope: "str | None"):
    """Same resolution rule as generation/orchestrator.py's
    _resolve_population() -- a plain value (including None) is used as-is;
    a dict is looked up by this run's report_scope, falling back to
    "default". Duplicated here rather than imported so this file keeps no
    runtime dependency on the generation/ package -- see C-002's docstring
    for why this check reads report_spec.yaml at all despite that."""
    if not isinstance(base_label, dict):
        return base_label
    if report_scope in base_label:
        return base_label[report_scope]
    return base_label.get("default")


def _load_summary_metrics() -> list:
    """Raw executive_summary.metrics entries from report_spec.yaml, in
    order. [] if the file or key is missing."""
    if not _SPEC_PATH.exists():
        return []
    spec = yaml.safe_load(_SPEC_PATH.read_text(encoding="utf-8")) or {}
    return spec.get("executive_summary", {}).get("metrics", [])


def _summary_metric_specs(report_scope: "str | None") -> list:
    """[(label, expects_base_label), ...] for every configured
    executive_summary metric, in report_spec.yaml order, resolved against
    report_scope exactly as generation/executive_summary.py's
    headline_numbers() resolves it at render time."""
    return [
        (m["label"], bool(_resolve_base_label(m.get("base_label"), report_scope)))
        for m in _load_summary_metrics()
    ]


def _summary_metric_labels() -> list:
    """Just the label strings from report_spec.yaml's executive_summary.
    metrics -- report_scope-independent (the label itself never varies by
    scope, only base_label does). Used by C-009/C-019 to keep the summary
    table's own row labels out of checks whose job is narrative prose, not
    the deterministic table."""
    return [m["label"] for m in _load_summary_metrics()]


def _summary_table_row_spans(text: str) -> "tuple[str, list]":
    """(normalized_text, spans) -- normalized_text is text run through
    _norm_keep_lines(), NOT this file's usual _norm() (which also
    collapses newlines); spans are offsets into normalized_text
    specifically. Callers that need this table's structure should adopt
    normalized_text as their own working text rather than maintaining a
    second, independently-_norm()-ed copy with different offsets (a
    newline and a run of spaces are both one whitespace run to _norm(),
    but not necessarily the same length after collapsing, so offsets from
    one do not reliably index into the other).

    spans: [(label, row_start, cell_start, cell_end), ...] for every
    configured executive_summary metric found in the Executive Summary
    table. row_start is the label's own match position; cell_start is
    right after it, where the Value/N/Base cell content begins; cell_end
    bounds that cell at its own line break, or -- if tighter -- the next
    known label, a known section heading, or a genuine sentence-ending
    period (not the decimal point inside this row's own Value cell, e.g.
    "36.1%"). [] if no "Executive Summary" heading or no configured labels
    are found. Matching is case-insensitive.

    The line-break bound is the important one, caught running this check
    against the real Test9.docx: its original table's 4th row is "Filed a
    Claim", a metric this session's agreed set no longer tracks, so none
    of the known-label/heading/period boundaries below could recognize it
    at all -- "First-Time Access to Insurance"'s cell bled straight
    through "Filed a Claim | 44.4% | 124" into the narrative paragraph
    that followed, a false FAIL with a garbled detail message rather than
    the honest "this table predates the new metric set" a stale report
    like Test9 should actually produce. A table row is reliably one line
    in any reasonable rendering of a Word table -- python-docx's own
    iter_inner_content() extraction, a "Save As Plain Text" export, a PDF
    copy-paste -- even when a row's own columns collapse onto that one
    line, so a newline is a far more robust row-boundary signal than
    knowing every label this session's config happens to track.

    Bounded to the Executive Summary section itself -- "About This
    Survey" always immediately follows it (see tests/test_assembler.py's
    test_executive_summary_precedes_about_this_survey). Without this, a
    label like "Claim Process Understanding" could match wherever it next
    appears anywhere in a full multi-part report (its own Part 1
    subsection, pages later), not the summary table row.

    Shared by three checks with three different needs against the same
    table: C-002 reads inside each row's cell to check its base label;
    C-009 excludes anything inside a row from its narrative-conflict scan
    (a table row is not a sentence); C-019 excludes the whole table from
    what counts as "the narrative."
    """
    nt = _norm_keep_lines(text)
    heading = re.search(r"Executive Summary", nt, re.I)
    labels = _summary_metric_labels()
    if not heading or not labels:
        return nt, []
    block_start = heading.end()
    block_end_match = re.search(r"About This Survey", nt[block_start:], re.I)
    block_end = block_start + block_end_match.start() if block_end_match else min(len(nt), block_start + 3000)
    region = nt[block_start:block_end]
    spans = []
    for label in labels:
        m = re.search(re.escape(label), region, re.I)
        if not m:
            continue  # row omitted entirely (e.g. not_applicable) -- nothing to span
        row_start = block_start + m.start()
        cell_start = block_start + m.end()
        line_end = nt.find("\n", cell_start)
        if line_end == -1 or line_end > block_end:
            line_end = block_end
        row_text = nt[cell_start:line_end]
        end = len(row_text)
        for boundary in [l for l in labels if l != label] + [
            "Data Availability", "Top Findings", "Recommended Actions",
        ]:
            idx = row_text.lower().find(boundary.lower())
            if idx != -1:
                end = min(end, idx)
        sentence_end = re.search(r"(?<!\d)\.(?!\d)", row_text)
        if sentence_end:
            end = min(end, sentence_end.start())
        spans.append((label, row_start, cell_start, cell_start + end))
    return nt, spans


@reg.add("C-002", "R-002", BLOCKING)
def summary_base_label_matches_config(text: str):
    """Every Executive Summary row's base-label presence matches
    report_spec.yaml's executive_summary.metrics config for this report's
    scope -- reads generation/report_spec.yaml directly, the one departure
    from this file's text-only pattern (see module docstring).

    Superseded heuristic (session 1, before this check existed in this
    form): flagged wide variance in the table's N column as a proxy for "N
    might be a numerator, not a denominator." That premise was wrong --
    session-2 orientation traced every row's n_path into
    analysis_engine/stats.py and found each one was already its own
    percentage's correct denominator (Filed a Claim's N=124 IS
    filed_claim_base_n, the denominator of 44.4% = 55/124). The actual
    defect was that a restricted-base row (e.g. Children's Wellbeing, on
    child_wellbeing_base) rendered identically to a full-sample row, with
    nothing telling a reader the two apart.

    A tempting middle ground -- compare each row's N against a "full
    sample" figure pulled from elsewhere in the text -- was considered and
    rejected: ordinary item non-response shrinks even a genuine full-sample
    row's N below the report's total respondent count, so N-vs-N comparison
    cannot tell "this row is restricted" apart from "a few people skipped
    this question," and would flag real full-sample rows as false
    positives. Checking against report_spec.yaml's own base_label
    declaration side-steps that entirely: whether a row is expected to
    carry base text is a config fact, not something inferred from
    arithmetic on the rendered numbers.

    Correctly (and expectedly) FAILS against Test9: Test9 predates R-002
    entirely -- its table has no Base column at all -- so every row this
    check finds correctly reads as base-label-absent, disagreeing with
    config for the two rows (Worth the Premium and Children's Wellbeing)
    that should carry one. That is the right answer for a report that has
    not been regenerated since the metric-set change, not a check defect.
    """
    nt, spans = _summary_table_row_spans(text)
    report_scope = "lacro" if "LACRO Regional Portfolio" in nt else None
    specs = dict(_summary_metric_specs(report_scope))
    if not specs:
        return True, "no executive_summary.metrics in report_spec.yaml, nothing to compare"
    if not spans:
        return True, "no executive summary found"
    bad = []
    for label, row_start, cell_start, cell_end in spans:
        expects_label = specs.get(label, False)
        cell = nt[cell_start:cell_end]
        # \d+ (not \d{1,3}) -- N renders unformatted (e.g. "1721", not
        # "1,721"; see generation/assembler.py's _add_table(), str(int)
        # with no thousands separator), and a capped \d{1,3} with a
        # trailing \b cannot match a 4+-digit run at all: \b blocks
        # starting mid-run, so a real N like "1313" produced no match,
        # `base_text` silently fell back to "", and every row with a
        # 4-digit N (including genuinely restricted ones) read as
        # label-absent regardless of what actually followed it -- caught
        # by a false FAIL against real lacro_final_check output where
        # Children's Wellbeing Improved's genuine base label was invisible
        # to this regex.
        n_match = re.search(r"\b\d+(?:,\d{3})*\b(?!\.\d|%)", cell)
        base_text = cell[n_match.end():].strip(" |\t") if n_match else ""
        has_label = bool(base_text)
        if has_label != expects_label:
            bad.append(
                f"{label}: base label {'present' if has_label else 'absent'} "
                f"({base_text!r}), report_spec.yaml expects "
                f"{'present' if expects_label else 'absent'} for report_scope={report_scope!r}"
            )
    if bad:
        return False, "; ".join(bad)
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

    Excludes the Executive Summary table specifically (session-2,
    2026-08-20) -- this check's job is catching a genuine narrative/table
    disagreement like the Part 5 defect above, not scanning the Executive
    Summary table itself. R-002's new table uses "Claim Process
    Understanding" as a row label -- already on this check's own hardcoded
    list, from the unrelated Part 5 defect -- and its three OTHER rows sit
    close enough together in flattened text to land inside that label's
    +/-90-character window, reading as conflicting values for a metric
    that only actually appears once. Excluding just the Executive Summary
    table's own rows (not tables in general -- Part 5's caregiver table,
    the real second half of the original defect, must stay in scope, so a
    blanket "no tables" or "requires a verb nearby" rule would have broken
    that) fixes this without widening the label list or loosening the
    window, per instruction.
    """
    # nt (not _norm(text)): _summary_table_row_spans() needs newlines
    # preserved to bound table rows (see its own docstring), and its
    # returned spans are offsets into nt specifically -- a separately
    # _norm()-ed copy can differ in length, making those offsets invalid.
    nt, spans = _summary_table_row_spans(text)
    excluded = [(row_start, cell_end) for _, row_start, _, cell_end in spans]
    findings = {}
    for label in ["healthcare access improved", "high financial stress",
                  "coverage understanding", "claim process understanding"]:
        vals = set()
        for m in re.finditer(re.escape(label), nt, re.I):
            if any(s <= m.start() < e for s, e in excluded):
                continue  # this occurrence is inside the Executive Summary table, not prose
            window = nt[max(0, m.start() - 90): m.end() + 90]
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
    """The executive summary draws on more than the NPS module.

    Restricted to the narrative prose block (session-2, 2026-08-20):
    previously scanned everything before "about this survey", which
    includes the deterministic Executive Summary table. R-002's new table
    uses "Worth the Premium" and "Claim Process Understanding" as row
    labels, both of which happen to match this check's own module-keyword
    phrases ("worth the premium" under value, "claim process" under
    claims) -- so a report with NO narrative at all (no
    qualitative_results.json) could pass on table row labels alone, which
    defeats the point of an advisory check meant to flag exactly that gap.
    Now excludes the table's own rows and stops before "Data Availability"
    (a template caveat box, not narrative -- and its cross-reference
    sentence happens to repeat "Claim Process Understanding" verbatim, so
    stopping before it matters even after the table itself is excluded),
    leaving only the genuine narrative zone: the exec_prose paragraph, Top
    Findings, Recommended Actions, whichever are present. Against a report
    with none of those (this session's own lacro_final_check regeneration
    has no qualitative_results.json), this now correctly FAILS -- an
    honest advisory gap instead of a coincidental pass.
    """
    # nt.lower() (not _lower(text)): _summary_table_row_spans() needs
    # newlines preserved to bound table rows (see its own docstring), and
    # its returned spans are offsets into nt specifically -- a separately
    # _norm()-ed copy can differ in length, making those offsets invalid.
    nt, spans = _summary_table_row_spans(text)
    t = nt.lower()
    block = t.split("about this survey")[0]
    block = block.split("data availability")[0]
    if spans:
        table_end = max(cell_end for _, _, _, cell_end in spans)
        if table_end < len(block):
            block = block[table_end:]
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
