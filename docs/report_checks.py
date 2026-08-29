"""
Insurance Impact Report: validation check suite.

Every check maps to a requirement ID in docs/report_spec.md.

Two kinds of check:
  TEXT   runs against the rendered report text. Portable, works on the
         committed Test9 baseline (fixtures/test9.txt), no pipeline
         integration needed.
  OBJECT runs against the assembled report object before rendering.
         Stubbed here with the assertion written out, to be wired in
         once the models exist.

One exception to the TEXT/OBJECT split: C-002 (R-002) also reads
generation/report_spec.yaml directly, not just rendered text. That
requirement is about a config-driven metric list matching what actually
renders, so the check needs the config to know what "matching" means --
see C-002's own docstring.

fixtures/test9.txt is the frozen baseline text -- committed, not
extracted ad hoc, so the blocking-failure count it produces (the
project's progress metric) is stable across sessions. It was extracted
from the real Test9.docx (not the PDF Lorenz reviewed) via python-docx's
iter_inner_content(), which reproduces paragraph/table document order
faithfully, PLUS an explicit reconstruction of Word's "List Number"
auto-numbering (python-docx's own Paragraph.text never includes a list
style's auto-generated number -- it's computed by Word's rendering
engine from the style, not stored as literal run text -- but IS baked
into a PDF export's text layer, which is what a reader actually sees).
Session-3 found and reconciled a real discrepancy this way: a raw
docx-text extraction reported 4 passed/16 blocking against Test9,
undercounting by exactly one true defect (R-013's Recommended Actions
continuing 4-6 instead of resetting to 1) that only becomes visible
once list numbering is reconstructed -- 3 passed/17 blocking, matching
a PDF-based extraction exactly. See docs/report_spec.md's R-002
Implementation note for the full investigation.

Usage:
    python report_checks.py fixtures/test9.txt
    python report_checks.py new_run.txt --compare fixtures/test9.txt
    python report_checks.py new_run.txt --qual-json runs/<run_id>/qualitative_results.json
        # feeds C-006/C-007/C-008's structural sentiment_split checks
        # (session-8) a real qualitative_results.json; omitted, those
        # three SKIP rather than fail -- see their own docstrings.

Severity:
    BLOCKING  a defect a reader would notice. Fails the build.
    ADVISORY  worth a look. Logged, does not fail the build.

Result (three states, not two):
    pass  the check found its subject matter present and correct.
    fail  the check found its subject matter present and wrong.
    skip  the check's subject matter is not present in this report at all
          (e.g. no protection appendix, no trend section) -- there was
          nothing to verify, so nothing was verified. A skip is not a
          pass: it carries no evidence the underlying requirement holds,
          only that this particular text had nothing to check it
          against. A check function signals skip by returning None
          (instead of True/False) as its first value. Every check that
          depends on a section that may legitimately be absent from a
          partial or in-progress report -- not universal, banned-phrase-
          anywhere checks like C-014/C-016/C-020/C-022 -- should skip
          rather than silently pass when that section is missing; see
          each check's own "nothing found" branch. Session-3
          orientation: a run against a deliberately partial regeneration
          (Executive Summary section only) reported "23/24 passed, 0
          blocking failures" under the old two-state model -- almost
          entirely because checks for sections that were never
          regenerated (the protection appendix, trend section, and so
          on) had nothing to check and silently counted as passes. A
          clean two-state result on a partial report reads as evidence
          of correctness it does not have; see main()'s coverage
          warning below for the other half of this fix.
"""

from __future__ import annotations

import inspect
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import yaml

BLOCKING = "BLOCKING"
ADVISORY = "ADVISORY"

PASS = "pass"
SKIP = "skip"
FAIL = "fail"


@dataclass
class CheckResult:
    check_id: str
    requirement: str
    severity: str
    status: str  # PASS | SKIP | FAIL
    detail: str = ""


@dataclass
class Registry:
    checks: list = field(default_factory=list)

    def add(self, check_id: str, requirement: str, severity: str):
        def wrap(fn: Callable):
            self.checks.append((check_id, requirement, severity, fn))
            return fn
        return wrap

    def run(self, text: str, qual_results: "dict | None" = None) -> list[CheckResult]:
        """qual_results: parsed qualitative_results.json for the run being
        checked, if available -- only passed to checks that declare a
        qual_results parameter (session-8: C-006/C-007/C-008 became
        structural checks against this JSON rather than rendered prose;
        see their own docstrings for why). Every other check's signature
        is untouched and keeps receiving text only."""
        results = []
        for check_id, requirement, severity, fn in self.checks:
            try:
                kwargs = {}
                if "qual_results" in inspect.signature(fn).parameters:
                    kwargs["qual_results"] = qual_results
                ok, detail = fn(text, **kwargs)
            except Exception as exc:  # a check that errors is a failed check
                ok, detail = False, f"check raised: {exc}"
            status = SKIP if ok is None else (PASS if ok else FAIL)
            results.append(CheckResult(check_id, requirement, severity, status, detail))
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
        return None, "no label or no dates found, nothing to compare"
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
        return None, "no executive_summary.metrics in report_spec.yaml, nothing to compare"
    if not spans:
        return None, "no executive summary found"
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
    if not entries:
        return None, "no protection appendix entries found"
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
        return None, "no stated total found"
    listed = len(re.findall(r"\(([\d\-]{4,20}),\s*[^)]{2,40}\)", t))
    if int(stated.group(1)) != listed:
        return False, f"states {stated.group(1)} concerns, lists {listed} entries"
    return True, ""


@reg.add("C-005", "R-004", BLOCKING)
def trend_table_declares_comparability(text: str):
    """Every trend indicator carries a comparability declaration.

    R-009 (session-4): header separator was `\\s+` only, so a real pipe-
    delimited table row ("Indicator | 2026 | 2025 | Comparability" -- this
    project's own extraction convention, including the committed
    fixtures/test9.txt) never matched at all, regardless of whether the
    Comparability column was actually present. `[\\s|]+` accepts either;
    still requires the four words in order, so a genuinely missing column
    still fails.
    """
    t = _lower(text)
    if "trend comparison" not in t:
        return None, "no trend section"
    header = re.search(r"indicator[\s|]+20\d\d[\s|]+20\d\d[\s|]+comparability", t)
    if not header:
        return False, "trend table has no Comparability column header"
    return True, ""


# ------------------------------------------------------------ Phase 2: schema

# C-006/C-007/C-008 moved from TEXT to STRUCTURAL checks (session-8): they
# now read qualitative_results.json's section_insights[*].sentiment_split
# directly (R-006a's uniform nested {group: {positive, negative, neutral,
# base_n, source_pool_n, selection_rule}} shape, docs/report_spec.md),
# rather than searching rendered prose for the literal phrase "sentiment
# split". That phrase is prompt-internal terminology (_fmt_insight_
# summary()'s own label in generation/writer.py) -- nothing instructs the
# writer LLM to reproduce it verbatim in its narrative. Against a real
# full-pipeline run (session-8, runs/lacro_final_check/), the model
# paraphrased every section differently ("showed mixed sentiment",
# "sentiment was overwhelmingly positive", "Analysis shows women were more
# likely...") and never once used the two-word phrase -- so all three
# checks reported SKIP against content that was, in fact, present,
# correct, and (for Part 7) demonstrating the cross-group comparison
# instruction working exactly as designed. A prose-matching heuristic
# cannot reliably verify a guarantee the PIPELINE is responsible for
# producing; reading the JSON the pipeline actually writes is the direct
# check, not an indirect proxy through whatever words the writer LLM
# happens to choose. All three now return SKIP (None) when no
# qualitative_results.json is available (fixtures/test9.txt predates
# R-006a entirely and has none) or when it has no sentiment_split content
# at all -- nothing to check, not a failure, same SKIP semantics as
# every other check in this file. Pass a parsed qualitative_results.json
# via Registry.run(text, qual_results=...) / main()'s --qual-json flag.

def _iter_sentiment_groups(qual_results: "dict | None"):
    """Yields (section, group_label, group_dict) for every group in every
    section's sentiment_split -- shared traversal for C-006/C-007/C-008."""
    if not qual_results:
        return
    si = qual_results.get("section_insights") or {}
    for section, entry in si.items():
        if not isinstance(entry, dict):
            continue
        split = entry.get("sentiment_split")
        if not isinstance(split, dict):
            continue
        for group_label, group in split.items():
            yield section, group_label, group


_SENTIMENT_SPLIT_REQUIRED_KEYS = (
    "positive", "negative", "neutral", "base_n", "source_pool_n", "selection_rule",
)


@reg.add("C-006", "R-006", BLOCKING)
def sentiment_split_has_required_fields(text: str, qual_results: "dict | None" = None):
    """STRUCTURAL (session-8, moved from text -- see module note above).

    Every group in every section's sentiment_split carries all six
    SentimentSplit fields (docs/report_spec.md's R-006a Rule):
    positive, negative, neutral, base_n, source_pool_n, selection_rule.
    """
    groups = list(_iter_sentiment_groups(qual_results))
    if not groups:
        return None, "no qualitative_results.json provided, or no sentiment splits found in it"
    bad = []
    for section, group_label, group in groups:
        if not isinstance(group, dict):
            bad.append(f"{section}.{group_label}: not an object")
            continue
        missing = [k for k in _SENTIMENT_SPLIT_REQUIRED_KEYS if k not in group]
        if missing:
            bad.append(f"{section}.{group_label}: missing {missing}")
    if bad:
        return False, f"{len(bad)} of {len(groups)} group(s) missing required fields: {bad[0]}"
    return True, ""


@reg.add("C-007", "R-006", BLOCKING)
def sentiment_split_counts_are_internally_consistent(text: str, qual_results: "dict | None" = None):
    """STRUCTURAL (session-8, moved from text -- see module note above).

    positive + negative + neutral == base_n, and base_n <= source_pool_n,
    for every group in every section -- the two numeric guarantees the
    SentimentSplit model (docs/report_spec.md's R-006a) exists to make.
    Guards the Test9 failure mode (a split reported with no traceable,
    internally-consistent base) directly at the data level, not by
    inferring it from prose.
    """
    groups = list(_iter_sentiment_groups(qual_results))
    if not groups:
        return None, "no qualitative_results.json provided, or no sentiment splits found in it"
    bad = []
    for section, group_label, group in groups:
        if not isinstance(group, dict) or not all(k in group for k in _SENTIMENT_SPLIT_REQUIRED_KEYS):
            continue  # structural problem already caught by C-006
        total = group["positive"] + group["negative"] + group["neutral"]
        if total != group["base_n"]:
            bad.append(f"{section}.{group_label}: counts sum to {total}, base_n={group['base_n']}")
        if group["base_n"] > group["source_pool_n"]:
            bad.append(f"{section}.{group_label}: base_n={group['base_n']} exceeds source_pool_n={group['source_pool_n']}")
    if bad:
        return False, f"{len(bad)} group(s) fail count/base consistency: {bad[0]}"
    return True, ""


@reg.add("C-008", "R-006", ADVISORY)
def sentiment_base_is_not_implausibly_small(text: str, qual_results: "dict | None" = None, floor: int = 25):
    """STRUCTURAL (session-8, moved from text -- see module note above).

    Flags a group whose base_n is far below what's plausible for LACRO's
    real pool size. Advisory, not blocking: a genuinely small population
    (e.g. Part 6's 55 claimants) is expected and already explained by its
    own selection_rule -- a human reviews a flagged case rather than this
    check rejecting it outright.
    """
    groups = list(_iter_sentiment_groups(qual_results))
    if not groups:
        return None, "no qualitative_results.json provided, or no sentiment splits found in it"
    tiny = [f"{section}.{group_label}={group['base_n']}"
            for section, group_label, group in groups
            if isinstance(group, dict) and "base_n" in group and group["base_n"] < floor]
    if tiny:
        return False, f"{len(tiny)} of {len(groups)} sentiment bases below {floor}: {tiny}"
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
    any_found = False
    for label in ["healthcare access improved", "high financial stress",
                  "coverage understanding", "claim process understanding"]:
        vals = set()
        for m in re.finditer(re.escape(label), nt, re.I):
            if any(s <= m.start() < e for s, e in excluded):
                continue  # this occurrence is inside the Executive Summary table, not prose
            any_found = True
            window = nt[max(0, m.start() - 90): m.end() + 90]
            vals.update(re.findall(r"(\d{1,3}\.\d)%", window))
        if len(vals) > 2:
            findings[label] = sorted(vals)
    if findings:
        first = next(iter(findings.items()))
        return False, f"{len(findings)} metric(s) with conflicting values, e.g. {first[0]}: {first[1]}"
    if not any_found:
        return None, "none of the tracked metric labels found outside the summary table"
    return True, ""


@reg.add("C-010", "R-007", BLOCKING)
def cross_references_point_to_the_right_part(text: str):
    """A footnote referring to another Part names the Part that holds it.

    Test9's Part 5 footnote cites 'Part 4's healthcare access metric';
    healthcare access is reported in Part 5.
    """
    t = _norm(text)
    matches = list(re.finditer(r"Part (\d+)'s ([a-z ]{4,40}?) metric", t, re.I))
    if not matches:
        return None, "no cross-part metric references found"
    bad = []
    for m in matches:
        part, metric = m.group(1), m.group(2).strip().lower()
        section = re.search(rf"Part {part}:(.{{0,4000}}?)(?=Part \d+:|$)", t, re.I | re.S)
        if section and metric.split()[0] not in section.group(1).lower():
            bad.append(f"'{metric}' cited as Part {part}")
    if bad:
        return False, "; ".join(bad)
    return True, ""


@reg.add("C-011", "R-008", BLOCKING)
def coping_behaviour_is_named(text: str):
    """Negative coping is not reported as a bare rate.

    "sell" added (session-10, R-008 implementation): every other verb here
    matches its own conjugations as a plain substring ("borrow" inside
    "borrowed"/"borrowing", "closed .{0,20}business" inside "closed their
    business"), but "sold" does not share a stem with "sell"/"selling" --
    an irregular verb, not a substring match -- so a real, correctly-named
    "selling assets or livestock" (the natural present-tense phrasing a
    writer model reaches for) failed this check even though a real
    behaviour was actually named, not omitted.
    """
    t = _norm(text)
    if "coping" not in t.lower():
        return None, "coping not reported"
    named = re.search(
        r"(sold|sell\w*|borrow|savings|reduc\w+ food|took .{0,20}children out|"
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
        return None, "no trend section"
    body = section.group(1)
    if re.search(r"\bSig\.", body) or "z-test" in body.lower():
        return False, "trend table still carries a significance column or z-test footnote"
    return True, ""


@reg.add("C-013", "R-009", BLOCKING)
def no_p_values_in_trend_section(text: str):
    """No p value appears in the trend section."""
    section = re.search(r"Trend Comparison(.{0,2600})", _norm(text), re.S)
    if not section:
        return None, "no trend section"
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
    if len(parts) == 1:
        return None, "no 'Key Qualitative Insights' headings found"
    empty = 0
    for chunk in parts[1:]:
        window = chunk[:1400]
        if not re.search(r"[\"\u201c][^\"\u201d]{12,}", window):
            empty += 1
    if empty:
        return False, f"{empty} qualitative block(s) render with no verbatim"
    return True, ""


@reg.add("C-016", "R-011", BLOCKING)
def non_filer_terminology_states_population(text: str):
    """R-011 (session-10, supersedes the literal LM10 request): both
    previously-tried labels are retired. "Non-Claimant" was tried first and
    retracted because it implies the much larger population who never had a
    claimable event at all; "Non-Filer" replaced it but is itself opaque
    about what population it names. The fix states the population directly
    -- in the column headers ("Claimant (filed, n=...)" / "Did not file
    (n=...)") and in an explicit note beneath the table -- rather than
    trusting either single word to carry it. See
    docs/maintenance/known-issues-log.md:71-81 and part_6.py's module
    docstring for the retracted-label history.
    """
    t = _lower(text)
    retired_hits = (
        t.count("non-filer") + t.count("non filer")
        + t.count("non-claimant") + t.count("non claimant")
    )
    if retired_hits:
        return False, f"retired non-filer/non-claimant terminology appears {retired_hits} time(s)"

    if "did not file" not in t:
        return None, "no Part 6 'Did not file' scorecard header found"

    if "restricted to clients who reported an insurable event" not in t:
        return False, "Part 6 scorecard is missing its population-scope note"

    return True, ""


@reg.add("C-017", "R-012", BLOCKING)
def trend_columns_use_wave_years(text: str):
    """LM3: columns are labelled by year, not Current and Prior Wave.

    Restricted to the table header region (session-5, found during
    R-004/R-005/R-009): previously scanned the whole trend section for the
    bare substrings "current wave"/"prior wave" anywhere, which also
    matched ordinary footnote prose ("Not comparable to the prior wave:
    ..." -- natural English, not a header). False positive, caught
    regenerating Part 10 with a genuinely year-labelled header that still
    failed this check purely because of unrelated footnote text further
    down the same section. Now bounded to the header row itself: the text
    starting at "indicator" within the Trend Comparison section, for a
    short, header-row-sized window -- not the whole section.
    """
    t = _lower(text)
    section = re.search(r"trend comparison(.{0,2600})", t, re.S)
    if not section:
        return None, "no trend section"
    body = section.group(1)
    header_start = body.find("indicator")
    if header_start == -1:
        return None, "no trend table header found"
    header_region = body[header_start:header_start + 100]
    if "current wave" in header_region or "prior wave" in header_region:
        return False, "trend table still uses Current Wave / Prior Wave headers"
    return True, ""


@reg.add("C-018", "R-013", BLOCKING)
def summary_actions_restart_numbering(text: str):
    """Recommended Actions are numbered from 1, not continuing from findings."""
    t = _norm(text)
    if "Recommended Actions" not in t:
        return None, "no Recommended Actions section found"
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
    if "executive summary" not in t:
        return None, "no executive summary found"
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

# Matches generation/writer.py's VOICE RULES instruction verbatim: "The
# percentages across all categories you mention must sum to approximately
# 100% (allow +/-1% for rounding only)." Session-8: this check previously
# allowed only +/-0.5%, stricter than what the writer is actually told is
# acceptable -- a correctly-rounded, instruction-compliant distribution
# (Part 6's real 45/53=84.9% -> 85%, 4/53=7.5% -> 8%, 4/53=7.5% -> 8%,
# summing to 101%, each figure independently and correctly rounded) failed
# a check enforcing a tighter tolerance than its own target. Widened to
# match; still catches a genuine defect outside +/-1% (e.g. the
# 55/40/8=103 case this check was originally built for).
_PCT_SUM_TOLERANCE = 1.0


@reg.add("C-021", "cross", BLOCKING)
def percentages_sum_to_about_one_hundred(text: str):
    """Distribution splits sum to 100 within rounding.

    Catches the 55/40/8 = 103 defect seen in an earlier iteration.
    Tolerance matches writer.py's own VOICE RULES instruction (+/-1%,
    session-8) -- see _PCT_SUM_TOLERANCE.
    """
    bad = []
    found_any = False
    for sentence in re.split(r"(?<=[.])\s", _norm(text)):
        pcts = [float(x) for x in re.findall(r"(\d{1,3}\.?\d?)%", sentence)]
        if len(pcts) < 3:
            continue
        found_any = True
        total = sum(pcts)
        # only a complete distribution should land near 100
        hi = 100 + _PCT_SUM_TOLERANCE
        lo = 100 - _PCT_SUM_TOLERANCE
        if hi < total < 108 or 92 < total < lo:
            bad.append(f"{pcts} sums to {total:.1f}")
    if bad:
        return False, "; ".join(bad[:3])
    if not found_any:
        return None, "no distribution-like sentences (3+ percentages) found"
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
        return None, "nothing suppressed"
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


# R-035 (docs/report_spec.md, session-11): a cross-sectional survey supports
# association claims, not causal ones -- the report must never describe a
# correlation or a group difference as one thing driving, causing, or
# determining another. This is a VOICE RULES instruction (generation/
# writer.py), and prompt instructions are probabilistic: a model can still
# drift back to causal phrasing on a given call. C-025 exists to catch that
# drift, not to replace the prompt rule.

# A quoted client verbatim is exempt -- the client's own words stand as
# given. Covers both a plain block quote and this codebase's bilingual
# pattern (an English gloss quoted, immediately followed by the original-
# language text in an unquoted parenthetical, e.g. writer.py's own example:
# "the process was very slow" ("el proceso fue muy lento")) in one match, so
# neither half of a bilingual quote reaches the scan below.
_C025_VERBATIM_SPAN = re.compile(r'["“][^"”]*["”](\s*\([^)]*\))?')

# Confirmed with the user (session-11): the ban covers descriptions of
# findings/correlations, not the formal Recommended Actions section --
# a recommendation inherently proposes a future action ("review coverage
# to improve the value proposition"), a different communicative act from
# claiming a correlation IS a causal mechanism. Narrower than "any
# forward-looking language anywhere" -- a narrative aside outside this
# section ("this gap highlights an opportunity to improve X") is NOT
# exempt and must still be reworded. Bounded to the next recognized
# heading (or end of text) so an unrelated section immediately after
# Recommended Actions is never swept in by accident.
_C025_RECOMMENDED_ACTIONS_REGION = re.compile(
    r"Recommended Actions\b.*?(?=\n?(?:Data Availability|About This Survey|Appendix:|Part\s+\d+\s*:)|\Z)",
    re.S,
)

# "Improved" (and, as confirmed on a real regeneration, "reduced") are the
# banned-family words with a genuine non-causal use in this report: a fixed
# metric label ("Healthcare Access Improved"), descriptive prose reporting
# what respondents said happened to them ("36.1% reported improved child
# wellbeing", "...reported that their access ... improved.") with no causal
# agent named, or a participle heading its own noun-phrase subject in an
# association statement ("Reduced financial stress is also associated with
# higher satisfaction"). Every other banned term in _C025_CAUSAL_TERMS has
# no such legitimate use anywhere in this report and is banned outright,
# with no exemption -- including the gerund forms "improving"/"reducing",
# which in practice need a named agent to read naturally ("insurance
# reducing financial stress"), unlike the past-participle forms above.
_C025_FIXED_IMPROVED_LABELS = (
    "Children's Wellbeing Improved", "Healthcare Access Improved", "Child Wellbeing Improved",
)
_C025_SAFE_IMPROVED_PRECEDING = re.compile(
    r"\b(?:reported?|reports?|showed|shows?|found|experienced?|saw|indicat\w*)\s+(?:an?\s+)?improved\b",
    re.I,
)
_C025_SAFE_IMPROVED_TRAILING = re.compile(
    r"\bimproved\b(?=\s*[.,;)]|\s+(?:and|but|while|whereas|among|for)\b)",
    re.I,
)

# "Reduced" has the identical non-causal state-description use "improved"
# does -- confirmed on a real regeneration: "Reduced financial stress is
# also associated with higher satisfaction" describes a level, not a causal
# claim, the same way "improved X" can. Both participles (past-tense only,
# not "improving"/"reducing" -- a gerund here reads as an active verb
# needing a named agent, e.g. the real, correctly-still-banned "insurance
# reducing financial stress") are exempt specifically when the noun phrase
# they head is itself the subject of an association statement.
_C025_SAFE_STATE_PARTICIPLE_ASSOCIATION = re.compile(
    r"\b(?:improved|reduced)\s+\S+(?:\s+\S+){0,3}\s+(?:is|are|was|were)\s+"
    r"(?:also\s+|likely\s+)?(?:strongly\s+|closely\s+)?(?:associated|correlated|linked)\b",
    re.I,
)

# Every inflection of each banned verb, not just the literal forms LM's
# colleague listed ("improving"/"improved" are exactly as causal as
# "improves"). "translat(e/es/ed/ing) ... into" allows up to 3 words between
# (e.g. Test11's real "translating cover into improved access") without
# spanning across a full sentence. Two words are banned as their inflected
# VERB forms only, bare noun uses left alone, confirmed against real
# generated text for each: "impact" (impacts/impacted/impacting -- bare
# "impact" is a noun in this report, including the report title, "Insurance
# Impact Report," the programme's name, not a causal claim) and "ease"
# (eases/eased/easing -- bare "ease" showed up as ordinary descriptive prose,
# "Positive feedback highlighted ease of use," not a causal claim).
_C025_CAUSAL_TERMS = re.compile(
    r"\b("
    r"driv(?:e|es|ing)|drove|driven|drivers?|"
    r"caus(?:e|es|ing)|caused|"
    r"leads?\s+to|"
    r"determin(?:e|es|ing)|determined|"
    r"improv(?:e|es|ing)|improved|"
    r"reduc(?:e|es|ing)|reduced|"
    r"strengthen(?:s|ing)?|strengthened|"
    r"underpin(?:s|ning)?|underpinned|"
    r"eas(?:es|ing)|eased|"
    r"translat\w*(?:\s+\S+){0,3}\s+into|"
    r"levers?|"
    r"impact(?:s|ing)|impacted"
    r")\b",
    re.I,
)


def _c025_strip_verbatims_and_safe_uses(text: str) -> str:
    t = _C025_RECOMMENDED_ACTIONS_REGION.sub(" ", text)
    t = _C025_VERBATIM_SPAN.sub(" ", t)
    for label in _C025_FIXED_IMPROVED_LABELS:
        t = t.replace(label, "")
    t = _C025_SAFE_IMPROVED_PRECEDING.sub(" ", t)
    t = _C025_SAFE_IMPROVED_TRAILING.sub(" ", t)
    t = _C025_SAFE_STATE_PARTICIPLE_ASSOCIATION.sub(" ", t)
    return t


@reg.add("C-025", "R-035", BLOCKING)
def no_causal_language_outside_verbatims(text: str):
    """Correlations and group differences are described as associations,
    never as one thing driving, causing, or determining another -- outside
    a quoted client verbatim (the client's own words are exempt) and
    outside the formal Recommended Actions section (a recommendation
    proposes a future action, not a claim about what the data shows).
    """
    t = _c025_strip_verbatims_and_safe_uses(_norm(text))
    hits = sorted(set(h.lower() for h in _C025_CAUSAL_TERMS.findall(t)))
    if hits:
        return False, f"causal language outside verbatims: {hits[:8]}"
    return True, ""

# ------------------------------------------------- Africa scope (R-036 onward)

@reg.add("C-026", "R-037", BLOCKING)
def insurable_event_terminology(text: str):
    """R-037 (TD24): rendered text says "insurable event", never "insured
    event". The survey question asks whether the client experienced an
    event that might be covered; "insured event" asserts a coverage
    determination that was never made.

    A universal banned-phrase check like C-014/C-016/C-020/C-022 -- it
    never skips, because the phrase is banned everywhere it could appear.

    Scope note: this governs DISPLAY strings only. The internal
    identifiers q_insured_event_12m, flag_negative_coping and
    insured_event_base are deliberately unchanged (R-037 records why) and
    never reach rendered text -- C-022 already enforces that separately,
    so there is no overlap between the two checks.

    Paired edit: C-016 asserts the literal Part 6 note "restricted to
    clients who reported an insurable event". Both were changed together
    under R-037; changing one without the other fails the suite.
    """
    t = _lower(text)
    hits = t.count("insured event")
    if hits:
        return False, (
            f"'insured event' appears {hits} time(s) in rendered text; "
            f"R-037 requires 'insurable event'"
        )
    return True, ""


# ------------------------------------------------------------------ reporting

def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    text = open(sys.argv[1], encoding="utf-8").read()

    # --qual-json PATH: optional, feeds C-006/C-007/C-008's structural
    # checks (session-8) a real qualitative_results.json. Omitted (or the
    # text file predates R-006a, e.g. fixtures/test9.txt) -> those three
    # SKIP rather than fail, same as any other check with nothing to check.
    qual_results = None
    if "--qual-json" in sys.argv:
        idx = sys.argv.index("--qual-json")
        qual_json_path = sys.argv[idx + 1]
        qual_results = json.loads(Path(qual_json_path).read_text(encoding="utf-8"))

    results = reg.run(text, qual_results=qual_results)

    width = max(len(r.check_id) for r in results)
    print(f"\n{'CHECK':<{width}}  {'REQ':<7} {'SEV':<9} {'RESULT':<7} DETAIL")
    print("-" * 100)
    for r in sorted(results, key=lambda x: x.check_id):
        label = {PASS: "pass", SKIP: "SKIP", FAIL: "FAIL"}[r.status]
        print(f"{r.check_id:<{width}}  {r.requirement:<7} {r.severity:<9} {label:<7} {r.detail[:120]}")

    passed = sum(1 for r in results if r.status == PASS)
    skipped = sum(1 for r in results if r.status == SKIP)
    blocking_failures = sum(1 for r in results if r.status == FAIL and r.severity == BLOCKING)
    advisory_failures = sum(1 for r in results if r.status == FAIL and r.severity == ADVISORY)
    print("-" * 100)
    print(
        f"{passed} passed, {skipped} skipped, "
        f"{advisory_failures} advisory failure(s), {blocking_failures} blocking failure(s)\n"
    )

    # Coverage assertion: a report can show zero blocking failures purely
    # because most of what BLOCKING covers was never present to check --
    # see the module docstring's "Result" section. If skips account for
    # more than a third of blocking checks, that "0 blocking failures"
    # is not evidence the report is correct, only that it's mostly
    # untested; say so loudly rather than let a clean-looking run pass
    # for a verified one.
    blocking_total = sum(1 for r in results if r.severity == BLOCKING)
    blocking_skipped = sum(1 for r in results if r.status == SKIP and r.severity == BLOCKING)
    if blocking_total and blocking_skipped / blocking_total > 1 / 3:
        print(
            f"WARNING: {blocking_skipped}/{blocking_total} blocking checks "
            f"({blocking_skipped / blocking_total:.0%}) were SKIPPED -- most of this "
            f"report's content was not present to check. This result is NOT evidence "
            f"the report is correct, only that it is PARTIAL.\n"
        )

    return 1 if blocking_failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
