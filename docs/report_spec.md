# LACRO Insurance Impact Report: Change Specification

**Baseline artifact:** `LAC_Insurance_Impact_Report_default_2026_Q2_Test9.pdf` (generated 17 August 2026)
**Reviewers:** Lorenz M (LM1 to LM11), second reviewer HO (HO2R1)
**Spec owner:** Binjie Wang
**Status:** draft, pending reviewer confirmation on R-006a, R-006b, R-008, R-014

---

## How to use this document

This file is the single source of truth for the next pipeline iteration. Every reviewer comment and every self identified defect is captured as a requirement with an ID, an owning layer, an intended behaviour, and a machine checkable verification.

**Rules of engagement for anyone (human or LLM) implementing against this spec:**

1. A requirement is only complete when its verification check passes, not when the output looks right.
2. If a rule can be expressed deterministically, it is implemented in code, schema or config. It is never implemented by instructing the report generator in prose.
3. No requirement may be satisfied by editing the report generation prompt unless its layer is explicitly `prompt`.
4. Work in the order given by the phases below. Commit after each phase and rerun the full check suite.
5. If implementation reveals that a requirement is mis-classified, update this document in the same commit as the code change.

**Layer definitions**

| Layer | Owns | Fixed by |
|---|---|---|
| `data_config` | Input scope, filters, labels, list contents | Config file or data preparation step |
| `schema` | Field definitions, required attributes, what a section may contain | Pydantic models |
| `code` | Deterministic logic, section assembly, table construction, label constants | Python modules |
| `prompt` | Writing judgement, emphasis, framing | Generator system or section prompts |

---

## Requirement index

| ID | Source | Layer | Title | Phase |
|---|---|---|---|---|
| R-001 | self | data_config | Period label matches fieldwork dates | 1 |
| R-002 | LM1a | data_config | Executive summary metric list is configurable | 1 |
| R-003 | self | code | Deduplicate client protection appendix | 1 |
| R-004 | LM3b | data_config | Per indicator comparability declarations | 1 |
| R-005 | self | data_config | Dominican Republic trend handling is explicit | 1 |
| R-006a | LM6, LM7 | schema | Sentiment split computed deterministically, with a real base_n | 2 |
| R-006b | LM6, LM7 | code | Verbatim shortlist widened for selection quality | 2 |
| R-007 | LM8 | schema | Every restricted base metric carries a base description | 2 |
| R-008 | LM5 | schema | Coping metric exposes component breakdown | 2 |
| R-009 | LM3b | schema | Trend table replaces significance with comparability | 1 (pulled forward from 2, session-4 -- see R-009) |
| R-010 | LM4, LM11 | code | Qualitative blocks omitted when no verbatims exist | 3 |
| R-011 | LM10 | code | Non filer renamed to non claimant | 3 |
| R-012 | LM3a | code | Trend columns labelled by wave year | 3 |
| R-013 | LM1b | code | Executive summary draws on all sections | 3 |
| R-014 | LM9 | code | Remove editorial phrase in Part 5 | 3 |
| R-015 | self | code | Post generation validation gate | 3 |
| R-016 | HO2R1 | prompt | NPS framed as one module among several | 4 |
| R-017 | self | code | Severity counts computed once from a canonical list | 3 |
| R-018 | self | code | Protection flag dedup must not collapse across source columns -- IMPLEMENTED | 3 |
| R-029 | self | code | found_by_id cache lookup keys on id alone -- IMPLEMENTED | 3 |
| R-030 | self | code | Rendered verbatims can be attributed to the wrong source column -- PARTIALLY IMPLEMENTED | 3 |
| R-031 | self | code | Report per-section verbatim source-pool counts | 3 |
| R-019 | self | code | Check suite gaps: C-013 window, C-009 detail specificity | 3 |
| R-020 | self | code | CLI output filename diverges from dashboard path | 3 |
| R-021 | self | code | Period label formatting duplicated across title and heading | 3 |
| R-022 | self | data_config | Stale prior_run_id should fail loudly, not resolve silently | 1 |
| R-023 | self | code | Sentiment split base is a model estimate, not a validated count -- SUPERSEDED by R-006a | 2 |
| R-024 | self | code | Qualitative is_claimant used a narrower definition than the report's own "claimant" -- IMPLEMENTED | 2 |
| R-025 | self | code | Claims-other pool reaches synthesis with no section routing | 3 |
| R-026 | self | schema | Sentiment enum cannot express "neutral in tone, negative in substance" -- verified real, not a fix | 3 |
| R-027 | self | code | Executive summary content silently discarded by a JSON-shape mismatch -- IMPLEMENTED | 1 |
| R-028 | self | data_config | report_spec.yaml's model: key names a model this pipeline cannot reach | 3 |
| R-032 | self | code | Required top-level keys are checked for presence, not content, beyond R-027's four | 3 |

---

# Phase 1: Data and config

Changes here alter figures downstream, so they land first.

## R-001 Period label matches fieldwork dates

**Source:** self identified (report already emits `period_label_mismatch` flag)
**Layer:** `data_config`
**Priority:** high
**Status:** Closed (2026-08-20) -- already satisfied by existing behaviour, confirmed with Lorenz

**Current behaviour**
The run is labelled 2026 Q2 while recorded fieldwork spans 26 June 2026 to 4 August 2026, crossing from Q2 into Q3. `data_quality_flags.derive_period_mismatch_flag()` already detects this and emits a `period_label_mismatch` flag.

**Investigation finding (session-2 orientation, 2026-08-20)**
Lorenz confirmed the period label is operator-entered on the dashboard at run setup (baked into `run_id`, e.g. `"2026_Q2"`) and that a mismatch should stay a warning, never a blocking failure. Tracing every render site named in the original "Current behaviour" above:
- There is no Word running header/footer anywhere in `generation/assembler.py` (no `python-docx` `section.header` usage) -- the only render site is one `doc.add_heading(..., level=1)` title block (`assembler.py:1054-1080`), built from `format_period_label(run_id)`. `writer.py:74-79`'s `_report_title()` calls the same function independently for the narrative prompt's own title (see R-021 -- this is duplication, not a second bug).
- `derive_period_mismatch_flag()` (`data_quality_flags.py:91-144`) is advisory-only by construction and by its own docstring ("worth a human's confirmation ... not ... a blocked run"). No code path reachable from it raises or exits. `generation/validate_output.py`'s separate post-generation gate is unrelated (no period-label logic in that module at all) and is itself documented as advisory, never blocking assembly.
- The flag surfaces two ways today: transiently via the dashboard's live log stream (`pipeline_runner.py:211-212`), and durably inside `analysis_results.json`'s `data_quality_flags` list (stage 2 output) -- not in `run_metadata.yaml`.
- `docs/report_checks.py`'s C-001 already implements this exact rule at ADVISORY severity, and already passes against Test9.

**Intended behaviour**
Unchanged from current: a mismatch is logged for the operator's confirmation, never blocks rendering. No code change required.

**Verification**
- C-001 (ADVISORY) -- already implemented, already passing.

**Resolution**
Closed without a code change. The "hard failure" rule and its two `assert`-based verification lines (removed above) encoded an incorrect diagnosis made before this was confirmed with Lorenz; the "running header" they referenced does not exist as a separate render site from the title.

---

## R-002 Executive summary metric list is configurable

**Source:** LM1a, "why the focus on only these 4 metrics in the table?"
**Layer:** `data_config`
**Priority:** medium
**Status:** Implemented (2026-08-20)

**Current behaviour (corrected, session-2 orientation, 2026-08-20)**
The four metrics are hardcoded in `_HEADLINE_METRICS` (`generation/executive_summary.py`). Each metric's `n_path` already resolves to the correct denominator of its own percentage; the N column is arithmetically correct. Two of the four rows use a restricted base (Filed a Claim on `n_event`=124, Children's Wellbeing on `child_wellbeing_base`), and the table has no way to distinguish a restricted base from a full-sample one, so a reader cannot tell which rows describe the whole portfolio.

Separately, Filed a Claim at 44.4 percent is the event-to-claim conversion rate, not the share of the portfolio that claimed (55/1,721 = 3.2 percent). Correct arithmetic, but easily misread as a portfolio rate. This is a metric-selection concern, not a defect, and is resolved by the agreed metric set below.

The original "Current behaviour" text in this section (superseded by the paragraph above) claimed Filed a Claim's N=124 was "not the denominator used for the 44.4 percent figure" -- that was wrong. Session-2 orientation traced `n_path` into `analysis_engine/stats.py`'s `claims_funnel()` and confirmed 124 IS `filed_claim_base_n`, the actual denominator of 44.4 percent (55/124). The real defect was always presentation (no restricted-base marker), never arithmetic.

**Intended behaviour**
The summary metric list moves to config as an ordered list of metric entries. The N column continues to show the denominator of the stated percentage (already correct, no change needed there). Any metric whose denominator differs from the full sample carries a short base label in the table.

**Rule**
```yaml
executive_summary:
  metrics:
    - key: first_time_access
      label: "First-Time Access to Insurance"
      value_path: "parts.part_3.metrics.no_prior_access.headline.value"
      n_path: "parts.part_3.metrics.no_prior_access.headline.n_valid"
      suppressed_path: "parts.part_3.metrics.no_prior_access.headline.suppressed"
      fmt: "pct"
      base_label: null
    - key: worth_premium
      label: "Worth the Premium"
      value_path: "parts.part_1.metrics.worth_premium.headline.value"
      n_path: "parts.part_1.metrics.worth_premium.headline.n_valid"
      suppressed_path: "parts.part_1.metrics.worth_premium.headline.suppressed"
      fmt: "pct"
      base_label:
        default: "Health & credit-life clients only"
        lacro: null
    - key: claim_process_understanding
      label: "Claim Process Understanding"
      value_path: "parts.part_1.metrics.claim_process_understanding.headline.value"
      n_path: "parts.part_1.metrics.claim_process_understanding.headline.n_valid"
      suppressed_path: "parts.part_1.metrics.claim_process_understanding.headline.suppressed"
      fmt: "pct"
      base_label: null
    - key: child_wellbeing_improved
      label: "Children's Wellbeing Improved"
      value_path: "parts.part_4.child_wellbeing.headline.value"
      n_path: "parts.part_4.child_wellbeing.headline.n_valid"
      suppressed_path: "parts.part_4.child_wellbeing.headline.suppressed"
      fmt: "pct"
      base_label: "clients with children in household"
```
`base_label` is `null` for a full-sample metric, a short phrase for a statically-restricted one, or a dict keyed by `report_scope` (plus an optional `default`) for a metric whose restriction is scope-conditional -- resolved by `generation/orchestrator.py`'s `_resolve_population()`, the same function every `population:` note elsewhere in this file already uses (no second config pattern).

**Verification**
- `assert len(summary.metrics) == len(config.executive_summary.metrics)`
- For each row: `assert row.base_label (resolved against report_scope) is non-empty iff config's base_label resolves non-null`

**Resolved**
Metric set confirmed with Lorenz, 2026-08-20: First-Time Access to Insurance, Worth the Premium, Claim Process Understanding, Children's Wellbeing Improved. NPS is reported in Part 4, not the summary table.

**Implementation note**
`generation/report_spec.yaml` gained a top-level `executive_summary.metrics` key (same list-of-dicts shape as `part_10.trend_indicators`). `generation/executive_summary.py`'s `_HEADLINE_METRICS` was removed outright, not kept as a fallback (R-017's lesson: a fallback defeats the requirement) -- `headline_numbers()` now loads the spec fresh each call, matching `orchestrator.py`'s own reload-per-call pattern for the same file. `generation/assembler.py`'s summary table gained a 4th "Base" column (empty for full-sample rows). Verified against `runs/lacro_final_check/`'s real `analysis_results.json` (report_scope="lacro", n_total=1,721): First-Time Access 77.2% (N=1,721, no base label), Worth the Premium 80.07% (N=1,721, no base label -- LACRO is 100% Health, `base_label.lacro: null` applies), Claim Process Understanding 80.13% (N=1,721, no base label), Children's Wellbeing Improved 36.1% (N=1,313, base label "clients with children in household").

**Rendering rule: tied percentages gain a second decimal.** Worth the Premium (0.8006972690296339) and Claim Process Understanding (0.8012783265543288) both round to "80.1%" at the report's standard 1 decimal, and sitting adjacent in a four-row table reads like a copy-paste error, not two distinct measures. `executive_summary.py`'s `_disambiguate_tied_percentages()` detects any group of `pct`-formatted rows whose 1-decimal rendering collides and re-renders only that group at 2 decimals (80.07% / 80.13%) -- every other row keeps the report's standard 1 decimal. Generic (grouped by rendered-value collision, not by metric name), a single escalation step (1 -> 2 decimals, not recursive), and excludes SUPPRESSED/NOT APPLICABLE rows (those "colliding" as identical strings is not a rounding artifact). Implemented in `executive_summary.py` only, per instruction, not as a hardcoded exception for these two specific metrics.

`docs/report_checks.py`'s C-002 was rewritten to a structural check (reads `report_spec.yaml`'s `executive_summary.metrics` directly, resolves each `base_label` against report_scope, and asserts the rendered row's base-label presence matches) rather than the superseded "N values vary widely" heuristic -- see C-002's own docstring for why an N-vs-full-sample-total comparison was considered and rejected (cannot distinguish a restricted population from ordinary item non-response).

Regenerating from `runs/lacro_final_check/` surfaced two side effects, neither a code defect, both caused entirely by the new metric labels colliding with two *other*, previously-unrelated checks -- confirmed both ways: the untouched, pre-session C-009/C-019 produced the identical flip against the new table text, and re-running the fixes below against the *old* table text reproduces the old pass/fail state exactly, isolating the cause to the new labels, not to anything in the C-002 rewrite. Both were fixed this session (authorised as an exception to "only C-002 was in scope"):
- **C-009** (R-007, "no metric reported with two values") failed: its hardcoded label list already included `"claim process understanding"` (added for an unrelated Part 5 defect), and the new table's four rows sit close enough together in flattened text that C-009's ±90-character proximity window picked up the other three rows' percentages as if they conflicted with Claim Process Understanding's own value. Fixed by excluding the Executive Summary table's own rows from the scan, via a new shared helper, `_summary_table_row_spans()` -- not by requiring a verb nearby (the other option considered), because the check's actual founding defect (Part 5's caregiver *table* vs. its own prose, 33.9% vs. 8.9%) is itself table-vs-prose, and a blanket verb requirement would have suppressed detection of a real future recurrence of that same defect, not just this session's false positive. Label list and window both left unchanged, per instruction. This is a different fix from the C-009 gap R-019 already logs (detail-line specificity) -- see R-019's session-2 addendum.
- **C-019** (R-013, ADVISORY, "summary spans multiple modules") passed where it should not have: "Worth the Premium" and "Claim Process Understanding" happen to match two of its five hardcoded module-keyword lists ("worth the premium" under `value`, "claim process" under `claims`), so a report with no narrative at all (no `qualitative_results.json`, this run's actual state) could still pass on table row labels alone. Fixed by excluding the table's own rows (via the same shared helper) and stopping the scanned block before "Data Availability" (a template caveat box, not narrative -- its cross-reference sentence also happens to repeat "Claim Process Understanding" verbatim, so the table exclusion alone wasn't sufficient). Against this run, C-019 now correctly FAILS ADVISORY ("0 non-NPS module(s): none") -- an honest gap instead of a coincidental pass.

**Final check-state comparison, `runs/lacro_final_check/` (regenerated with the new metric set)**: baseline (pre-session `report_checks.py` against the pre-session four-metric table, both from `git show fe5d1cc:...`) vs. final (this session's `report_checks.py` against the regenerated table). Every check's pass/fail state is identical between baseline and final **except C-002** (BLOCKING FAIL -> pass, the intended fix). C-009 is pass -> pass. C-019 is ADVISORY FAIL -> ADVISORY FAIL (unchanged state; the reason changed from a coincidental 2-of-5-module table-label match to a correct 0-of-5, since this run has no narrative at all).

**Second verification pass, the real Test9.docx** (`D:\Vision Fund International\report_test\VFI_Insurance_Impact_Report_default_2026_Q2 Test9.docx`, extracted via `python-docx`'s `iter_inner_content()` so table rows and paragraphs interleave in true document order): running the shared row-span helper against a full 12-part real report (not a short exec-summary-only fixture) surfaced one more bug before it could be trusted here. `_summary_table_row_spans()` originally searched for each configured label with no upper bound on how far into the document it would look, and its per-row cell boundary relied only on recognizing *other configured* labels, known headings, or a sentence period. Test9's real, unmigrated table has "Filed a Claim" as its 4th row -- a metric this session's agreed set no longer tracks at all -- so none of those boundaries could recognize it, and "First-Time Access to Insurance"'s cell bled straight through "Filed a Claim | 44.4% | 124" into the exec_prose narrative paragraph that immediately follows the table with no heading between them, producing a garbled, misleading C-002 failure message instead of the honest "this table predates R-002" it should have given.

Fixed by anchoring row boundaries on line breaks instead: a new `_norm_keep_lines()` (collapses spaces/tabs, preserves newlines, unlike this file's usual `_norm()`) plus `_summary_table_row_spans()` now bounding each row's cell at its own line break first. A table row is reliably one line in any reasonable rendering of a Word table -- python-docx's own extraction, a "Save As Plain Text" export, a PDF copy-paste -- even when a row's columns collapse onto that line, so this holds regardless of which labels a given session's config happens to track. The search region is also now bounded to the Executive Summary section itself (up to "About This Survey", which always immediately follows it), not the rest of the document. C-002, C-009, and C-019 were updated to consume the helper's own newline-preserving normalized text instead of maintaining a second, independently-`_norm()`-ed copy with different character offsets.

After the fix, against the real Test9.docx: **all 24 checks (16 blocking failures, 4 advisory failures, 4 passes) show the identical pass/fail state as the true pre-session baseline** (`git show fe5d1cc:docs/report_checks.py`, the commit before this session's work), including C-002 itself -- Test9 was never regenerated with the new `report_spec.yaml`, so it still fails C-002, exactly as before, now for an accurate reason ("Children's Wellbeing Improved: base label absent, report_spec.yaml expects present") instead of the superseded N-variance heuristic. C-009 reproduces the identical genuine Part 5 conflict (`healthcare access improved: ['1.2', '1.8', '8.6', '8.9']`), byte-for-byte the same detail string as baseline. C-019 reproduces the identical `['claims', 'access']`, 2-of-3 result -- Test9's real narrative genuinely covers only two non-NPS modules, the actual R-013 defect this check exists to catch, unaffected by the table-exclusion fix. The two verification passes together (a synthetic regenerated report showing the intended C-002 flip, and the real, unmigrated Test9 showing zero unintended movement anywhere) cover both sides of what "only C-002 moved" needs to mean.

**Session-3: SKIP state, a coverage assertion, and a frozen baseline fixture.** Three findings, none about R-002 itself, all about whether this check suite's own results can be trusted.

*1. `passed`/`FAIL` was a false binary.* Most checks' "nothing found" branch returned `True` (pass) -- C-003 with no protection appendix, C-005/C-012/C-013/C-017 with no trend section, C-007/C-023 with no sentiment splits or nothing suppressed, and others. Against the session-2 partial regeneration (Executive Summary section only, from `runs/lacro_final_check/`), this produced "23/24 passed, 0 blocking failures" -- a clean-looking result that was really "8 things genuinely checked and correct, 15 things never present to check at all." `docs/report_checks.py` now has a third result state, `SKIP` (a check function returns `None` instead of `True`/`False`), reported separately: `8 passed, 15 skipped, 1 advisory failure(s), 0 blocking failures`. Audited all 24 checks individually (see the module docstring's "Result" section): every check whose subject matter can legitimately be absent from a partial report now skips rather than silently passing when it's missing (C-001, C-002 (both its own branches), C-003, C-004, C-005, C-006, C-007, C-008, C-009 (only when none of its four tracked labels appear anywhere outside the summary table), C-010, C-011, C-012, C-013, C-015, C-017, C-018, C-019, C-021, C-023). Four checks scan for a banned pattern anywhere in the text with no dependent section (C-014, C-016, C-020, C-022) and one scans for a leaked placeholder string with the same property (C-024) -- these have no legitimate "nothing to check" state (an absence of the banned pattern is itself the checked, correct outcome, not evidence of missing content) and were left pass/fail only.

*2. Coverage assertion.* `main()` now warns when more than a third of BLOCKING checks skip: `f"WARNING: {blocking_skipped}/{blocking_total} blocking checks ({pct}%) were SKIPPED -- most of this report's content was not present to check. This result is NOT evidence the report is correct, only that it is PARTIAL."` -- printed after the summary line, before the exit code. Against the session-2 partial regeneration this fires at 60% (12/20 blocking checks skipped).

*3. Frozen baseline fixture, and a reconciled PDF/docx discrepancy.* `fixtures/test9.txt` is now committed -- the Test9 baseline extracted once and pinned, not re-extracted ad hoc each session (the actual Test9.docx lives outside the repo, at `D:\Vision Fund International\report_test\...`, and was never itself committed here or previously converted to a stable text form). This surfaced a real discrepancy: the user's own PDF-based run reported 3 passed / 17 blocking against Test9; the docx-based extraction used earlier this session reported 4 passed / 16 blocking. Same underlying document, two different answers.

Root cause, confirmed by converting the real Test9.docx to an actual PDF (via Word COM automation, `docx2pdf`) and extracting both texts with standard tools (`python-docx`'s `iter_inner_content()` for docx; `pypdf` for the PDF) rather than guessing: Word's "List Number" paragraph style renders an auto-generated number (1., 2., 3., ...) that is computed by Word's numbering engine at *display* time from the paragraph's style, not stored as literal text in the paragraph's XML runs -- so `python-docx`'s `Paragraph.text` never includes it, while a PDF export bakes the rendered number into its text layer, where a standard PDF text extractor picks it up. Test9's Top Findings (List Number style, 3 items) and Recommended Actions (same List Number style, no restart in between) render as one continuous 1-6 sequence to a reader -- exactly the R-013 defect this spec already documents ("Top Findings are numbered 1 to 3 and Recommended Actions continue as 4 to 6"). The raw docx extraction was blind to this: C-018 (`summary_actions_restart_numbering`) found no leading number at all after "Recommended Actions" and silently passed, a false negative. Two more checks differed for unrelated, extraction-artifact reasons: C-002's row-span helper mis-parses the PDF's word-wrapped table cells (each cell on its own line rather than one line per row, breaking the newline-anchored row boundary fixed earlier this session) and silently found no table to check; C-004 undercounts the protection appendix's parenthetical `(client_ref, location)` entries by 2 in the PDF text, most likely for the same line-wrapping reason, producing a stated-vs-listed mismatch that isn't real.

Reconciled by building `fixtures/test9.txt` from the docx (reliable single-line-per-row table structure, immune to the PDF's word-wrap artifacts) but explicitly reconstructing Word's list numbering: every paragraph with style `"List Number"` gets a running counter prefix (`f"{n}. "`) in extraction order. Confirmed this is unambiguous for this document -- `"List Number"` style is used for exactly these 6 paragraphs and nowhere else, so a single global counter, not a per-numbering-definition one, exactly reproduces what Word renders. Result: **3 passed, 0 skipped, 4 advisory failures, 17 blocking failures** -- matching the user's own PDF-based count exactly, with every check's *reasoning* now correct rather than an artifact of which extraction path happened to preserve which formatting detail. Test9 is a complete, fully-populated report, so nothing skips against it; the 0-skip line is itself a coverage confirmation, the opposite of the session-2 partial-regeneration case above.

This blocking-failure count (17) is the project's baseline progress metric going forward. It is pinned to `fixtures/test9.txt`, not to an ad hoc extraction, specifically so it stops moving for reasons unrelated to the report itself.

**Baseline updated (session-8, 2026-08-2X) -- read this before citing "17 blocking" again.**
`fixtures/test9.txt` now reports **3 passed, 3 skipped, 3 advisory
failures, 15 blocking failures** against the current check suite, not
17. The drop from 17 to 15 blocking (and 4 to 3 advisory) is **not**
evidence of a defect fixed against Test9 -- Test9 itself has not
changed, and nothing about the report it represents got better. It is
entirely explained by C-006/C-007/C-008 becoming structural checks
that read `qualitative_results.json` directly instead of searching
rendered prose for the literal phrase "sentiment split" (see their own
docstrings in `docs/report_checks.py`). Test9 predates R-006a
entirely and has no `qualitative_results.json` at all, so all three
now correctly **SKIP** ("no qualitative_results.json provided")
instead of FAILing on a text-matching heuristic that happened to find
the phrase in Test9's own (pre-R-006a, genuinely broken) sentiment
prose. Two of the three were BLOCKING severity, one ADVISORY -- hence
17->15 blocking, 4->3 advisory, and 0->3 skipped. State this plainly so
nobody later reads the drop as progress: the 15 real blocking failures
Test9 still exhibits are exactly the same 15 substantive defects as
before (R-007, R-008, R-010, R-011, R-013's numbering, R-014's phrase,
the unrendered visuals, and the rest) -- none of them were touched.
**15 blocking failures is the baseline progress metric going forward**,
superseding the 17 above for the same reason 17 itself was pinned: so
it stops moving for reasons unrelated to the report itself.

---

## R-003 Deduplicate client protection appendix

**Source:** self identified, not raised by reviewers
**Layer:** `code`
**Priority:** high
**Status:** Implemented (2026-08-20)

**Current behaviour**
The appendix states 36 concerns (3 high, 24 medium, 9 low) but contains repeated entries:

| Client ref | Location | Times listed | Severity |
|---|---|---|---|
| 587099342 | San Felipe | 2 | high |
| 724084250 | Puebla | 3 | medium |
| 276806199 | Orizaba | 3 | medium |
| 549859 | QUITO | 2 | medium |
| 521899 | GUAMOTE | 2 | medium |

The stated count of 36 is therefore inflated, and the section that goes to the client protection team overstates its own caseload.

**Intended behaviour**
Signals are deduplicated on client reference plus signal category before counting and before rendering. Where one client raised genuinely distinct concerns, both are kept and the shared reference is noted.

**Rule**
```
key = (client_ref, signal_category)
Identical key with identical description -> collapse to one entry.
Identical key with differing description -> keep both, annotate
  "same client, multiple concerns".
Severity counts are computed after deduplication.
```

**Verification**
- `assert len(set((s.client_ref, s.category, s.description) for s in signals)) == len(signals)`
- `assert stated_total == len(signals)`
- `assert sum(severity_counts.values()) == stated_total`

**Note**
Flag this to Lorenz rather than fixing silently, since it changes a figure she has already read.

**Implementation note**
Found during the orientation pass (2026-08-20): the existing dedup in
`qualitative/llm_call.py`'s `_dedupe_protection_flags` collapses on
`(id, flag_type)`, where `id` is a survey row id, not a client. The same
client can generate a protection flag from more than one free-text row
(e.g. an NPS follow-up and a separate sparse-text field), so two distinct
rows for the same client survive that dedup as two entries. There is no
config knob for the dedup key today, and `client_id` is not attached to a
flag until `qualitative/parse_results.py`'s `_enrich_protection_flags`
runs, well after `_dedupe_protection_flags` has already run in
`llm_call.py`. A `(client_ref, signal_category)` dedup therefore cannot
live in config; it has to be code, and it has to run in
`qualitative/parse_results.py` (or later), after enrichment attaches
`client_id`, not in `llm_call.py`. Layer reclassified from `data_config`
to `code` accordingly.

**Verified figures**
Confirmed against the rendered Test9 appendix reason text (2026-08-20):
all five duplicated client refs above carry byte-identical reason text --
true duplicates, not distinct incidents. Actual entries rendered were 34
(not the 36 originally stated in-body -- a pre-existing stated/listed
mismatch, independent of the duplicates, that R-017 makes structurally
impossible going forward since both figures now read from the same
canonical list). After the client-level dedup pass: 27 (high 3->2, medium
24 stated/23 listed->17, low 9 stated/8 listed->8, unchanged). Verified on
a reconstructed fixture (no run artifact for this exists in-repo) against
`docs/report_checks.py`'s real C-003/C-004, plus a negative control
confirming C-003 fails pre-dedup on exactly these five refs.

---

## R-004 Per indicator comparability declarations

**Source:** LM3b, "replace with a column for Comparability ... indicate whether it is a clean comparison or indicative only"
**Layer:** `code`
**Priority:** high
**Pairs with:** R-009 (pulled forward into this phase, same code path -- see R-009 below), R-012 (code, not in scope this session)
**Status:** Re-specified (2026-08-20) -- layer changed from `data_config`, not yet implemented

**Current behaviour (corrected, session-4 orientation, 2026-08-20)**
Comparability reasoning already exists, but as a boolean in `analysis_engine/sections/part_10.py`'s `_COMPARABLE` dict (`True`/`False` per indicator), not the three-value status this requirement wants, and not in config. `_COMPARABLE[key]` gates whether `_compare_indicator()` attempts a delta/significance test at all -- a computation-time decision, not just a display label. A separate `_INCOMPARABILITY_REASON` dict carries reason text, but only for the three `False` indicators; the two comparable ones (`first_time_access`, `client_satisfaction_nps`) have no reason string today.

The Sig. column is empty for **all five rows**, not "three of five" as this section originally stated -- corrected against the real rendered `fixtures/test9.txt:53-58`. Four rows (`access_to_alternatives`, `child_wellbeing_improvement`, `product_understanding` -- `comparable=False`; `client_satisfaction_nps` -- comparable but hand-special-cased to never compute a test, `part_10.py:273-290`) are empty by design, structurally incapable of ever showing a mark. Only `first_time_access` ever attempts a real two-proportion z-test, and in this run it came out empty too because p >= 0.05 -- five of five empty in practice, four of five empty by construction. The original "three of five" matched neither count.

**Layer correction (session-4 orientation, 2026-08-20)**
`report_spec.yaml` is loaded only in the generation phase (`generation/orchestrator.py`, `generation/run_generation.py`), strictly after `analysis_engine` has already run and written `analysis_results.json`. It cannot gate `_compare_indicator()`'s decision to attempt a delta/significance test at all -- that decision is made during analysis, before generation ever runs. `analysis_engine` does read its own YAML config elsewhere (`analysis_engine/country_config.py` loads `country_configs/*.yaml`), so an analysis-phase config file is an available pattern in principle, but this requirement doesn't need a new config file to stop being "hardcoded prose" -- the comparability decision is Python today and stays Python; only its shape and completeness change. Layer reclassified from `data_config` to `code` accordingly.

**Intended behaviour**
`_COMPARABLE` in `analysis_engine/sections/part_10.py` becomes a three-value status per indicator (`"clean"`, `"indicative"`, `"not_comparable"`) instead of a bool, and every indicator -- including the two currently-comparable ones -- carries a reason string. Only `"clean"` attempts a significance test; `"indicative"` and `"not_comparable"` both skip it, exactly as today's `False` does -- no computation change, just a status distinguishing two cases today's boolean collapses into one. Per Lorenz (LM3): `access_to_alternatives` and `child_wellbeing_improvement` are `"indicative"` (the instrument changed, but a figure exists on both sides of the comparison); `product_understanding` is `"not_comparable"` (2025's combined question has no 2026 equivalent at all, so there is no current-wave figure to compare in the first place, not merely an incompatible one).

**Rule**
```python
# analysis_engine/sections/part_10.py
_COMPARABILITY = {
    "first_time_access": "clean",
    "client_satisfaction_nps": "clean",
    "access_to_alternatives": "indicative",
    "child_wellbeing_improvement": "indicative",
    "product_understanding": "not_comparable",
}
_COMPARABILITY_REASON = {
    "first_time_access": "Identical question wording and options in both waves.",
    "client_satisfaction_nps": "Same 0 to 10 scale in both waves.",
    "access_to_alternatives": "2026 adds a neutral midpoint and an I don't know option.",
    "child_wellbeing_improvement": "2025 used a 5 point scale; 2026 uses binary yes or no.",
    "product_understanding": "2025 used one combined 6 option question; 2026 splits it into two 4 point questions.",
}
```
Key fixed from the original draft's `child_wellbeing` to `child_wellbeing_improvement`, matching `_INDICATORS`, `_COMPARABLE`, and `report_spec.yaml`'s own `trend_indicators` key everywhere else in the codebase. `_INCOMPARABILITY_REASON`'s existing three reason strings are kept where they already exist (they match this spec's substance); only the two comparable indicators' reasons and the three-value status split are new.

**Verification**
- `assert every trend indicator has a comparability value in {"clean", "indicative", "not_comparable"}`
- `assert every indicator has a non empty reason string`
- `assert only "clean" indicators have a significance test attempted` (same gate as today's boolean `True` -- `"indicative"` and `"not_comparable"` both skip it)

**Correction (session-5, per Lorenz/LM3, 2026-08-20)**
The first implementation (session-4) also suppressed BOTH wave values for every non-`"clean"` row, reasoning that "no computation change" meant "no display change either." That conflated the two: the delta/significance-test GATE is unchanged (still `"clean"` only, as designed above), but Lorenz's actual point in raising this in the first place was to STOP suppressing real numbers, not just to relabel why they were suppressed -- `"the whole point [of a Comparability column is] so we can SHOW both numbers and label the quality of the comparison, rather than suppressing one side."` `access_to_alternatives` and `child_wellbeing_improvement` both have real figures on both sides (48.9%/44.5% and 23.5%/36.1% respectively) that the first pass rendered as "NOT COMPARABLE" anyway. Fixed the same session it was caught in (see R-005's own implementation note for the rendering detail, since this crosses into that requirement's territory).

**Scoring correction (session-6, per Lorenz, 2026-08-20)**
`product_understanding`'s 2025 figure (the only real value this
indicator ever has -- 2026 has no equivalent question, see above) was
computed as the single most positive response option only
(`_PRODUCT_UNDERSTANDING_GOOD = ["I know everything"]`), a judgment call
`analysis_engine/sections/part_10.py`'s own prior comment flagged as
"pending survey-team confirmation... the remaining 5 options don't have
an unambiguous ordering agreed with the survey team yet." Lorenz has now
confirmed the ordering of the 2025 instrument's six options:

```
rank 1: I know everything                                      (190)
rank 2: Partially, I know the benefits process only             (295)
        Partially, I know the claims process only                (74)   [equal rank]
rank 3: I know little, but I can contact VFI to help clarify    (202)
        I know little                                           (445)   [equal rank]
rank 4: No knowledge                                            (149)
```

With the ordering settled, the metric moves to a proper top-2-box:
ranks 1 and 2 count as positive. Verified against
`runs/lacro_2025_pooled/survey_clean.parquet` directly (the only run
that still has `q_product_understanding_combined`, since 2026 splits
the question in two): base is 1,355 (matches the count above exactly:
190+295+74+202+445+149=1355), positive is 190+295+74=559, giving
559/1355 = 41.3%, replacing the previous 190/1355 = 14.0%. Both
`analysis_engine/sections/part_1.py` and
`analysis_engine/sections/part_10.py` define `_PRODUCT_UNDERSTANDING_GOOD`
independently (by design, so Part 1 and Part 10 can never disagree only
if both are updated together) -- both updated to
`["I know everything", "Partially, I know the benefits process only",
"Partially, I know the claims process only"]`. `generation/report_spec.yaml`'s
narrative note for `product_understanding` previously instructed the
writer to describe this as "the single most positive response option
only... a stricter bar than a typical top-2-box... do not describe it
as top-2-box" -- also updated, since that instruction now
actively contradicts the metric it describes.

Because `runs/lacro_2025_pooled/analysis_results.json` is a persisted
snapshot from a run predating this change, the new figure only reaches
a rendered report after that run is regenerated -- changing the
`_PRODUCT_UNDERSTANDING_GOOD` constant alone does not retroactively
update already-written prior-wave JSON.

---

## R-005 Dominican Republic trend handling is explicit

**Source:** self identified
**Layer:** `data_config`
**Priority:** medium
**Status:** Re-specified (2026-08-20) -- verification scope narrowed, not yet implemented

**Current behaviour**
The Dominican Republic is new in 2026 and contributes 270 respondents (15.7 percent). The trend section handles this correctly by computing a five country comparable subset, but the handling is described only in footnotes and the headline figures in the table are the all country values, so the table and its own footnotes disagree on which number matters.

**Intended behaviour**
The trend table reports the comparable subset figures as its primary values, with all country figures shown separately or omitted. The exclusion is stated once, near the table, not repeated per indicator.

**Rule**
```yaml
trend_scope:
  comparable_countries: [Ecuador, Guatemala, Bolivia, Mexico, Honduras]
  excluded_new_countries: [Dominican Republic]
  primary_figures: comparable_subset
```

**Scope correction (session-4 orientation, 2026-08-20)**
The subset swap applies to the two `"clean"` rows only (`first_time_access`, `client_satisfaction_nps`), not every row where comparability `!= "not_comparable"` as originally verified here. `"indicative"`/`"not_comparable"` rows keep today's no-delta behaviour unchanged -- the three-value status (R-004) is a labelling/reason distinction, not a new significance-testing capability. Only `"clean"` rows ever populate `current_common_scope`, and R-004's design point is explicit that this session makes no computation changes beyond the status split. Extending the five-country swap to indicative rows would require attempting a delta for them, a real behaviour change outside this session's scope. **This note originally continued with "'NOT COMPARABLE' in the prior-wave column [for indicative rows] -- exactly like 'not_comparable' rows" -- that specific claim about DISPLAY (not delta-testing) was wrong and superseded the same session it shipped; see the session-5 correction below and in R-004.**

**Implementation note**
- `analysis_engine/sections/part_10.py`'s `calculate()` currently persists only `current_full` as `"current"` in the returned/saved dict (`analysis_results.json`) -- `current_common` (the five-country subset) is computed every run but discarded after use, never saved. This session also persists it (`"current_common": current_common` alongside `"current": current_full`), so a future wave's `_load_prior_snapshot()` can read back this wave's own five-country figure once it becomes someone else's prior wave. Not consumed by anything this session -- 2025's own data is inherently five-country already (Dominican Republic has no 2025 rows at all) -- but costs one line now versus a rerun later once a third wave exists. Verified persisted: `runs/lacro_final_check/analysis_results.json`'s `parts.part_10.current_common.first_time_access.value` = 0.7670572..., `client_satisfaction_nps.value` = 46.175... -- both match Test9's own published five-country footnote figures (76.7%, 46.2) exactly.
- `generation/orchestrator.py`'s `_build_trend_data()` currently sets the table's `group_a_value` (2026) from `current_full_scope` unconditionally. For `"clean"` rows this switches it to `current_common_scope`'s value instead; `"indicative"`/`"not_comparable"` rows keep `current_full_scope`, matching what every other Part reports for that same indicator (there is no test result to keep it consistent with instead).
- The Dominican Republic exclusion sentence, previously rebuilt inside each `"clean"` row's own footnote (appearing twice in `fixtures/test9.txt` -- once per clean row), now renders once as a table-level scope note before the table.

**Correction (session-5, per Lorenz/LM3, 2026-08-20)**
The session-4 implementation suppressed BOTH wave values for `"indicative"`/`"not_comparable"` rows, rendering the literal string "NOT COMPARABLE" in the prior-wave (2025) column even when a real figure existed. Caught immediately against the real render: `access_to_alternatives` (2025=48.9%, 2026=44.5%) and `child_wellbeing_improvement` (2025=23.5%, 2026=36.1%) both have real figures on both sides -- the instrument change is exactly why they're `"indicative"` rather than `"clean"`, not a reason either number is missing. Fixed: both values now render for every row whenever they exist; only the delta/significance test stays withheld (never computed for non-`"clean"` rows, unchanged from R-004). `product_understanding` is the genuinely different case R-004 already describes -- its OWN 2026 figure is truly absent (the unified schema has no combined-question form to compute it from), so it correctly shows a real 2025 value (confirmed resolving from `runs/lacro_2025_pooled/`) against 2026 "NOT APPLICABLE", not "NOT COMPARABLE" on either side.

This required an authorised exception to this session's own file-scope constraint: `generation/validate_output.py`'s `_non_comparable_labels()` identified which rows need the "no comparative language" ban applied by checking `row["group_b_value"] == "NOT COMPARABLE"` literally -- once that string stopped being what those rows render, the check would have silently gone quiet for exactly the rows most needing it. Fixed to key off `comparability in ("indicative", "not_comparable")` instead, a durable signal independent of what the cell displays.

**Verification**
- `assert trend_table.scope_note appears exactly once`
- `assert trend rows use comparable subset (current_common_scope) values for "clean" rows only`
- `assert indicative/not_comparable rows render a real prior-wave value whenever one exists, never the literal string "NOT COMPARABLE" when data is available`
- `assert no delta or significance test is computed for indicative/not_comparable rows even though both values may now be displayed`

---

## R-009 Trend table replaces significance with comparability

**Source:** LM3b
**Layer:** `schema`
**Priority:** high
**Depends on:** R-004
**Status:** Pulled forward from Phase 2 into Phase 1 (2026-08-20) -- same code path as R-004 and R-005: removing the Sig. column and adding the Comparability column is one table restructure in `generation/orchestrator.py`'s `_build_trend_data()` and `generation/assembler.py`'s `build_part_10()`, not two. Splitting them across phases would leave R-004's three-value status computed but nothing downstream reading it. Not yet implemented.

**Current behaviour (corrected, session-4 orientation, 2026-08-20)**
Columns are Indicator, Current Wave, Prior Wave, Sig. The significance column is empty for **all five rows** (see R-004's correction of the same "three of five" error, made in the same pass), and its footnote claims a two proportion z test is used for all rows including NPS, which is not a proportion and for which respondent level prior wave scores were never retained.

**Intended behaviour**
Columns become Indicator, 2025, 2026, Comparability. The significance column and its footnote are removed entirely. The comparability reason moves from footnote to an inline note beneath the table, one line per indicator.

**Rule**
```python
class TrendRow(BaseModel):
    indicator_label: str
    prior_wave_value: str | None      # "NOT COLLECTED" where absent
    current_wave_value: str | None
    comparability: Literal["clean", "indicative", "not_comparable"]
    comparability_reason: str
    # no significance field exists on this model
```
Illustrative shape carried over from the original draft, not a commitment to a new Pydantic model this session -- see the implementation plan for how this actually threads through the existing scorecard-row dict shape `_build_trend_data()` already produces (shared rendering path with Parts 6/7). Revisit this Rule block if implementation reveals the dict shape is the better fit long-term, per this document's own rule 5.

**Implementation note**
The literal "p=0.0553" text Test9 exhibits does not come from the table (which only ever renders "*" or nothing for a match) -- it comes from `generation/writer.py`'s `_build_scorecard_text()` (shared by Parts 6, 7, and 10), which builds a `(p=...)` string into the LLM prompt whenever `row["sig_p"]` is set, combined with the global VOICE RULES instruction to "cite the p-value." `significance_test()` (`analysis_engine/stats.py`) itself is not touched -- it is also used by Parts 5, 6, and 7's own legitimate significance tests via `scorecard_row()`. The fix is `orchestrator.py`'s `_build_trend_data()` no longer setting `sig_p`/`significant` on Part 10's rows; `_build_scorecard_text()`'s existing `if row['sig_p'] is not None` guard then goes quiet for Part 10 without any change to that shared function, and without touching Part 6/7's own rows. Proven directly (per instruction, not just inferred from the row dict): `tests/test_writer.py::TestBuildScorecardTextPart10NoPValueLeak` feeds Part-10-shaped rows into the real, unmodified `_build_scorecard_text()` and asserts no `(p=` text and no significance asterisk are produced, while a Part-6/7-shaped row with a real `sig_p` still cites it.

Column order (session-5, per Lorenz): chronological, "Indicator, 2025, 2026, Comparability" -- current-wave-first was this session's own initial choice, not what was asked ("renaming... not restructuring"); Lorenz specifically wants left-to-right chronology since descending order invites misreading the direction of change, and is flagging to Lorenz's own reviewer (Lorenz to Lorenz's stakeholder) that this is a deliberate, acknowledged departure from her literal "rename" instruction. `row["group_a_value"]`/`["group_b_value"]` stay current/prior internally in `orchestrator.py` (unchanged, matches Parts 6/7's convention and what `writer.py`'s prompt text still calls them, R-012 not this session) -- the swap to chronological order happens only in `assembler.py`'s render step. C-005's header regex is order-agnostic (`20\d\d\s+20\d\d` matches either year first) and needed no change for the reorder.

**Verification**
- `assert "Sig." not in trend_table.headers`
- `assert trend_table.headers == ["Indicator", "2025", "2026", "Comparability"]`
- `assert no p value appears anywhere in Part 10`
- `assert every row has a comparability value and reason`

**Session-5 check-suite finding**
C-005's header regex (`indicator\s+20\d\d\s+20\d\d\s+comparability`) assumed pure-whitespace-separated header cells and never matched this project's own `|`-delimited extraction convention (including the committed `fixtures/test9.txt`) regardless of whether the Comparability column existed -- fixed to `indicator[\s|]+20\d\d[\s|]+20\d\d[\s|]+comparability`. Separately, C-017 (R-012) fired on the natural-English footnote phrase "the prior wave" ("Not comparable to the prior wave: ...", present in the original text before this session too) rather than a genuine header, once the real header text no longer contained the more obvious literal "Current Wave"/"Prior Wave" trigger to mask it -- restricted to the header row region specifically (the text starting at "indicator" within the Trend Comparison section, not the whole section). Both authorised exceptions, per instruction.

---

# Phase 2: Schema

These changes make defective output structurally impossible rather than merely discouraged.

## R-006 Sentiment and verbatim selection (split session-6, 2026-08-20)

**Source:** LM7 ("I am leaning towards the actual counts because it's less prone to misinterpretation"), LM6 ("how is the data being sliced ... making the base too small for percentages?")

Originally one requirement. Split this session once the investigation
below distinguished two independent problems sharing one symptom (bases
of 3 to 10 per section): **R-006a** fixes the sentiment base.
**R-006b** fixes the verbatim nomination cap. Neither depends on the
other and they are implemented separately. This section keeps the
shared investigation; R-006a and R-006b follow with their own decision
and rule.

**Current behaviour**
Sentiment is reported inconsistently across sections: percentages in Part 1 (10 percent, 60 percent, 30 percent on a base of 10), raw counts in Parts 2 through 6, and an explicit apology in Part 3 that the base is too small for percentages.

The underlying problem is larger than presentation. Observed bases by section:

| Section | Sentiment base |
|---|---|
| Part 1 | 10 |
| Part 2 | 7 |
| Part 3 | 7 |
| Part 4 | 6 |
| Part 5 | 7 |
| Part 6 | 3 |
| Part 7 | 3 |

The NPS follow up field is filled by every respondent in the LACRO instrument, and something discards over 99 percent of the available pool by the time it reaches sentiment reporting.

**Root cause (session-6 investigation, 2026-08-20)**
There is no relevance filter discarding responses. Every NPS follow-up
record is theme-tagged at full coverage in the batch call
(`qualitative/llm_call.py`, Task 1) -- nothing about the LACRO
instrument's single always-on NPS column causes responses to be dropped
before tagging.

The actual mechanism is a compounding nomination cap, unrelated to
relevance or response quality:
1. `_CANDIDATES_PER_SECTION_PER_BATCH = 2` (`llm_call.py:71`) -- each
   batch independently shortlists at most 2 verbatim candidates per
   report section, drawn from its own slice only, with no visibility
   into what any other batch shortlisted.
2. LACRO's roughly 1,721 NPS responses split into 3 batches of
   `_NPS_BATCH_SIZE = 600` (`llm_call.py:65`), so the pooled candidate
   ceiling per section going into the synthesis call is 3 x 2 = 6,
   before the synthesis call runs at all.
3. The synthesis call is then hard-instructed to "Pick exactly 3 row
   IDs (verbatim quotes)" per section (`llm_call.py:453`) -- a fixed
   count, not a threshold, which is why every section with any
   verbatims renders exactly three.

Both (1) and (3) were sized to solve a token-budget problem in the 2026
two-call redesign (see `llm_call.py`'s module docstring: the original
single-call design broke past roughly 2,100 respondents), not to
control per-section sample size, and neither has been revisited against
respondent volume since.

**Investigation prerequisite (blocking) -- resolved, session-6, 2026-08-20**
1. Pool: every configured open-ended column in `qualitative/config.yaml`,
   filtered only by `min_text_length: 10` **characters**
   (`config.yaml:5`, applied at `prepare_payload.py:109`) -- not a
   word-count floor, and far below the observed 6-word median LACRO
   response length. This filter is not the bottleneck.
2. There is no relevance selection rule with a threshold. The
   restriction that matters is the nomination cap described above, not
   a quality bar -- see root cause.
3. **Corrected (session-6, continued investigation, 2026-08-20):** the
   previous report's "ruled out" conclusion here was incomplete. It
   confirmed that `prepare_payload.py:21-36`'s purpose-built `by_score`
   bucketing for LACRO's single always-on `q_nps_followup` column
   exists in code, but did not confirm that code path is what the real
   2026 data actually exercises. It is not: `runs/lacro_final_check/
   survey_clean.parquet` has no `q_nps_followup` column at all. The
   2026 unified-schema load instead produces `q_nps_promoter_followup`
   / `q_nps_passive_followup` / `q_nps_detractor_followup` -- Africa's
   exact three gated columns, 100 percent collectively filled (1,044 +
   465 + 212 = 1,721) -- so `qualitative/config.yaml:35-46`'s
   documented `by_score` architecture is dead code against the dataset
   every current LACRO report is actually generated from. Only
   `runs/lacro_2025_pooled/survey_clean.parquet` still has the single
   always-on `q_nps_followup` column that architecture was built for
   (1,355/1,355 filled). In outcome this is harmless -- the gated-
   column split already encodes the score band at load time, so NPS
   promoter/passive/detractor grouping is still correct and fully
   deterministic for 2026 data, just via Africa's mechanism rather than
   LACRO's purpose-built one -- but prerequisite #3, taken literally,
   is not ruled out for 2026. Whether the now-dead `by_score` path is
   worth removing is a separate cleanup question, not raised as a
   requirement here.

**Additional finding, required before R-006a's Rule can be
implemented:** `base_n`, `source_pool_n`, and `selection_rule` do not
exist anywhere in the current schema. `section_insights.sentiment_split`
is an unlabeled `{positive, negative, neutral}` dict with no
accompanying pool-size field, and the model is never asked how many
responses it reviewed for a section.

Record findings in this section before writing code.

---

## R-006a Sentiment reported as counts with a stated base

**Layer:** `schema`
**Priority:** high
**Depends on:** R-006's investigation above

**Decision (session-6):** compute the sentiment split deterministically
in Python over the full theme-tagged NPS pool (not the roughly
6-candidate verbatim shortlist), giving a real `base_n`. This decouples
sentiment entirely from R-006b's nomination cap and subsumes R-023
(logged separately; see R-023's own note -- now superseded by this
decision).

**Feasibility (session-6, read-only, 2026-08-20)**
Section assignment is NOT a deterministic, code-held mapping for four
of the seven report sections. Nothing in the codebase maps
`THEME_TAXONOMY` codes (`llm_call.py`'s `_THEME_TAXONOMY_BLOCK`, 13
codes) to report section keys. Section membership for Part 1 (Product
Understanding), Part 2 (Claims Experience), Part 3 (Financial
Inclusion), and Part 4 (Client Voice) is decided entirely by the
model's judgement -- both the per-batch shortlist (Task 3) and the
synthesis final pick (Task 4A) match a response's free text against
freeform `topic_hint` prose per section (`qualitative/config.yaml:199-229`),
not against theme codes. A record is asked, by prompt instruction only
("Do NOT repeat the same row_id across sections", `llm_call.py:297`
and its synthesis-call equivalent at `llm_call.py:460`), not to appear
in more than one section -- nothing in code enforces or validates that,
so it is a soft rule, not a guarantee, and nothing stops a response's
themes from genuinely relating to more than one section's topic_hint.

Three of the seven sections are different: Part 5 (Child Wellbeing),
Part 6 (Claimant Outcomes), and Part 7 (Gender) are not topic-matched
at all. They are driven by `config.yaml`'s `prefer_segment` /
`require_diversity` keys against `is_caregiver` / `is_claimant` /
`is_female` flags already computed deterministically per record in
`prepare_payload.py`'s `_build_response_record()` (`prepare_payload.py:39-58`).
These three sections' `base_n` is Python-computable today, with no new
design work.

Implication: the deterministic split is directly achievable now for
Parts 5, 6, and 7. Parts 1 through 4 need a new, code-held
theme-code-to-section grouping designed first -- without one, "which of
the pool's responses belong to Part 2" is not a question code can
currently answer, only the model's judgement can.

**Order of magnitude (session-6, computed against
`runs/lacro_final_check/survey_clean.parquet`)**
1,674 of 1,721 NPS responses pass `min_text_length`. Segment-scoped
pools, computed directly:
- Part 5 (is_caregiver): 1,281
- Part 6 (is_claimant): 47
- Part 7: 1,196 female / 478 male

Hundreds is the right order of magnitude for most sections, but not
uniformly: Part 6 is structurally capped near 47 to 55 by how few
LACRO respondents are claimants at all -- no mapping design changes
that ceiling, since it reflects a real population size, not an
artifact of the nomination cap. Parts 1 through 4 have no computed
number yet (no mapping exists), but a structural estimate -- roughly
1,674 records, 1 to 3 theme tags each, 13 taxonomy codes, several
codes plausibly grouped per section -- lands in the low-to-mid hundreds
per section once a mapping is designed, consistent with the "hundreds"
expectation for those four sections specifically.

**Intended behaviour (revised session-8, per Lorenz, 2026-08-2X -- see
correction below)**
Sentiment is always reported as integer counts, with a percentage
permitted alongside once the base is large enough to make one
meaningful. The base is always stated. The selection rule is always
available to the renderer.

**Percentage rule revised (session-8, per Lorenz, 2026-08-2X)**
The original rule below ("percentages are never emitted for
sentiment") and the `SentimentSplit` model's "no float or percentage
field" design were written when every section's base was 3 to 10 and
unstated. Re-reading LM7 precisely: *"I am leaning towards the actual
counts because it's less prone to misinterpretation"* objects to an
**unstated, unverified base being dressed up as a percentage** --
100% of 3 reads as a finding when it is nothing of the kind. It is not
an objection to percentages as a concept. That rationale does not
survive R-006a: bases are now real, code-computed, and stated
(`base_n`/`source_pool_n`/`selection_rule`), and at the scale R-006a
Stage 1/2 actually produce (hundreds, not single digits), a bare count
becomes LESS informative than a percentage once two differently-sized
groups are compared -- 428 positive women against 180 positive men
(Part 7) is not interpretable without normalising by each group's own
base. Suppressing the percentage there would not protect a reader from
misinterpretation, it would cause it.

Revised rule: a percentage MAY be reported for a sentiment split
whenever `base_n >= 10` (the existing `_SENTIMENT_SPLIT_MIN_BASE_FOR_PCT`
threshold, unchanged), and MUST always appear alongside its count,
never alone. `generation/writer.py`'s existing VOICE RULES instruction
("state EVERY category as `n (pct%)` together... never a bare count
and never a bare percentage on its own") already enforces exactly
this and is correct as written -- it stays unchanged; nothing in
`writer.py` needed to change for this revision. Below `base_n = 10`,
counts only, unchanged from the original rule.

**Rule**
```python
class SentimentSplit(BaseModel):
    positive: int
    negative: int
    neutral: int
    base_n: int
    selection_rule: str          # human readable, e.g.
                                 # "NPS follow up responses scored
                                 #  relevant to product understanding"
    source_pool_n: int           # Pinned definition (session-6 Stage 1
                                 # implementation, superseding the
                                 # original "total free text responses
                                 # considered" wording): the section's
                                 # ELIGIBLE population (e.g. every
                                 # claimant in the dataset), independent
                                 # of whether they left any usable text.
                                 # base_n is the subset of source_pool_n
                                 # whose response also passed
                                 # min_text_length and was therefore
                                 # actually classified. Stated once here
                                 # so it cannot drift between sections.

    @model_validator(mode="after")
    def counts_sum_to_base(self):
        if self.positive + self.negative + self.neutral != self.base_n:
            raise ValueError("sentiment counts must sum to base_n")
        return self
```

No float or percentage field exists on this model -- a ratio is
computed at render time from the stated counts and `base_n`, per the
revised rule above, not carried as data. This model's job is still to
guarantee a real, stated base exists to compute a percentage FROM;
that guarantee, not a blanket percentage ban, is what LM7's concern
actually required.

**Verification**
- `assert every rendered sentiment percentage is accompanied by its count and its base_n` (revised session-8; supersedes the original "no sentiment string contains %" bullet, which banned the wrong thing -- see the percentage rule revision above)
- `assert every sentiment block states base_n and source_pool_n`
- `assert positive + negative + neutral == base_n for all sections`
- `assert base_n is derived from a Python-computed pool, not a model self-report, for every section where a deterministic mapping exists`
- Report level check: log the base for every section so over restriction is visible at a glance

**Open question for implementation (not this session)**
Design the theme-code-to-section grouping for Parts 1 through 4 (or an
alternative deterministic rule specific to those sections) before
implementing them.

**Stage 1 implemented (session-6, 2026-08-20)**
Parts 5 and 6 implemented as designed: `qualitative/parse_results.py`'s
`compute_stage1_sentiment_splits()` computes `base_n`/`source_pool_n`/
`selection_rule`/counts in Python from every NPS record Task 1 tagged
(`qualitative/llm_call.py`'s Task 1 now emits a per-record sentiment
enum alongside theme codes), wired into `parse_and_save()` to override
just those two sections' `sentiment_split` (theme_summary/top_drivers
untouched, still the model's own).

Two corrections made during implementation, before commit:
- `selection_rule`'s wording originally said "N of M {population} left
  a response" -- inaccurate, since the NPS follow-up is filled by 100%
  of respondents. The gap between `base_n` and `source_pool_n` is the
  `min_text_length` (10-character) filter excluding short responses,
  not respondents failing to answer. Corrected to: *"NPS follow-up
  responses from {population}, excluding responses under {N}
  characters; {base_n} of {source_pool_n} {population} qualify."*
- A hard guard (`_looks_synthetic()`) now raises `ValueError` if a
  section's positive/negative/neutral counts are exactly tied at a
  base_n of 15 or more -- the signature a round-robin or other
  placeholder generator produces, and not a plausible coincidence for a
  real classification at that scale. Verified it does not false-positive
  on a real-looking uneven distribution or on a small, plausibly-tied
  base (below the threshold). Note: filtering to a segment (as Parts 5/6
  do) breaks a naive round-robin's periodicity, so this guard is
  strongest against an unfiltered pool (which is exactly Part 7's
  shape, see below) -- it is defense in depth for Parts 5/6, not a
  guarantee against every possible synthetic pattern.

**Part 7 (Gender): direct answer (session-7, 2026-08-2X) -- the schema
permits only one split per section. Two splits were not built.**

The prior "paused" wording in this section answered neither of the
questions it was asked. Precisely: `section_insights.*.sentiment_split`
is, today, one flat dict per section
(`{positive, negative, neutral, base_n, source_pool_n, selection_rule}`),
enforced not by a formal schema but by two consumers that both assume
that flat shape uniformly across every section -- `generation/writer.py`'s
`_fmt_insight_summary()` (`writer.py:370-373`, sums `split.values()` and
joins `k=v` pairs over the dict) and `generation/validate_output.py`'s
sentiment-base checks (`validate_output.py:410-414`, same summation). A
two-way split for Part 7 cannot be added by changing
`qualitative/parse_results.py` alone -- both of those consumers would
need to branch on Part 7 specifically. That cross-file scope, not any
uncertainty about what was wanted, is why it was not built this
session: R-006a Stage 1's authorization covered `parse_results.py`
(and `llm_call.py`'s Task 1 prompt), not the rendering/validation
layer.

Proposed shape (session-7): `{"female": {...}, "male": {...}}` for
Part 7 only, every other section staying a bare flat dict. **Revised
before building (session-8, per instruction): rejected in favour of ONE
uniform shape for every section.**

**Part 7 implemented (session-8, 2026-08-2X)**
Every section's `sentiment_split` is now `{group_label: {positive,
negative, neutral, base_n, source_pool_n, selection_rule}}` -- a
single-group section (Parts 1 through 6) nests under the one key
`"all"`; Part 7 uses `{"female": {...}, "male": {...}}`. No section is a
schema special case: `_fmt_insight_summary()` and
`validate_output.py`'s sentiment-base check always iterate
`sentiment_split.items()` as groups, never branch on section identity or
group count. This means a hypothetical future section needing its own
split (by country, by claimant status) needs no further schema work --
it is simply another set of group keys.

`qualitative/parse_results.py`'s new `compute_part7_sentiment_splits()`
computes each sex's population the same way Stage 1 computes part5/part6
(a demographic count in `df`, independent of tagging -- `source_pool_n`
= total women/men; `base_n` = the subset who left a response of at
least `min_text_length` and were tagged), sharing the same synthetic-
split guard (`_finalize_split`).

**writer.py: local instruction, no VOICE RULES change** (per
instruction, approved before building) -- `_fmt_insight_summary()`
renders one line per group, and when a section has more than one group
it prepends a local instruction ("compare these groups explicitly in
your prose... do NOT report each group's figures as a separate,
isolated statement") specific to that section's own text block, not the
shared VOICE RULES every part's prompt uses. VOICE RULES' existing
"state EVERY category as `n (pct%)` together" instruction already
applies per group unchanged (each group's own `base_n` gates whether
that group is percentage-eligible, per the revised percentage rule
above) -- comparing two groups now naturally uses each one's own
percentage, which is exactly why the percentage rule needed revising
first (428 positive women against 180 positive men is not comparable
without normalising by each group's own base).

**validate_output.py: per-group, not summed** (per instruction) -- the
old `sentiment_total = sum(v for v in sentiment_split.values() if
isinstance(v, (int, float)))` assumed a flat dict; under the nested
shape every value is itself a dict, so that line would have silently
summed to 0 for every section, misfiring on every percentage found
anywhere. Rewritten: `_check_tiny_sentiment_base_percentages()` now
takes the whole `sentiment_split` dict and checks each group's own
`base_n` independently, so a tiny group's problem is never hidden
behind a large group's size in the same section.

**C-006 / C-007 (docs/report_checks.py), authorised for these two
checks only:** C-006 renamed in substance to
`sentiment_percentage_paired_with_count_and_base` -- no longer bans
"%", instead requires every percentage found within a "sentiment split"
text window to be paired with both a raw count (`"N (pct%)"`) and a
stated base. C-007 unchanged in intent (states its base) but its base-
detection pattern is broadened from the literal word "responses" to
also match the population nouns R-006a's `selection_rule` text now uses
("caregivers", "claimants", "women", "men"). Both already iterate every
"sentiment split" mention `_find_all()` finds in the text, so a grouped
section producing multiple mentions (one per group) needed no
structural change -- only the two checks' own logic (percentage
pairing; base-word vocabulary).

**Consumer audit (session-8, per instruction, before building):**
grepped the whole repo including `dashboard/` and any frontend code.
Two authorised consumers (`writer.py`, `validate_output.py`) plus one
NOT authorised and left untouched: `qualitative/run_qualitative.py`'s
own CLI debug summary printer (lines ~128-141) also read
`sentiment_split` -- fixed anyway per instruction (in scope: "three
lines and a console log that prints wrong is a trap for whoever reads
it next") to iterate groups instead of assuming a flat dict.
`qualitative/llm_call.py`'s synthesis prompt still shows the model a
flat `sentiment_split` example in its OUTPUT SCHEMA text for all seven
sections -- left as is per instruction (overridden downstream for every
section regardless of what the model actually returns there; changing
prompt text is a separate authorisation). No dashboard or frontend code
reads `sentiment_split` at all.

**Separately (session-8 smoke test finding, fixed not logged, per
instruction):** neither `qualitative/run_qualitative.py` nor
`dashboard/api/pipeline_runner.py` called `load_dotenv()`, so a `.env`
file at the project root was never picked up by the real pipeline --
only `os.environ` being pre-populated some other way worked. Both now
call `load_dotenv()` against the project-root `.env` at import time.

---

## R-006a Stage 2: theme-to-section mapping for Parts 1-4

**Layer:** `code` (config-driven)
**Priority:** high
**Status:** Implemented (session-7, 2026-08-2X) -- **unverified against
real tags**, see below.

**Mapping (Lorenz-approved, session-7)**
Stored in `qualitative/config.yaml`'s `report_sections` entries, as a
`theme_codes` list per Part 1-4 section (`qualitative/parse_results.py`'s
`_load_theme_section_map()` reads it back into a `{section: set(codes)}`
lookup):

| Section | Theme codes | Count |
|---|---|---|
| Part 1 (Product Understanding) | `product_understanding` | 1 |
| Part 2 (Claims Experience) | `claims_speed`, `claims_process`, `payout_adequacy` | 3 |
| Part 3 (Financial Inclusion) | `access_inclusion`, `financial_relief` | 2 |
| Part 4 (Client Voice) | `product_value`, `staff_service`, `general_satisfaction`, `improvement_suggestion`, `complaint_grievance` | 5 |

`child_family` and `crop_agricultural` are unmapped by design -- they
match Part 5's and Vietnam's own constructs, not any of Parts 1-4's
topics; a record tagged only with one of these contributes to no
Part 1-4 base (expected, not a defect).

**Principle (record this next to the mapping, per instruction): single
primary mapping, not dual-mapping**
Each theme code maps to exactly one section. A cross-cutting case is
handled by **co-tagging**, not by listing a code under two sections: a
response about a staff complaint arising during a claim carries both
`staff_service` and `claims_process`, and reaches both Part 4 and
Part 2 that way (`compute_stage2_sentiment_splits()` already does
this -- a record belongs to every section whose `theme_codes` intersect
its own tags, so co-tagging naturally produces overlap where it is
real). Dual-mapping a broad code like `staff_service` to a second
section directly would instead pull every unrelated staff complaint
into that section regardless of what the complaint was actually about.
Two judgment calls resolved this way this session: `payout_adequacy`
to Part 2 only (not also Part 3), `staff_service` to Part 4 only (not
also Part 2). Apply the same principle to any future addition.

**Projected relative base sizes (flagged per instruction, not yet
verified)**
Part 1 carries exactly one theme code against Part 4's five. Part 1's
`base_n` is expected to be materially smaller than Part 4's for that
structural reason alone -- Part 1 has a narrower, more specific topic
(product knowledge specifically) where Part 4 is a broad "general NPS
driver" catch-all across five different codes. A smaller Part 1 base
must not be read as evidence of a bug or of under-tagging; it is the
direct, predictable consequence of the code counts above.

**Pinned `source_pool_n` for theme-mapped sections (distinct from Stage
1's demographic reading, same contract)**
There is no independent "eligible to be about claims" population the
way there is an "eligible to be a caregiver" one -- eligibility for a
theme-mapped section can only be known after tagging. `source_pool_n`
for Parts 1-4 is therefore every NPS record Task 1 tagged with at least
one theme (the pool that could possibly have matched ANY section) --
the same number across all four sections. `base_n` is the subset of
that pool whose themes specifically matched THIS section's
`theme_codes`. Both still satisfy the same pinned contract from Stage 1
(`source_pool_n` is what was eligible to count; `base_n` is what
actually did).

**First real-tag signal (session-8, smoke test, 2026-08-2X) -- still not
a full run**
A `GEMINI_API_KEY` is now configured; a one-batch smoke test (200 real
records, mixed nps_group, `runs/lacro_final_check/`) tagged real themes
and sentiment (see the session-8 smoke test report). Applying the
approved Stage 2 mapping to those 200 real tags, before any full run:

| Section | Codes | base_n | of 200 |
|---|---|---|---|
| Part 1 (Product Understanding) | 1 | 41 | 20.5% |
| Part 2 (Claims Experience) | 3 | 6 | 3.0% |
| Part 3 (Financial Inclusion) | 2 | 38 | 19.0% |
| Part 4 (Client Voice) | 5 | 132 | 66.0% |

Part 1 vs Part 4 confirmed directionally as projected (Part 4 far
larger). **Not confirmed: code count predicting base size in general.**
Part 2 has 3 codes -- more than Part 1's 1 -- but the SMALLEST base of
the four, well below Part 1's. Reading the actual tagged text explains
why: this pool is NPS follow-up ("why did you give this score"), and
most responses default to general satisfaction, value, and staff
themes (Part 4's territory) rather than claims-process specifics, which
show up more in a claim-specific survey question than in a general NPS
prompt -- most LACRO respondents describing their NPS score simply
never mention a claim at all. Scaled to the full ~1,674-response pool,
Part 2's base could land in the neighbourhood of 50, not the low-to-mid
hundreds the original structural estimate assumed uniformly across all
four sections. This is a real fact about what the NPS follow-up prompt
actually elicits, not a flaw in the mapping -- the mapping is analytically
correct regardless of how many responses happen to land in each bucket.
Flagged for review, not treated as disqualifying.

**Still unverified**: this is 200 of ~1,674 responses (12%), one batch,
not a full run, and `source_pool_n` here is 200 (the smoke sample), not
the real full-pool figure. **The first full live run must still print
every Part 1-4 `base_n` and `source_pool_n` for review before this
mapping is treated as settled** -- this smoke-test signal narrows the
uncertainty (confirms the mechanism works end to end on real tags,
surfaces the Part 2 size finding early) but does not replace it.

**Verification**
- `assert every Part 1-4 selection_rule names the theme codes it matched on`
- `assert no theme code appears in more than one section's theme_codes` (single-mapping principle)
- `assert Part 1-4 base_n and source_pool_n counts are printed and reviewed against a real FULL run before this mapping is marked settled`

---

## R-006b Verbatim shortlist widened for selection quality

**Layer:** `code`
**Priority:** medium
**Depends on:** R-006's investigation above

**Decision (session-6):** three rendered verbatims per section stays.
The nomination cap is now purely a selection-quality question --
picking 3 from a pool of only 6 is a weak ratio, and widening the
shortlist improves which three get chosen without changing how many
render.

**Intended behaviour**
Increase `_CANDIDATES_PER_SECTION_PER_BATCH` (`llm_call.py:71`) and/or
`_NPS_BATCH_SIZE` (`llm_call.py:65`) so the pooled per-section candidate
count feeding the synthesis call's final pick (still exactly 3,
`llm_call.py:453`) is meaningfully larger than today's ceiling of 6,
within the token budget the two-call redesign was built to respect.

**Verification**
- `assert pooled per-section candidate count exceeds the current 6-per-section ceiling by a stated, deliberate margin`
- `assert section_verbatims still contains exactly 3 entries per section with any candidates` (unchanged from today)
- `assert the batch call's own output stays under max_output_tokens with stated headroom` (the original token-budget constraint this cap was sized against)

---

## R-007 Every restricted base metric carries a base description

**Source:** LM8, "what is the difference of these 2 groups described?"
**Layer:** `schema`
**Priority:** high

**Current behaviour**
Part 5 reports healthcare access improved at 33.9 percent (n=448) for "clients who needed care" and medical costs decreased at 39.1 percent (n=519) for "health insurance clients who needed medical care". The two descriptions are near identical in prose but the bases differ by 71 respondents, so the reader cannot tell what distinguishes them.

Related defect in the same part: the caregiver comparison footnote states that healthcare access uses "the same base as Part 4's healthcare access metric", but healthcare access is reported in Part 5. The cross reference is wrong.

A third inconsistency: Part 5 narrative reports healthcare access improved at 33.9 percent, while the caregiver table reports 8.9 percent and 8.6 percent for the same metric. These cannot both be describing the same measure on the same base.

**Intended behaviour**
Any metric whose denominator differs from its section default carries a structured base definition. Cross references between parts are generated from part IDs rather than written by hand. Where the same named metric appears twice with different values, the pipeline fails rather than rendering both.

**Rule**
```python
class MetricWithBase(BaseModel):
    label: str
    value: float
    n: int
    base_definition: str | None   # required when n != section_default_n
    base_id: str                  # canonical ID for cross referencing

    @model_validator(mode="after")
    def restricted_base_is_described(self):
        if self.n != self.section_default_n and not self.base_definition:
            raise ValueError(f"{self.label}: restricted base needs a definition")
        return self
```

**Verification**
- `assert every metric with a restricted base has a non empty base_definition`
- `assert no two metrics share a label but differ in value`
- `assert every cross reference resolves to the part where the metric is actually reported`

**Open question for reviewer**
Confirm with the data team what genuinely separates the 448 and 519 bases, then write the two definitions plainly.

---

## R-023 Sentiment split base is a model estimate, not a validated count

**Source:** self identified, during R-006 investigation
**Layer:** `code`
**Priority:** medium
**Status:** SUPERSEDED by R-006a (session-6, 2026-08-20). R-006a's
decision to compute the sentiment split deterministically in Python
over the full theme-tagged pool, with a real `base_n`, directly
resolves the concern this requirement raises -- a model self-report
with no traceable pool size. Kept below for history; do not implement
separately from R-006a.

**Current behaviour**
`section_insights.*.sentiment_split` (`llm_call.py`'s synthesis prompt,
Task 4B) is produced as "your best-judgment approximate counts...
among the material you reviewed for this section." Nothing validates
this against `len(section_verbatims)` for the same section, nothing
cross-checks it against the actual candidate pool size the synthesis
call was given, and the model is never asked to report how many
responses it reviewed. The number that becomes a section's stated
"base" is therefore the model's own unverified claim about its own
review process, not a quantity computed or checked anywhere in code.

Counts of an unstated, unverified pool are not more trustworthy than
percentages -- that is the premise of Lorenz's LM7 request for R-006.
Moving from percentages to raw counts (R-006) does not by itself fix
this: a reader is asked to trust "3 positive, 0 negative" on the same
kind of faith they were asked to trust "100%" on, unless the pool that
produced it is itself real and stated.

**Intended behaviour**
A section's sentiment base is either a quantity computed deterministi-
cally in code from a known, countable pool, or -- if it must remain a
model judgment -- a quantity the model is explicitly asked to report
and that is validated against the size of whatever pool it was actually
given (e.g. `sentiment_total <= len(pooled_candidates[section]) +
len(other-group records considered)`). An unvalidated self-report should
not reach the renderer as if it were a fact about the data.

**Verification**
- `assert every rendered sentiment base is traceable to a countable pool the model was actually given, not merely stated by the model`
- `assert sentiment split total does not exceed the known candidate pool size for that section, where a pool size is computable`

**Note**
Logged during the R-006 investigation (session-6, 2026-08-20). See the
read-only question in that session about whether Task 1's per-record
theme tagging could carry a per-record sentiment value, which would let
this be computed deterministically over the full NPS pool instead of
estimated by the model over a 6-candidate shortlist -- pending answer,
recorded separately.

---

## R-024 Qualitative is_claimant used a narrower definition than the report's own "claimant"

**Source:** self identified, while grounding R-006a's Part 6 base
**Layer:** `code`
**Priority:** medium
**Status:** Implemented this session (session-6, 2026-08-20)

**Current behaviour (before fix)**
`qualitative/prepare_payload.py`'s `_build_response_record()` and
`qualitative/parse_results.py`'s `_lookup_profile()` both computed
`is_claimant` from `flag_paid_claimant` -- "claim was approved AND
paid" (`data_loader/data_loader_derived.py`'s
`compute_flag_paid_claimant()`). Every other "claimant" figure in this
report -- `analysis_engine/segments.py`'s canonical `claimant` segment,
Part 6's own "Claimant vs Non-Claimant Scorecard", `analysis_engine/
sections/part_8.py`'s "Claims Experience is restricted to claimants
(q_claim_submitted == True)" -- uses `q_claim_submitted`: simply
whether a claim was submitted, regardless of outcome.

`flag_paid_claimant` is a strict subset of `q_claim_submitted`: a
claimant whose claim was denied or is still pending is a claimant by
every definition used elsewhere in the report, but was silently
excluded from the qualitative pipeline's own notion of "claimant" --
affecting which verbatims got labelled/preferred as claimant quotes
(Part 6's `prefer_segment: is_claimant`) and each verbatim's rendered
profile, not only the sentiment base. Against
`runs/lacro_final_check/`: `flag_paid_claimant` counts 49 claimants;
`q_claim_submitted` counts 55 -- a 6-respondent gap, all claimants with
a denied or still-pending claim.

Found while computing Part 6's real population for R-006a's sentiment
base: the qualitative pipeline's own number (49) disagreed with the
report's own published "claimant" figure (55) for the same LACRO run.

**Fix**
Both sites changed to `q_claim_submitted`, matching the canonical
definition. `prepare_payload.py`'s `_build_response_record()` (feeds
verbatim candidate selection and sentiment population) and
`parse_results.py`'s `_lookup_profile()` (feeds the rendered verbatim's
profile metadata) now agree with each other and with every other
"claimant" figure in the report.

**Verification**
- `assert qualitative/prepare_payload.py and qualitative/parse_results.py's is_claimant both key off q_claim_submitted, not flag_paid_claimant`
- `assert a claimant with a denied or pending claim (q_claim_submitted=True, flag_paid_claimant=False) is counted as is_claimant=True`
- Confirmed against real data: `runs/lacro_final_check/`'s claimant population reads 55 after the fix (`tests/test_parse_results.py::TestLookupProfile::test_is_claimant_uses_canonical_q_claim_submitted_not_flag_paid_claimant`)

---

## R-025 Claims-other pool reaches synthesis with no section routing

**Source:** self identified, while evaluating whether Part 2's small
R-006a Stage 2 base could be supplemented from `claim_no_reason_other`/
`claim_challenges_other_support`
**Layer:** `code`
**Priority:** low
**Status:** Decision made (Part 2), not started (sparse_other) -- see below

**Current behaviour**
The NPS pool is now deterministically routed to sections by segment
(R-006a Stage 1: Parts 5/6) or theme code (Stage 2: Parts 1-4). The
`claim_no_reason_other`, `claim_challenges_other_support`, and
`sparse_other` groups have no equivalent routing at all -- they reach
the synthesis call as three undifferentiated pools, tagged (where
tagged at all) without any per-record section assignment, and only
enter a section's output via the model's own Task 4A verbatim pick or
Task 4B "material you reviewed" sentiment estimate, exactly the kind of
model judgment R-006a's Stage 1/2 exists to replace for the NPS pool.

**Decision: Part 2 (claims-specific pool) -- rejected on drift
grounds, 2026-08-2X**
Quantified against `runs/lacro_final_check/` (corrects an initial
`~227` estimate, which wrongly lumped in `sparse_other`'s 144 records --
coping mechanisms, income sources, and channel preference, none of
which are claims content): `claim_no_reason_other` = 23,
`claim_challenges_other_support` = 2 -- **25 claims-specific records
total**, genuinely on-topic for Part 2 by construction. Of those 25,
**24 (96%) already share a `row_id` with a record in the NPS pool**.
Adding them to Part 2's base by source group would net **at most +25,
and likely nearer +1 after deduplication**, against Part 4's roughly
1,100-record base -- not a meaningful fix at any point on that range.
Rejected because the cost is real (a second, source-based population
rule alongside Part 2's existing theme-based one -- exactly the kind of
per-section definition drift R-024 just found and fixed for
`is_claimant`) and the benefit is not: **not pursued.**

Part 2 ships at its Stage-2 theme-matched base (~50 projected pre-full-
run) -- a large improvement on Test9's base of 7, and defensible as
under-lying reality rather than a pipeline defect: most respondents
answering "why did you give this score" describe general sentiment,
not claims specifics, so a small Part 2 base is what the NPS follow-up
question actually elicits. `compute_stage2_sentiment_splits()`'s
`selection_rule` now says so explicitly whenever a section's match rate
falls below 10% (`_STAGE2_LOW_MATCH_RATE_THRESHOLD`,
`qualitative/parse_results.py`), so a small base is never read as a
data problem without also being told why.

**The larger, still-open gap: `sparse_other` (144 records, no tagging
at all)**
Six columns, all currently invisible to sentiment/theme routing:
coping mechanisms, income sources, communication-channel preference,
claim-channel preference, VF services received, child improvements.
Unlike `claim_no_reason_other`/`claim_challenges_other_support`, these
get **no theme codes and no sentiment anywhere in the pipeline** --
synthesis Task 1 ("Claims Other Tagging") only reads the two
claims-other groups; `sparse_other` is read directly by Task 4A
(verbatim pick) and folded into Task 6's executive summary, but never
classified. Several of these columns map naturally to sections that
currently report no qualitative content of their own (income sources
and coping mechanisms both relate to Part 3's financial-resilience
territory; channel preference and services received don't map cleanly
to any of the seven sections at all). Not for now, but flagged so it
stays visible rather than being rediscovered from scratch.

**Intended behaviour**
Not decided for `sparse_other`. Options include: leave as is (stays
model-judgment only, same as every section before R-006a existed);
extend Stage 2-style theme tagging to `sparse_other` so it can
participate in the same deterministic routing the NPS pool now has;
or accept that its columns are too small and heterogeneous individually
to warrant it. Whatever is decided, the asymmetry (NPS pool
deterministic, `sparse_other` not) should be a stated design choice,
not an unexamined gap.

**Verification**
- Part 2: `assert selection_rule states the low-match-rate context whenever match_rate < 0.10` (implemented, session-8)
- `sparse_other`: not applicable until a direction is chosen

---

## R-026 The sentiment enum cannot express "neutral in tone, negative in substance"

**Source:** self identified, investigating Part 1's real-tag sentiment distribution against `runs/lacro_final_check/`
**Layer:** `schema`
**Priority:** medium
**Status:** Verified as a real finding, not a tagging artifact -- do not fix this session

**Current behaviour**
Part 1 (Product Understanding) is 90% neutral in its real, deterministic
sentiment split: 421 of 467 records (25 positive, 21 negative, 421
neutral) -- starkly different from every other section, which runs
60-90% positive. This reads as contradicting the executive summary,
which names product understanding as the largest driver of
dissatisfaction: a section reporting near-total neutrality on exactly
the topic the summary calls out as a dissatisfaction driver will
confuse a reader left to reconcile the two unaided.

**Verified as real (2026-08-2X), four independent checks, all
converging:**
1. Reading 20 random `product_understanding` + neutral records: the
   large majority are flat statements of non-use or non-knowledge
   ("no lo he usado," "no sé como funciona," "no tengo la informacion")
   -- factually neutral in tone even though the substance is a real
   information gap.
2. Cross-tabulated against `nps_group`: neutral spreads across
   promoters (81.8%, 81 of 99), passives (93.9%, 200 of 213), and
   detractors (90.3%, 140 of 155) -- not concentrated in one group, which
   rules out "detractors default to neutral" or "one group's terse
   style skews the average" as the explanation. A promoter who scores
   VisionFund 9-10 overall can still flatly report not knowing how the
   coverage works.
3. Word-count distribution: Part 1's neutral records run shorter than
   Part 1's own positive records (median 7 vs 10 words) -- but the
   direction **inverts** in Part 4 (neutral median 9, positive median
   5 -- short responses skew POSITIVE there, e.g. "beneficios," "muy
   bueno"). A generic "short response defaults to neutral" pipeline
   artifact would skew the same direction in both sections; it does
   not, so the length correlation is content-driven (blunt non-usage
   statements are inherently short), not an artifact of the tagging
   mechanism.
4. 355 of 467 (76%) carry `product_understanding` as their ONLY theme
   code -- the neutral signal is not diluted or produced by co-tagged,
   unrelated content.

**Additional finding: Part 1's base conflates two different things**
Read qualitatively, roughly half the neutral sample is **non-usage**
("no lo he ocupado" -- has not used the product, so has no basis to
describe understanding of it) rather than **non-comprehension** ("no me
dieron información" -- was given insurance but never had it explained).
The `product_understanding` theme code absorbs both without
distinction. Part 1's base is therefore not a pure "how well do clients
understand the product" measure -- it mixes "never had occasion to find
out" with "was never told." These likely warrant different narrative
treatment and possibly different remediation (the first is arguably not
a gap at all; the second is the dissatisfaction driver Lorenz's summary
names). Worth splitting into two theme codes or two sub-populations in
a future round -- not attempted this session.

**Intended behaviour**
Not decided. The sentiment enum (`positive`/`negative`/`neutral`) is a
deliberate, simple design (R-006/R-006a) and expanding it (a fourth
value, or a separate "substance" dimension alongside tone) is a real
schema change with its own tradeoffs, not undertaken here. At minimum,
**Part 1's narrative must state its neutral share explicitly and
explain it** -- not just render the raw counts -- so a reader is not
left reconciling "90% neutral" against the executive summary unaided.

Requirement recorded here, not yet implemented: this session's run is
an infrastructure smoke test (per instruction), and Part 1's narrative
prose is generated by the existing, un-fixed pipeline -- `_build_
sections_text()`'s `insight` branch (`generation/writer.py:428-440`)
does not currently read a `note` field at all (it `continue`s before
reaching the generic note-rendering code at `writer.py:492-495`, which
only applies to the metric-leaf sections above it), so simply adding a
`note:` key under Part 1's `insight:` block in `report_spec.yaml` would
have no effect without a small code change first. Implementation is a
future step, not this session's.

**Verification**
Not applicable until a direction is decided for the enum itself. The
narrative-level mitigation (state and explain the neutral share) is
verifiable once implemented: `assert Part 1's narrative states its
neutral share and explains it, not just the raw counts`.

---

## R-027 Executive summary content silently discarded by a JSON-shape mismatch

**Source:** self identified, session-8 full-pipeline smoke test against `runs/lacro_final_check/`
**Layer:** `code`
**Priority:** high
**Status:** Implemented (session-10)
**Blocks:** R-013 -- no longer blocked; the executive summary's inputs now reliably reach the top level before R-013's own rewiring work begins

**Current behaviour**
The synthesis call's `section_insights` output is only ever meant to
contain `part1` through `part7`. This run, the model also nested full
copies of `executive_summary`, `top_findings`, `top_actions`, and 2
`protection_flags` *inside* `section_insights` -- while the correct
**top-level** `executive_summary`/`top_findings`/`top_actions` came back
empty (`""`, `[]`, `[]`). `parse_results.py`'s `_validate()` only checks
that the required top-level keys are *present*, not that they are
non-empty, so an empty string and an empty list both satisfy it
trivially. `_check_section_insights()` sees the misplaced nested keys
(`protection_flags`, `executive_summary`, `top_findings`, `top_actions`
inside `section_insights`) and only logs a warning ("is not an
object") -- it never relocates them.

Result: the model generated genuinely good content --
*"A critical gap in product understanding is the single largest driver
of client dissatisfaction and non-use of the insurance..."* was sitting
in `section_insights.top_findings[0]` -- and it was silently discarded.
`qualitative_results.json`'s top-level `executive_summary`/
`top_findings`/`top_actions` are empty; the rendered docx's Executive
Summary section contains only the metrics table, no narrative, no Top
Findings heading, no Recommended Actions heading.

**The lost `protection_flags` matter more than the lost prose.** Two
flags -- a `premium_without_consent` (high severity: *"I didn't know I
was with the insurance"*) and an `unfair_claim_denial` (high severity)
-- were generated by the synthesis call's own protection scan (Task 5,
over `claim_no_reason_other`/`claim_challenges_other_support`/
`sparse_other`) and lost the same way. This is a silent data-loss path
into the client protection appendix, not just a missing narrative
paragraph -- same class of defect as R-018 (a real client protection
concern generated, then silently never reaching a human).

**Intended behaviour**
`_validate()` rejects empty required top-level keys (empty string,
empty list) as a validation failure, not a satisfied presence check.
Content found nested under `section_insights` at any of the four
non-section keys (`protection_flags`, `executive_summary`,
`top_findings`, `top_actions`) is relocated to the top level (merged
with, not silently overwritten by, whatever the top-level key already
holds) rather than only logged as a warning.

**Verification**
- A fixture with real content nested under `section_insights.
  {protection_flags,executive_summary,top_findings,top_actions}` and
  the corresponding top-level keys empty must render that content in
  the correct (top-level) location, not discard it.
- `assert parse_and_save() raises or fails loudly when a required
  top-level key is empty, not merely absent`

**Implementation (session-10)**
`parse_results.py` gained `_relocate_misplaced_section_insights_keys()`,
run as the first statement inside `parse_and_save()`, before
`_validate()`. Generalised, not a hardcoded four-key list: any key
found nested inside `section_insights` that isn't one of the 7 section
keys is a relocation candidate (confirmed on real data to be exactly
the four this entry names -- everything the synthesis OUTPUT SCHEMA
declares *after* `section_insights` -- consistent with the model
continuing to write inside the last-opened JSON object instead of
stepping back out to the top level once Task 4B's per-section loop
finished, though see the determinism note below).

Collision handling: `protection_flags` is always **merged**, never
replaces -- both the top-level list and any nested copy can hold real,
distinct flags from different scans. A plain concatenation would
reintroduce exactly what R-018/R-003 exist to prevent (the same case
counted twice), so the merged list is re-deduped through
`llm_call._dedupe_protection_flags()` -- the same `(id, column,
flag_type)` key R-018 fixed -- before use. Every other key: empty top
+ non-empty nested -> relocate; non-empty top + empty nested -> leave
alone; both empty -> leave alone (the new `_validate()` checks below
catch that honestly, rather than this function guessing); both
non-empty -> **keep the top-level value, discard the nested copy, log
loudly** -- a genuine content collision needs a human, not a silent
guess. Every relocation or merge is logged (key name + size).

`_validate()` gained three emptiness checks: `executive_summary` must
be a non-empty (post-strip) string, `top_findings` and `top_actions`
must be non-empty lists. Deliberately **not** extended to
`protection_flags`/`claims_other_tagged`/`not_worth_it_themes`/
`other_subthemes` -- those are legitimately data-dependent and can be
empty on a real run with nothing to report (a run with zero protection
concerns is a valid outcome, not a bug); see R-032 for the broader
presence-not-content gap those four are part of.

**Real-data demonstration (session-10, `runs/lacro_final_check/`)**
Reconstructed the fully-correct `raw_gemini` for this run without
re-calling the API: the real batch-phase pre-dedup protection flags (30,
saved from the session-9 live run) run through the already-fixed
`_dedupe_protection_flags()`/`_apply_protection_flag_cache()` for the
top-level `protection_flags`, combined with the real synthesis output's
own still-misplaced `section_insights` (unchanged, exactly as Gemini
produced it) for the nested side. Fed through the newly-fixed
`parse_and_save()`:
- `executive_summary`, all 3 `top_findings`, and all 3 `top_actions`
  were recovered verbatim at the top level (previously `""`/`[]`/`[]`).
- `protection_flags` went from 30 (top-level only) to 32 (merged,
  post-dedup) -- both of row_1015's entries now survive in the final
  list: the NPS-phase `unfair_claim_denial` (column `nps_detractors`)
  and the claims-other-phase entry naming the client's daughter (column
  `claim_challenges_other_support`), previously trapped in
  `section_insights` and lost.
- `docs/report_checks.py` re-run against `fixtures/test9.txt` (unaffected,
  as expected -- it is a frozen extraction predating this run) and
  against the `lacro_final_check` docx extraction with
  `--qual-json runs/lacro_final_check/qualitative_results.json`: no
  check regressed; full test suite (688 tests) passes.

**Determinism is unestablished.** This was observed on exactly one live
synthesis call. Whether the model reliably makes this same mistake, or
whether it is a one-off, is not known -- no repeated-call evidence
either way. The fix is a parsing-time recovery, not a generation-time
guarantee: it makes the pipeline resilient to the misplacement
recurring, but does not confirm or rule out that it will.

---

## R-028 report_spec.yaml's model: key names a model this pipeline cannot reach

**Source:** self identified, session-8 full-pipeline smoke test
**Layer:** `data_config`
**Priority:** medium
**Status:** Not started -- logged only, no fix yet (worked around for this session's run only, not fixed in config)

**Current behaviour**
`generation/report_spec.yaml`'s top-level `model: "Claude Opus 4.8"`
implies the report is written by Claude. `generation/run_generation.
py`'s `main()` calls `write_all_parts(packages, run_id,
model=spec["model"])` without ever passing `provider=`, so
`write_all_parts()` defaults to `provider="gemini"` and sends the
literal string `"Claude Opus 4.8"` to the Gemini endpoint as a model
name -- an immediate `400 INVALID_ARGUMENT` ("unexpected model name
format"). No `ANTHROPIC_API_KEY` is configured in this environment
either, so even a corrected provider pairing would not currently run.
Anyone reading `report_spec.yaml` alone would reasonably believe
Claude wrote this report; nothing in the config or the CLI's own
behaviour corrects that assumption before the call fails.

**Which model actually wrote `runs/lacro_final_check/`'s report
(recorded per instruction):** `gemini-2.5-pro`, substituted for this
session's run only, outside `report_spec.yaml` (a standalone script
overrode `model=` and `provider="gemini"` directly when calling
`write_all_parts()`; the committed config file was not edited).

**Intended behaviour**
Not decided; not fixed this session. Either `report_spec.yaml` gains a
`provider:` key that actually drives which endpoint `write_all_parts()`
calls (so the config is the single source of truth for both), or the
`model:` key is removed/replaced with something that matches what the
pipeline can actually reach, so the config never again describes a
report that was not, in fact, generated the way it says.

**Verification**
Not applicable until a direction is chosen.

---

## R-008 Coping metric exposes component breakdown

**Source:** LM5, "can we mention what that negative coping behavior is?"
**Layer:** `schema`, with a computation change
**Priority:** medium

**Current behaviour**
Negative coping is collapsed to a binary flag before the narrative is generated, so the option level detail (used savings, borrowed money, sold assets, reduced food consumption, took children out of school, closed business) is discarded upstream and cannot be named.

**Intended behaviour**
The coping metric carries a ranked breakdown of the underlying multi select options alongside the headline rate.

**Rule**
```python
class CopingMetric(BaseModel):
    rate: float
    n: int
    base_definition: str
    components: list[ComponentCount]   # ranked descending
    suppressed_components: int         # count falling below threshold
```

**Caution**
The current headline is 6.5 percent of 124, which is roughly 8 respondents. Component counts will be very small. Apply the standard suppression threshold to components and state the number suppressed rather than listing single respondent categories.

**Verification**
- `assert coping metric has a non empty components list OR an explicit suppression note`
- `assert sum(component counts) <= n`
- `assert no component with count below the suppression threshold is named`

---


# Phase 3: Code

## R-010 Qualitative blocks omitted when no verbatims exist

**Source:** LM4 ("remove this section", Part 10), LM11 ("we can also remove this part", Part 9)
**Layer:** `code`
**Priority:** high
**Status:** Implemented (session-10)

**Current behaviour**
When no verbatims pass selection, the pipeline still renders the Key Qualitative Insights heading and fills it with a paragraph explaining the absence. Part 10 produces roughly 100 words of this, Part 9 roughly 90. Both reviewers asked for removal.

The same pattern appears in the Part 9 Services Used introduction and would recur in any future section lacking verbatims, so this is one rule with two reported symptoms rather than two edits.

**Intended behaviour**
A qualitative block renders only when at least one verbatim passes selection. Otherwise the heading and all its content are omitted. The report never narrates the absence of data.

**Rule**
```python
def render_qualitative_block(section):
    if not section.verbatims:
        return None          # heading omitted entirely
    return QualitativeBlock(...)
```

This is deliberately not a prompt instruction. Asking a generator to reliably suppress output succeeds most of the time and fails occasionally, which is the failure mode that produced the fabricated Confidence in Payout paragraph in the previous iteration.

**Verification**
- `assert no section contains a "Key Qualitative Insights" heading with zero verbatims`
- `assert the phrases "not yet available", "not yet been provided", "once ... become available" appear nowhere in the report`
- Generalised check: `assert no section body describes what the report cannot say`

**Implementation (session-10)**
`generation/assembler.py`'s `_add_insight_box()` (the single function all
12 call sites share, one per rendered section) now filters to verbatims
carrying actual text and returns before rendering anything -- heading
included -- when that filtered list is empty. This closes both C-014 and
C-015 with one change, not two: on real data
(`runs/lacro_final_check/`), the Part 9 Services Used block had zero
verbatims AND its LLM-written `insight_text` narrated exactly the banned
absence ("...have not yet been analyzed for this report... cannot be
provided at this time"). Confirmed as code-level, not prompt-level, per
instruction -- `insight_text` is not filtered or rewritten, it is simply
never reached when there is nothing to quote.

**Verified:** `tests/test_assembler.py::TestAddInsightBox` (7 cases:
no verbatims, verbatims with empty text, heading suppressed, narrated-
absence text suppressed, one valid verbatim renders correctly, mixed
valid/empty only renders the valid one, cap still holds at 3).

**Confirmed against real data:** re-assembled `runs/lacro_final_check/`'s
`.docx` from its already-saved `written_texts.json` (Phase 4 only, no
new LLM call) with the fixed `assembler.py`, re-extracted, re-ran
`docs/report_checks.py`. **C-014 and C-015 both flipped FAIL -> pass**
(blocking failures for this extraction: 8 -> 6); `fixtures/test9.txt`
(a frozen, not-regenerated fixture) is unchanged as expected.

---

## R-011 Non filer renamed to non claimant

**Source:** LM10, "Change non-filer to non-claimants"
**Layer:** `code`
**Priority:** low

**Current behaviour**
The term "non filer" appears in the Part 6 heading, the scorecard column header, the findings prose and the section introduction.

**Intended behaviour**
A single label constant supplies the term everywhere. Renaming is a one line change.

**Rule**
```python
LABEL_CLAIMANT = "Claimant"
LABEL_NON_CLAIMANT = "Non-claimant"   # was "Non-Filer"
PART6_TITLE = f"{LABEL_CLAIMANT} vs. {LABEL_NON_CLAIMANT} Outcomes"
```

Do not implement as a find and replace across generated text, since the generator may produce the term in prose it writes itself. Pass the constants into the section prompt as the required terminology.

**Verification**
- `assert "non-filer" not in report_text.lower()`
- `assert "non filer" not in report_text.lower()`

---

## R-012 Trend columns labelled by wave year

**Source:** LM3a, "renaming the current wave to 2026 and the prior wave 2025"
**Layer:** `code`
**Priority:** medium
**Depends on:** R-009

**Current behaviour**
Columns read Current Wave and Prior Wave. The years appear only in footnote prose.

**Intended behaviour**
Column headers are the wave years, derived from config rather than hardcoded, so the same code serves next year's report.

**Rule**
```python
prior_label = str(config.prior_wave.year)      # "2025"
current_label = str(config.current_wave.year)  # "2026"
```

**Verification**
- `assert "Current Wave" not in report_text`
- `assert "Prior Wave" not in report_text`
- `assert trend headers include both wave years`

---

## R-013 Executive summary draws on all sections

**Source:** LM1b ("the exec summary focused only on NPS findings instead of the overarching narrative from the survey")
**Layer:** `code`, with a prompt component
**Priority:** high

**Current behaviour**
The summary narrative discusses promoter themes, detractor themes, and client protection signals. It does not mention the claims funnel, first time access, healthcare access, additional services uptake, or product value, all of which are reported later. All three Top Findings and all three Recommended Actions trace back to NPS free text.

Diagnosis: this is most likely an input selection defect rather than a writing defect. If the summary generator receives only the NPS follow up theme summaries, no prompt instruction will produce balanced coverage.

**Intended behaviour**
The summary generator receives a structured digest of every section: headline metric, direction, and top theme. Its output covers findings from at least four distinct modules.

**Rule**
```python
summary_inputs = [section.digest() for section in all_sections]
# digest() returns headline metric, base, top theme, and any
# flagged anomaly, for every part including 1, 2, 3, 5, 7 and 9
```

Prompt component, applied only after the input fix: instruct that findings must span modules and that no more than one of three findings may derive from NPS.

**Secondary defect in the same section**
Top Findings are numbered 1 to 3 and Recommended Actions continue as 4 to 6. List numbering must reset.

**Verification**
- `assert summary_inputs covers every rendered part`
- `assert findings reference at least 4 distinct section IDs`
- `assert at most 1 finding is sourced from the NPS module`
- `assert recommended actions are numbered from 1`

---

## R-014 Remove editorial phrase in Part 5

**Source:** LM9, "can this phrase be removed? 'unrelated to child wellbeing itself'"
**Layer:** `code` if templated, `prompt` if generated
**Priority:** low

**Current behaviour**
The caregiver comparison narrative opens with "Comparing caregivers against non-caregivers on two measures unrelated to child wellbeing itself ...". The qualifier is editorial and reads as the pipeline apologising for its own table.

**Intended behaviour**
The phrase is removed. The sentence states what is compared without justifying the choice.

**Implementation note**
Grep for the phrase before deciding the layer. If it is a hardcoded template string this is a one line template fix, which is cheaper and more reliable than a prompt change. Only treat it as a prompt requirement if the generator produced it freely.

**Verification**
- `assert "unrelated to child wellbeing" not in report_text`

---

## R-015 Post generation validation gate

**Source:** self identified
**Layer:** `code`
**Priority:** high

**Current behaviour**
No validation runs between report object construction and rendering. The previous iteration rendered a fabricated narrative paragraph for an indicator the same document declared as not collected.

**Intended behaviour**
All verification checks in this spec run as a suite against the assembled report object before rendering. Failures block rendering. Results are written to a run log alongside the output.

**Rule**
```python
result = validate_report(report)
if result.has_failures:
    raise ReportValidationError(result.summary())
write_run_log(result, output_dir)
```

Checks are grouped as blocking (a defect a reader would notice) and advisory (worth reviewing, such as an unusually small sentiment base).

**Verification**
- `assert validation runs on every generation`
- `assert a run log is written for every generation, pass or fail`

---

## R-017 Severity counts computed once from a canonical list

**Source:** self identified
**Layer:** `code`
**Priority:** medium
**Status:** Implemented (2026-08-20)

**Current behaviour**
`_add_protection_signals_summary` and `_add_protection_signals_annex` in
`generation/assembler.py` each build their own `by_severity` dict by
independently iterating `protection_flags`. The two functions are called
at different points in assembly (the summary inline in Part 2, the annex
once at the end of the document) and have no shared state between them.
Because the counts are recomputed twice from the same source list rather
than computed once and read twice, the in-body summary and the appendix
can disagree if either function's counting logic changes without the
other being updated, or once R-003's dedup step is added and only one
of the two call sites is updated to use the deduplicated list.

**Intended behaviour**
Severity counts are computed once, from the canonical (deduplicated)
`protection_flags` list, into a single structure. Both the in-body
summary and the appendix read from that structure rather than each
recomputing it.

**Rule**
```python
def compute_severity_counts(protection_flags: list) -> dict[str, int]:
    ...  # single implementation

severity_counts = compute_severity_counts(protection_flags)
_add_protection_signals_summary(doc, protection_flags, severity_counts)
_add_protection_signals_annex(doc, protection_flags, severity_counts)
```

**Verification**
- `assert summary severity counts == appendix severity counts`

**Implementation note**
Shipped slightly differently from the Rule pseudocode above:
`_compute_severity_counts(protection_flags)` is called independently at
each of the two call sites in `generation/assembler.py` (inline in
`build_part_2`, and again where the appendix is rendered), rather than
computed once into a variable threaded through both. Both call sites read
the same canonical (already client-deduplicated, per R-003)
`protection_flags` list, and the function is pure, so identical input
still guarantees identical output -- the two renderings cannot disagree.
This was chosen over threading a single value through so that
`build_part_2`'s generic `(doc, package, texts)` builder signature (shared
by every other Part builder) did not need to change. Verified directly:
summary and appendix severity counts checked equal on a fixture, and via
a docx round-trip through `docs/report_checks.py`.

---

## R-018 Protection flag dedup must not collapse across source columns

**Source:** self identified
**Layer:** `code`
**Priority:** high
**Status:** Implemented (session-9, 2026-08-2X)

**Current behaviour (before fix)**
`prepare_payload.build_payload()` loops columns then rows: for each
configured source column, it iterates every respondent and, where that
column has qualifying text, emits a record with `row_id = f"row_{idx:04d}"`
derived only from the respondent's dataframe index. One respondent can
therefore produce multiple records -- one per source column with
qualifying text (e.g. an NPS follow-up column and a separate sparse-text
column) -- and every one of them shares the same `row_id`, because the id
is a function of the respondent, not of the (respondent, column) pair.

`_dedupe_protection_flags` in `qualitative/llm_call.py` keys on
`(id, flag_type)`. If the same respondent raises two genuinely distinct
protection concerns in two different source columns, and both happen to
be tagged with the same `flag_type`, they collapse into one entry because
they share `id` -- even though they came from different text, about
different concerns.

This is more serious than R-003: R-003 inflated a count by rendering the
same concern twice. This silently drops a concern the client protection
team would otherwise have seen at all.

**Orientation (session-9), before implementing:** traced
`_dedupe_protection_flags` and `_dedupe_protection_flags_by_client` in
full and quantified against `runs/lacro_final_check/`'s real pre-dedup
pool (reconstructed from the saved per-batch/synthesis debug files, not
guessed):
- Confirmed at the line level: `row_id` is genuinely one-per-respondent
  (`prepare_payload.py:127`), not one-per-(respondent, column).
- `_lookup_text()` (`parse_results.py`) is a SEPARATE, real defect with
  the same root cause -- see R-030 below, fixed alongside this.
- R-003's client-level pass (`(client_id, flag_type, normalised reason)`)
  does not independently reproduce this collapse -- its reason-text
  component already distinguishes genuinely different concerns, and it
  runs on whatever survives `_dedupe_protection_flags` regardless, so it
  cannot recover what this function already dropped. R-018 is confined
  to `llm_call.py`.
- Quantified: exactly 1 real pair in this run's data shares `(id,
  flag_type)` with different reasons -- `row_1015`, `unfair_claim_denial`,
  an NPS-phase complaint ("could never use the insurance...") and a
  claims-other-phase complaint specifically naming a second affected
  person, the client's daughter. Of 2 synthesis-phase-flagged
  respondents, 1 was also independently flagged by the batch phase (the
  narrowed overlap that actually matters, distinct from the general
  96% row_id overlap between the NPS and claims-other pools).
- Caught live, not hypothetical: found a second, related bug this same
  investigation -- see R-029.

**Fix**
Key changed to `(id, column, flag_type)`. No prompt change needed:
every flag dict reaching this function already carries `"column"` --
batch-phase flags get it from `call_gemini()` via `NPS_GROUP_TO_COLUMN`
before this runs; synthesis-phase flags carry it directly, since the
synthesis OUTPUT SCHEMA already asks for it and the model already
complies (confirmed against this run's real, if R-027-trapped,
synthesis output). `row_id`'s own shape is unchanged -- it remains
one-per-respondent, since it's load-bearing elsewhere (the theme-tag
cache, `_lookup_profile()`) and reshaping it would have reached beyond
this fix.

**Verification**
- A fixture with one respondent raising the same `flag_type` from two
  different `source_column`/`column` values retains both entries
  through `_dedupe_protection_flags` (`tests/test_llm_call.py::
  TestDedupeProtectionFlags::test_same_id_and_flag_type_different_column_both_kept`).
- Confirmed against real data: reconstructing this run's true pre-dedup
  pool (30 batch-phase + the 2 R-027-trapped synthesis-phase flags,
  recovered by hand for this demonstration) and running it through the
  fixed function retains both `row_1015` entries, daughter detail
  intact. **A live rerun today cannot yet reproduce this** -- the
  synthesis-phase flag is still trapped by R-027 (separately scoped,
  sequenced after this fix) and never reaches `call_gemini()`'s own
  reconciliation step in a real run until that's also fixed.

**Note**
Found during R-003 implementation (2026-08-20), while confirming that
duplicated-reason-text entries reflected genuinely different survey rows
rather than an id-mapping defect between the batch scan and the synthesis
call (they did -- see the R-003 implementation note). This sits upstream
of R-003's client-level dedup pass, in `llm_call.py` rather than
`parse_results.py`.

---

## R-029 `_apply_protection_flag_cache`'s found_by_id keys on id alone

**Source:** self identified, R-018 orientation (session-9)
**Layer:** `code`
**Priority:** high
**Status:** Implemented (session-9, 2026-08-2X)

**Current behaviour (before fix)**
`_apply_protection_flag_cache` (`llm_call.py`) builds `found_by_id =
{f["id"]: f for f in found_flags if f.get("id")}` -- keyed on `id`
alone, weaker than R-018's `(id, column, flag_type)` dedup key it sits
downstream of. A respondent with a record in two scanned groups (the
same row_id collision R-018 is about) appears twice in
`scanned_records = all_nps + other_group_records`; the id-only lookup
handed BOTH instances the same flag object regardless of which one it
actually came from.

**This was not hypothetical -- caught live in this run's own saved
output before the fix**: `row_0841` and `row_1015` each appeared TWICE,
byte-identical, in the final `gemini_raw_response.json`'s
`protection_flags` list. Both respondents have a record in two payload
groups (row_0841: `nps_promoters` + `sparse_other`; row_1015:
`nps_detractors` + `claim_challenges_other_support`).

**Fix**
`found_by_id` re-keyed to `(id, column)`, using each scanned record's
own resolved column (`_record_column()`, new shared helper -- also used
by R-018's batch-phase flag enrichment). A genuine subtlety caught
before this shipped: a protection flag's `"column"` field uses the
payload GROUP name vocabulary (`"claim_challenges_other_support"`,
matching `payload`'s own top-level keys and what the model is shown),
which is NOT the same string as a record's own `source_column`
(`prepare_payload.py`'s raw survey column name, e.g.
`"q_claim_challenges__other_text"`). `_record_column()` translates raw
`source_column` values to the group-name vocabulary via
`_SOURCE_COLUMN_TO_GROUP` (mirrors `prepare_payload.py`'s own
column-to-group routing; update both if a column is ever added or
moved) before comparing.

**On the tag_cache key itself** (`tag_cache.get/put(cache, "flag",
record_id, text)`, which already hashes `text`): left unchanged, per
instruction. Text already disambiguates in every real case observed --
two different columns produce two different answers, hence two
different hashes -- and `_cache_key()` is shared with theme-tag
caching, where "column" doesn't map onto the same idea. `found_by_id`
had zero disambiguation before this fix, not weak disambiguation; that
is the mechanism that was actually broken.

**Verification**
- `tests/test_llm_call.py::TestApplyProtectionFlagCache` -- a shared id
  across two columns with one real flag is attributed to the correct
  record and appended exactly once, not twice; two distinct flags for
  the same id across two columns are both attributed correctly.
- Confirmed against real data (same reconstruction as R-018's
  verification, above): `row_0841` and `row_1015` no longer appear
  twice in the fixed pipeline's output.

---

## R-030 Rendered verbatims can be attributed to the wrong source column

**Source:** self identified, R-018 orientation (session-9)
**Layer:** `code`
**Priority:** medium
**Status:** Partially implemented (session-9, 2026-08-2X) -- resolvable
majority fixed; residual ambiguous case deliberately left on the
original fallback, not attempted, since closing it needs a prompt
change (out of scope, separately authorised)

**This is a reader-facing correctness defect, not an internal one.** A
quote attributed to a client in the rendered report may be a different
answer from the same client than the one that actually justified its
selection -- not a miscount or a dropped internal record, but a wrong
quotation presented as that person's words.

**Current behaviour (before fix)**
`_lookup_text()` (`parse_results.py`) re-derives the respondent's
dataframe index from `row_id` and walks a *fixed-order* `text_cols`
list (NPS columns first, then claims-other, then sparse-other),
returning the first non-null match -- correct only because most
respondents have text in exactly one column. The synthesis call's Task
4A explicitly allows picking a `section_verbatims` row ID "from EITHER
source... OR your own direct reading of `claim_no_reason_other`/
`claim_challenges_other_support`/`sparse_other`." For a respondent with
text in two columns (the same row_id collision R-018/R-029 are about),
the model may select a row_id specifically because of its claims-other
text, and `_lookup_text()` would silently render that respondent's NPS
text instead, simply because NPS columns sort first.

**Fix, scoped deliberately (per instruction: fix the resolvable
majority, leave the ambiguous minority on today's behaviour, make the
fallback observable, do not touch the generation prompt)**

`parse_and_save()` now accepts `payload` (both real callers,
`run_qualitative.py` and `dashboard/api/pipeline_runner.py`, already
have it in scope). `build_row_id_column_map(payload)` maps every
`row_id` that appears under EXACTLY ONE raw dataframe column across the
full payload to that column, with certainty, no prompt change needed --
a row_id under 2+ distinct columns is deliberately left OUT of the map
rather than guessed at. `_enrich_section_verbatims()` uses the resolved
column directly when available; when not (the genuinely ambiguous
case), it falls back to the original fixed-order guess, unchanged
behaviour, not silently claimed to be fixed.

Why the ambiguous case isn't closed here: Python has no way to know
which of a respondent's several answers the model actually read and
selected -- only the model's own selection step knows that, and Task
4A is not currently asked to say. Fully resolving it would need the
synthesis prompt to return column alongside each picked row_id, a
prompt change, explicitly out of scope and not attempted.

**Observability (per instruction: the fallback must be seen, not
inferred)**: `_enrich_section_verbatims()` returns `(enriched,
resolution_counts)`, `resolution_counts = {"exact": int, "fallback":
int}`. `parse_and_save()` logs a warning naming the fallback count when
it's non-zero, and writes `resolution_counts` into
`qualitative_results.json`'s `meta.verbatim_column_resolution`
unconditionally, every run.

**Confirmed against real data**: re-parsing `runs/lacro_final_check/`'s
real `section_verbatims` (21 total, 3 per section) against the real
payload: **15 of 21 resolved exactly; 6 fell back**. The fallback count
is non-zero on a real run, as expected, and is now visible in
`meta.verbatim_column_resolution` rather than requiring inference.

**Verification**
- `tests/test_parse_results.py::TestBuildRowIdColumnMap`,
  `TestLookupTextColumnResolution`,
  `TestEnrichSectionVerbatimsResolutionCounts`,
  `TestParseAndSaveVerbatimColumnResolutionWiring` -- single-column
  row_ids resolve exactly; multi-column row_ids are excluded from the
  map (never silently guessed at) and fall back; resolution counts are
  threaded through to `parse_and_save()`'s saved `meta` correctly; no
  `payload` given is fully backward compatible (all-fallback, matching
  pre-R-030 behaviour).

**Open question for a future session**
Whether to pursue the prompt change that would close the residual
ambiguous case (Task 4A returning column alongside each picked row_id),
and whether the same treatment should extend to protection flags'
`id` resolution for verbatim-adjacent reader-facing surfaces, if any
exist. Not evaluated this session.

---

## R-031 Report per-section verbatim source-pool counts

**Source:** self identified, in answer to a read-only question about
R-030's payload wiring (session-9)
**Layer:** `code`
**Priority:** low
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
`build_row_id_column_map()` (R-030, `parse_results.py`) already walks
every payload group once and computes, per `row_id`, the full set of
columns it appears under -- it discards everything except the singleton
case before returning, since R-030 only needed the unambiguous subset.
There is currently no visibility into which POOL (NPS vs
`claim_no_reason_other` vs `claim_challenges_other_support` vs
`sparse_other`) a section's rendered verbatims actually came from, or
whether the claims-other pool contributes to verbatim selection at all
versus the model effectively only ever reading NPS.

Current inference (not a count): of the 25 real claims-specific records
this run (R-025), 24 already overlap the NPS pool, so most claims-other
row_ids that could be picked are also NPS-resolvable and would land in
R-030's "ambiguous" fallback bucket rather than a clean claims-other
attribution -- suggesting close to zero non-ambiguous claims-other-only
verbatim picks, but this has never been counted directly.

**Intended behaviour**
Extend the row_id -> column mapping (a sibling of
`build_row_id_column_map()`, returning the full `{row_id: {group_names}}`
set rather than collapsing to the unambiguous singleton) into a
per-section tally: `{section: {"nps": N,
"claim_no_reason_other": N, "claim_challenges_other_support": N,
"sparse_other": N, "ambiguous": N}}`, written into
`qualitative_results.json`'s `meta` alongside
`verbatim_column_resolution`.

No new data collection and no prompt change -- this is a reporting
pass over data the R-030 wiring already walks, reusing
`_raw_column_for_record()`'s per-record group resolution.

**Verification**
- A fixture with verbatims drawn from each of the four pools, plus one
  ambiguous (multi-pool) row_id, produces the correct per-section
  counts and they sum to that section's verbatim count.
- Confirmed against a real run: the counts either confirm or replace
  the "close to zero non-ambiguous claims-other picks" inference above
  with an actual number.

---

## R-032 Required top-level keys are checked for presence, not content, beyond R-027's four

**Source:** self identified, during R-027 implementation (session-10)
**Layer:** `code`
**Priority:** medium
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
R-027 added emptiness checks to `_validate()` for exactly the three
keys the misplacement bug was observed to affect
(`executive_summary`/`top_findings`/`top_actions`; `protection_flags`
is deliberately excluded, see below). `REQUIRED_TOP_KEYS` has five
other members --  `nps_tags`, `claims_other_tagged`,
`not_worth_it_themes`, `other_subthemes`, `section_verbatims` -- that
`_validate()` still only checks for *presence*, the same shape of gap
R-027 exists to close for the other four. `section_verbatims` already
has its own non-empty-per-section check (unrelated to R-027), but
`claims_other_tagged: {}`, `not_worth_it_themes: []`, and
`other_subthemes: {}` currently satisfy validation even if the model
generated real content for them and something upstream (a future
JSON-shape mismatch, not necessarily this exact one) discarded it
before it reached the top level.

`protection_flags` is different in kind from these, not just degree:
zero protection concerns found is a legitimate, common, desirable
outcome on a real run -- an emptiness check on it would be a false
alarm, not a safety net. It stays deliberately unchecked.

**Intended behaviour**
Not decided. An emptiness check alone would be wrong for
`claims_other_tagged`/`not_worth_it_themes`/`other_subthemes` too, for
the same reason as `protection_flags` -- a run with no claims-other
records, no "not worth it" respondents, or no "other" subthemes this
wave is plausible, not a bug. Closing this gap needs a way to
distinguish "genuinely nothing to report" from "content was generated
and lost," which presence/absence alone cannot do -- unlike R-027,
where the misplaced content and the empty top-level key existed in the
same payload at the same time and made the loss provable.

**Verification**
Not written -- no fix decided yet.

---

## R-019 Check suite gaps: C-013 window, C-009 detail specificity

**Source:** self identified
**Layer:** `code`
**Priority:** low
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
Two limitations in `docs/report_checks.py`, found while establishing its
baseline state against Test9:

- **C-013** (`no_p_values_in_trend_section`, R-009) only searches a fixed
  2,600-character window immediately following the "Trend Comparison"
  heading (`re.search(r"Trend Comparison(.{0,2600})", ...)`). A p-value
  stated further into Part 10 -- e.g. in Findings prose that follows the
  table, comparability notes, and any methodology text -- falls outside
  that window and is never checked, so C-013 can pass even when a p-value
  is genuinely present in Part 10.
- **C-009** (`no_metric_reported_with_two_values`, R-007) correctly
  detects when a tracked metric label is followed by more than two
  distinct percentage values within +/-90 characters, but its detail
  line reports every percentage found in that window, not only the ones
  actually tied to the matched label -- an unrelated percentage from a
  neighbouring sentence can be pulled into the reported detail alongside
  the genuine conflicting values, making the failure message
  misleading about which numbers actually conflict.

**Intended behaviour**
- C-013's search window is bounded by the next section heading (or Part
  boundary) rather than a fixed character count, so it reaches any
  p-value genuinely inside Part 10, regardless of how much text precedes
  it.
- C-009's detail line is narrowed to name only the percentage(s) that can
  actually be attributed to the matched metric label (e.g. scoped to the
  same sentence, or tied to the label via closer proximity/explicit
  attribution), not every percentage incidentally inside the window.

**Verification**
- C-013 catches a p-value placed anywhere in Part 10.
- C-009's detail line names only the conflicting values for the metric it
  matched.

**Note**
Not a defect in this session's R-003/R-017 work -- found while recording
the check suite's baseline run against Test9 (3 pass, 17 blocking
failures, 4 advisory failures) for `docs/report_checks.py`'s own commit.
Logged so these two gaps aren't mistaken for "check passed, therefore
correct" in a future session. Not fixed in this session.

**Session-2 addendum (2026-08-20)**
R-002's implementation hit a concrete instance of the C-009 gap logged
above, but not the same one: regenerating the executive summary from
`runs/lacro_final_check/` with the new metric set, C-009 failed against
"Claim Process Understanding" because its own proximity window (+/-90
characters) picked up the summary table's three *other* rows' percentages,
not a genuine conflict. Confirmed against the untouched, pre-session-2
C-009 before fixing, so this was a real false positive, not an artifact
of anything else changed this session.

Fixed as part of R-002 (see its Implementation note for the full
before/after check-state comparison): C-009 now excludes the Executive
Summary table's own rows from its scan via a shared row-span helper,
`_summary_table_row_spans()`. This is a *different* fix from the one this
requirement originally logged -- the gap above is about C-009's *detail
line* naming irrelevant percentages once it has already correctly fired;
today's fix stops it from firing at all on a table it was never meant to
scan. **The original C-009 detail-line gap, and C-013's window gap, are
both still open** -- neither was touched this session. R-019 stays
logged, not closed.

---

## R-020 CLI output filename diverges from dashboard path

**Source:** self identified
**Layer:** `code`
**Priority:** low
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
`generation/run_generation.py:131-132` (the CLI entry point) builds the
output filename from `report_spec.yaml`'s static `output_filename` string
(`"VFI_Insurance_Impact_Report_2026_Q2.docx"`, not templated by `run_id`
at all -- a leftover from a specific quarter). `dashboard/api/
pipeline_runner.py:432-435` (the dashboard entry point) instead builds
`f"VFI_Insurance_Impact_Report_{state.run_id}.docx"` explicitly, with a
comment noting the spec's filename is stale and successive runs would
otherwise collide. The two entry points disagree, and the CLI path is the
stale one.

**Intended behaviour**
One filename-construction rule, used by both entry points, templated by
`run_id` (or by the derived period label, once R-021 gives both entry
points a single place to get it from) rather than a static string.

**Verification**
- `assert run_generation.py's output filename == pipeline_runner.py's output filename for the same run_id`

**Note**
Found during session-2 orientation (2026-08-20) while tracing every
render/consumption site of the period label for R-001. Not fixed this
session.

---

## R-021 Period label formatting duplicated across title and heading

**Source:** self identified
**Layer:** `code`
**Priority:** low
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
`format_period_label(run_id)` is called independently in two places:
`generation/writer.py:74-79`'s `_report_title()` (the narrative prompt's
own title) and `generation/assembler.py:1046-1080` (the rendered docx's
cover-page heading). Same class of duplication R-017 already fixed for
severity counts -- two call sites computing the same derived value from
the same input, with no shared state between them, so they can drift if
either call site changes without the other being updated.

**Intended behaviour**
Derive the period label once per run and thread it through, rather than
recomputing it at each render site. Given `format_period_label()` is pure
and both call sites pass the same `run_id`, this is lower-risk than
R-017's case (identical input still guarantees identical output today),
but the duplication itself is the same shape of latent defect.

**Verification**
- `assert writer.py's title period label == assembler.py's heading period label` (already true today; this requirement is about removing the duplication, not fixing an observed disagreement)

**Note**
Found during session-2 orientation (2026-08-20), same pass as R-020. Not
fixed this session.

---

## R-022 Stale prior_run_id should fail loudly, not resolve silently

**Source:** self identified
**Layer:** `data_config`
**Priority:** medium
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
`runs/lacro_final_check/`'s own `analysis_results.json` stores
`prior_run_id: "e2e_dryrun_lacro_2025_test"` -- a directory that no longer
exists anywhere on disk. `analysis_engine/sections/part_10.py`'s
`_load_prior_snapshot()` handles this the same way it handles a run that
was simply never given a `--prior-run-id`: it logs a warning
(`f"Part 10: prior_run_id={prior_run_id!r} has no analysis_results.json at
{prior_path}"`) and returns `None`, so `calculate()` quietly sets
`prior_available: False` and omits the comparison block entirely. Nothing
in the pipeline distinguishes "no prior wave was ever configured" from "a
prior wave WAS configured, but the directory it points at is gone" -- both
produce the identical, silent, no-comparison output.

The actual resolvable prior wave for this run is `runs/lacro_2025_pooled/`
(confirmed by regenerating and matching Test9's own published figures
exactly: 73.6% first-time access, 36.2 NPS) -- but nothing in the stored
metadata points there. Finding it required manual substitution
(`--prior-run-id lacro_2025_pooled` typed by hand), not anything the
pipeline itself could have told an operator to do.

**Intended behaviour**
A `prior_run_id` that is set but doesn't resolve to a real
`analysis_results.json` should fail the run at start (or at minimum
surface as a loud, blocking warning an operator can't miss), not silently
degrade to "no prior wave" -- the two situations have very different
correct responses (proceed without a trend section vs. go find the right
run id first) and today's behaviour makes them indistinguishable from the
output alone.

**Verification**
- `assert a run whose stored/passed prior_run_id does not resolve to a real analysis_results.json fails loudly at run start, distinct from a run with no prior_run_id configured at all`

**Note**
Found during session-3 while regenerating `runs/lacro_final_check/` for
R-005 verification (2026-08-20) -- the stale `prior_run_id` was silent
until manually noticed and worked around. Not fixed in session 3 or
session 5 (this session used `lacro_2025_pooled` directly, confirmed
correct against Test9's own figures, rather than fixing the underlying
silent-failure behaviour).

---

# Phase 4: Prompt

Only requirements that are genuinely about writing judgement reach this phase.

## R-016 NPS framed as one module among several

**Source:** HO2R1, "NPS is its own module that can be affected by other variables that are not measured in the survey"
**Layer:** `prompt`, with a template alternative
**Priority:** medium
**Depends on:** R-013

**Current behaviour**
NPS is presented as the portfolio's overall verdict, both in the summary table's leading position and in the narrative's reliance on promoter and detractor themes.

**Intended behaviour**
NPS is characterised as a satisfaction module whose drivers include factors the survey does not measure. It is not treated as a proxy for overall impact.

**Prompt guidance**
When describing NPS, state it as a measure of client advocacy specifically. Do not describe it as a measure of impact, value delivered, or portfolio performance overall. Where NPS is compared across waves or groups, note that unmeasured factors may contribute.

**Template alternative (preferred if Lorenz wants it stated every time)**
Add a fixed caveat line beneath the Part 4 NPS figure, so the statement cannot be dropped by generation variance.

**Verification**
- Advisory only, since this is a judgement. Manual reviewer check.
- If implemented as a template line: `assert the caveat string is present in Part 4`

---

# Deferred items

Recorded so they are not lost, but out of scope for this iteration.

| ID | Item | Reason deferred |
|---|---|---|
| D-01 | Verbatims shown in Spanish only, with translations appearing inconsistently in surrounding prose | Needs a convention decision from Lorenz |
| D-02 | Verbatims rendered in original all caps as typed by enumerators | Cosmetic, pending D-01 |
| D-03 | PPI poverty segmentation not used anywhere | New capability, not a defect |
| D-04 | Bolivia enumerator duration outlier (213 of 278 interviews under 5.3 minutes, 98.6 percent from one enumerator) | Field team reconciliation, not a pipeline fix |
| D-05 | Part 8 Kling Index available on dashboard only | Confirmed intentional |
| D-06 | Claim experience rating and its free text follow up unused | New capability, propose for a future round |

---

# Reviewer response table

To be completed after regeneration and sent to Lorenz alongside the new draft.

| Comment | Requirement | Status | Note |
|---|---|---|---|
| LM1 (metrics) | R-002 | Implemented | Metric list moved to `report_spec.yaml`; four hardcoded metrics replaced with the agreed set (First-Time Access, Worth the Premium, Claim Process Understanding, Children's Wellbeing Improved), each carrying a base label where its base is restricted. |
| LM1 (NPS focus) | R-013 | | |
| HO2R1 | R-016 | | |
| LM3 (labels) | R-012 | | |
| LM3 (comparability) | R-004, R-009 | | |
| LM4 | R-010 | | |
| LM5 | R-008 | | |
| LM6 | R-006 | | |
| LM7 | R-006 | | |
| LM8 | R-007 | | |
| LM9 | R-014 | | |
| LM10 | R-011 | | |
| LM11 | R-010 | | |
| (not raised) | R-003 | Implemented | Protection appendix duplicates, flagged proactively. Verified: 34 listed -> 27 after dedup (high 3->2, medium 23->17, low 8 unchanged). |
| (not raised) | R-017 | Implemented | Found during R-003 implementation: summary and appendix each recomputed severity counts independently and could disagree. Now both read from the same `_compute_severity_counts()` call on the canonical list. |
