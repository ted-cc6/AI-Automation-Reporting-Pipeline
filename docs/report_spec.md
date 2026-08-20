# LACRO Insurance Impact Report: Change Specification

**Baseline artifact:** `LAC_Insurance_Impact_Report_default_2026_Q2_Test9.pdf` (generated 17 August 2026)
**Reviewers:** Lorenz M (LM1 to LM11), second reviewer HO (HO2R1)
**Spec owner:** Binjie Wang
**Status:** draft, pending reviewer confirmation on R-006, R-008, R-014

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
| R-006 | LM6, LM7 | schema | Sentiment reported as counts with a stated base | 2 |
| R-007 | LM8 | schema | Every restricted base metric carries a base description | 2 |
| R-008 | LM5 | schema | Coping metric exposes component breakdown | 2 |
| R-009 | LM3b | schema | Trend table replaces significance with comparability | 2 |
| R-010 | LM4, LM11 | code | Qualitative blocks omitted when no verbatims exist | 3 |
| R-011 | LM10 | code | Non filer renamed to non claimant | 3 |
| R-012 | LM3a | code | Trend columns labelled by wave year | 3 |
| R-013 | LM1b | code | Executive summary draws on all sections | 3 |
| R-014 | LM9 | code | Remove editorial phrase in Part 5 | 3 |
| R-015 | self | code | Post generation validation gate | 3 |
| R-016 | HO2R1 | prompt | NPS framed as one module among several | 4 |
| R-017 | self | code | Severity counts computed once from a canonical list | 3 |
| R-018 | self | code | Protection flag dedup must not collapse across source columns | 3 |
| R-019 | self | code | Check suite gaps: C-013 window, C-009 detail specificity | 3 |
| R-020 | self | code | CLI output filename diverges from dashboard path | 3 |
| R-021 | self | code | Period label formatting duplicated across title and heading | 3 |

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
**Layer:** `data_config`
**Priority:** high
**Pairs with:** R-009 (schema), R-012 (code)

**Current behaviour**
Comparability reasoning exists but is buried in five footnotes beneath the trend table. The table itself carries a significance column that is empty for three of five rows and statistically inappropriate for NPS.

**Intended behaviour**
Each trend indicator carries a declared comparability status and a short reason, held in config so it can be updated when instruments change without touching code.

**Rule**
```yaml
trend_indicators:
  first_time_access:
    comparability: clean
    reason: "Identical question wording and options in both waves."
  client_satisfaction_nps:
    comparability: clean
    reason: "Same 0 to 10 scale in both waves."
  access_to_alternatives:
    comparability: indicative
    reason: "2026 adds a neutral midpoint and an I don't know option."
  child_wellbeing:
    comparability: indicative
    reason: "2025 used a 5 point scale; 2026 uses binary yes or no."
  product_understanding:
    comparability: not_comparable
    reason: "2025 used one combined 6 option question; 2026 splits it into two 4 point questions."
```

Permitted values: `clean`, `indicative`, `not_comparable`.

**Verification**
- `assert every trend indicator has a comparability value in the permitted set`
- `assert every indicator has a non empty reason string`

---

## R-005 Dominican Republic trend handling is explicit

**Source:** self identified
**Layer:** `data_config`
**Priority:** medium

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

**Verification**
- `assert trend_table.scope_note appears exactly once`
- `assert trend rows use comparable subset values when comparability != not_comparable`

---

# Phase 2: Schema

These changes make defective output structurally impossible rather than merely discouraged.

## R-006 Sentiment reported as counts with a stated base

**Source:** LM7 ("I am leaning towards the actual counts because it's less prone to misinterpretation"), LM6 ("how is the data being sliced ... making the base too small for percentages?")
**Layer:** `schema`, with an investigation prerequisite
**Priority:** high

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

The NPS follow up field is filled by every respondent in the LACRO instrument. A relevance filter that reduces 1,721 free text responses to between 3 and 10 per section is over restrictive, and is the real answer to LM6.

**Investigation prerequisite (blocking)**
Before implementing, determine and document:
1. What pool of free text fields feeds each section's sentiment.
2. What the relevance selection rule is and what threshold it applies.
3. Whether the LACRO single always on NPS follow up is being processed with logic written for Africa's three gated columns.

Record findings in this section before writing code.

**Intended behaviour**
Sentiment is always reported as integer counts. The base is always stated. The selection rule is always available to the renderer. Percentages are never emitted for sentiment.

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
    source_pool_n: int           # total free text responses considered

    @model_validator(mode="after")
    def counts_sum_to_base(self):
        if self.positive + self.negative + self.neutral != self.base_n:
            raise ValueError("sentiment counts must sum to base_n")
        return self
```

No float or percentage field exists on this model, so a ratio cannot be returned.

**Verification**
- `assert no sentiment string in the rendered report contains "%"`
- `assert every sentiment block states base_n and source_pool_n`
- `assert positive + negative + neutral == base_n for all sections`
- Report level check: log the base for every section so over restriction is visible at a glance

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

## R-009 Trend table replaces significance with comparability

**Source:** LM3b
**Layer:** `schema`
**Priority:** high
**Depends on:** R-004

**Current behaviour**
Columns are Indicator, Current Wave, Prior Wave, Sig. The significance column is empty for three of five rows, and its footnote claims a two proportion z test is used for all rows including NPS, which is not a proportion and for which respondent level prior wave scores were never retained.

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

**Verification**
- `assert "Sig." not in trend_table.headers`
- `assert trend_table.headers == ["Indicator", "2025", "2026", "Comparability"]`
- `assert no p value appears anywhere in Part 10`
- `assert every row has a comparability value and reason`

---

# Phase 3: Code

## R-010 Qualitative blocks omitted when no verbatims exist

**Source:** LM4 ("remove this section", Part 10), LM11 ("we can also remove this part", Part 9)
**Layer:** `code`
**Priority:** high

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
**Status:** Not started -- logged only, no fix yet

**Current behaviour**
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

**Intended behaviour**
Either the dedup key distinguishes source column (e.g.
`(id, source_column, flag_type)`), or `row_id` is made unique per record
at payload construction (e.g. `f"row_{idx:04d}_{source_column}"`) so two
records for the same respondent never collide on `id` in the first place.

**Verification**
- A fixture with one respondent raising the same `flag_type` from two
  different `source_column` values must retain both entries through
  `_dedupe_protection_flags`.

**Note**
Found during R-003 implementation (2026-08-20), while confirming that
duplicated-reason-text entries reflected genuinely different survey rows
rather than an id-mapping defect between the batch scan and the synthesis
call (they did -- see the R-003 implementation note). This sits upstream
of R-003's client-level dedup pass, in `llm_call.py` rather than
`parse_results.py`: R-003 dedups what survives `_dedupe_protection_flags`,
so it neither masks nor fixes a concern this bug already dropped before
R-003's pass ever sees it. Not fixed in this session.

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
