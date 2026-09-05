# Core Credit Impact Report: Change Specification

**Scope:** This file covers the **Core Credit** report pipeline only
(`core_credit/agent/**`). It is the Core Credit counterpart to
`docs/report_spec.md`, which covers the separate **Insurance / Cupboard Week**
pipeline. The two pipelines share no report code, no schemas, and no prompts, so
a requirement logged in one file does not apply to the other. Requirement IDs
here are prefixed `CC-` to keep them distinct from `docs/report_spec.md`'s `R-`
series.

**There is no CC-005.** An earlier revision bundled two unrelated concerns under
CC-003 (the ban on competitive verbs, and the rule that every subgroup figure
names its base) and numbered the grounding-checker work CC-005 / CC-006. They
were split and renumbered so each requirement is verified on its own: CC-003
and CC-004 are the two halves of the old CC-003, and the old CC-005 / CC-006
became CC-006 / CC-007. The number 5 is left unused rather than reflowing every
later ID again. Recorded so the gap is never read as a dropped requirement.

**Baseline artifact:** Test5 Core Credit draft report.
**Reviewers:** two reviewers, seventeen comments total on the Test5 draft,
concentrated on generated narrative that asserted causation, mechanism, or
competitive superiority the study design cannot support.
**Spec owner:** Binjie Wang

---

## CC-001: narrative describes what clients report, never what caused it

Source: Test5 review. Both reviewers, across roughly a dozen of the seventeen
comments, flagged generated prose that read a self-reported, cross-sectional
finding as a causal result, a treatment effect, or a verified mechanism, or that
turned a finding into a promised future outcome.

The Core Credit survey is self-reported and cross-sectional. There is no
counterfactual and no group that went without a loan, so the data can support a
statement about what clients report and about associations between reported
figures, but not a statement about what produced an outcome. Segment cuts, loan
cycle cuts, and first-time versus repeat borrower cuts are all observational:
none of these groups was randomised, and the groups differ from one another on
many dimensions beyond the one being discussed, so a difference between them is
an association, never an effect, a lever, or a payoff.

Fix, all in `core_credit/agent/analysis/writer/`:

1. `chain.py` `SYSTEM_PROMPT` gains a paragraph, placed after the metric-polarity
   paragraph, stating that the narrative describes what clients report and never
   what caused it; banning the assertion that one thing produced, drove, or
   explains another, and the words *confirms, drives, translating into, shifts,
   proves, causes, mechanism behind, payoff, evidence of, demonstrates, leads
   to*; requiring forward-looking sentences to be framed as things to explore or
   investigate ("could be explored as actions to support these outcomes", "may be
   a priority area to investigate") rather than promised results ("should raise",
   "will improve", "carries the most leverage", "would remove"); and requiring a
   free-text quote to be described as a frequently reported reason or pathway, not
   a verified mechanism. It cites three real Test5 strings: "confirming that
   credit access is translating into tangible household gains", "pointing to
   bundled services as a lever worth expanding", and "the concrete mechanism
   behind these gains".
2. `section_prompts.py` `GENDER_INSIGHT` now instructs the writer to describe the
   observed pattern only and not propose an explanation for it, citing the Test5
   draft's claim that women's advantage is concentrated in outcomes tied to
   tenure and relationship depth, which the report never tested.

Enforced by `SYSTEM_PROMPT` and the section prompt for now. Not yet covered by
`chain.py` `_writer_violations`; a deterministic banned-phrase check is a
candidate follow-up.

---

## CC-002: no asserted relationship between two figures unless it was computed

Source: Test5 review. Reviewer comments on Part 3 and Part 4 narrative that
stated two separately computed figures "mirror", "track", or "reflect" each other
and then read that invented correspondence as a causal chain.

Reporting two figures in adjacent sentences is legitimate and often the right
thing to do. Asserting that they move together, mirror each other, or reflect one
another is a separate claim, and in every flagged case it was a claim nothing in
the pipeline had computed. An association is only reportable when it has actually
been calculated and is presented in the same subsection.

Fix, all in `core_credit/agent/analysis/writer/`:

1. `chain.py` `SYSTEM_PROMPT` gains a paragraph, placed after the CC-001
   paragraph, forbidding any claim that two figures move together, mirror each
   other, or reflect one another unless an association between them has been
   computed and is shown in the same subsection. It cites the real Test5 string:
   "This broad-based wellbeing gain mirrors the business income improvements seen
   above, suggesting stronger earnings are translating directly into better
   everyday life".
2. `section_prompts.py` `QUALITY_OF_LIFE_CHANGE` (subsection 3.2) no longer asks
   the writer to "tie it back to business income above"; it now instructs the
   writer to report the quality-of-life figure on its own and not tie it to
   business income or any other metric, since no association between them has been
   computed.

Enforced by `SYSTEM_PROMPT` and the section prompt for now. Not yet covered by
`_writer_violations`.

---

## CC-003: benchmark comparison discipline (no competitive verbs against the MFI Index)

Source: Test5 review. One reviewer flagged competitive framing of the MFI Index
comparison ("Our Net Promoter Score of 69 outpaces the MFI Index's 58").

The MFI Index is an external 60 Decibels dataset that differs from ours in sample
composition, timing, geography, questionnaire wording, and survey context. A
difference between our figure and the Index figure is descriptive, not a contest,
so a competitive verb (*outpaces, beats, outperforms, ahead of, wins*) overstates
what the comparison means.

Fix, in `core_credit/agent/analysis/writer/chain.py` `SYSTEM_PROMPT`: the existing
benchmark-discipline paragraph is extended (not duplicated) with a sentence
stating that the MFI Index comparison is descriptive only, banning the competitive
verbs above, requiring "is higher than" / "is lower than", and citing the real
Test5 string "Our Net Promoter Score of 69 outpaces the MFI Index's 58".

Implemented in the same edit pass as CC-004 (both are `SYSTEM_PROMPT` changes in
the benchmark region), but they are separate requirements and are verified
separately.

Enforced by `SYSTEM_PROMPT` for now. Not yet covered by `_writer_violations`.

---

## CC-004: every subgroup figure names its base

Source: Test5 review. One reviewer flagged a Part 6 paragraph that switched
comparison bases mid-paragraph without saying so.

A reader carries a subgroup base forward onto the next number in the same
paragraph, so a figure that describes a subgroup has to name that subgroup, and a
paragraph that moves from one comparison base to another has to restate the base
when it does.

Fix, in `core_credit/agent/analysis/writer/chain.py` `SYSTEM_PROMPT`: a short new
paragraph, placed after the CC-002 linking paragraph and before the benchmark
paragraph, requires every subgroup figure to name its subgroup and forbids moving
from a comparison of women and men into a comparison of caregivers and
non-caregivers within one paragraph without restating the base. It cites the real
Test5 defect: section 6.2 opened on women at 84.2% versus men at 82.2%, then gave
caregivers at 86.2% versus non-caregivers at 69.9% without restating that the
second pair covers all clients, leaving a reviewer unable to tell whether the
paragraph was about all clients or only women.

Implemented in the same edit pass as CC-003; verified separately.

Enforced by `SYSTEM_PROMPT` for now. Not yet covered by `_writer_violations`.

---

## CC-006: two grounding checks in `grounding.py` produce false positives that make their output unusable

Source: **checker defect found during CC-001 verification, not a reviewer comment.**
Re-running the Business & Household Impact insight (case A2) against Test5 data
eight times, `check_quote_grounding` fired on 8/8 and `check_profile_grounding`
on 3/8. Every instance was a false positive: no run produced a fabricated or
misattributed quote. Because both flags land on `WrittenText` and are aggregated
by `report_assembly/completeness.py`, a real fabrication would currently be
indistinguishable from this noise.

Three defects, all fixed in `core_credit/agent/analysis/writer/grounding.py` only:

1. **`_QUOTED_SPAN_RE` paired quote marks across prose.** The pattern was
   `r'"([^"]{25,})"'`. The `{25,}` meant a short quoted string (the metric box
   label `"very much improved"`, 18 characters, which `format_metric_result`
   itself presents in double quotes and the writer faithfully copies) did not
   match as its own span, so `re.finditer` then paired *that* span's closing
   quote mark with the opening quote mark of the next real verbatim, capturing
   300 to 640 characters of ordinary prose as one bogus span that then failed the
   pool match. Fixed by matching every `"..."` pair first
   (`r'"([^"]*)"'`, left to right, so a closing mark can never open a span) and
   applying the length floor (`_MIN_QUOTE_LEN = 25`) to the matched spans
   afterward. Verified: a subsection quoting a box label and a client verbatim in
   the same paragraph now yields exactly one candidate span, the verbatim.

2. **`check_profile_grounding` searched for one-character verbatims.** Pool
   verbatim 18 has `quote == "B"` (a real but useless survey answer).
   `text.find("B")` matched inside any word containing a capital B (e.g.
   `BUSINESS`), then scanned the preceding window and flagged whatever country
   was named for the real, correctly-attributed quote nearby. Fixed with two
   guards: a pool verbatim must be at least `_MIN_QUOTE_LEN` characters to be
   searched at all, and the match must be word-bounded (`(?<!\w)...(?!\w)`).
   `_MIN_QUOTE_LEN` is 25, the same floor `check_quote_grounding` already uses:
   a quote too short to be checked for fabrication is also too short to be worth
   checking for misattribution, and short strings are exactly what collide as
   substrings. `check_quote_grounding` does **not** use `str.find` (it iterates
   regex spans and does set membership), so it was not affected by this defect.

3. **The 200-character lookback bled across sentences.** A correctly attributed
   quote was flagged because a different, also correctly attributed quote in the
   preceding sentence named another country inside the flat window. The
   attribution clause is not cleanly parseable from free-form prose
   ("A female client, age 37, Vietnam, Caregiver ... reported"), so the scan is
   now scoped to start at the later of: the previous quoted span's closing quote
   mark, or the last sentence boundary (`_CLAUSE_BOUNDARY_RE`), within the
   200-character lookback. In practice this is the quote's own clause: from the
   end of the previous quote (or the start of the sentence) up to this quote.

Verification (`scratchpad` harness, live writer + no-LLM probes):

- A2 re-run five times: 3/5 finals fully clean; the other two carry a residual
  on a **real, correctly-attributed** client quote (see CC-007 below), not a
  fabrication. Zero fabrications and zero misattributions reached any final
  across all five.
- The other eight harness cases: no case newly fires a quote or profile flag;
  case B8 lost a pre-existing false positive.
- Probe (fabrication): a plausible sentence not in the pool, placed immediately
  after the `"very much improved"` box label and immediately before a real
  verbatim (the exact desync trap), is still flagged by `check_quote_grounding`
  and nothing else is.
- Probe (misattribution): a real pool quote given the wrong country in its own
  clause is still flagged by `check_profile_grounding`.
- Probe (old false positives): two real correctly-attributed quotes in adjacent
  sentences, and the one-letter `"B"` verbatim against text containing `"BL"`,
  both now return clean.

`writer/tests/` pass unchanged (CC-007 later adds five).

---

## CC-007 (resolved): writer quotes a fragment or re-punctuates a real verbatim

Source: surfaced by the CC-006 fix. With the 300-character desync spans gone,
`check_quote_grounding` surfaced a smaller, previously-masked mismatch on about
2 of 5 insight runs: the writer quotes an exact **substring** of a real client
verbatim (a trimmed fragment), or reproduces one exactly but places the
sentence-ending period **inside** the closing quote mark. Both land on genuinely
real client words with the correct country. These are two distinct residuals and
get two treatments, both in `core_credit/agent/analysis/writer/grounding.py`
(plus the new field on `schemas/common.py::WrittenText`, populated in `chain.py`,
surfaced in `report_assembly/completeness.py`).

**1. Re-punctuation -- normalised away.** `_match_core()` now strips a trailing
run of ` .,;:!?…` from both the candidate span and the pool verbatim before the
exact-match test, alongside the quote-mark and whitespace normalisation that was
already there. A moved terminal period no longer registers as a different quote.
Only the *trailing* run is stripped: internal punctuation is left intact, so a
verbatim with a word (and its comma) removed from the middle still fails to match
and is treated as fabrication (see edge case below). Verified against the pool
that no two materially different verbatims collapse to the same core.

**2. Fragments -- a separate `partial_quotes` field, not folded into
`ungrounded_quotes`.** `_classify_quoted_spans()` sorts every quoted span into:
exact (clean), an exact **contiguous** substring of a real verbatim
(`check_partial_quotes` -> `WrittenText.partial_quotes`), or neither
(`check_quote_grounding` -> `WrittenText.ungrounded_quotes`, which now means
fabrication only). `ungrounded_quotes` keeps its narrowed meaning. `partial_quotes`
is surfaced by `completeness.py` like the other residual flags. It is **not**
added to `_writer_violations`: the corrective rewrite replaces quotes rather than
restoring dropped context, so triggering it on a truncation would likely make
things worse.

**Coverage threshold: none.** Every fragment is flagged regardless of how much of
the source verbatim it covers. Meaning distortion does not scale with length -- a
short fragment ("the money I was waiting for" out of a longer broken-promise
complaint) and a near-complete one that drops a decisive final clause are both
misleading, and a threshold would create a silent pass zone for exactly the cases
a reviewer most needs to see. In practice, fragments below roughly two-thirds of
the source verbatim are where meaning-change risk concentrates, but that is an
observation for the reviewer, not a gate. `_MIN_QUOTE_LEN` (25) already keeps
trivially short spans out of consideration entirely.

**Edge case verified.** A span that is a substring of a real verbatim but has
been altered *inside* -- e.g. a word deleted from the middle -- is classified
`ungrounded`, not `partial`. Python `in` is a contiguous test, so a
non-contiguous overlap never reaches the `partial` bucket.

Verification (`scratchpad` harness, live writer + no-LLM probes):

- A2 re-run five times and the other eight harness cases once: `ungrounded_quotes`
  empty on every final. The fragment residuals that CC-006 exposed now appear in
  `partial_quotes` instead, and the re-punctuation residual is gone.
- Probe (fabrication): a planted fake quote, positioned in the old desync trap,
  still lands in `ungrounded_quotes` and not in `partial_quotes`.
- Probe (contiguous fragment): lands in `partial_quotes`, not `ungrounded_quotes`.
- Probe (internal deletion): lands in `ungrounded_quotes`, not `partial_quotes`.
- Probe (moved terminal period): clean on both.

`writer/tests/` pass, with five new regression tests for the split and the
re-punctuation and internal-deletion cases.

**Note (incidental), context for a pending decision, not a requirement.** The
new `partial_quotes` field turns out to help with a separate open question about
duplicate verbatims across severity tiers. The Zambia KASAMA client-protection
verbatim currently appears under two severity bands in the rendered report;
`partial_quotes` now makes it possible to see whether that verbatim is being
trimmed differently in each of its two appearances. Recorded here so the field's
availability is on the record when the duplicate-verbatim decision is taken.

---

## CC-008 (open, not fixed): `check_grounding` produces false positives on `ungrounded_percentages`

Source: **checker defect found during CC-001 verification, not a reviewer comment.**
Same root cause as the quote checks in CC-006: the `acceptable` set that
`check_grounding` compares a percentage against does not match what
`SYSTEM_PROMPT` authorises the writer to put in prose.

Two instances observed:

- **B7 (5.4 fair treatment)** flagged `4.6%`. That is the complement of the real
  `95.4%` figure, and `SYSTEM_PROMPT` explicitly permits the writer to compute
  `100% minus the given figure` and state it. The complement is never added to
  the `acceptable` set, so a correct, authorised computation reads as ungrounded.
- **A5 (gender insight)** flagged the female-versus-male gap values. The gender
  scorecard's `acceptable` set is built from the female and male shares only
  (`synthesis/build_gender_scorecard.py`), never the gaps, even though the
  scorecard prints the gap in its own table and the prompt invites the writer to
  discuss it.

`check_grounding` is **not** part of `_writer_violations`, so it never triggers
the corrective rewrite. It is advisory only, surfaced through
`report_assembly/completeness.py`. **No fix is being made in this batch.**

---

## CC-009: the MFI Index benchmark workbook was outside the repo -- every run shipped with all benchmarks missing

Source: **live defect found during CC-010 prerequisite checking, not a reviewer
comment.**

All three `External Benchmarks.xlsx` path defaults --
`run_for_dashboard.py`'s `--benchmarks-path`, `core_credit_runner.py`'s
`DEFAULT_BENCHMARKS_PATH`, and `driver/build_resilience.py`'s `BENCHMARKS_PATH`
(and `build_executive_summary.py`'s own `PROJECT_ROOT`) -- resolve to
`Project/core_credit/External Benchmarks.xlsx`. That file did not exist. The
workbook was at `D:\Vision Fund International\core_peoject\External Benchmarks.xlsx`,
a sibling folder left behind when the project directory was renamed from
`core_peoject` to `Project/core_credit`. The `# core_peoject` comment on every
`PROJECT_ROOT =` line was the fingerprint.

`load_mfi_index_sheet()` returned `()` on a missing file by design, so a whole
Core Credit run finished and shipped a report with **every MFI Index benchmark
degraded to `not_available_reason`**, surfaced nowhere -- the same "fail after
the fact" failure the Insurance pipeline records as R-040 / R-045.

Fix:

1. `External Benchmarks.xlsx` copied into `core_credit/` so it travels with the
   repo (tracked by git, baked into the Docker image -- `.dockerignore` does not
   exclude it). No path default was repointed at a machine-specific absolute
   path.
2. `benchmark_module/reference_data.py`: both loaders now call `_require_workbook()`,
   which raises `FileNotFoundError` with a clear message when the workbook is
   absent, so a misconfigured path fails the run early. A benchmark-free run is
   still possible but only by explicitly setting
   `CORE_CREDIT_ALLOW_MISSING_BENCHMARKS`, which downgrades to a `RuntimeWarning`
   and the old empty-tuple return.
3. The stale `# core_peoject` comment replaced with `# core_credit` on 16 files
   (every `PROJECT_ROOT` line and path-trace comment outside `analysis/writer/`
   and `report_render/`, which are out of scope for this batch -- 3 occurrences
   remain there).

Verified: the resolved default path now exists; `load_mfi_index_sheet()` loads
all **29** indicator rows and `load_national_poverty_rates()` all 19 country
rows; the missing-file path raises, and `CORE_CREDIT_ALLOW_MISSING_BENCHMARKS`
restores the degraded return with a warning. `benchmark_module/tests` (22) pass.

**Same class of defect, NOT fixed (needs its own decision):** `PPI_scorecards.xlsx`
and `PPI_lookups.xlsx` -- the `ppi_module` reference workbooks for Part 2 (Poverty
Likelihood) -- are also still in `core_peoject/` and also resolve to a
non-existent `Project/core_credit/` path. 28 `ppi_module` tests error on the
missing fixture, and a real Part 2 run degrades the same way benchmarks did.
Out of scope here; flagged for a follow-up with the same three-step fix.

---

## CC-010: Agency Goal Achievement uses the combined "in full or partially" basis

Source: Core Credit Dashboard Design specification, section 3 spider-chart table.
The spec defines Goal Achievement as **"Yes, in full" plus "Yes, partially"**.
The report's `loan_purpose_achieved_fully` metric is "Yes, in full" only (70.1%);
the combined figure is 97.9%.

`loan_purpose_achieved_fully` could not be redefined in place: it also feeds
`build_gender_scorecard.py:102` (the Part 9 "Loan purpose fully achieved" row),
`build_child_wellbeing.py:124` (the 4.2 caregiver-vs-other table), and the 6.1
subsection prose, all of which should keep reporting full achievement
specifically. So a **new** metric was added.

Fix:

1. `section_configs/sections/agency.py`: new `MetricConfig` `loan_purpose_achieved`,
   same `Agency/AGENCY03_resp_en` column, `top_box_values = {"a. Yes, in full",
   "b. Yes, partially"}`. Added to `metric_schema_fields` only -- **not** to
   `subsection_metric_ids` or `insight_metric_ids`, so 6.1 prose and the Agency
   Insight are unchanged and it feeds the theme score alone.
2. `schemas/agency.py`: `loan_purpose_achieved: Optional[MetricResult] = None`.
   Optional so section outputs produced before CC-010 still load; a fresh
   config-driven run always populates it via `compute_metric_node`.
3. **Benchmark binding: none.** `benchmark_module/mapping.py` binds the MFI Index
   "Goal Achievement" figure (0.32) to `loan_purpose_achieved_fully` because the
   60 Decibels indicator is scored on "achieved ALL goals" (confirmed with the
   source). Pairing that benchmark with the broader "in full OR partially" basis
   would be exactly the box-type mismatch CC-003 bans, so `has_benchmark=False`
   and the existing mapping is left alone.

Verified: `loan_purpose_achieved` overall = 97.83% (n=5,818), equal to
`fully` 70.06% + `partially` 27.78% as expected (disjoint categories, same base).
`validate_section_config(AGENCY_CONFIG)` passes; `section_configs/tests` (15) pass.

---

## CC-011: theme scores are the unweighted mean of their constituent indicators

Source: Core Credit Dashboard Design specification, section 3 spider-chart table.
`_theme_scores()` picked one representative metric per theme; three of those
values disagreed with the published Power BI dashboard (Agency 70.1, Client
Protection 95.4, Resilience 77.5) and reviewers flagged the disagreement. The
dashboard spec governs.

`build_executive_summary.py` `_theme_scores()` rewritten so each theme's
`headline_value` is the unweighted mean of its constituent indicator `overall.share`
values, per the spec:

| theme | before (single metric) | after (mean of) | before % | after % |
|---|---|---|---|---|
| Financial Access | first-time access | first-time access, access to alternatives | 42.7 | **43.9** |
| Poverty Likelihood | below $1.90/day | *(single, unchanged)* | 12.4 | 12.4 |
| Business & Household Impact | quality of life | business income, quality of life | 92.9 | **92.2** |
| Child Wellbeing | improved child wellbeing | *(single, unchanged)* | 93.5 | 93.5 |
| Client Protection | no unfair treatment | financial worry, loan understanding, complaints mechanism, fair treatment, reporting behaviour, reduced food intake | 95.4 | **75.0** |
| Agency | fully achieved (in full only) | goal achievement (combined, CC-010), household influence, community respect | 70.1 | **85.1** |
| Resilience | savings increased | savings increased, realized preparedness | 77.5 | **67.5** |
| Client Satisfaction | NPS | *(single, unchanged)* | 68.8 | 68.8 |

Constituent values (Test5): Financial Access 42.68 / 45.03; Business & HH 91.54 /
92.87; Client Protection 47.22 / 91.63 / 92.39 / 95.41 / 33.33 / 90.20; Agency
97.83 / 83.50 / 73.99; Resilience 77.52 / 57.39.

**Unavailable-constituent handling:** average across the constituents that exist,
with the count recorded in `metric_label` ("N of M available this wave"). A theme
with zero available constituents raises rather than emit a meaningless number.
Chosen over marking the theme unavailable because `ThemeScore.headline_value` is
a required float and a partial mean is still informative; the recorded count
tells a reader it is partial. (Confirmed working: against a pre-CC-010 agency
output with no combined metric, Agency degrades to the 2-of-3 mean = 78.7% with
the count in the label.)

**Benchmarks:** an averaged theme carries no MFI Index benchmark (the 60 Decibels
figures are per-indicator, each on its own box definition; there is no single
benchmark for a multi-indicator mean, and CC-003 bars loose comparison). The
three single-indicator themes keep whatever benchmark their one metric carried --
in practice only Client Satisfaction's NPS. The rendered Executive Summary table
now shows "n/a" in the benchmark columns for the five averaged themes; this is a
visible change and a deliberate consequence.

The module docstring keeps the old one-representative-metric rationale, records
why it was chosen (schema holds one number) and that the dashboard spec
supersedes it.

**Resilience open item:** the new 67.5% is expected to differ from the
dashboard's 45%; that discrepancy remains open pending the reviewer's reply and
was **not** reconciled here.

Verified: expected-result gate passes -- Agency 85.11%, Client Protection 75.03%,
Resilience 67.45%. Live writer run of the Executive Summary on the new inputs:
123 words, grounding clean (no ungrounded percentages or quotes).

**NPS display note.** `ThemeScore.headline_value` for Client Satisfaction is the
raw NPS, 68.79, unchanged by CC-011. It renders as "69" in both the `.docx` table
(`report_render/section_layout.py`, `f"{headline_value:.0f} (NPS)"`) and the
writer prompt (`_format_theme_scores`, `f"{headline_value:.0f}"`). A `.1f`
before/after check shows 68.8; the difference from the Test5 report's "69" is
`:.0f` rounding in those two format strings, not a value change.

---

## CC-012: per-country six-indicator client-protection average for the Part 5 Insight

Source: reviewer request -- the Part 5 Insight should be able to name the country
with the highest client-protection score.

`graph/nodes.py` `write_insight_node()`, gated on
`config.section_id == "client_protection"`, now computes a per-country unweighted
mean of the six protection indicators from each metric's own `COUNTRY` segment
cuts, formats it into the Insight's data block, and whitelists the derived
per-country averages for the grounding check.

**Low-n handling: flagged and gated, threshold n=30.** Core Credit has no shared
low-n constant, so `_LOW_N_THRESHOLD = 30` mirrors the Insurance pipeline's
`analysis_engine.stats.LOW_N_THRESHOLD`. A country's per-indicator cell below
that base is **dropped** from its average (not silently averaged in), and every
row states `k of 6` and which indicators were dropped. Reporting Behavior
(`reported_when_unfair`) is denominated on clients who experienced unfair
treatment -- ~267 globally across 21 countries -- so almost every country is
single-digit on that one indicator; requiring all six would leave no country
rankable. A country is therefore eligible to be **named** as the highest only if
at least `_CP_MIN_INDICATORS_TO_RANK = 5` of 6 cells survive; countries below
that are listed but marked "coverage too thin to rank".

**Coverage context in the block (added on verification).** A country can rank
highest partly by having no incidents to report -- Vietnam tops the list on 5 of
6 because every Vietnamese client answered "never" on unfair treatment, so there
is no Reporting Behavior denominator at all. The block now distinguishes an
indicator with **no cell** (a clean record -- Vietnam, Kosovo) from one **dropped
for low n** (a cell exists but < 30 -- every other non-full country), states
plainly that **only Zambia and Uganda are scored on all six** indicators above
n=30, and instructs the writer to say the highest country's lead is partly the
absence of the Reporting Behavior indicator. The ranking logic is unchanged.

Verified against Test5: 21 countries, all rankable (k = 5 or 6). Highest is
Vietnam at 97.9% over 5 of 6 (no unfair-treatment incidents, so no Reporting
Behavior cell); Zambia and Uganda are the only two with all 6 cells above n=30.
Live writer run of the Part 5 Insight (203 words, grounding clean): the prose
names Vietnam highest, states "this omits reporting behaviour since no client
there reported unfair treatment", and adds "Only Zambia and Uganda are scored on
all six indicators above the n=30 threshold, sitting lower at 71.7% and 65.1%".

---

## CC-013: the PPI reference workbooks were outside the repo -- Part 2 was unrunnable

Source: **same class of defect as CC-009, found during CC-010 prerequisite
checking.** `PPI_scorecards.xlsx` and `PPI_lookups.xlsx` were still in
`core_peoject/`; `build_poverty_likelihood.py:57-58`'s `SCORECARD_PATH` /
`LOOKUP_PATH` resolve to `Project/core_credit/`, where neither existed. A real
Part 2 run raised a bare `openpyxl` `FileNotFoundError` deep in the country loop,
and 28 `ppi_module` tests errored on the fixture guard. More importantly for a
reviewer: with the workbook absent there was no way to tell whether a low
`n_scored` figure (Kenya 90 of 271, Zambia 32 of 281) was a real scorecard result
or an artifact of the missing file.

Fix (identical three steps to CC-009):

1. `PPI_scorecards.xlsx` and `PPI_lookups.xlsx` copied into `core_credit/`
   (tracked by git, baked into the Docker image).
2. `ppi_module/reference_data.py`: `_open_workbook()` now calls `_require_workbook()`,
   which raises `FileNotFoundError` with a clear message when a workbook is
   absent, unless `CORE_CREDIT_ALLOW_MISSING_PPI` is set -- then it warns
   (`RuntimeWarning`) and `load_scorecard()` / `load_lookup()` return empty, so
   every country scores `NOT_AVAILABLE` and Part 2 reports no poverty likelihood.
   A separate env var from `CORE_CREDIT_ALLOW_MISSING_BENCHMARKS` because the
   consequences differ (an empty Part 2 vs. a missing benchmark column).
3. No path default repointed at a machine-specific absolute path.

Verified: all **28** previously-erroring `ppi_module` tests pass (36 total).
A live Part 2 score of the Test5 CSV runs against the committed workbooks: 21
countries, portfolio $1.90/day likelihood 12.37% (Test5 report: 12.4%). The
Kenya (90 of 271) and Zambia (32 of 281) exclusions are **real scorecard
results** -- both report `PARTIAL` with `status_reason` "N of N clients could not
be scored (incomplete PPI answers)", i.e. those clients did not answer enough of
the 12 PPI questions for a valid score. Not a missing-workbook artifact.

**Left in `core_peoject/`, correctly not copied:** a 125 MB raw survey CSV and a
`.env` -- a per-run pipeline input and a secrets file, neither of which belongs in
the repo. The three reference workbooks (External Benchmarks + the two PPI files)
were the only committed-asset gap.

---

## CC-014: the Executive Summary "Comparable to Benchmark" column

Source: reviewer -- the literal string "same as Score" in the third column "reads
as a null to anyone outside the team", and was the first comment raised.

`report_render/section_layout.py` `render_executive_summary()`:

- The column now **always prints a number**: VisionFund's own figure on the
  benchmark's box definition where a stricter-box `benchmark_comparable_value`
  exists, otherwise the theme's Score itself (the boxes match, or there is no
  benchmark to be comparable to). No more "same as Score" and no more "n/a" in
  this column.
- Header renamed `Comparable to Benchmark` -> `VisionFund (benchmark-comparable
  basis)` so the basis is explicit.

**What the eight rows now render as (post-CC-011, Test5 data):**

```
Theme                        Score      VisionFund (benchmark-comparable basis)   MFI Index Benchmark
Financial Access             43.9%      43.9%                                     n/a
Poverty Likelihood           12.4%      12.4%                                     n/a
Business & Household Impact   92.2%      92.2%                                     n/a
Child Wellbeing              93.5%      93.5%                                     n/a
Client Protection            75.0%      75.0%                                     n/a
Agency                       85.1%      85.1%                                     n/a
Resilience                   67.5%      67.5%                                     n/a
Client Satisfaction          69 (NPS)   69 (NPS)                                  58.0 (2025)
```

**The table now reads as mostly empty, stated plainly.** After CC-011 only Client
Satisfaction retains a benchmark, and none of the eight themes has a
`benchmark_comparable_value` any more (the two that used to -- Business &
Household Impact, Resilience -- are now averages). So **column 3 is a verbatim
copy of column 2 in every row**, and column 4 is "n/a" for seven of eight. The
four-column benchmark-comparison table has effectively collapsed to "Theme |
Score" plus one live benchmark cell. This change makes the column read as a
number rather than a null, but it does not add information; whether the two
right-hand columns still earn their place is a separate decision (options: drop
to a two-column table with a footnote for the single NPS benchmark, or the
"average the constituent benchmarks" route, which -- see the CC-011 discussion --
only cleanly covers two of the five averaged themes and cannot cover Agency).

**Test impact:** `test_section_layout.py::test_executive_summary_table_shows_comparable_value_not_just_headline`
checked the exact strings this change and CC-015 alter. Updated as a CC-016
follow-up -- see the CC-016 entry.

---

## CC-015: the MFI Index benchmark year is now rendered

Source: `BenchmarkComparison.external_mfi_index_year` is parsed per value in
`benchmark_module/reference_data.py` but was never shown.

`render_executive_summary()` appends it to the **cell**, not the header:
`"58.0 (2025)"`. Chosen over a header year (`"MFI Index Benchmark (2025)"`)
because after CC-011 only Client Satisfaction carries a benchmark -- a header year
would imply a 2025 vintage for the seven "n/a" rows, which have no benchmark at
all. On the cell it attaches only to the figure it dates.

---

## CC-016: the PPI coverage footnote moved next to section 2.1

Source: reviewer -- the PPI exclusion note rendered in small italics at the very
end of Part 2, well past the Kenya (90 of 271 clients) and Zambia (32 of 281)
figures it qualifies.

`render_poverty_likelihood()`: the `na_footnote` render moved from a small-italic
`add_caption` after the 2.2 prose to a **body-size note directly under 2.1**,
alongside the figures it qualifies (Kenya's 35.0% on 90 of 271 is in the 2.1
prose immediately above it). CC-013 established these are real scorecard results,
so it reads as a fact, not a disclaimer.

**Follow-up (also CC-016): the `na_footnote` opening reworded, framing sentence
trimmed.** `ppi_module/country_policy.py::na_footnote()` opened with "Not
available this wave --", wrong for the block's third group -- countries that were
scored but only partially (Kenya, Zambia, Myanmar). It now opens **"PPI scoring
coverage by country this wave --"**, neutral across all three situations
(not collected / no usable scorecard, excluded by policy, partially scored). The
docstring, which claimed "every NOT_AVAILABLE country", was corrected too -- the
function includes any country carrying a `status_reason`, partial ones included.

With the opening fixed, the CC-016 framing sentence in `section_layout.py` no
longer needs to restate the coverage point (the footnote now does it). Trimmed to
just what it uniquely adds -- the CC-013 data-quality framing and the pointer to
the figures above:

> These are genuine scorecard outcomes, not estimates or omissions -- incomplete
> PPI answers, a guide or survey-version gap, or a country where PPI was not
> collected. Read the 2.1 figures alongside them.

Rendered result (Test5): the 2.1 prose, then the italic framing sentence, then
"PPI scoring coverage by country this wave -- DOM: ...; KEN: 181 of 271 clients
could not be scored ...; ZMB: 249 of 281 ...".

**Test fix (CC-014/015 follow-up):**
`test_section_layout.py::test_executive_summary_table_shows_comparable_value_not_just_headline`
updated -- header assertion to `"VisionFund (benchmark-comparable basis)"`, and
the benchmark-cell assertion from exact list membership to
`any("16.0%" in cell for cell in data_row)` so it tolerates the year suffix. It
still verifies the comparable value (27.8%) renders distinctly from the headline
(77.5%); that synthetic `ThemeScore` still carries `benchmark_comparable_value=0.278`.
Full suite afterward: the only remaining `report_render` failures are the
pre-existing `wvi-docx.skill not found` ones (8).

---

## CC-017 (resolved): nested verbatim gloss in `_apply_inline_translations`

Source: Test5 review. The Part 8 client-satisfaction insight rendered as
`""KINDNESS FEW REQUIREMENTS EXCELLENT SERVICE" (original Spanish: "AMABILIDAD
POCOS REQUISITOS "EXCELLENT" (original Spanish: "EXCELENTE") ATENCION")."` -- the
Spanish original was glossed a second time inside its own inline gloss.

**Cause.** `_apply_inline_translations` used `text.replace(v.quote, gloss)` per
verbatim, replacing every occurrence. Two non-English verbatims were in play: the
long `"AMABILIDAD POCOS REQUISITOS EXCELENTE ATENCION"` and the short
`"EXCELENTE"` (a different real client answer). `"EXCELENTE"` is a substring of
the long quote. After the long quote was glossed inline, its original text
survived verbatim in the gloss's parenthetical, and the pass for `"EXCELENTE"`
then matched inside that parenthetical and glossed it again.

**Fix** (`report_assembly/translate_verbatims.py`, new `_inline_glossed_text()`):
one non-overlapping match set per `WrittenText`, verbatims processed **longest
quote first**, every substituted span recorded as occupied so no later (shorter)
verbatim can match inside it -- not in the raw text and not in an inserted gloss's
parenthetical. A standalone `"EXCELENTE"` elsewhere in the paragraph is still
glossed. Idempotency unchanged. Two regression tests added.

Verified against the exact Test5 sentence: old logic -> two `(original Spanish:`;
new logic -> one.

---

## CC-018 (resolved): section 7.4 must name its conditional base

Source: reviewer -- a whole comment thread asking what the realized-preparedness
denominator is, because the report never states it. 7.2 reports shock incidence
over the full portfolio (n=5,817); 7.4 reports realized preparedness over the
n=1,178 clients who reported a climate/economic shock affected their household
(the dashboard-spec denominator). **No numbers change.**

`writer/section_prompts.py` `VF_REDUCED_SHOCK_SEVERITY` now requires the base
stated explicitly using the n beside the figure, named as a conditional subset,
and contrasted in the same sentence with 7.2's full-portfolio base. `word_cap`
70 -> 90. Verified (live writer, Test5 data): "Among the 1,178 clients who
reported that a climate or economic shock affected their household, 57.4% said
VisionFund services reduced the severity of that shock ... a pattern visible only
within this shock-affected subset rather than across the full portfolio." 72
words, grounding clean.

**Also checked -- other conditional bases reported without being named (reported,
not fixed):**
- **5.4 `reported_when_unfair`** -- base is the ~267 clients who experienced any
  unfair treatment. `FAIR_TREATMENT_AND_REPORTING` says "among those who did" but
  does not require the count/base stated. Same pattern as 7.4; this indicator is
  implicated in a dashboard discrepancy.
- **7.3 (`COPING_MECHANISMS`)** -- `negative_coping_share`, `coping_mechanisms`,
  `shock_impacts` all run on the same n=1,178 impacted-clients base; the prompt
  names no base.
- **7.2 (`SHOCK_INCIDENCE_AND_IMPACT`)** -- reports `shock_incidence` (full
  portfolio) and `shock_impacts` (1,178 subset) together, naming neither. Likely
  the root of the reviewer thread.
- 4.1 `improved_child_wellbeing` *does* name its base ("the share of caregiver
  clients"), for contrast.

---

## CC-019 (prompt done; metric NOT wired -- scope): Agency 6.2 top-improvement sentence

Source: reviewer -- AGENCY04a is the right field; wants one sentence after the
improved-household-influence figure naming the top improvement (selections a-d
over clients answering A or B in AGENCY04).

**Prerequisite confirmed.** `Agency/AGENCY04a_resp_{1,2,3}_en` is populated for
4,857 of the 4,858 A/B answerers, near-100% in all 21 countries/MFIs (lowest DOM
240/241). Test5 distribution among A/B answerers: `c. spouse and I make decisions
jointly` 2,146; `a. I independently make more decisions` 1,977; `b. I contribute
to more decisions` 1,227; `d. Other` 23. **Top improvement = option c ("jointly").**

**Prompt done, metric blocked.** `HOUSEHOLD_INFLUENCE_IMPROVED` now instructs the
writer to add the naming sentence *if* the data includes a ranked AGENCY04a
breakdown and to omit it (not guess) otherwise; `word_cap` 80 -> 95. Verified: on
current data (no breakdown) the writer correctly omits the sentence. The metric
is a multi-select ranked distribution, which the `section_configs`
`MetricConfig`/graph machinery does not support (single top-box `MetricResult`
only). Wiring it needs `schemas/agency.py` (a `RankedOptions` field),
`section_configs/config.py` (a distribution config type), and
`analysis/graph/nodes.py` (a compute node) -- none in this task's scope. Until
then the new clause is inert.

---

## CC-020 (resolved): a protection verbatim shown under two severity tiers

Source: reviewer -- the Zambia KASAMA quote (`client_id ZMB_70302`) appears in
Part 5 under **both** a High-severity theme (coercive collection) and a
Medium-severity theme (rude staff conduct). It genuinely describes both, so this
is not a merge bug, but a reader reads the repeat as an error.

`report_assembly/translate_verbatims.py` new
`_suppress_duplicate_protection_verbatims()`: keys each
`protection_signals` representative verbatim by `client_id` (or quote) and keeps
it only on its highest-severity theme (`high > medium > low`), dropping lower-tier
copies. Called from `translate_report_verbatims()` before translation. Client
Protection only; a no-op for a report without that section. Verified on Test5:
ZMB_70302 removed from Medium, kept in High; no verbatim now appears twice.

**Alternative:** a cross-reference on the lower-tier appearance. Rejected as more
clutter for the same information.

---

## CC-021 (Mongolia fixed; Kenya/Zambia reworded, exact counts need `pipeline.py`)

Source: reviewer, two corrections in `ppi_module/country_policy.py`.

**Mongolia -- fixed.** The old reason ("Only 10 of the 12 scorecard questions were
asked this wave; cannot be scored under the current guide") is wrong on both
counts. Diagnostic: the MNG2016 guide is valid and complete (12 questions -- MNG
is the only 12-question guide in the workbook, matching the reviewer), but every
MNG client's PPI answer fields (`PPIxx_resp_value`) are blank -- there is no PPI
response data for Mongolia this wave. `NOT_AVAILABLE["MNG"].reason` reworded to
say exactly that.

**Kenya / Zambia -- reworded generically.** The old wording bundled a fixable
scorecard label typo with ordinary incomplete responses into one sentence that
read as though the typo drove the whole exclusion (the reviewer misread it that
way). Diagnostic split: **Kenya** 181 unscored = 51 from the Q3 label typo + 130
incomplete responses; **Zambia** 249 = 56 + 193 -- the typo is the minority cause
in both. `na_footnote()` now rewrites the KEN/ZMB entry (new `_footnote_entry()`,
regex-matched on the label-conflict sentence) to state the two causes as
separate, unrelated problems with the total, flag the typo as an upstream
`PPI_scorecards.xlsx` fix, and say neither is the sole cause. The exact per-cause
client split is computed inside `pipeline.py::score_country` and is not on
`CountryPovertyResult`, so putting the precise numbers in the footnote needs a
`pipeline.py` change -- out of this task's scope. The label typo is a
workbook-wide defect: Kenya Q3 (`G` on options 7 and 9), Zambia Q2 (`C` on options
3 and 4), and **India Q2** (`B` on options 2 and 3, latent -- India is
policy-excluded).

---

## CC-022 (open, not fixed): benchmark workbook per-country columns mix 2024 and 2025 vintages

Source: benchmark-vintage diagnostic.

`External Benchmarks.xlsx`'s "60 DB Benchmarks" tab mixes vintages by column: the
global column is `Global Benchmark-2025`, the three regional columns are all
`...-2025`, but the per-country columns are a mix -- Ghana / Kenya / Tanzania /
Myanmar / Philippines / Ecuador / Mexico under `2024 MFI Index`, only India under
`2025 MFI Index`. `benchmark_module/reference_data.py` parses the year per column
correctly (`MfiIndexColumn.year`).

**No current code path reads the per-country columns.** Every
`get_mfi_index_benchmark()` call site passes `metric_id` and the path only -- no
`country=` / `region=` -- so resolution always falls to the global (2025) column
for all 12 benchmarked indicators. The reviewer confirmed 2025 is correct and
that is what the report uses, consistently.

**The trap:** `get_mfi_index_benchmark(metric_id, path, country="KEN")` would
silently resolve Kenya's 2024 figure, with no warning. If a future change adds
country- or region-level benchmark comparison it must restrict to 2025 columns or
surface the vintage. Recorded so the trap is visible before that change is made.

---

## CC-023 (resolved): sections 7.2 and 7.3 must name their bases

Source: the CC-018 audit -- the same conditional-base-without-naming defect it
fixed in 7.4. **No numbers change.**

- **7.2 (`SHOCK_INCIDENCE_AND_IMPACT`)** reports shock incidence over the full
  portfolio (n≈5,817) and shock impacts over the ~1,178 affected subset in the
  same subsection. The prompt now requires each figure to name its own base and
  requires the switch from the full portfolio to the affected subset to be
  explicit in the prose. `word_cap` 80 -> 110.
- **7.3 (`COPING_MECHANISMS`)** reports coping mechanisms and the negative-coping
  share, both on the ~1,178 affected base. The prompt now requires that base
  stated explicitly, using the n beside the figures, the first time a figure is
  cited, and not implied to be portfolio-wide. `word_cap` 90 -> 120.

Verified (live writer, Test5): 7.2 renders "Across the full portfolio (n=5817),
36.2% ... Among clients whose households reported being affected by a shock
(n=1178, not the full portfolio), impacts are ..."; 7.3 renders "Among the 1,178
clients who reported a shock affected their household, the most common responses
were ...". Both land a little over cap (109 / 119) after the required disclosure,
within the pre-existing subsection cap softness; grounding clean.

**5.4 left for now.** `reported_when_unfair` reports on the ~267 clients who
experienced any unfair treatment (`base_column=CP05`,
`base_values={Regularly, Sometimes, Rarely}`).
`FAIR_TREATMENT_AND_REPORTING` gestures at the subset ("among those who did") but
does not require the count/base stated. Fixing it is the same one-clause prompt
edit as 7.2/7.3 (require "state that this share is calculated only among the ~267
clients who reported experiencing unfair treatment, using the n beside the
figure"), plus a `word_cap` bump (currently 80). It was held because
`reported_when_unfair` is entangled in a separate open dashboard question about
that indicator -- change it in the same pass as that resolution so the wording is
settled once.

---

## CC-024 (resolved): ranked multi-select distribution metrics in the config-driven graph

Source: CC-019 -- the 6.2 follow-on sentence naming the top way household
influence improved (AGENCY04a) could not be built because `MetricConfig` /
`compute_metric_node` produce a single top-box `MetricResult` only, and AGENCY04a
is a "select all that apply" multi-select.

**Existing pattern reused, not reinvented.** The output shape is `RankedOptions`
(schemas/common.py) computed by `metrics_engine.engine.multiselect_distribution`
-- the same pair the bespoke drivers already use for child-wellbeing "what
improved", resilience coping mechanisms / shock impacts, and NPS promoter reasons.
CC-024 only adds the config-driven-path wiring:

- `section_configs/config.py`: new `RankedMetricConfig` (metric_id, label,
  slot_columns, base_column, base_values, exclude_labels) and
  `SectionConfig.ranked_metrics` / `ranked_metric_schema_fields`.
  `validate_section_config` extended -- a ranked metric_id may appear in
  `subsection_metric_ids`, must have a `ranked_metric_schema_fields` entry
  pointing at a real `RankedOptions` schema field, and may not collide with a
  plain `MetricConfig` id. Not allowed in `insight_metric_ids` (that path calls
  `format_metric_result`).
- `analysis/graph/state.py`: new `ranked_metric_results` channel.
- `analysis/graph/nodes.py`: `metrics_ready_node` (which already fires once, after
  the metric fan-out) computes every `RankedMetricConfig` via
  `multiselect_distribution` -- pure pandas, one to two per section, so serial
  rather than a second Send fan-out. `fan_out_subsection_writes` formats a ranked
  result into the subsection's `data_summary` with `format_ranked_options` and
  whitelists its shares for grounding. `assemble_section_node` sets the ranked
  schema fields and gates on them being present.
- `schemas/agency.py`: `household_influence_improvements: Optional[RankedOptions]`.
- `section_configs/sections/agency.py`: `RankedMetricConfig` for AGENCY04a
  (`AGENCY04a_resp_{1,2,3}_en`, base = clients who answered A or B in AGENCY04),
  wired to subsection 6.2.
- `writer/section_prompts.py` `HOUSEHOLD_INFLUENCE_IMPROVED`: the CC-019
  conditional clause made direct (the breakdown is now always in 6.2's data).

Verified (live writer, Test5): the ranked metric computes to base n=4,858, top =
`c. You and your spouse are making more decisions jointly` 44.2% (n=2,146). 6.2
renders "Overall, 83.5% of clients report improved influence ... Among clients who
reported an improvement, the most frequently cited way this happened was making
more decisions jointly with a spouse, reported by 44.2% of that subgroup ...".
82 words, within cap, grounding clean -- the follow-on sentence names the top
improvement, its share, and its base. Four `section_configs` tests added.

---

## CC-025 (resolved): Kenya/Zambia exclusion split on `CountryPovertyResult`

Source: CC-021 follow-up -- the footnote reworded the two causes generically
because the per-cause client split was computed in
`pipeline.py::score_country` and not carried on `CountryPovertyResult`.

- `schemas/poverty_likelihood.py` `CountryPovertyResult`: `n_unscored_label_conflict`
  and `n_unscored_incomplete` (both default 0; populated only when the guide has a
  conflicting-option-label question this wave). Together they sum to
  `n_total - n_scored`.
- `ppi_module/pipeline.py` `score_country`: when `ambiguous` is non-empty, scores
  every client twice on the best-covered poverty line -- once with the real index
  (ambiguous key dropped) and once with the key kept (last-write-wins) -- and
  takes the difference as `n_unscored_label_conflict` (clients unscored *purely*
  because of the typo). The rest is `n_unscored_incomplete`. Imports
  `_scorecard_index_and_ambiguous` from `.scoring`.
- `ppi_module/country_policy.py` `_footnote_entry`: uses the two fields directly.

Verified (fresh score, Test5): **Kenya 51 + 130 = 181**, **Zambia 56 + 193 = 249**
-- exactly the earlier diagnostic. New footnote entry:

> KEN: 181 of 271 clients unscored this wave, from two separate and unrelated
> problems. (1) 51 from a source-workbook label typo on PPI question 3: two answer
> options were given the same letter, so a client who chose it cannot be scored --
> fixable upstream in PPI_scorecards.xlsx. (2) 130 from incomplete PPI responses on
> other questions, a data-collection gap unrelated to the typo.

---

## CC-026 (resolved): section 4.2 caregiver gaps are standardised for country composition

Source: Test5 review. A reviewer asked whether the section 4.2 caregiver-vs-
non-caregiver gaps are driven by country composition rather than caregiver
status. A standalone diagnostic (`core_credit/scratch/caregiver_4_2_standardisation.py`)
found that **none of the eight raw gaps survives country standardisation** --
composition accounts for 60-95% of each, and two gaps reverse sign. This is not
a caveat to bolt on; it changes what 4.2 says, so the standardisation is now a
permanent per-wave computation.

**Why the raw comparison is contaminated.** Caregivers are 4,851 of the 5,827
analysis-ready rows (83%), so their country mix ≈ the population's. Non-caregivers
are only 967 and are geographically concentrated -- Ecuador (122) and Montenegro
(151) alone hold 28% of them, and Montenegro reports weak outcomes on these
measures. An unadjusted caregiver-vs-non-caregiver difference therefore partly
measures which countries the two groups sit in.

- `metrics_engine/engine.py`: new `LOW_N_THRESHOLD = 30` (mirrors
  `graph.nodes._LOW_N_THRESHOLD`) and `directly_standardised_gap(mask, group_a,
  group_b, stratum, stratum_weights, min_group_b_n=LOW_N_THRESHOLD)`. Direct
  (epidemiological) standardisation: the standardised gap is the size-weighted
  mean of the within-stratum gaps, weights = `stratum_weights` (the full sample's
  per-country row counts) renormalised over the included strata. A stratum enters
  **only where `group_b` has at least `min_group_b_n` answered rows for that
  outcome** -- not full support, because a country with 3-10 non-caregivers all
  scoring ~100% at full population weight swings the result. Returns `raw_gap`,
  `standardised_gap` (None if no stratum qualifies), `composition_share`,
  `included` / `excluded` (`{country: group_b n}`), `contributions`, `group_a_n`,
  `group_b_n`. Handles a wave with different usable support, or a stratum with no
  `group_b` at all (excluded, reported), or `raw_gap ≈ 0` (`composition_share`
  None).
- `schemas/child_wellbeing.py`: `CaregiverGapStandardisation` (one per outcome,
  parallel to `caregiver_vs_other`: `raw_gap`, `standardised_gap`,
  `composition_share`, `top_composition_countries`) and
  `CaregiverStandardisationSupport` (`n_threshold`, `method`, `caregiver_n`,
  `non_caregiver_n`, `included` / `excluded` country->non-caregiver-count,
  `concentration_note`). `ChildWellbeingSection` gains
  `caregiver_standardisation` and `caregiver_standardisation_support` (both
  default-empty so older outputs still load).
- `driver/build_child_wellbeing.py`: `_outcome_masks` extracted (shared by the
  raw comparison and the standardisation so they cannot drift);
  `_caregiver_standardisation(df, caregiver_vs_other)` computes all eight rows +
  the support object; `_format_comparison_summary` hands the writer a terse
  factual block (support header + one line per outcome with raw gap, significance,
  standardised gap, composition share). `composition_share` is anchored on the
  displayed (rounded) `GapComparison.gap` so it equals `(raw - standardised) /
  raw` of the two numbers the table prints. `_standardisation_acceptable_percentages`
  whitelists the standardised gaps, composition shares and the caregiver-share
  figure for the grounding check (`grounding.py` untouched).

Verified (live, Test5), standardised on the 11 countries with a non-caregiver
base ≥ 30 (BOL 89, DOM 70, ECU 122, GTM 67, HND 69, IND 36, KOS 79, MEX 83,
MMR 58, MNE 151, VNM 53); 10 excluded (GHA 19, KEN 13, MLI 10, MNG 12, MWI 4,
RWA 12, SEN 3, TZA 4, UGA 5, ZMB 8):

| Outcome | Raw gap | Standardised | Composition share |
|---|---|---|---|
| Improved quality of life | +5.1% | +2.1% | 60% |
| Financial worry decreased | +6.7% | +1.2% | 83% |
| Improved community respect | +19.3% | +3.6% | 82% |
| Improved business income | +9.3% | +3.0% | 67% |
| Loan goal fully achieved | -4.7% | +0.3% | 106% (sign reverses) |
| Improved household influence | +16.3% | +3.8% | 77% |
| Increased savings | +10.3% | +2.5% | 76% |
| NPS (promoter) | -2.5% | +2.4% | 195% (sign reverses) |

Five `directly_standardised_gap` unit tests added (pure composition effect ->
standardised gap 0; thin strata excluded and reported; no usable support ->
None; sign reversal).

---

## CC-027 (resolved): the 4.2 table carries the standardised gap and composition share

`report_render/section_layout.py` `render_child_wellbeing`: the 4.2 table goes
from 4 columns to 6 -- `Outcome | Caregiver % | Non-caregiver % | Raw gap (sig?) |
Country-standardised gap | Composition share`. The significance annotation stays
on the raw-gap column (unchanged `_significance_label`). Standardised gap /
composition share are zipped in from `section.caregiver_standardisation` by
outcome name; a row with no standardisation entry (older output) renders `n/a`,
one where `standardised_gap is None` renders `not computable this wave`. A
caption below the table states the method, lists the excluded countries with
their non-caregiver counts, explains that a composition share above 100% means
the standardised gap runs the other way, and repeats the CC-001 line that
standardisation removes one confounder without making the comparison causal.

---

## CC-028 (resolved): the 4.2 and Part 4 insight prompts lead with the corrected reading

`writer/section_prompts.py`. Both prompts now lead with the raw gap **as
observed**, then state that most of it is country composition, not caregiver
status, and name Ecuador and Montenegro.

Two Test5 conclusions are **removed, not softened**:

1. *"suggesting caregivers reach buffer-need households well, though loan
   targeting could improve"* -- rested on the loan-goal -4.7pt gap, which
   reverses to a +0.3pt caregiver edge once countries are matched. `CAREGIVER_VS_OTHER`
   now instructs: "the raw loan-goal gap says nothing about caregivers reaching
   buffer-need households; it does not survive matching." The old "note whether
   caregivers are reaching the households that most need a buffer" instruction is
   deleted.
2. *"the loan's social payoff for caregivers runs deeper than the wellbeing
   metric alone captures"* -- rested on the community-respect and household-
   influence gaps, which are 82% and 77% composition. `CHILD_WELLBEING_INSIGHT`
   now instructs: "do not read a broader social benefit, a deeper loan effect, or
   buffer-targeting success into these numbers; any small standardised gap is an
   association only."

The mechanism is stated as CC-028 specifies -- **non-caregivers** are the
concentrated group (ECU + MNE = 28%, MNE a weak-outcome market), not "caregivers
clustering in strong markets". Both prompts keep the CC-001 causation rules.

**Word caps raised** (`CAREGIVER_VS_OTHER` 80 -> 175, `CHILD_WELLBEING_INSIGHT`
120 -> 180): CC-028 turned 4.2 from a one-line note into a methodological
correction that has to carry the raw gaps, the standardised gaps, the two sign
reversals, the country-concentration reason and the causation caveat. That does
not compress below ~170 words without dropping a required point; the
`report_assembly/completeness.py` check still flags a run that overshoots.

Verified (live, Test5) -- 4.2, 172 words, within cap, grounding clean:

> Caregivers report higher rates than non-caregivers on most outcomes, with the
> widest raw gap on improved community respect at 19.3 percentage points, 77.2%
> versus 57.9%. Once both groups are standardised to a common country mix, almost
> all of these gaps collapse toward zero, and two outcomes flip direction, loan
> goal fully achieved moves from a 4.7-point non-caregiver lead to a slight
> 0.3-point caregiver edge, and the Net Promoter Score promoter rate moves from a
> 2.5-point non-caregiver lead to a 2.4-point caregiver edge. This pattern
> reflects that non-caregivers are a small group concentrated in a handful of
> countries, with Ecuador and Montenegro alone holding about a quarter of all
> non-caregiver respondents, and Montenegro reporting weak results on these
> outcomes, so the raw comparison is partly picking up country mix rather than
> caregiver status itself. Practically, the raw loan-goal gap cannot be read as
> caregivers being less likely than non-caregivers to reach buffer-need
> households. Even the standardised gaps remain associations rather than effects,
> since country is only one of several possible confounders left unaddressed.

---

## CC-029 (open, not fixed): the pipeline and dashboard-spec caregiver definitions disagree on ~7% of rows

**Report, do not fix.** The pipeline's `caregiver_mask`
(`metrics_engine/segments.py`) derives caregiver status from **IMPACT04**
("a. Yes" / "b. No" -> caregiver; "c. Do not support any children" ->
non-caregiver; blank -> unclassified). The dashboard spec defines a caregiver
**structurally**, as a client supporting children where **PROFILE04b, PROFILE04c
or PROFILE04d > 0**.

Confirmed on Test5 (5,827 analysis-ready rows):

| | Caregiver | Non-caregiver | Unclassified |
|---|---|---|---|
| IMPACT04 (pipeline) | 4,851 | 967 | 9 |
| PROFILE04b/c/d > 0 (spec) | 4,693 | 1,134 | 0 |

The two disagree on **417 rows (7.2%)**:

- **283** IMPACT04 says caregiver, PROFILE04 says non-caregiver
- **125** IMPACT04 says non-caregiver, PROFILE04 says caregiver
- **9** IMPACT04 blank, PROFILE04 says non-caregiver (0 the other way)

Net effect of switching to the PROFILE04 definition: the caregiver base drops
**4,851 -> 4,693 (-158)**.

**Figures that would move if the definition changed:**

- **4.1 improved child wellbeing** -- base is the caregiver mask. Rate moves
  **93.5% -> ~95.5%** (+2.0pp: the 283 rows dropped from the base skew toward
  "b. No"), plus its by-segment cuts and its benchmark-comparable value.
- **4.2, every one of the 8 rows** -- non-caregiver base 967 -> 1,134 changes
  every caregiver and non-caregiver rate, every raw gap, and every significance
  test.
- **4.2 standardisation (CC-026)** -- per-country non-caregiver counts change, so
  the included/excluded country set moves (more countries clear n >= 30), and
  every standardised gap and composition share is recomputed.
- **Executive Summary "Child Wellbeing" theme** --
  `improved_child_wellbeing.overall.share`, so the headline theme value moves with
  4.1.
- **Gender scorecard "Improved child wellbeing" row** -- base is `caregiver_mask`.
- **Every section's `SegmentAxis.CAREGIVER` cut** -- `standard_categorical_segments`
  builds that axis from `caregiver_status` (IMPACT04); redefining it structurally
  shifts the "Caregiver" / "Non-caregiver" by-segment rows in Parts 1-8.

The definition is **not changed**. `caregiver_status` / `caregiver_mask` /
`child_wellbeing_improved_mask` all stay on IMPACT04, which is the question that
also carries the "did wellbeing improve" answer 4.1 needs. Logged so a future
decision to align with the dashboard spec starts from the measured impact.

---

## CC-030 (resolved): subsection-prompt audit against CC-001..CC-004, and the 1.2 fix

Source: the first Hugging Face Space run surfaced a reviewer comment (Henry)
against `1.2`'s "competitive moat" phrase, present in every historical run since
Test2 -- the writer never invented it, the subsection prompt's own `instructions`
field says "Read it for the competitive moat, for retention". CC-002 had already
fixed the same class of defect once, for `3.2` ("tie it back to business income
above" -> report the figure standing on its own). Audited every `SubsectionPrompt`
in `writer/section_prompts.py` (34 total) against the CC-001-004 rules for the
same pattern: an instruction telling the writer to do something the rules now
forbid, rather than the model inventing it unprompted.

**Confirmed violations (instruction directly conflicts with a rule, phrase traced
into real rendered output):**

- **1.2** `ALTERNATIVE_LENDER_HARD_TO_FIND` -- "Read it for the competitive moat,
  for retention, and for the responsibility that comes with limited competition."
  Investor-register, business-strategy framing applied to a single self-reported
  perception metric. Fixed this entry (below).
- **7.1** `SAVINGS_INCREASED` -- "Note any gradient across segments and the link
  to resilience below." This is CC-002's exact defect recurring: it instructs the
  writer to assert a relationship between the savings figure (7.1) and the
  shock-severity-reduction figure (7.4) that nothing computes. Confirmed in
  rendered output: "...a gradient worth linking to resilience patterns below."
  Not fixed in this pass -- flagged for a follow-up CC-NNN, since fixing it
  correctly needs the same care CC-002 gave 3.2 (word cap, replacement wording),
  and this batch was scoped to the four items above.
- **8.2** `NPS_DRIVERS` -- two separate hits in one subsection. (a) The subsection
  *title* itself, "What drives recommendation and dissatisfaction", contains the
  literal banned word "drives" -- fed to the writer via `chain.py`'s
  `_task_preamble` (`f"Subsection: {prompt_config.title}"`) AND printed verbatim
  as the document heading (`section_layout.py`: `h.add_subheading(doc, "8.2 What
  drives recommendation and dissatisfaction")`). (b) "Name the single fix with the
  most leverage" -- "leverage" is one of the SYSTEM_PROMPT's own named-forbidden
  forward-looking phrases ("never... 'carries the most leverage'..."). The model
  self-corrected to CC-001-compliant phrasing in the one run checked, but the
  instruction itself still says it. Not fixed in this pass.
- **4.1** `IMPROVED_CHILD_WELLBEING` -- "describe the likely pathway, for example
  higher income leading to school fees and then to wellbeing" models the literally
  banned phrase "leading to" as its own worked example, one sentence before "never
  a fabricated causal claim" -- internally contradictory. Not fixed in this pass.
- **7.4** `VF_REDUCED_SHOCK_SEVERITY` -- "the resilience dividend that comes with
  access". "Dividend" is a return-on-investment metaphor functionally equivalent
  to the banned "payoff", describing the shock-severity reduction as something the
  loan pays out. Did not surface in the one run checked (the model wrote
  "preparedness reported" instead), but the instruction still carries it. Not
  fixed in this pass.

**Borderline (real, lower confidence, worth watching):**

- **gender-scorecard** `GENDER_SCORECARD_ANALYSIS` -- "Tie it back to first time
  access in Part 1 and to satisfaction in Part 8" produced the "worth noting
  against Part 1 first-time access goals" / "linking gender to the Part 8
  satisfaction story" phrasing the pipeline's own `qa_review` independently
  flagged as internal-reference leakage. Softer than the 7.1 case: Part 1 and
  Part 8's own metrics are directly reused in the gender table (not a second,
  uncomputed figure), so this reads more as a drafting artifact than a CC-002
  violation proper.
- **3.1** `BUSINESS_INCOME_CHANGE` -- "later cycles should show more improvement,
  so flag it if they do not" bakes in a dose-response expectation across loan
  cycles that isn't itself computed or randomised, adjacent to CC-001's "loan
  cycles... are observational associations, never effects" rule. The model
  described the actual pattern factually in the one run checked ("not a
  consistent gradient"), without overclaiming.
- **5.2** `LOAN_TERMS_CLEAR` -- "low clarity carries a risk of misselling and of
  clients taking on too much debt" is domain rationale for why to look at the
  pattern, not itself a claim about this data -- but it demonstrably leaked into
  rendered output as an inferred, uncomputed risk claim: "suggesting misselling
  risk concentrated in specific markets."

**Not violations, checked explicitly:** 1.1, 1-insight, client-profile (a
different, factual-accuracy defect -- see CC-033), executive-summary, 2.1, 2.2,
2-insight, 4.2, 4-insight, 3.2 (already fixed under CC-002), 3-insight, 5.1, 5.3,
5.4, 5.5, 5-insight, 6.1, 6.2, 6.3, 6-insight, gender-insight (has a good
self-correcting caveat, citing a real flagged mistake), 7.2, 7.3, 7-insight, 8.1,
8-insight.

**Scope note.** No source in this repo -- this spec doc, git history, or the
codebase -- references "Henry" or a 33-comment review list; `grep` for both
returns nothing. This audit is therefore a fresh pass against the CC-001-004
rule text and real rendered output, not a mapping onto that external list. 8 of
34 prompts (5 confirmed + 3 borderline) carry an instruction-level problem; how
many of the 33 external comments that accounts for is unknown without the list
itself.

**Fixed, this entry:** `writer/section_prompts.py` `ALTERNATIVE_LENDER_HARD_TO_FIND`
(1.2) no longer mentions moat, retention, or competitive framing. It now
instructs: report the headline figure; state that it measures clients' perceived
ability to find an alternative, not actual market scarcity (the reviewer's
suggested wording, "suggesting limited perceived alternatives", is given as the
worked phrasing); note patterns by gender and country.

Verified live: "Overall, 45.0% of clients report it would be very or slightly
difficult to find another lender, a self-reported perception rather than a
measured level of market competition, suggesting many feel their alternatives
are limited. ..." -- 65 words, within cap, no "moat".

---

## CC-031 (resolved): comparable-basis figure was nested inside the benchmark check

Source: the first Hugging Face Space run has no benchmark workbook (by design --
see CC-033), so every "our own figure on a stricter box definition" line vanished
along with the benchmark, even though that figure is computed from survey data,
not the workbook, and has nothing to do with whether the benchmark loaded.

`writer/formatting.py` `format_metric_result`: the `benchmark_comparable_value`
block was nested inside `if mr.benchmark and mr.benchmark.external_mfi_index is
not None`. Unnested -- the comparable-basis line is now emitted whenever
`benchmark_comparable_value` itself is populated, independent of whether a
benchmark exists. Two renderings: with a benchmark present, unchanged wording
("use this one for the comparison, not 'overall' above"); with no benchmark, new
wording that explicitly withholds the comparison ("no external MFI Index
benchmark is available this run -- report this as our own number standing alone
... never as something compared against a benchmark").

`writer/chain.py` `SYSTEM_PROMPT`'s CC-003 benchmark-discipline paragraph gains a
closing clause for the no-benchmark case: when there is no "MFI Index benchmark"
line for a metric (or for any metric this run), a "figure on a stricter box
definition" line is not a benchmark comparison -- state it as our own standalone
number, never "higher than" / "lower than" a benchmark, never "comparable" to
anything, never implying an external figure exists elsewhere in the report.

New test `test_format_metric_result_shows_comparable_value_without_a_benchmark`
(`writer/tests/test_formatting.py`) locks in the unnest. `writer/tests/`: 8/8
pass.

---

## CC-032 (resolved): the Executive Summary comparable-basis column was never populated

Source: CC-031's investigation. The exec-summary table's third column,
"VisionFund (benchmark-comparable basis)" (added CC-014, to fix a real incident
where the table showed a loose headline next to a stricter-basis benchmark), had
silently regressed to always equalling the Score column -- confirmed by reading
`synthesis/build_executive_summary.py::_theme_scores()` in full: no
`ThemeScore(...)` construction anywhere in that function ever sets
`benchmark_comparable_value`. `_format_theme_scores` and `_acceptable_percentages`
only ever read it (and its `render_executive_summary` fallback -- "otherwise the
Score itself" -- silently masked the gap by always printing a number).

**Recommendation given before changing it:** remove the column rather than
populate it. Reasoning: 5 of 7 (up to 8, when Poverty Likelihood is present)
themes are CC-011 unweighted means of 2-6 constituent metrics, each on its own
box definition -- CC-011 already established there is no single MFI Index
benchmark for a mean like that, and the identical reasoning means there is no
single "comparable basis" for it either; populating it would mean averaging
several different constituents' own stricter-box figures with no shared
benchmark to justify why that particular box definition is the relevant one to
average, reproducing the exact problem CC-011 was written to avoid, one column
later. Of the remaining single-indicator themes, only Child Wellbeing could
carry a genuine value; Client Satisfaction's NPS runs on a -100..100 scale with
no box-share concept at all, so even a "populate where possible" approach fills
at most 1 of 7 cells while implying a general-purpose column that mostly isn't
one.

Fix: `schemas/executive_summary.py` `ThemeScore.benchmark_comparable_value`
removed. `synthesis/build_executive_summary.py`: the dead read paths in
`_format_theme_scores` and `_acceptable_percentages` removed.
`report_render/section_layout.py` `render_executive_summary`: table drops to
three columns (Theme, Score, MFI Index Benchmark); docstring rewritten to record
why the column was removed rather than fixed. `test_executive_summary_table_...`
in `report_render/tests/test_section_layout.py` rewritten as a regression test
for the column's absence (was CC-014's original regression test for its
presence).

---

## CC-033 (resolved): the Hugging Face degrade is silent in the report itself

Source: run_for_dashboard.py (CC_030's predecessor work, the prior session) sets
`CORE_CREDIT_ALLOW_MISSING_PPI` / `CORE_CREDIT_ALLOW_MISSING_BENCHMARKS`
automatically whenever the reference workbooks are absent, so every Hugging Face
Space run silently omits Part 2 and every MFI Index benchmark, with only a
`print(..., flush=True)` note on the subprocess's stdout log -- nothing in the
delivered document itself. A reader has no way to tell "Part 2 is missing because
this deployment doesn't ship reference data" from "Part 2 is missing because
something is broken." Separately, `client-profile`'s Analysis block asserted, via
an ungrounded instruction with no backing data, that "PPI and other worked
scores are calculated upstream and reported elsewhere as finished figures" --
true whenever Part 2 actually ran, false on a degraded run, and the writer had no
way to know which was true because it was never given the fact, only told to
assert it.

Kept the degrade (the deployment decision behind it stands) and made it visible
instead:

- `schemas/report.py` `CoreCreditImpactReport.data_availability_note: Optional[str]`.
- `report_assembly/build_report.py` `_data_availability_note()`: reads the same
  two env vars `run_for_dashboard.py` sets -- the direct, actual cause of the
  degrade, not a re-derivation from section output shape -- and composes one
  sentence per missing workbook plus a closing "infrastructure gap ... not a data
  quality issue" line. `None` when both workbooks loaded.
- `report_render/section_layout.py` `render_report`: renders the note as a
  caption right under the existing base-count caption, before the first section
  divider -- so a reader hits it on the title page, not two sections in.
- `driver/build_client_profile.py`: new `_ppi_status_line()` reads
  `CORE_CREDIT_ALLOW_MISSING_PPI` directly (Client Profile and Poverty Likelihood
  build concurrently with no data dependency between them, so this can't be read
  off Poverty Likelihood's own output) and hands the writer a bracketed
  `[FACT -- state this PPI status line exactly, do not paraphrase into a
  different claim]` line, true either way. `writer/section_prompts.py`
  `CLIENT_PROFILE_ANALYSIS` now points at that fact instead of asserting PPI is
  "reported elsewhere" unconditionally.

Verified live: with `CORE_CREDIT_ALLOW_MISSING_PPI` set, Client Profile now
writes "PPI scoring is not available this run, so Part 2 (Poverty Likelihood) is
omitted" (was: "PPI and other worked scores are calculated upstream and reported
elsewhere as finished figures"). With both env vars set, `build_report()` +
`render_report()` end to end: the note renders as document paragraph 3 (right
after the base-count caption, before Client Profile), reads "This run is missing
reference data VisionFund normally provides server-side: the PPI reference
workbooks ... were not available, so no client could be scored and Part 2
(Poverty Likelihood) is omitted; and the External Benchmarks.xlsx workbook was
not available, so no MFI Index comparison appears anywhere in this report. This
is an infrastructure gap for this run, not a data quality issue with the survey
responses...".

---

## CC-034 (resolved): the five confirmed CC-030 violations, plus two the CC-035 guard found

Fixed all five prompts CC-030 confirmed:

- **7.1** `SAVINGS_INCREASED` -- "and the link to resilience below" removed. Now:
  "Report the share whose savings rose since they took the loan. Note any
  gradient across segments."
- **8.2** `NPS_DRIVERS` -- title changed from "What drives recommendation and
  dissatisfaction" to "Reasons clients gave for recommending or not
  recommending" (also updated in `report_render/section_layout.py`'s hardcoded
  heading and `build_client_satisfaction.py`'s stdout summary label -- both
  reproduce the title independently of `SubsectionPrompt.title`). "Name the
  single fix with the most leverage" removed.
- **4.1** `IMPROVED_CHILD_WELLBEING` -- the "for example higher income leading to
  school fees and then to wellbeing" worked example removed outright, per the
  instruction that a banned construction used as an illustration teaches the
  pattern regardless of the surrounding caveat. Replaced with an explicit "never
  assert what produced the improvement."
- **7.4** `VF_REDUCED_SHOCK_SEVERITY` -- "the resilience dividend that comes with
  access" removed. Now: "Read it as realized preparedness among clients who
  faced a shock."
- **5.2** `LOAN_TERMS_CLEAR` -- the misselling-risk rationale removed. Reframed
  per the reviewer's objection (low clarity does not by itself demonstrate
  misselling) to: "a low figure there is worth reviewing for gaps in client
  understanding and potential protection risks. On its own it does not
  establish misselling."

**Two more found by CC-035's own guard on first run**, not part of the original
audit:

- **4.2** `CAREGIVER_VS_OTHER` -- "flip from a non-caregiver lead to caregivers
  level or slightly ahead" tripped the guard's `lead to` pattern. This one is a
  checker false positive, not a real violation -- "lead" here is the noun
  (advantage), not the causal verb construction -- but a `\blead to\b` phrase
  match can't distinguish the two, and teaching the checker English grammar is
  worse than routing around it once. Reworded to "flip from favoring
  non-caregivers to caregivers level or slightly ahead", meaning unchanged.
- **8-insight** `CLIENT_SATISFACTION_INSIGHT` -- "name the fix with the most
  leverage" is the identical defect as 8.2, in the section's own Insight prompt,
  missed by the manual CC-030 audit. Reworded to "name the fix that could be
  explored as the most impactful priority" (CC-001's sanctioned forward-looking
  form).

Verified: `writer.chain` now imports cleanly (CC-035's guard passes). Full
test suite: 277 passed.

---

## CC-035 (resolved): startup guard against a rule and an instruction contradicting each other

Source: every CC-030 violation existed because SYSTEM_PROMPT's banned-term rules
were extended over time (CC-001, CC-003) without re-checking the subsection
prompts already written against them. Nothing mechanical connected the two.

`writer/chain.py`: `CC001_BANNED_TERMS` and `CC003_BANNED_TERMS`, hand-maintained
tuples of the literal terms SYSTEM_PROMPT's own paragraphs name -- not derived
from the prose, so a maintainer edits this list explicitly when a banned-word
sentence in SYSTEM_PROMPT changes. `validate_subsection_prompts()` scans every
`SubsectionPrompt`'s `title` and `instructions` (word-boundary regex, case
insensitive) and raises `ValueError`, listing every hit, if any banned term
appears. Called unconditionally at module import time, right after `SYSTEM_PROMPT`
is defined -- `chain.py` is imported by every driver and by both orchestrator
entry points (`run_orchestrator.py`, `run_for_dashboard.py`), so nothing can
reach a writer call without the check having already passed. Fails at import,
before any section builds, exactly as asked -- not a lint step someone can skip.

Two deliberate departures from SYSTEM_PROMPT's literal wording, both because a
literal match would have missed a real violation this same audit found:
"leverage" is banned standalone (SYSTEM_PROMPT's literal phrase is "carries the
most leverage", but the real 8.2/8-insight defect was "the fix with the most
leverage" -- contains the word, not the exact phrase); "leads to" is a regex
also matching "leading to" / "lead to" (the real 4.1 defect used "leading to").
The "lead to" broadening produced one false positive on rollout (4.2, see
CC-034) -- routed around by rewording the prompt, not by making the checker
smarter, since a phrase match fundamentally cannot distinguish "lead" the noun
from "leads to" the causal verb, and either choice trades one gap for another.

Scope: literal SYSTEM_PROMPT terms only, not the fuller "moat" / "dividend"
class CC-030 found by human read-through. Those aren't named anywhere in
SYSTEM_PROMPT's CC-001/CC-003 paragraphs, so a keyword scan was never going to
catch them; they need a human or a semantic check, not a string match. This
guard closes the narrower, mechanically-checkable gap: a named banned term
silently sitting in a prompt.

`writer/tests/test_prompt_validation.py` (9 tests, new file): the checker
against synthetic modules -- passes clean, catches a CC-001 term in
instructions, catches one in the title, catches a CC-003 competitive verb,
catches "leverage" standalone, catches "leading to", confirms the noun-"lead"
false-positive is real and current behavior (not silently taught away), ignores
non-`SubsectionPrompt` module members, and checks the two term lists are
non-empty and disjoint.

---

## CC-036 (open, not fixed): borderline audit cases and the 3.3 duplicate-verbatim category

Read-only findings, not acted on this pass.

**Borderline cases from CC-030, checked against the most recent Hugging Face
run's actual rendered output (`Core_Credit_Impact_Report_core_credit_6a31d76c05.docx`):**

- **gender-scorecard** `GENDER_SCORECARD_ANALYSIS` -- "Tie it back to first time
  access in Part 1 and to satisfaction in Part 8" did **not** produce
  section-number leakage in this run: `analysis_text` reads "Once onboarded,
  women report loan purpose fully achieved..." and closes "Widening women's
  first-time access could be explored as a priority area, given these
  onboarding-stage gaps" -- no literal "Part 1" / "Part 8" anywhere. This
  differs from the local `e2e-0903c` run three turns ago, where the identical
  instruction produced "worth noting against Part 1 first-time access goals"
  and "linking gender to the Part 8 satisfaction story" (independently flagged
  by the pipeline's own `qa_review`). Same instruction, two different outputs --
  the risk is real but nondeterministic. **Recommendation:** reword "Tie it back
  to first time access in Part 1 and to satisfaction in Part 8" to name the
  metrics directly ("tie it back to first-time access and to NPS promoter
  share") rather than the Part numbers, so the writer has no section-number
  language available to reach for even on an unlucky generation.
- **3.1** `BUSINESS_INCOME_CHANGE` -- "later cycles should show more
  improvement, so flag it if they do not" produced fully descriptive prose in
  the checked run: "Across loan cycles the pattern is not fully progressive:
  Loan cycle 2 sits at 90.6%, rising to 92.5% at Loan cycle 3, but easing
  slightly to 92.1% at Loan cycle 4, so later cycles do not show a consistent
  gradient of increasing improvement" -- exactly the descriptive framing the
  reviewer asked for, with no dose-response claim. The instruction still
  presupposes a normative expectation (more loan cycles implying more
  improvement) that the study design cannot support, and the fact the model
  wrote around it safely this time is not the same as the instruction being
  safe. **Recommendation:** drop "should show more improvement" and state it
  neutrally -- "note any gradient across loan cycles, without assuming later
  cycles show more improvement" -- so a future generation isn't relying on the
  model resisting its own instruction's framing.

**3.3 duplicate-verbatim category, confirmed still present.** In the most recent
Hugging Face run, section 3.3 (`business_household_impact.qol_drivers`) renders
"Increased income/earnings (general)" (n=577, 10%) immediately followed by
"Increased income/earnings (general) - business profit growth" (n=473, 8%),
both illustrated with the identical two verbatims -- "I have more income" /
"Tengo mas ingresos" (Female, DOM) and "Income sources increased" (Female,
IND). CC-020's dedup (`report_assembly/translate_verbatims.py::_suppress_duplicate_protection_verbatims`)
is scoped to Client Protection's `protection_signals` pool only; it has no
counterpart for `qol_drivers` or any other section's qualitative theme list.
Root cause is upstream of rendering: the theme-tagging pass is producing two
near-duplicate themes ("general" and "general - business profit growth") for
what reads as one underlying category, and both happen to draw their top
representative verbatims from the same two respondents. Not fixed this pass --
flagged for a follow-up CC-NNN, and worth deciding there whether the fix belongs
in theme consolidation (fewer, better-separated themes) or in a
qol_drivers-scoped verbatim dedup mirroring CC-020's.

---

## CC-037 (resolved): share_of_respondents could exceed 1.0 -- the merge summed opaque counts, not deduplicated identities

Source: `build_client_satisfaction` crashed 13 minutes into a local end-to-end run
with `pydantic_core.ValidationError: share_of_respondents ... Input should be
less than or equal to 1 [input_value=1.285]`, inside the qualitative batch
merge.

Root cause, confirmed by reading `qualitative_agent/agent.py`, not assumed:
`theme_tag_batch`'s own SYSTEM_PROMPT explicitly allows one response to belong
to more than one theme within a batch ("a response may belong to more than one
theme if it genuinely touches on more than one"). `merge_batches` groups
per-batch themes into canonical themes via an LLM call, then computed
`frequency = sum(t.frequency for t in member_themes)`. If two of a single
response's own per-batch themes both land in the same merge group -- a real
case: a batch's "increased income" and "business growth" themes both citing the
same client, later merged into one canonical theme -- that response's count was
summed twice. `ThemeFinding` never carried the underlying response identities
past `theme_tag_batch`, only the aggregate `frequency` int, so `merge_batches`
had no way to notice the overlap: it could only sum opaque counts. Not "batch
shares summed instead of recomputed against a common base" literally, but the
same category of defect -- aggregated per-batch counts combined without ever
touching the actual underlying response identities.

Fix, calculation only -- `ThemeFinding.share_of_respondents`'s `le=1` bound is
untouched:

- `schemas/common.py` `ThemeFinding` gains `response_keys: list[str]` --
  per-response identity for every response counted in `frequency`, carried
  through the batch/merge boundary (survives LangGraph's SQLite checkpointing,
  unlike a Python `id()`).
- `qualitative_agent/agent.py` `_response_key()`: `client_id` when present
  (content-based, stable); a fallback namespaced by source field and local
  index when blank (`clean_blank_strings` turns "" into `None` for some rows),
  so a fallback key can never collide with a real `client_id` or with another
  fallback -- undercounting a rare duplicate is the safe direction, never
  inflating a count.
- `theme_tag_batch`: `valid_all_ids` deduplicated via `sorted(set(...))` before
  computing `frequency` -- closes a smaller, same-class risk (the model
  repeating an ID within one theme's own list). `response_keys` set on every
  `ThemeFinding` it returns.
- `merge_batches`: `frequency`/`share_of_respondents` now computed via
  `_dedup_frequency()` (pulled out as a pure function so it's testable without
  an LLM call) -- the **union**, not sum, of every member theme's
  `response_keys`. Double counting is now structurally impossible rather than
  merely unlikely.

`qualitative_agent/tests/test_agent_helpers.py`: 7 new tests, including the
exact incident shape (two overlapping-response themes merged: naive summing
gives `3 + 2 = 5` over a 4-response universe, i.e. `share_of_respondents =
1.25`; the fix gives the correct `4`).

---

## CC-038 (resolved): run_orchestrator.py had no exception handling -- a node failure produced nothing

Source: the CC-037 crash left no report, no docx, and no record of which node
failed or what had already completed -- `run_orchestrator.py`'s `main()` calls
`compiled.invoke()` with no `try`/`except` around it, so an uncaught node
exception 13 minutes in printed a bare Python traceback and exited. The
dashboard path (`run_for_dashboard.py`) already handles this
(`{"event": "error", "reason": ...}`); the CLI didn't.

The graph is already checkpointed to SQLite (`sqlite_checkpointer`), and
`main()` already resumes from an existing checkpoint under the same `--run-id`
(skips completed sections) -- so a resume path already existed and is cheap;
what was missing was reporting the failure itself instead of crashing bare.

Fix: `orchestrator/run_orchestrator.py` gains `diagnose_failure(compiled,
graph_config, exc)`, built from whatever the checkpointer already persisted --
LangGraph writes state after each completed node (a superstep), so a node that
raises never gets its own write in, but every node that finished first is
already there. `main()` wraps the `invoke()` call in `try`/`except`: on
failure, writes `orchestrator/output/run_status_{run_id}.json` (completed
sections, missing sections, exception type and message), prints a clear
summary instead of a bare traceback, and tells the operator the run is
checkpointed and a re-run under the same `--run-id` will resume rather than
recompute.

`diagnose_failure` is deliberately a standalone function, not inlined in
`main()`, so the real claim under test -- that completed sections survive a
later node's crash -- is provable against a real (temp-file) SQLite
checkpointer and a graph with one deliberately-failing stub node, not just
trusted. `orchestrator/tests/test_failure_handling.py` (3 new tests): the 8
theme sections that run concurrently with a failing `client_satisfaction` node
and don't depend on it are confirmed present in `sections_completed`; an
early-failure case where nothing completed yet; and a defensive case where
`get_state()` itself raises.

---

## CC-039 (resolved): CC-020's verbatim dedup extended to qol_drivers

Source: CC-036 confirmed the exact incident live -- a Hugging Face run rendered
"Increased income/earnings (general)" and "...business profit growth" back to
back in section 3.3, with the identical two verbatims under both. Root cause is
the same exposure `report_render.section_layout.add_protection_signals` had
before CC-020: `add_theme_list` (3.3's own renderer) prints each theme's own
`representative_verbatims[:2]` independently, with zero visibility into what an
earlier theme in the same list already showed.

Audited every place a `QualitativeSynthesis` gets rendered, to answer "which
theme sets did you cover": exactly two functions render a theme list with
verbatims directly, `add_theme_list` (used only for `qol_drivers`, 3.3) and
`add_protection_signals` (used only for `protection_signals`, already
CC-020-covered). Three other qualitative fields exist
(`other_improvements_qualitative` 4.1, `other_coping_qualitative` 7.3,
`nps_followup_themes` on Client Satisfaction) but none of them render their own
theme list directly -- the first two only ever feed the writer (any quote it
cites is resolved and grounding-checked through `used_verbatim_ids`, not
printed as a raw theme dump); `nps_followup_themes` feeds Client Voices (Part
10) via `build_client_voices.py`, which pools verbatims from its top themes and
selects through `pick_diverse_verbatims` -- a single pooled selection over a
flat list, not independent per-theme slicing, so an identical verbatim
appearing in two contributing themes is already excluded by that function's
own country-seen and "already picked" checks (Pydantic model equality). **Covered:
`qol_drivers` (new). Confirmed already covered: `protection_signals` (CC-020).
Confirmed not needed: `other_improvements_qualitative`, `other_coping_qualitative`,
`nps_followup_themes`/Client Voices.**

Fix: `report_assembly/translate_verbatims.py`'s CC-020 function split into a
general `_suppress_duplicate_theme_verbatims(qs, rank_key)` (keeps each
verbatim once, on the theme `rank_key` ranks highest, drops it from every
lower-ranked theme -- no backfill) plus two one-line callers:
`_suppress_duplicate_protection_verbatims` (rank = severity, unchanged
behavior) and `_suppress_duplicate_qol_driver_verbatims` (rank = frequency --
`qol_drivers` has no severity concept, and frequency is already the section's
own natural ranking, so a reader sees a duplicate survive on the same theme
they'd expect from the table). Both run from `translate_report_verbatims`
before translation, so a dropped copy is never translated.

`report_assembly/tests/test_translate_verbatims.py`: 4 new tests, including the
exact incident reproduced (n=577 / n=473 themes sharing both verbatims -- fix
keeps them on the n=577 theme, drops both from n=473) and a check that two
different clients typing the identical short phrase ("good") are correctly
NOT treated as a duplicate (matched by `client_id` first, not quote text
alone).

---

## CC-040 (open, not fixed -- diagnosis and recommendation only): word-cap overruns

Source: the CC-034..036 rerun finished with 12 of 34 blocks over cap (5 more
than 20% over), worse by raw count than the prior run's 9 (3 over 20%).

**Do the overruns concentrate in prompts that gained methodological content
this round?** No. Of the 7 prompts actually touched in CC-034 (7.1, 8.2, 4.1,
7.4, 5.2, 4.2, 8-insight), 5 finished within cap (7.1 62/70, 7.4 90/90, 4.1
78/90, 5.2 69/70, 4.2 174/175) -- the content trims made them, if anything,
safer. Only 8.2 (103/90, 14.4% over) and 8-insight (167/120, 39.2% over)
worsened, and both are explainable: 8.2's title change plus dropping the
"leverage" sentence, and 8-insight's "leverage" -> "could be explored as..."
replacement, both correlate with the model elaborating more, not less, around
the new phrasing. The 5 worst offenders overall (5-insight 65.0%, 3-insight
39.2%, 8-insight 39.2%, 7-insight 26.7%, client-profile 26.7%) are dominated by
sections this round never touched -- 5-insight, 3-insight, and 7-insight were
**already** the worst three in the very first diagnostic run, before any
CC-030+ prompt edit existed (5-insight 56.7% over, 8-insight 31.7%, 3-insight
20.0% then). This is a pre-existing, systemic pattern in the "Insight"
subsections specifically, not something this round's prompt changes caused.
The one genuine, explainable regression is **client-profile** (8.3% -> 26.7%
over): CC-033 added a required `[FACT]` PPI-status line to its data, and that
extra required content plausibly pushed the natural draft length up. The rest
of the count increase (2.2, 3.1, 6.1, 7.2, newly over by 1-2 words each) reads
as ordinary run-to-run sampling variance on borderline sections, not a
regression.

**Is the single rewrite failing to compress, or are first drafts simply too
long?** Both, but the dominant cause is unambiguous. Every one of the 5 worst
offenders' rewrites DID compress, measurably:

| Subsection | First draft | Final | Compressed by | Cap | Still over by |
|---|---|---|---|---|---|
| 3-insight | 230w | 167w | -63w (-27%) | 120 | +39.2% |
| 5-insight | 245w | 198w | -47w (-19%) | 120 | +65.0% |
| 7-insight | 179w | 152w | -27w (-15%) | 120 | +26.7% |
| 8-insight | 186w | 167w | -19w (-10%) | 120 | +39.2% |
| client-profile | 166w | 152w | -14w (-8%) | 120 | +26.7% |

The rewrite mechanism works. It just isn't given a realistic job: a 230-word
first draft against a 120-word cap needs a 48% cut in one pass while
preserving every required point (headline figures, verbatim attribution,
actionable framing) -- no single "please shorten" instruction reliably does
that, and it didn't here. The real problem is upstream: these prompts ask for
more content than fits in the cap, so the first draft starts too long, and the
rewrite only claws back a fraction of the gap.

**Recommendation: tighten what the worst-offending Insight prompts ask for,
not the rewrite mechanism.** Every chronically-over Insight (3, 5, 7, 8,
gender) currently asks for "two or three verbatims with profile," on top of
folding in every headline figure and an actionable close, inside a 120-word
cap. `4-insight` (CC-028) carries comparably dense required content --
standardised vs. raw gaps, two sign reversals, a causation caveat -- in a
comparable word budget, and lands within cap specifically because it asks for
exactly **one** verbatim, not two or three, and lists a small, fixed set of
required points rather than "fold in the section." Recommend the same
discipline for 3-insight, 5-insight, 7-insight, 8-insight, and gender-insight:
cut the verbatim requirement to one, and trim each prompt's "fold in ..." list
to the two or three points that actually matter, rather than everything the
section computed. This directly reduces what the first draft has to fit,
which CC-028 already proved works, rather than asking a second corrective pass
to do more compression than the first one already demonstrably attempts.

**Why not add a second retry instead:** a second `_writer_violations` pass
would face the identical problem the first rewrite already has -- compressing
230 words to 120 in one instructed pass is a large, specific ask regardless of
how many times it's attempted, and the data above shows the model already
tries and partially succeeds every time; there's no evidence a second attempt
compounds rather than plateaus. It would also add LLM cost and latency to
every subsection that needed even one rewrite, for a problem whose actual
cause -- the prompt asking for more than fits -- a second pass doesn't touch.
Trimming the prompt's own required-content list fixes the cause; another
rewrite pass would only spend more compute chasing the symptom.

Not fixed this pass, pending sign-off on the recommendation above.

---

## CC-041 (resolved): the two CC-036 borderline prompts

- **gender-scorecard** `GENDER_SCORECARD_ANALYSIS` -- "Tie it back to first
  time access in Part 1 and to satisfaction in Part 8" replaced with "connect
  the pattern to first-time access and to the Net Promoter Score, by name --
  never by citing a Part number, which reads as an internal cross-reference
  left in the text rather than finished prose." Verified live: "On
  first-time access, men show the higher share... Expanding first-time reach
  among women could be explored as an action to support equity in access." No
  "Part 1" / "Part 8".
- **3.1** `BUSINESS_INCOME_CHANGE` -- "later cycles should show more
  improvement, so flag it if they do not" replaced with "note any gradient
  across loan cycles as a plain description of the pattern in the data,
  without assuming later cycles show more improvement." Verified live: "a
  pattern rather than a steady climb" -- no normative claim.

Full test suite: 302 passed.

---

## CC-042 (resolved): insight word caps raised, client-profile fixed, four insights lose a second verbatim

Source: is the 120-word insight cap (Core Credit Impact Report Template v2.0,
predates CC-026's standardisation table, CC-023's base disclosures, and
CC-031's benchmark caveats) disciplining content or fighting it?

**The 150-word question, answered from the CC-034..036 rerun's actual
first-pass and final word counts (`writer_trace3.jsonl`), before any change in
this entry:**

| | at 120 (actual) | at 150 (recomputed) |
|---|---|---|
| Within cap on first pass (no rewrite needed), of 34 | 17 | 19 (+1-insight, +2-insight join) |
| Still over on first pass (needs a rewrite), of 34 | 17 | 15 |
| Still over after the rewrite (final), of 34 | 12 | 11 (gender-insight resolves: 136w &lt; 150) |

Per-insight (the 8 blocks literally named `*-insight` at the template's 120;
`4-insight` already sits at 180 from CC-028 and is unaffected):

| Insight | First pass | Final (120-cap run) | At 150? |
|---|---|---|---|
| 1-insight | 143w | 117w | already within 120 on final; within 150 too |
| 2-insight | 124w | 119w | already within 120 on final; within 150 too |
| 3-insight | 230w | 167w | **still over** (by 17w) |
| 5-insight | 245w | 198w | **still over** (by 48w) |
| 6-insight | 111w | 111w | already within both |
| 7-insight | 179w | 152w | **still over** (by 2w) |
| 8-insight | 186w | 167w | **still over** (by 17w) |
| gender-insight | 159w | 136w | **resolves** (14w to spare) |

**Verdict: mixed, not uniform.** For 1-insight, 2-insight, 6-insight the 120
cap was already being met on the final draft (they only needed their one
rewrite pass, same as before) -- 150 gives headroom, not a fix for a real
problem. For gender-insight, 120 was genuinely too tight for content that
otherwise compresses fine -- 150 resolves it with zero content change: the cap
was fighting the content. For 3-insight, 5-insight, 7-insight, 8-insight, even
150 isn't enough on its own (7-insight only barely, the other three
meaningfully) -- these need real content trimmed regardless of where the
number sits, so a cap raise alone would not have been an honest fix for them.

**Implemented: both, applied precisely where each block's own data says it's
needed, not uniformly.**

- **Cap raised to 150** on all 8 `*-insight` blocks (1, 2, 3, 5, 6, 7, 8,
  gender) and on **client-profile** (`writer/section_prompts.py`).
- **client-profile: cap raised, nothing trimmed.** Unlike the insights,
  client-profile has no verbatims and no narrative padding -- it's a fixed
  checklist of demographic and methodology facts (respondents, MFIs,
  countries, gender split, age, household size, loan cycle mix, household
  head status, education, income source, populated/unavailable segments, and
  now CC-033's PPI-status fact), and first-pass drafts ran 152-166 words even
  before CC-033 added the PPI line. There is nothing here to cut without
  removing information a reader of a client-profile page actually wants, so
  this is a pure "the cap was fighting real content" case -- fixed by raising
  it, matching the diagnosis, not by shortening the fact list.
- **Verbatim requirement cut from "two or three" to "one", on exactly four
  prompts: 3-insight, 5-insight, 7-insight, 8-insight** -- the four whose
  final draft is still over even at 150. Not applied to 1-insight, 6-insight,
  or gender-insight, which don't need it (the cap raise alone already
  resolves them) -- keeping their existing "two or three verbatims"
  instruction unchanged, so those three keep the fuller client-voice content
  they already had. 2-insight (Poverty Likelihood) never had verbatims to
  begin with -- no free-text source for that Part -- so it's unaffected
  either way. 4-insight (CC-028) already asks for exactly one; untouched.
  **What this actually gives up:** each of these four insights now cites one
  representative client quote instead of the two it could previously draw
  on -- 3-insight (Business & Household Impact) and 8-insight (Client
  Satisfaction) both routinely used two full quotes in recent runs; 5-insight
  (Client Protection) and 7-insight (Resilience) had mostly been drawing on
  one already in practice, so the instruction change mainly locks in what
  they were already doing rather than removing content actively shown to
  readers.
- **5-insight only, additionally:** told not to walk through the per-country
  client-protection breakdown that `write_insight_node`'s
  `_format_client_protection_country_block` unconditionally appends to its
  data (5.1-5.5 already cover the indicators individually; naming at most one
  country if it sharpens the point is still allowed) -- this, not the
  verbatim count, was the actual driver of 5-insight being the single worst
  offender (245w first pass against a 120-word cap).

Verification is the CC-043 full rerun below, not a synthetic check -- these
are prompt-level changes to real writer calls, and the honest test is what the
next real run actually produces, over-cap or not.

Full test suite: 302 passed (no test asserted a specific cap value for any
changed prompt).

---

## CC-043: final local full run (all workbooks present) -- diagnostics and reviewer read-through

Run `local-cc043`, all three reference workbooks and `wvi-docx.skill` present
locally. Reached all 12 theme/cross-cutting sections successfully (9 theme
sections, 90s-6.3min range each depending on qualitative volume), then hit an
external, non-code failure: `BadRequestError 400 "Your credit balance is too
low to access the Anthropic API"`, inside `assemble_report_node`'s
verbatim-translation step. **CC-038's new failure handling worked exactly as
designed** -- printed `PIPELINE CRASHED after 6.3 min: BadRequestError: ...`,
correctly listed all 12 sections as `sections_completed` (none missing), wrote
`run_status_local-cc043.json`, and gave the resume instruction. Not retried
further -- a billing state doesn't change on retry. Every driver/graph node
writes its own JSON as a side effect before assembly runs, so all 12 completed
sections' output existed on disk; assembled a `CoreCreditImpactReport` from
them directly (skipping only the translation call that needs the API) to
still deliver real diagnostics and a read-through against current code. One
consequence: verbatims in this analysis are untranslated (no `.english_gloss`)
since that step never ran -- noted where it matters below, not a pipeline
defect.

**CC-035 guard:** `import writer.chain` confirmed clean before and after the
run; the run itself only got as far as it did because every prompt passed
the check at import time.

**Executive summary, all 8 rows** (matches the deterministic non-LLM
computation from the prior run, as expected): Financial Access 43.9%, Poverty
Likelihood 12.4%, Business & Household Impact 92.2%, Child Wellbeing 93.5%,
Client Protection 75.0%, Agency 85.1%, Resilience 67.5%, Client Satisfaction
69 (NPS) / MFI Index 58.0 (2025).

**Grounding (34 blocks):** `ungrounded_quotes` **0**. `partial_quotes` **1**
(3-insight: a Uganda verbatim requoted starting mid-sentence -- "she 'has been
able to build a two bedroom parment house, paid school fees for 11
Children.'" -- exact substring of the real quote, correctly flagged, not a
concern). `misattributed_quotes` **0**. `ungrounded_percentages` **6**, all
the known CC-008 class (88%, 33%, 88%, 33%, 7.6%, 9.8% -- coverage/complement
arithmetic stated in the same sentence). `orphan_markers` **0**.
`banned_punctuation` **0**.

**Word cap, post-CC-042:** within cap on first pass 17/34 (unchanged --
CC-042 targeted final compliance, not first-draft rate), needed rewrite 17/34,
**finished over cap 9/34 (was 12)**, **>20% over 2/34 (was 5)**: 5-insight
(190w/150, +26.7%) and 8-insight (193w/150, +28.7%) -- the two prompt trims
reduced but did not eliminate the two worst cases, exactly as CC-042
predicted for 5-insight (48w short even at 150) and roughly matches the
7-insight/3-insight predictions (7-insight landed at only +10.7%, nearly
resolved; 3-insight +14.7%). client-profile is now within cap (143/150,
confirms the diagnosis that it needed room, not a trim). New minor overruns
this run not seen before: executive-summary (129/120, +7.5%) and 7.2
(119/110, +8.2%) -- both untouched by any CC-042 edit, ordinary run-to-run
variance on prompts that were previously right at the edge.

### Reviewer read-through -- what a critical reader would flag

**1. A subsection narrates its own drafting failure into the deliverable (6-insight, Agency).**
The full sentence: *"A female client in Kenya, Caregiver, described this kind
of standing shift directly. A male client in India, Caregiver, and a female
client in Ghana each pointed to household and community-level changes tied to
their loan use, though the exact phrasing should be drawn from the verbatim
pool rather than summarized here without quotation."* This is exactly the
class of defect SYSTEM_PROMPT names by real incident ("never write something
like '[quote placeholder removed]' or 'actually omitting fabricated text'")
and `raise_on_meta_text_leaks` exists to catch -- but it slipped past because
`META_TEXT_LEAK_PATTERNS = ("placeholder", "fabricat", "omitting", "as
tagged")` is a fixed 4-substring list built from those specific historical
phrasings, and this is a new, unseen phrasing of the same underlying "the
model is narrating that it should have quoted something instead of quoting
it" failure. The gate is exact-substring, not semantic, so any new phrasing
of the same class walks straight through it. This is the single worst defect
in this run -- a reader hits three named clients with no actual quotes, and a
sentence that reads as an editing note left in by mistake.

**2. The Executive Summary opens with a category that doesn't exist ("Client Wellbeing").**
*"Client Wellbeing outcomes anchor this year's results. Child Wellbeing
stands at 93.5%..."* -- the opening sentence names a theme, "Client
Wellbeing," that isn't one of the report's eight themes (the real one, named
correctly one sentence later, is "Child Wellbeing"). Likely bleed from the
nearby "Client Protection" / "Client Satisfaction" theme names in the same
data block. This is the first sentence of the most-read section in the
document.

**3. The same verbatim renders in three unrelated places.** "Vision Fund has
got wonderful services and gives enough time to clients when it comes to
paying back money" (Female, ZMB, Caregiver) appears in Client Voices'
green_lights, in 8-insight, and in gender-insight -- three independent
selection/citation paths (Client Voices' pooled pick, 8-insight's own writer
citation, gender-insight's own writer citation), none of which know about the
other two. CC-020/CC-039's dedup only covers verbatims competing within the
*same* rendered theme list, not the same quote surfacing across different
Parts of the document. A reader who reads the report straight through hits
this client's words three times.

**4. Stylistic, lower severity.** 5-insight closes on "a country where
clients have described experiences of disrespectful treatment and distressing
collections practices when loans go unpaid" -- grounded in real protection
themes, but "distressing" is editorial word choice rather than the plainer,
descriptive register the rest of the report uses; a copyeditor would flag it
alongside the "competitive moat" class of tone issue even though it isn't a
causal claim. 6-insight's own tone is also noticeably choppier than its
neighbors even before the drafting-note sentence -- three back-to-back
short, list-like sentences about different clients with no throughline.

**Not flagged, checked and clean this run:** no banned-term slips (moat,
dividend, leverage, drives-as-verb) anywhere in the 34 blocks; CC-041's
gender-scorecard and 3.1 fixes both held (no "Part 1"/"Part 8", no
dose-response framing); CC-031's benchmark-comparable lines read correctly
with real benchmarks present throughout (1.1, 1-insight, 3.1, 3.2, 5.1, 5.2,
7.1, 7-insight all correctly pair "our own figure on the stricter basis" with
the real MFI Index number); base-naming discipline (CC-004) held everywhere
checked (6.2, 7.4 both name every subgroup's base); no CC-002 violations
(figures reported in adjacent sentences without an invented link) found
anywhere the previous audit didn't already flag.

## CC-044: generalize the meta-text-leak gate (structural check + phrase list + SYSTEM_PROMPT)

CC-043's finding #1 (the 6-insight drafting-narration defect) exposed a real
limitation: `META_TEXT_LEAK_PATTERNS` was four literal substrings from past
incidents, and the new defect's wording didn't match any of them -- a phrase
list can only catch wording it has already seen.

**`report_assembly/completeness.py`:**
- Added five entries to `META_TEXT_LEAK_PATTERNS`: `"should be drawn from"`,
  `"rather than summarized here"`, `"verbatim pool"`, `"without quotation"`,
  `"should be quoted"` -- still reactive by nature (wording-based), but closes
  the specific gap the 6-insight text exposed.
- Added a genuinely structural check, merged into `find_meta_text_leaks`:
  `_CLIENT_ATTRIBUTION_RE` matches "a/one female/male client ... in COUNTRY";
  for every sentence that matches, if neither that sentence nor the next one
  contains a `"`, it's flagged. This doesn't depend on which words describe
  the gap, only on the shape (a client named with no quote anywhere nearby).
  Deliberately scoped narrow -- singular "client" (not "caregiver"), "in"
  (not "from") -- matching this pipeline's actual citation-setup phrasing
  exactly, not a broader net. Tested against a real false-positive candidate:
  *"A female caregiver from Malawi ... described planting drought-resistant
  crops as her way of adapting to the strain"* -- legitimate unquoted
  paraphrase of a real client's story, and outside the narrow pattern's
  scope, so it does not fire. Also confirmed clean against a generic
  country-mention with no client attribution at all ("Kenya's 35.0% rests on
  only 90 of 271 clients scored").
- Verified against the real defect: reloading `local-cc043`'s assembled
  report (the correct way -- `from schemas.report import CoreCreditImpactReport`,
  matching `build_report.py`'s own import path; an earlier ad-hoc check using
  `analysis.schemas.report` instead produced a false negative purely from a
  module-identity mismatch between that import path and completeness.py's,
  not a pipeline bug) and re-running `find_meta_text_leaks`: **6 leaks**, all
  on `agency.insight_text` -- 4 from the new phrase entries, 2 from the new
  structural check (one per client attribution, Kenya and India).
- Both checks remain part of the existing hard gate (`raise_on_meta_text_leaks`
  / `MetaTextLeakError`) -- called from `orchestrator/assembly_node.py` and
  `report_render/build_docx.py`, unchanged call sites.

**`analysis/writer/chain.py` SYSTEM_PROMPT:** the existing drafting-commentary
paragraph already banned "ANY comment about your own drafting process" in
general terms, but its only worked examples were short bracketed insertions
("[quote placeholder removed]"). The model produced a full, fluent,
unbracketed clause instead and apparently didn't recognize it as the same
category. Added one sentence naming this incident directly by its exact text
("though the exact phrasing should be drawn from the verbatim pool rather
than summarized here without quotation") as a worked example of the
no-brackets-needed version of the same ban.

9 new regression tests added to `report_assembly/tests/test_completeness.py`
(the exact 6-insight text by phrase and structurally; both false-positive
controls; a real-citation control that must stay clean).

## CC-045: fabricated theme-name gate

CC-043's finding #2: the executive summary opened *"Client Wellbeing outcomes
anchor this year's results"* -- not one of the report's eight real theme
names (the real one, named correctly one sentence later, is "Child
Wellbeing"), likely bleed from the adjacent "Client Protection" / "Client
Satisfaction" names in the same data block.

**`report_assembly/completeness.py`:** added `EXECUTIVE_SUMMARY_THEME_NAMES`
(the fixed set of 8), `_THEME_NAME_ANCHORS` (`Wellbeing` -> "Child Wellbeing",
`Likelihood` -> "Poverty Likelihood", `Satisfaction` -> "Client Satisfaction"
-- the three anchor words distinctive enough in this report's vocabulary that
any other qualifier in front of them is necessarily a garbled or fabricated
theme reference; the other five theme names have no such confusable tail, so
aren't checked this way), `find_unknown_theme_references(report)`, and a new
hard gate `raise_on_unknown_theme_references` / `UnknownThemeNameError`,
wired into both `orchestrator/assembly_node.py` and
`report_render/build_docx.py` alongside `raise_on_meta_text_leaks`. Verified
against the real `local-cc043` executive summary text: catches "Client
Wellbeing" correctly (`'Client Wellbeing' is not a real theme name -- the
real theme is 'Child Wellbeing'`) and stays silent on the correct "Child
Wellbeing" phrasing. 5 new regression tests.

**`analysis/writer/section_prompts.py`:** `EXECUTIVE_SUMMARY_ANALYSIS`
instructions now spell out all eight exact theme names and close with the
real incident by name: *"the child-wellbeing theme is 'Child Wellbeing',
never 'Client Wellbeing' -- that name does not exist and has shipped into a
report before."*

Full suite after CC-044/045: **311 passed** (was 302 before this session's
CC-042 work; +9 from CC-044, +5 from CC-045, net of pre-existing count
drift).

## CC-046: cross-Part verbatim reuse -- audit only, no fix (per explicit instruction)

CC-043's finding #3 flagged one quote (the Zambia "wonderful services" quote)
appearing in three unrelated Parts. Instructed to report the full scope
before changing anything. Walked every `Verbatim` in the real `local-cc043`
assembled report (421 total occurrences, 362 distinct by `client_id or
quote.strip()` -- the same dedup key `translate_verbatims._dedup_key`
already uses), grouped by that key, and split into two categories:

**Cross-Part (the actual question -- no existing mechanism covers this): 28
distinct verbatims appear in more than one top-level Part.** 1 of the 28 (the
Zambia quote CC-043 already flagged, `ZMB_77828`) appears **5 times across 3
Parts** (`client_satisfaction`, `client_voices`, `gender_scorecard`); the
other 27 each appear **2 times across 2 Parts**. Total individual occurrences
among the 28: 59 -- a global uniqueness rule would remove 31 of them. This is
not "one or two quotes" -- structurally concentrated, not scattered: 27 of
the 28 involve `client_satisfaction`, and 16 of those 27 pair it with
`business_household_impact` specifically (12 pure pairs + 2 of the 3-way
cases). Read as a mechanism, not a coincidence: `client_satisfaction`'s
`nps_followup_themes` tags the same free-text "why this score" response pool
that each theme section's own qualitative pass (`qol_drivers`,
`other_improvements_qualitative`, `other_coping_qualitative`,
`protection_signals`) also draws its own representative verbatims from --
four independent selection processes with zero visibility into each other,
all pulling from thematically overlapping source text.

**Within a single Part: 26 distinct verbatims repeat inside one Part's own
theme list** -- 24 of them in `business_household_impact.qol_drivers` alone.
This number does **not** indicate a new gap: it's the same class CC-020/037
already dedupe (`_suppress_duplicate_theme_verbatims`), but that suppression
runs inside `translate_report_verbatims()`, which `local-cc043`'s saved JSON
never went through (translation was skipped -- API credits were exhausted
before it ran; see CC-047). Confirmed by reading the call chain, not
assumed. Re-auditing after a real translated run completes would be the way
to confirm this class is still fully covered; not done here since it wasn't
part of what was asked.

No code changed for this item. Awaiting direction on the global-uniqueness
rule for the cross-Part case.

## CC-047: local-cc043 resume attempt -- still blocked on API credits

Checked before attempting the resume: a minimal live call
(`build_chat_model(use_thinking=False).invoke(...)`) against the real
Anthropic key in `core_credit/.env` still returns the same error as when the
run first failed: `Your credit balance is too low to access the Anthropic
API.` Did not attempt to resume `run_orchestrator.py --run-id local-cc043`
against this -- would fail at the same `translate_report_verbatims()` call
for the same reason. Resume command, ready to run once credits are restored:
`python agent/orchestrator/run_orchestrator.py <raw_csv> --run-id
local-cc043` (same `--run-id` triggers the existing checkpoint-resume branch
in `main()`).

## CC-048: cross-Part verbatim reuse -- corrected count, root cause, fix

**Correction to CC-046's headline number.** Re-examined before building
anything, per instruction to answer two questions first. CC-046's "28
distinct verbatims, 59 occurrences" was wrong on two counts, both caught
while tracing the two answers below, not asserted from a fresh look:

1. The audit grouped by `client_id or quote.strip()` (matching
   `translate_verbatims._dedup_key`), which is correct for spotting the same
   *verbatim* reused across a theme list, but wrong for a cross-Part census:
   it silently treats two genuinely different answers from the same client
   -- their quality-of-life follow-up and their separate NPS follow-up -- as
   "the same verbatim" the moment both happen to carry a `client_id`, even
   when the two quote texts share not one word. 23 of the 28 were this.
   Re-grouped strictly by literal quote text: **7** distinct quotes actually
   repeat verbatim across more than one Part, not 28.
2. Of those 7, only **1** is something a reader can actually encounter twice.
   `report_render/section_layout.py`'s `render_client_satisfaction` renders
   only `insight_verbatims` -- `nps_followup_themes[*].representative_verbatims`
   (and the equivalent backing pools in `resilience`/`child_wellbeing`) are
   never independently shown to a reader; they exist purely as candidate
   material for `write_insight()` and (for `client_satisfaction`
   specifically) for `build_client_voices.py`. Restricting the walk to only
   the paths `render_report`'s functions actually call
   (`add_verbatims`/`add_theme_list`/`add_protection_signals`) drops the
   count from 7 to **1**: the Zambia quote CC-043 already named, rendered 3
   times (`client_satisfaction.insight_verbatims`, `client_voices.green_lights`,
   `gender_scorecard.insight_verbatims`) across 3 Parts. Every other
   apparent duplicate in the document is backing-data-only and invisible in
   the rendered `.docx`.

**Question 1 (same field, or different fields with similar answers?)** For
the pair asked about -- `business_household_impact.qol_drivers` vs.
`client_satisfaction.nps_followup_themes` -- genuinely different columns
(`IMPACT03a/b/c_resp_en` vs. `CLIENTSAT01a/b/c_resp_en`, confirmed in
`section_configs/sections/business_household_impact.py` and
`driver/build_client_satisfaction.py`) answering different survey questions.
Checked several of the specific client_ids CC-046 had flagged directly
against the raw analysis-ready CSV: the two answers are consistently
different sentences for the same client (e.g. IND_96014's QoL answer is "I
am able to save little money now."; their NPS answer is "Easy to access
loan and good behavior of the staff."). Once measured by literal quote
text rather than client_id, this pair contributes **zero** real duplicates
-- CC-046's finding here was entirely the dedup-key artifact above. This is
a non-issue, not a sourcing question.

The pair that *does* share a field, confirmed directly in code: `client_voices`
and `client_satisfaction`. `build_client_voices.py`'s own docstring says it
plainly -- "Client Satisfaction already produced exactly the raw material
needed... there's nothing left to compute... just select" -- and
`build_section()` reads `client_satisfaction.nps_followup_themes` directly,
selecting from the exact same `representative_verbatims` pool
`client_satisfaction`'s own writer draws its `insight_verbatims` citation
from. This is a real, designed, code-level dependency, not a coincidence --
which is exactly why it's the one pair that produced the one real duplicate.

**Question 2 (pool size vs. citations).** `qol_drivers`: 164 representative
verbatims cited out of 9,057 tagged (1.8%). `client_satisfaction.nps_followup_themes`
(3 bands combined): 168 cited out of 8,843 tagged (1.9%). Both pools have
enormous headroom -- uniqueness is easily achievable by exclusion for
anything drawing from either. The pool that actually mattered for the fix
turned out to be a different, much thinner one: `gender_scorecard`'s own
citation pool (`build_gender_scorecard.py::_verbatim_pool`) is built *only*
from four other sections' already-selected `insight_verbatims` (2-3 quotes
per section at most), not their full tagged pools -- in the real
`local-cc043` run it held exactly **2 candidates total** (`child_wellbeing`
contributed 1, `client_satisfaction` contributed 1; `business_household_impact`
and `resilience` contributed 0). A hard exclusion there could leave the
section with too little, or zero, grounded material on an unlucky run.

**Recommendation, implemented:** not a global uniqueness rule, not a
Parts-cap, and not touching `gender_scorecard`. Two targeted fixes, each
scoped to where the data actually supports it:

1. **`report_assembly/translate_verbatims.py`: `_suppress_duplicate_nps_verbatims`.**
   Extends the existing CC-020/037 within-theme-list dedup
   (`_suppress_duplicate_theme_verbatims`) to all three `nps_followup_themes`
   bands, exactly the gap CC-046 first noticed and this entry now explains
   (client_satisfaction never got this fix when qol_drivers and
   protection_signals did). Confirmed live: the Zambia quote was sitting in
   two different promoter-band themes at once; this removes the extra copy.
   Not a reader-visible fix by itself (this pool is never rendered directly)
   -- it stops the same verbatim from carrying double weight in the exact
   candidate pool `write_insight()` and `build_client_voices.py` both read.
2. **`analysis/synthesis/build_client_voices.py`: exclude what Client
   Satisfaction already cited.** `build_section()` now computes
   `already_cited = {dedup_key(v) for v in client_satisfaction.insight_verbatims}`
   and filters both the green and red candidate pools against it before
   `pick_diverse_verbatims` runs. Safe given Q2's headroom number -- there is
   always a real alternative. Keyed by `client_id or quote.strip()`, same as
   everywhere else in this pipeline, so a client already cited elsewhere is
   excluded even when the two quotes' texts differ entirely (deliberately
   broader than "exact text match" -- once a client has been quoted once,
   quoting them again elsewhere reads the same to a reader regardless of
   which of their sentences it is).

**Verified against the real `local-cc043` report** (reloaded via
`schemas.report.CoreCreditImpactReport`, matching `build_report.py`'s own
import path -- see CC-044's note on why that matters): applying both fixes
in sequence, `client_voices.build_section()` no longer selects the Zambia
quote (falls back to its next-ranked, still-legitimate candidate instead);
`client_satisfaction.insight_verbatims` and `gender_scorecard.insight_verbatims`
are untouched, as intended. Net result: the Zambia quote's reader-visible
footprint goes from 3 occurrences across 3 Parts to **2 occurrences across
2 Parts** (`client_satisfaction`, `gender_scorecard`) -- its 3-Part state
does not survive, and 2 is within the explicitly stated "one or two is
fine" bar. `gender_scorecard`'s remaining exposure is accepted rather than
closed: its pool is empirically too thin this run to add an exclusion
without risk, and closing it would need either deepening that pool (a
bigger change than this problem's actual size -- one real incident in the
whole report) or a same-guarantee-as-writer-choice prompt instruction
(weaker than the deterministic fixes above). Flagging this scoping call
explicitly rather than deciding it silently.

9 new tests: `test_translate_verbatims.py` (`_suppress_duplicate_nps_verbatims`,
mirroring the existing qol_drivers/protection_signals regression tests plus
a noop case) and `test_build_client_voices.py` (exclusion by client_id, and
exclusion holding even when the two quotes' text differs entirely). Full
suite: **315 passed**.

## CC-049: local-cc043 resume attempt -- still blocked on API credits

Requested: resume the run, report the full diagnostic set (executive summary
table, node failures, aggregate grounding, word cap performance), confirm
CC-044/045 don't false-positive on legitimate prose, confirm CC-048's dedup
held end to end, confirm translation produced glosses with CC-017's nested-
quote fix intact, and do a full reviewer read-through. None of it attempted
-- checked live first, same as CC-047: `build_chat_model(use_thinking=False).invoke(...)`
against the real key in `core_credit/.env` still returns `Your credit
balance is too low to access the Anthropic API.` Confirmed there is no
second key source that could be masking this (no `ANTHROPIC_API_KEY` in the
shell environment ahead of `.env`, only one `.env` defines it). Every part of
this request depends on the run actually completing -- not approximated or
partially answered from old data. Resume command unchanged and ready:
`python agent/orchestrator/run_orchestrator.py <raw_csv> --run-id
local-cc043`.

## CC-050: local-cc043 resume -- checkpointing bug found and fixed, run completed

Credits restored; resumed for real. Hit three real, previously-unknown
problems in sequence, none hypothetical -- each confirmed live before being
fixed.

**1. Checkpoint deserialization allowlist was missing 7 types.**
`graph/checkpointing.py`'s `ALLOWED_CHECKPOINT_TYPES` was written for the
section-level graphs only and never updated when the orchestrator's own
top-level graph started checkpointing section types the section-level
graphs never held (`client_profile`, `client_satisfaction`,
`poverty_likelihood` -- built via `driver/`, not `graph/` -- plus
`client_voices`, `executive_summary`, `gender_scorecard`, and
`dashboard_visuals.lookup.DashboardVisual`, which only ever exist in
orchestrator state). Writes to SQLite always succeeded (`pickle_fallback=True`
covers that silently); the gap only bites on **read**, which nothing had
ever exercised before -- this is the first run in the project's history to
resume this far into a checkpoint. Confirmed live: the real resume printed
`Blocked deserialization of schemas.client_profile.ClientProfileSection -
not in allowed_msgpack_modules` for all 7, and every one of those sections
came back as a plain `dict` instead of its real Pydantic type, crashing
`assemble_report_node` on the first attribute access
(`AttributeError: 'dict' object has no attribute 'reporting_period'`).
Fixed by adding all 7 to the allowlist; verified by reading the SAME
already-written checkpoint back afterward -- every section now deserializes
to its real class.

**2. `client_voices` and `agency` were checkpointed before this session's
fixes existed.** LangGraph's resume only re-invokes nodes that haven't
completed -- all 12 sections were already checkpointed from the run that
originally crashed on the API billing error, so a plain resume would carry
CC-048's stale, pre-fix `client_voices` and CC-044/045's stale, pre-fix
`agency` straight into assembly, silently undoing this session's work
without either gate having a chance to prove anything. Patched both via
LangGraph's supported `update_state(..., as_node=...)` API (no re-running of
the other 11, already-expensive sections):
- `client_voices`: rebuilt with the CC-048-fixed `build_client_voices.py`
  (no LLM cost -- pure selection). Before: `green_lights` included the
  Zambia quote. After: excluded, replaced by its next-ranked real
  candidate (`HND_130055820`).
- `agency`: rebuilt via `build_agency_node` (real LLM calls, current fixed
  `SYSTEM_PROMPT`/prompts). The rebuilt `insight_text` no longer mentions
  any client by name at all -- a clean, purely quantitative version -- and
  independently checked clean against `find_meta_text_leaks`.

Patching `agency` correctly triggered LangGraph to also mark
`executive_summary` (which reads a headline value from every theme section)
as needing a rebuild -- not something I forced, the graph's own dependency
edges did that.

**3. CC-045's gate caught a live, independent recurrence of the exact
"Client Wellbeing" defect it exists for.** `executive_summary`'s first
rebuild attempt produced *"Client Wellbeing outcomes anchor this year's
results... Child Wellbeing stands at 93.5%"* -- the identical mistake
CC-045's tightened prompt explicitly names as a real past incident, on a
completely fresh generation. `raise_on_unknown_theme_references` caught it
and stopped the run, exactly as designed. Retried once (LLM output is
non-deterministic, not a fixed trigger) -- the second attempt came back
clean (`find_unknown_theme_references` empty) and was patched in. **This is
a real, load-bearing finding, not a false positive**: the prompt fix alone
is not reliable against this exact confusion; the hard gate is still
necessary and just proved it live.

After all three fixes, the full resume completed clean:
`Core_Credit_Impact_Report_local-cc043.docx` rendered, QA review ran, 13
completeness issues logged (word-cap/ungrounded-percentage class, see
CC-051), 26 of 26 dashboard visuals missing as expected for a local run (no
dashboard screenshots available outside the deployed Space).

## CC-051: CC-044 structural rule -- a real false positive, found and fixed

Before reporting diagnostics, tested the CC-044 structural check (client
attribution with no nearby quote) against the three specific legitimate
cases asked for, since it is a hard gate and a false positive there fails
the whole run rather than warning:

1. Country mentioned with no quote attribution at all ("Kenya's 35.0% rests
   on only 90 of 271 clients scored") -- clean, does not fire.
2. Quote precedes the attribution in the same sentence
   ("\"Harassment...,\" said a female client in Kenya, Caregiver.") -- clean,
   does not fire (the check never cared about order, only presence).
3. Client named, described further, quoted two sentences later -- **fires.
   Confirmed false positive.** The original window only looked at the
   attribution's own sentence plus the next one; a client named in sentence
   1 and quoted in sentence 3 (a completely ordinary shape -- name, add a
   clause of color, then quote) fell outside it.

Fixed: widened `_ATTRIBUTION_WINDOW_SENTENCES` from 2 sentences (self +
next) to 3 (self + next two) in `report_assembly/completeness.py`.
Re-verified after the fix: the original 6-insight defect text still fires
(both its sentences), all three of the cases above now come back clean, and
the widened window is still narrow enough that it does not swallow the
real, load-bearing catch it exists for. Two new regression tests added to
`test_completeness.py` (delayed-quote case 3, and the order-independence of
case 2, which wasn't explicitly tested before). Full suite: **317 passed.**

## CC-052: full diagnostics, gate validation, and reviewer read-through -- local-cc043, completed

**Executive summary table (8 rows, all real):**
Financial Access 43.9% | Poverty Likelihood 12.4% | Business & Household
Impact 92.2% | Child Wellbeing 93.5% | Client Protection 75.0% | Agency
85.1% | Resilience 67.5% | Client Satisfaction NPS 68.8 [MFI Index 58.0,
2025]. n=5,827 respondents, 21 MFIs, 21 countries, Jul-Dec 2025.

**Node failures this run:** none in the final successful invocation --
every failure that occurred (checkpoint deserialization, then CC-044 on
stale `agency`, then CC-045 on the first `executive_summary` regeneration)
happened during the CC-050/051 repair work above, each one a real defect
caught and fixed before the reported-clean run.

**Aggregate grounding, all 34 WrittenText blocks:** `ungrounded_quotes` **0**.
`partial_quotes` **1** (3-insight, unchanged from CC-043 -- a real Uganda
verbatim requoted starting mid-sentence, flagged correctly, not a new
issue). `misattributed_quotes` **0**. `ungrounded_percentages` **6**, all
the known CC-008 coverage/complement class (88%, 33% in poverty_likelihood
x2; 7.6%, 9.8% in client_protection). `orphan_markers` **0**.
`banned_punctuation` **0**.

**Word cap:** 8 of 34 over cap, 2 of those >20% over -- 5-insight
(190w/150, +26.7%) and 8-insight (193w/150, +28.7%), both previously
flagged in CC-043 and still not resolved by CC-042's trim.

**CC-044/045 gate behavior -- explicit answer to "did either fire, and on
what":** Yes, both fired during this session, and both were true
positives, not false alarms -- see CC-050. CC-044 stopped stale `agency`
prose containing the exact original 6-insight defect. CC-045 stopped a
*fresh, independently-generated* recurrence of the "Client Wellbeing"
mistake. Neither fired on the final, reported-clean report
(`find_meta_text_leaks` and `find_unknown_theme_references` both empty).
The one false positive found (CC-044's structural rule, case 3 above) was
found through the requested legitimate-case testing, not through a real
run, and is now fixed -- see CC-051.

**CC-048 dedup, confirmed end to end on the real, completed report:**
- Zambia quote's reader-visible footprint: **2 occurrences across 2 Parts**
  (`client_satisfaction.insight_verbatims`, `gender_scorecard.insight_verbatims`)
  -- down from 3 across 3 (`client_satisfaction`, `client_voices`,
  `gender_scorecard`). `client_voices.green_lights` no longer contains it.
- Within-list dedup, confirmed separately: `client_satisfaction.nps_followup_themes`
  held the Zambia quote in 2 themes before CC-048; the final assembled
  report holds it in exactly **1** (kept on "Good service / friendly,
  respectful staff treatment," frequency=2071, the higher-ranked theme) --
  `_suppress_duplicate_nps_verbatims` ran as part of this real assembly, not
  just in isolated tests. Confirms the earlier CC-046 diagnosis: the 26
  same-Part repeats found there really were an artifact of that report
  never having reached `translate_report_verbatims()`, not a separate bug.

**Translation, confirmed:** 395 total verbatims in the report; 227
non-English (`.language` set, != "English"); **0** still untranslated; **0**
non-English verbatims missing an `english_gloss`. CC-017 doubled-opening-
quote check (`""X" (original ...)."`, the defect from the earlier Space
report) scanned across all 34 blocks: **0 occurrences** -- not present in
this run.

### Reviewer read-through -- full document, cover to cover

Cross-checked against the pipeline's own automated QA pass
(`qa_notes_local-cc043.md`) rather than working blind -- most of what
follows was independently found by both; where it wasn't, that's noted.

**1. Formulaic closing hedge, the report's most visible defect.** "Priority
area(s) to investigate" (or a one-word variant) closes **10 of 34** blocks
-- 7 of the 9 `-insight` blocks (only 4-insight is exempt), plus 5.4,
gender-scorecard's analysis_text, and gender-insight. Read cover to cover,
nearly every section reaches for the identical hedge regardless of what it
actually found, which flattens sections that have genuinely different
findings into the same generic register. The QA pass caught this
independently and named it first too.

**2. The four insights CC-042 trimmed to one verbatim did not shrink
evenly -- three of four effectively lost their client voice.** Checked
`insight_verbatims` directly, not just the rendered prose:
- **3-insight**: 1 real direct quote, woven inline -- reads fine, though it
  still carries the same `partial_quotes` flag CC-043 already found (quoted
  starting mid-sentence) and the quoted client's own typo ("parment" for,
  almost certainly, "permanent") survives verbatim, correctly per SYSTEM_PROMPT,
  but reads like a production typo to anyone who doesn't know that's the rule.
- **5-insight**: `insight_verbatims` is **empty**, and the prose has *no*
  quote or even a named individual -- only "a country where clients have
  described experiences of disrespectful treatment," a paraphrase with
  nobody attached. Of the four, this is the one that reads genuinely thin.
- **7-insight**: `insight_verbatims` is **empty** too. The prose names a
  client ("A female caregiver from Malawi...") but never quotes her --
  "described planting drought-resistant crops" is a paraphrase, not her own
  words in quotation marks. Not a CC-044 violation (paraphrase without
  attribution-then-nothing is legitimate, and this is exactly the
  false-positive-control case CC-044's own tests use), but it means a
  reader gets a name and no voice.
- **8-insight**: the only one of the four with a populated
  `insight_verbatims` (1 entry) *and* a direct quote in the prose --
  reads the fullest of the four, but is also the one carrying the
  Zambia repetition (see next point).
- Because `report_render.add_verbatims()` renders nothing at all for an
  empty list (no placeholder text, unlike `client_voices`'s explicit
  "[ No verbatims available ]" fallback), 3-insight, 5-insight, and
  7-insight get **no separate quote callout box** in the rendered .docx --
  whatever citation exists is inline in the paragraph or, for 5-insight,
  absent entirely. 8-insight alone gets both an inline mention and a
  distinct italicized callout underneath. The four "one-verbatim" insights
  read structurally inconsistent with each other, not uniformly thin.

**3. The Zambia quote's remaining repetition is still noticeable to a
reader, even though it's within the accepted tolerance.** Read straight
through, Part 8 (`client_satisfaction`) and Part 9 (`gender_scorecard`) --
one section apart -- both quote the identical sentence from the same
client. Also independently caught by the QA pass, which additionally
flagged that the two sections introduce it differently ("a female
caregiver client from Zambia described her experience by saying..." vs.
"A female client from ZMB, a caregiver, valued that...") -- and that the
second one uses the raw ISO code "ZMB" where every other quote in the
report spells the country out in full (Uganda, Senegal, Malawi, Kenya).

**4. Internal drafting artifacts leaked into reader-facing prose** (QA
pass, confirmed): `resilience.vf_reduced_shock_severity_analysis` says
"...a much smaller and conditional base than the shock-incidence figure in
7.2..." -- "7.2" is a section-number reference with nothing to anchor it in
final layout. `client_profile.analysis_text` similarly says "...reported in
Part 2." Both read like drafting notes rather than finished copy.

**5. The executive summary states the Child Wellbeing figure without its
scope** (QA pass, confirmed, and worth weighing above the pure style
notes -- this one can genuinely mislead). Every other mention of 93.5%
explicitly says "among caregivers" (4.1's analysis and insight both do).
`executive_summary.analysis_text` drops the qualifier: "Child Wellbeing is
strong at 93.5%," sitting next to six other themes' genuinely
all-client figures, with nothing to signal it's a narrower base.

**6. A confirmed bug in the QA reviewer itself, not the report.** The QA
notes flag the executive summary's position as wrong ("appears
second-to-last... rather than at the front"). Checked against
`report_render/section_layout.py::render_report` directly: the executive
summary actually renders **second**, right after client_profile, correctly
near the front. The QA reviewer's own input
(`report_render/qa_review.py::_full_report_text`, built via
`report_assembly.completeness._walk`) walks the report in **Pydantic field
declaration order**, not true render order -- `executive_summary` is
declared later in `schemas/report.py`'s field list than it renders, so the
QA prompt's own claim of "in document order" is false for this one field.
Not fixed (out of this round's scope), but worth flagging: this specific
false finding will recur on every future run until `qa_review.py` is given
text in real render order.

**7. Smaller, real, and lower-severity** (QA pass, both confirmed against
the actual text): `client_protection.insight_text`'s "our own number on the
benchmark's stricter box definition" parenthetical sits ambiguously between
two percentages, reading as though it modifies the first (91.6%) when it's
meant to introduce the second (72.7%). `agency.insight_text` (the CC-050
rebuild) has a number-agreement slip: "...as areas that may be a priority
area to investigate further" ("areas" / "a priority area").

Full test suite after CC-051's fix: **317 passed.**

## CC-053: checkpoint staleness audit -- item 1

Asked whether any of the 9 sections still checkpointed from before CC-044/
045/048 (i.e. everything except `agency`, `client_voices`, and
`executive_summary`) would render differently under current code, mapped
per requirement:

- **CC-044** (phrase list + structural check, `chain.py` SYSTEM_PROMPT +
  `completeness.py`): applies uniformly to every `WrittenText` in every
  section via a comprehensive, always-fresh-run post-hoc gate
  (`find_meta_text_leaks`), not a one-time writer-side check. Re-ran it
  explicitly against each of the 9 sections individually: **all clean**.
  Staleness doesn't matter here because compliance is verified at assembly
  time regardless of when a section's prose was written.
- **CC-045** (fabricated theme name): scoped entirely to
  `executive_summary.analysis_text`, which was already regenerated. Zero
  relevance to the other 9.
- **CC-048**: two parts. `build_client_voices.py`'s exclusion fix only
  affects `client_voices` (already regenerated) -- zero relevance to the 9.
  `_suppress_duplicate_nps_verbatims` (the within-list dedup) *does* apply
  to one of the 9 -- `client_satisfaction.nps_followup_themes` -- but it's a
  post-hoc mutation applied fresh on every assembly, not a writer-time fix,
  so it already ran correctly against that stale section's data (confirmed
  in CC-052: 2 occurrences of the Zambia quote in that pool became 1).

**Conclusion at the time of asking: no.** None of the 9 would render
differently in a way tied to these three requirements specifically --
each fix is either a comprehensive post-hoc gate (already verified clean),
a post-hoc mutation (already verified applied), or scoped to a section that
wasn't stale. The report was representative with respect to CC-044/045/048
before any of the work below started. (Superseded in practice by CC-055/056
below, which regenerated 8 of the 9 anyway for unrelated reasons -- see the
final status at the end of this entry.)

## CC-054: CC-044 false negative on 7-insight -- item 2

**Did widening the window (CC-051) cause 7-insight to stop firing? No.**
Tested directly: `_CLIENT_ATTRIBUTION_RE` never matches "A female caregiver
from Malawi ... described planting drought-resistant crops" at all, at any
window size -- the exclusion happens at the regex stage (requires "client",
not "caregiver"; "in", not "from"), before any window is considered. This
sentence was in fact the *original* false-positive control case used to
scope the regex when CC-044 was designed -- it was always meant to be
excluded, not a side effect of CC-051.

**Is this the same defect as the 6-insight case? No, and that distinction
matters.** The 6-insight defect was the model narrating that it should have
quoted something instead of quoting it -- a meta-commentary failure.
7-insight's behavior -- naming a client, then paraphrasing what she did
without quotation marks -- is explicitly sanctioned by SYSTEM_PROMPT itself:
*"If you want to make a general point without a specific client's exact
words, write it as your own analytical sentence with no quotation marks at
all, not as an invented quote."* Broadening the structural rule to catch
"named individual, no quote, regardless of noun" would put the gate in
direct conflict with that explicit, deliberate permission -- it would start
failing builds over prose the writer was told is acceptable.

**New live evidence, found during CC-055/056's reruns below, sharpens this
further.** Regenerating `resilience.insight_text` produced *"A male client
in Rwanda, Climate-shock-affected, reported selling land as a coping
route..."* -- using "client" + "in" (the rule's own intended matching
scope, not the excluded "caregiver"/"from" pattern) for what is clearly
legitimate, contentful, sanctioned paraphrase. The gate did not fire on it
(no fresh regeneration happened to retrigger a check at that exact moment
before the report moved on), but it demonstrates the false-positive risk
isn't confined to the noun choice already excluded -- it's inherent to the
"named individual + no nearby quote" signal itself, regardless of exact
wording. In the same batch, `agency.insight_text` separately produced *"A
female client in Guatemala described this directly"* -- content-free,
dangling, no antecedent for "this" -- which the live gate **did** correctly
catch and stop the build on. That one reads as a genuine defect (an empty
attribution), just a different shape than the original narration case, not
a false positive.

**Verdict, as asked: the rule cannot catch both without a policy change.**
Making it also catch 7-insight/Rwanda-style unquoted paraphrase requires
either (a) broadening the pattern to any named-individual attribution
regardless of noun, which reintroduces false positives on sanctioned
paraphrase (confirmed live, twice, in this session alone), or (b) changing
SYSTEM_PROMPT itself to require a real quote whenever a client is named,
removing the paraphrase option entirely -- a real policy decision, not a
bug fix. Not implemented either way; reporting for a decision as asked.

## CC-055: the templated closer -- item 3, widened and verified live

`chain.py` SYSTEM_PROMPT's forward-looking-sentence rule prescribed exactly
two forms and the writer had collapsed to reaching for one of them ("may be
a priority area to investigate") in 10 of 34 blocks. Widened to three
sanctioned shapes, deliberately different grammatically rather than
synonyms of the same construction: (1) "could be explored as actions to
support these outcomes" (infinitive-purpose clause, unchanged), (2) "may be
a priority area to investigate" (predicate-nominal, unchanged), (3) "is
worth watching" (adjectival predicate, new -- chosen partly because it had
already appeared once, spontaneously, in the original run's 6-insight:
"...a gap worth watching alongside..."). Instructed to pick whichever fits
and not default to the same one out of habit, naming the repetition problem
explicitly as something a reviewer already flagged.

**Verified with a real rerun, not just inline reasoning.** Rebuilt all 8
sections that had used the old phrase (everything except `client_profile`,
which never used it). Result, read against actual output rather than a
strict regex (several outputs used natural variants like "a pattern worth
watching alongside" or "could be explored as an action to support X" --
still genuinely one of the three shapes, just not the literal string):
shape 3 ("worth watching") used most often this pass, shape 1 used twice,
and several blocks closed without any of the three at all, ending cleanly
on the finding itself. This is a real, verified shift from monolithic
single-phrase repetition to a genuinely mixed set -- not eliminated
(the automated QA pass on the rerun still names "worth watching" and
"priority area to investigate" as repeating enough to notice), but no
longer the same phrase in 10 of 34 blocks.

## CC-056: CC-004 caregiver-scope fix + gate (item 4a), ZMB source diagnosis (item 4b, report only)

**Fix:** `EXECUTIVE_SUMMARY_ANALYSIS` in `section_prompts.py` now explicitly
requires the caregiver scope in the same sentence as any Child Wellbeing
figure, naming the real incident by example, matching the pattern already
used for CC-045's theme-name fix.

**Gate: feasible, and implemented.** `find_missing_caregiver_scope` /
`raise_on_missing_caregiver_scope` in `completeness.py`: any sentence in
`executive_summary.analysis_text` naming "Child Wellbeing" must also
contain "caregiver" in that same sentence. Feasible specifically because
this is narrow -- one known theme (the only one of the eight scored on a
subgroup rather than the whole base), one known subsection, one known
qualifier word -- not a general CC-004 gate (any subgroup figure, anywhere
in the report has no comparable check, and none is proposed here). Wired
into both `assembly_node.py` and `build_docx.py` alongside the existing
executive-summary gates. 6 new tests, including the real incident text and
a clean-pass control. Verified live: the rerun executive_summary (below)
passed this gate on its first attempt, correctly writing "Child Wellbeing
is strong at 93.5% among caregivers."

**ZMB source, diagnosed, not fixed (as asked -- "find where the
inconsistency enters").** Root cause: `chain.py::_format_verbatim_profile`
renders `v.country` directly (`v.country or "unknown country"`) with no
translation from the raw ISO code stored on every `Verbatim` -- the
numbered pool shown to every writer call literally reads "... -- Female,
age 44, ZMB, ...". Nothing in SYSTEM_PROMPT instructs expanding this to a
full country name; most writer calls do it anyway from general knowledge,
some don't. **Reproduced live, twice, with completely different clients**:
in the original run, `gender-insight` wrote "A female client from ZMB" for
the same quote that `client_satisfaction.insight_text` correctly called
"a female caregiver client from Zambia." In this session's rerun, with a
*different* pair of clients entirely, the exact same split recurred:
`gender-insight` wrote "One female client from ZMB" and "A female client
from SEN" for two quotes that `business_household_impact.insight_text` and
`child_wellbeing.insight_text` respectively rendered correctly as "Zambia"
and "Senegal" for the identical clients. Two independent occurrences,
same specific writer call (`GENDER_INSIGHT` / `write_insight` for
`gender_scorecard`) both times, every other section's insight call getting
it right both times -- strong, reproducible evidence the gap is real and
narrows specifically to that one prompt/call, not random noise. Fix would
be a one-line SYSTEM_PROMPT addition ("the country field in the pool is a
raw code -- always write the full name in prose"); not made, per the
request to report only.

## CC-057: second checkpointing allowlist gap, full rerun, final status

Hit one more instance of CC-050's bug while patching sections for CC-055/
056: `schemas.report.CoreCreditImpactReport` itself -- only ever
deserialized once a run's `state["report"]` is read back, which nothing had
exercised before either. Added to `ALLOWED_CHECKPOINT_TYPES`.

**Full rerun sequence for CC-055/056's verification:** rebuilt
`financial_access`, `poverty_likelihood`, `business_household_impact`,
`client_protection`, `agency`, `resilience`, `client_satisfaction`,
`gender_scorecard`, `executive_summary` (9 of 12 -- everything except
`client_profile` and the already-current `client_voices`). Two fresh
CC-044 catches surfaced mid-rebuild (see CC-054's Guatemala/Rwanda
evidence) and were retried once each, both clean on the first retry.
Reassembled, translated, rendered, QA-reviewed. Full report:
`Core_Credit_Impact_Report_local-cc043.docx`.

**Status after this round -- CC-053's answer no longer describes the
report.** 11 of 12 sections are now current-code (only `client_profile`
predates this session's fixes, and it never used any of the affected
phrasing or structures). This is by design, not drift: CC-055/056 required
real regeneration to verify, and doing that necessarily touched every
section using the old closer phrase.

**CC-044/045/053(caregiver-scope) gates:** all clean on the final report.

**CC-048, re-checked on the new content:** the *original* Zambia quote is
now cited nowhere (client_satisfaction's insight lost its verbatim entirely
this pass -- a citation choice, not a gate effect). But the underlying
mechanism CC-048 always flagged as accepted residual risk fired anyway,
just against different sections: `gender_scorecard.insight_text` cited two
verbatims this round, and **both** turned out to already be
`business_household_impact.insight_text`'s and `child_wellbeing.insight_text`'s
own cited quotes respectively -- because `gender_scorecard`'s pool is
built directly from those sections' own `insight_verbatims` (see CC-046).
This is exactly the residual exposure flagged and deliberately left open in
CC-048 ("gender_scorecard's remaining exposure is accepted rather than
closed... its pool is empirically too thin to add an exclusion without
risk") -- now observed recurring against different source sections, not
just `client_satisfaction`. Two duplicated quotes this round (2 occurrences
each, 2 Parts each) -- still within the previously-stated "one or two is
fine" tolerance, but confirms this will keep happening on future runs
until `gender_scorecard`'s pool is addressed directly. Not fixed this
round -- flagged for a decision, not implemented unprompted.

Also newly visible this round, inside a single Part (not cross-Part, so
outside CC-048's original scope): `client_protection.insight_text` and
`client_protection.protection_signals`'s own rendered theme list both cite
the identical Zambia complaint verbatim ("Vision Fund female workers lack
good customer service and respect") -- the CC-020 dedup covers duplication
*within* `protection_signals`' own theme list, not between that list and
`insight_verbatims`, a different field entirely. Reported, not fixed --
out of scope for what was asked this round.

**Translation and CC-017, re-confirmed on the final content:** 397 total
verbatims, 231 non-English, 0 missing a gloss, 0 doubled-quote occurrences.

**QA pass on the final rerun, independently cross-checked:** caught the
verbatim reuse above on its own, plus a genuine internal contradiction in
`client_protection.financial_worry_decreased_analysis` (states "less
common" for a figure that is numerically higher) worth a look separately
from anything asked this round.

Full test suite: **322 passed.**

## CC-058: CC-044 redesigned around dangling attribution, downgraded to a warning

Direct decision from CC-054's report: key the structural rule on the actual
defect shape (a reporting verb with nothing after it) rather than "no
quote nearby," and downgrade it from a hard gate to a soft completeness
issue.

**`report_assembly/completeness.py`:** `find_meta_text_leaks` is phrase-list
only again (structural check removed from it). New, separate
`find_dangling_attributions`: within a sentence that names a client by
country (`_CLIENT_ATTRIBUTION_RE`, unchanged), flags it only if that same
sentence's reporting verb has nothing but a bare demonstrative pronoun
("this"/"that"/"it") as its object, with at most two trailing words before
the sentence ends. No multi-sentence window anymore -- the signal is a
single sentence's own grammar, which also removes the CC-051 window-size
question entirely (there's nothing left to tune). Wired into
`completeness_report()`, not into `raise_on_meta_text_leaks` -- appears
in the same list as `partial_quotes`/`ungrounded_percentages`/etc., not as
an exception.

**Tested against exactly what was asked:**
- Guatemala ("A female client in Guatemala described this directly.") --
  **flags**. No content at all past the reporting verb.
- Rwanda ("...reported selling land as a coping route...") -- **clean**.
  Gerund-headed real content, not a bare pronoun.
- The original six-leak text -- **the build still fails on it**, via the
  phrase list alone (4 separate hits on the second sentence), independent
  of whether the new structural check also flags the first sentence on its
  own (it doesn't, by design -- "this kind of standing shift directly" has
  5 words between the pronoun and the sentence end, past the 2-word cap;
  widening the cap to force that specific catch was considered and
  rejected as overfit to one example, since the overall requirement --
  the six-leak text must still fail -- was already met).

All prior false-positive controls re-verified clean under the new design
(real citation, generic country mention, delayed quote two sentences
later, quote preceding the attribution, unquoted caregiver/from
paraphrase) plus two new ones for the redesign itself. `MetaTextLeakError`
is phrase-list-only now; nothing raises on a dangling attribution alone.
9 tests changed/added in `test_completeness.py`. Full suite: 337 passed
(see CC-059/060 below for the rest of that count).

## CC-059: the two duplicates, fixed

**client_protection: insight_verbatims vs. its own protection_signals
list.** New `_suppress_insight_verbatims_already_in_protection_signals` in
`translate_verbatims.py`, called from `translate_report_verbatims()` right
after the existing within-list dedup. Removes the overlap from
`insight_verbatims`, not from `protection_signals` -- the theme list
renders first (`add_protection_signals` before the Insight's own callout,
same Part) and is the section's established bank; the insight callout is
what's duplicating it. Confirmed against the real incident text ("Vision
Fund female workers lack good customer service and respect") and applied
directly to the delivered report (see CC-060) since it needed no new LLM
call. 3 new tests in `test_translate_verbatims.py`.

**gender_scorecard: pool sharing against a different section every run.**
The old `_verbatim_pool` in `build_gender_scorecard.py` drew *only* from
each of its four source sections' own `insight_verbatims` (1-3 items each)
-- meaning every candidate was, by construction, already spotlighted by
its own source section, so "prefer unused" was previously meaningless (the
whole pool was always "used"). Rebuilt to pool from each source's *deeper*
qualitative-tagging pass instead (`qol_drivers`, `other_coping_qualitative`,
`other_improvements_qualitative`, `nps_followup_themes` -- the full
100+-candidate sets each source's own insight_verbatims was itself drawn
from), split into `unused` (not in any of the four sources' own
insight_verbatims) and `reused` (already there). Uses `unused` whenever
it's non-empty; falls back to `reused` only if `unused` comes back
completely empty -- literal "prefer unused, reuse only when the pool is
exhausted." New test file `analysis/synthesis/tests/test_build_gender_scorecard.py`,
6 tests, including the exhausted-pool fallback case and a same-key dedup
check across the four sources. This fix changes *pool composition for a
future write_insight() call* -- it cannot retroactively change what's
already been written on the delivered report (see CC-060 on what that
means for this round).

**ZMB / raw ISO code.** `chain.py::_format_verbatim_profile` now expands
`v.country` through `benchmark_module.mapping.COUNTRY_CODE_TO_NAME` --
the same canonical mapping `grounding.py`'s own country cross-check already
uses, so there's one source of truth rather than a second one invented
here. Falls back to the raw code if a country isn't in the mapping (it
covers 20; Montenegro/"MNE" is not among them, a pre-existing gap in the
shared mapping, not introduced here -- flagged, not fixed, since it's
outside what was asked and could affect other callers). Updated
`test_chain_formatting.py`'s existing profile test (it had been asserting
the raw "ECU" code appeared, which is now the exact thing this fix
removes) and added two new tests: the real ZMB incident, and the
unmapped-code fallback. Like the gender_scorecard fix, this changes future
writer *input* -- it doesn't retroactively rewrite already-generated
prose.

## CC-060: verification pass -- no full pipeline rerun

**Delivered report vs. the CC-058 gate change:** loaded the already-
assembled `core_credit_impact_report_local-cc043.json` (no new section
builds, no LLM calls) and ran all three hard gates directly.
`raise_on_meta_text_leaks`, `raise_on_unknown_theme_references`,
`raise_on_missing_caregiver_scope` all pass with no exception.
`find_dangling_attributions` (informational, not raised) returns empty --
the delivered content has no dangling attributions to flag either way.
**Confirmed: the delivered report still assembles cleanly under the
CC-058 change.**

**client_protection dedup applied to the delivered artifact, no LLM
needed.** Since this fix is a pure post-hoc mutation on already-written
content (not a future-write-time change like the other two), it was
applied directly: removed the one duplicate from
`client_protection.insight_verbatims` (which held only that one entry, so
its callout box is now empty -- the quote still appears once, in
`protection_signals`' own theme list, and inline within `insight_text`'s
own prose, both untouched). Report JSON re-saved, `.docx` re-rendered
locally via `report_render.section_layout.render_report` directly (no
LangGraph, no checkpoint touched, no new LLM call) -- the delivered
`Core_Credit_Impact_Report_local-cc043.docx` now reflects this fix.

**gender_scorecard's duplicate and the ZMB codes are NOT yet reflected in
the delivered docx.** Both fixes change what a *future* `write_insight()`
call would produce -- neither can retroactively alter prose already
written by the prior (un-fixed) call without a new LLM generation, which
this round explicitly excluded ("do not rerun the whole pipeline"). The
delivered `gender-insight` still cites the two duplicated verbatims and
still says "ZMB"/"SEN". Both fixes are code-complete and unit-tested,
ready to take effect the next time `gender_scorecard` is actually
rebuilt.

### Read-through: the 9 sections touched this round (8 rebuilt for phrase variety + executive_summary)

Read `financial_access`, `poverty_likelihood`, `business_household_impact`,
`client_protection`, `agency`, `resilience`, `client_satisfaction`,
`gender_scorecard`, and `executive_summary` end to end against their final
CC-057 text.

**Direct answer to "does it read better, or just spread three stock
phrases across ten blocks": mostly the latter, so far.** Counted every
occurrence of the three sanctioned forms across just these 9 sections'
own subsections (not the full 34-block report): shape 1 ("could be
explored as actions to support...") 3 times, shape 2 ("priority area to
investigate") 4 times, shape 3 ("worth watching") **at least 14 times** --
appearing not only as insight-closers but scattered mid-sentence through
ordinary `.1`/`.2`/`.3`-level analysis paragraphs too (5.1, 5.3, 5.4, 5.5,
6.1, 6.3, 7.1, 7.3), something the old single-phrase version never did.
The fix worked exactly as specified -- three genuinely distinct shapes,
real variety, no more single-phrase monoculture -- but the model has
now converged on "worth watching" as a new dominant default, used loosely
enough (often trailing an ordinary factual sentence with no real stakes
attached) that the underlying problem -- a formulaic hedge reached for by
reflex rather than by the point actually calling for it -- is still
substantially present. Two sections (`3-insight`, `8-insight`) now stack
*two* of the three forms back to back in the same paragraph, which reads
worse than the original single-phrase repetition did, not better --
technically "varied," but redundant within one block. The automated QA
pass independently flagged the same pattern.

**Other things worth surfacing from this specific read, beyond phrase
variety:**
- `client_protection.financial_worry_decreased_analysis` (5.1) still
  contains the real internal contradiction the QA pass flagged in CC-057
  ("slightly less common ... at 49.1% versus 46.1%" -- 49.1 is the larger
  number) -- unrelated to anything asked this round, but a genuine factual
  error sitting in the delivered docx.
- `client_protection.insight_text` (5-insight) ends cleanly on its real
  quote with no forward-looking hedge tacked on at all -- one of the few
  blocks that reads as a considered choice rather than a reflex, worth
  noting as what "good" looks like here.
- `agency.insight_text` (6-insight, the CC-050 rebuild) and
  `resilience.insight_text` (7-insight, the CC-054 Rwanda-case rebuild)
  both read coherently and cleanly under the new dangling-attribution
  rule -- 7-insight's unquoted paraphrase ("described planting drought-
  resistant crops like cassava and nandolo") is specific and grounded,
  exactly the shape the redesigned rule is supposed to leave alone.
- `gender_scorecard.insight_text` still visibly carries both defects this
  round targeted -- the two duplicated quotes and the "ZMB"/"SEN" codes --
  since fixing either required regeneration, which this round didn't do
  (see above).

Full test suite: **337 passed.**

## CC-061: stop requiring a closer -- SYSTEM_PROMPT rewritten, not just re-phrased

CC-058's three-shape rotation didn't work because the actual problem was never
phrase variety -- it was that the rule made a hedged forward-looking sentence
mandatory, so every block produced one and "worth watching" became the new
reflex. Rewrote `chain.py` SYSTEM_PROMPT: most subsections are now told
explicitly they're complete once they've stated the finding, and a
forward-looking sentence is the exception, added only when the data raises a
genuine next step -- not a reflex closer. The three sanctioned shapes still
apply, but only *if* a forward-looking sentence is used at all. Named the
prior failed fix directly in the prompt as a worked example of the failure
mode ("a rewrite meant to fix one over-used closing phrase produced three
alternatives instead, and the model used one in nearly every block anyway").

## CC-062: comparative-claim audit -- one-off, not systemic; a check is feasible, not built

**Confirmed no verification exists at all.** `grounding.py`'s checks
(`check_grounding`, `check_quote_grounding`, `check_partial_quotes`,
`check_profile_grounding`, `check_orphan_markers`, `check_banned_punctuation`)
verify a cited number is real and a quote is genuine -- none of them check
that a comparative word ("more," "less," "higher," "lower," "trails,"
"ahead of") correctly describes the direction between the two numbers it's
attached to. Structurally, every comparative claim in every run has always
been unverified.

**In practice: manually checked every comparative construction across two
full, independent 34-block reports (local-cc043's CC-057 content and this
round's local-cc061) -- 60+ claims total. Found exactly one error, the
original 5.1 case** (49.1% called "less common" than 46.1%, which is
backwards). Every other instance checked out, including several with the
same structural shape as the error (a subgroup pair stated, then a
comparative word applied). local-cc061's own regeneration of the identical
5.1 comparison came back correctly hedged this time ("close to 46.1%... not
notably lower"), consistent with this being a one-off generation slip, not
a systematic direction confusion the model makes reliably.

**Feasibility, not built:** achievable, but not cheap the way CC-044/045/053/
058's checks were. Those were single-sentence regex structural matches.
A comparative-direction check needs to (1) find a comparative word, (2)
correctly identify which of two nearby numbers is its subject and which is
its referent -- genuinely variable across the real shapes seen this
session ("X, COMPARATIVE than Y"; "COMPARATIVE at X versus Y"; ranked
"followed by" lists with no comparative word at all; comparisons split
across a whole sentence with the comparative word in the middle), and (3)
classify the word's implied direction (a maintained ascending/descending
word list, similar upkeep burden to CC001_BANNED_TERMS). A narrow version
covering the 2-3 most common explicit patterns is roughly the same scope as
the existing soft checks; full coverage of every shape actually observed
this session would cost meaningfully more and still not be complete, since
comparative English isn't a closed set of patterns. Not built, per
instruction.

## CC-063: full clean run, current code, new run_id (local-cc061)

Ran `run_orchestrator.py` fresh (not a resume) under `--run-id local-cc061`
-- all 12 sections built from scratch under CC-058/059/061's code, real
translation, real QA review. Completed in 14.6 min.

**Executive summary table (8 rows, unchanged from prior runs' underlying
data, as expected -- no metric computation changed this session):**
Financial Access 43.9% | Poverty Likelihood 12.4% | Business & Household
Impact 92.2% | Child Wellbeing 93.5% (among caregivers, correctly scoped) |
Client Protection 75.0% | Agency 85.1% | Resilience 67.5% | Client
Satisfaction NPS 68.8 [MFI Index 58.0, 2025]. n=5,827, 21 MFIs, 21
countries.

**Gates, all confirmed clean:** `raise_on_meta_text_leaks`,
`raise_on_unknown_theme_references`, `raise_on_missing_caregiver_scope` --
no exceptions. `find_dangling_attributions` (soft): empty.

**Grounding:** `ungrounded_quotes` 0, `partial_quotes` 1 (8.2, a real
verbatim fragment -- for a reviewer to check, not a fabrication),
`misattributed_quotes` 0, `ungrounded_percentages` 7 (all the known CC-008
coverage/complement class), `orphan_markers` 0, `banned_punctuation` 0.

**Word cap:** 9 of 34 over cap, 2 severely (5-insight +24.7%, 7-insight
+26.0%) -- persistent, pre-existing, not touched this round.

### Item 1's verification, with real numbers

Counted every block's closing content across all 34 blocks (not a sample):
**13 total forward-looking-sentence instances, across 12 of 34 blocks** --
down from 14+ instances of "worth watching" *alone* found in the CC-057
read-through, and now concentrated almost entirely in `-insight` blocks (7
of 9) rather than bleeding into ordinary `.1`/`.2`/`.3` analysis paragraphs
the way it had. **22 of 34 blocks now end on findings alone, with no
closer at all** -- including `4-insight` and `8.2`, which end directly on
a real client quote with nothing appended.

By form: shape 2 ("priority area to investigate," literal) -- 6 instances
(2-insight, 3-insight, 5-insight, 6-insight, 7-insight, 8-insight). Shape
3 ("worth watching" and lexical variants "worth reviewing"/"worth
flagging"/"worth reading") -- 7 instances (1-insight, 3-insight, 5.2, 5.4,
executive-summary, gender-scorecard, gender-insight). Shape 1 ("could be
explored as actions to support these outcomes") -- **zero** instances this
run.

**Residual issue, smaller than before but not gone:** `3-insight` still
stacks two closers back to back (shape 3 then shape 2) -- one block out of
34, versus the "double-stacking" pattern that had shown up in multiple
blocks in the CC-057 read. The automated QA pass independently flagged the
same residual repetition (still names "priority area to investigate" and
"worth watching"/"flagging"/"reviewing" as recurring, though the QA
reviewer's own framing undercounts slightly by treating each variant as a
separate item rather than one family).

### Reviewer read-through -- what's actually new or wrong

**1. CC-017's doubled-quote defect is back -- 2 occurrences, both in
`client_satisfaction`.** `8.2`: `cited ""EXCELLENT SERVICE...` (Spanish
gloss substitution). `8-insight`: `saying ""GOOD TREATMENT AND EXCELLENT
SERVICE...`. Root cause, confirmed by reading both: the writer wrapped the
*original non-English text* in its own quote marks before the translation
substitution ran, and `_apply_inline_translations`'s replacement (itself
quote-wrapped, `"<gloss>" (original ...)`.`) landed inside the writer's
own quotes, doubling the opening mark. This is not a new regression --
it's a real edge case CC-017's fix never actually covered (longest-match-
first and re-entrance protection don't address a writer-supplied quote
mark colliding with the substitution's own), it just hadn't recurred in
the last several runs by chance (depends on whether the writer happens to
wrap the raw non-English quote in its own marks, which is inconsistent).
Not fixed this round -- flagging per the read-through request, not
instructed to fix.

**2. Two new cross-Part duplicate verbatims, two different mechanisms,
neither the same one CC-059 closed:**
- `gender_scorecard.insight_verbatims[0]` duplicates
  `business_household_impact.qol_drivers.themes[2].representative_verbatims[1]`
  (the Zambia "EMPOWERED MY BUSINESS" quote). **This is a real gap in
  CC-059's own fix**: the "already cited" exclusion set gender_scorecard's
  pool checks against was built only from each source's *insight_verbatims*
  (1-3 items), not from `qol_drivers` itself -- but `business_household_impact`
  is the one source among the four that *also* renders its deeper
  qualitative pool directly to a reader (`add_theme_list`, top 5 themes x
  top 2 verbatims each), unlike resilience/child_wellbeing/client_satisfaction,
  which only expose their deeper pools through their own `insight_verbatims`.
  CC-059's exclusion set never accounted for that asymmetry.
- `client_protection`'s own `protection_signals` theme list duplicates
  `client_voices.red_flags[0]` (the "sarcastic... bad customer service"
  Zambia complaint). This is a *third*, previously unseen pathway --
  `client_voices` pools from `client_satisfaction.nps_followup_themes`
  only (CC-048's scope); nothing connects it to `client_protection` at
  all, so this duplication isn't something either CC-048 or CC-059
  could have caught, by design. Not investigated further this round --
  reported, not fixed, per the read-through request.
- No within-Part duplicates this run (CC-059's `client_protection` fix,
  re-verified: 0 occurrences of an insight_verbatim repeating its own
  protection_signals entry).

**3. Comparative-claim audit, this run's contribution to CC-062: zero new
errors found** across all 34 blocks (see CC-062 above for the combined
two-run tally).

**4. Cross-validated against the automated QA pass**, which independently
caught: an internal cross-reference leak ("...in 7.2") in
`resilience.vf_reduced_shock_severity_analysis`; a genuinely dangling
reference in `business_household_impact.insight_text` ("the lower MEER
figures" -- MEER is never actually cited anywhere else in that section,
so the reference has nothing to resolve to); a real ambiguity between
`client_satisfaction.nps_analysis`'s NPS *score* (71.3 vs 63.9) and
`gender_scorecard`'s NPS *promoter share* (77.0% vs 71.6%) sitting close
enough in value and topic to plausibly confuse a reader skimming both; two
different topline respondent counts (5,827 vs 5,818) in adjacent sentences
of `client_profile.analysis_text` with no bridging phrase; and a
stylistic inconsistency where `gender_scorecard.insight_text`'s new Zambia
quote is left in raw all-caps with a double space and typos while every
other quote in the report is sentence-cased -- correct per SYSTEM_PROMPT's
verbatim-preservation rule, but visually inconsistent against the rest of
the report's presentation. The QA pass did not catch either cross-Part
duplicate found above -- a real, verifiable difference in what a
programmatic audit finds versus a linear LLM read-through.

Full test suite: **337 passed.** Report: `Core_Credit_Impact_Report_local-cc061.docx`.

## CC-064: CC-017 doubled quote fixed; regeneration surfaced a far more severe, previously-latent bug

**The fix, exactly as specified.** `translate_verbatims.py`: `_inline_gloss`
now takes `omit_leading_quote`; `_inline_glossed_text` checks, for each
match, whether `text[i-1] == '"'` in the *original* text (correct
regardless of how many other substitutions land before or after it in the
same pass) and skips the substitution's own opening quote when the writer
already supplied one. 4 new tests: both real local-cc061 incidents (Part
8.2's "cited" and 8-insight's "saying"), the ordinary no-writer-quote case
(unaffected), and two substitutions in one text where only one is
quote-preceded (confirms per-match, position-based correctness). 341
passed.

**Regenerated from scratch, not a resume -- `local-cc064`, 19.6 min.**
CC-017 doubled-quote check: **0 occurrences**, confirmed on the fresh
content, not just the two known incidents. All three hard gates clean.

**A far more severe, previously-latent bug surfaced in this same
regeneration -- not caused by the CC-064 fix, confirmed independent, but
far worse than what was fixed.** `_inline_glossed_text` matches a
verbatim's quote as a **raw substring with no word-boundary check**. This
run selected a real, 2-character verbatim -- `"da"` (client `MNE_16578`,
detected as "Indonesian" for "yes," though the client is Montenegrin and
"da" is actually Montenegrin/Serbian/Croatian for "yes" -- the language
tag itself is also wrong, a smaller, separate issue) -- as a
`representative_verbatim` in `business_household_impact.qol_drivers`
(theme index 63, a low-frequency tail theme). Because "da" is a common
substring inside ordinary English words, its gloss substitution fired
**13 times across 9 different blocks**, everywhere those words appear,
with no connection to the theme it was actually tagged for:
"Secon**da**ry" (client-profile, twice), "stan**da**rdised"/
"stan**da**rdized" (4.2 twice, 4-insight twice), "Ugan**da**" (3-insight,
5-insight), "Rwan**da**" (2.1, 2-insight), "a**da**ptation" (7.3), and
"secon**da**ry" again (8.2). Every occurrence renders as literal garbage,
e.g. `Secon"yes" (original Indonesian: "da")ry` in place of "Secondary" --
**including in `client_profile.analysis_text`, the report's opening
section, and throughout `child_wellbeing`'s standardisation methodology
paragraph.** Confirmed via direct scan (regex for a gloss-substitution
marker immediately preceded by a letter rather than whitespace/punctuation)
that this is the full extent of it in this run -- 13 occurrences, all from
the same one verbatim; the other four non-English verbatims at or under 5
characters (`Mucho`, `shume`, `nema`, `Ggĥ`) did not happen to collide with
any word in this particular report's text, but nothing prevents them
from doing so on a different run. This is unrelated to the doubled-quote
mechanism just fixed (confirmed: none of these 13 matches were
quote-preceded, so CC-064's new logic was never invoked for them) and
meaningfully more severe -- the doubled-quote defect looked like a typo;
this one produces nonsensical, unreadable prose in the most-read part of
the document. **Not fixed this round** -- flagged per "report the standard
diagnostics and flag anything new," not "one fix." The fix itself is a
different shape of change than CC-064's (word-boundary-aware matching,
e.g. requiring the match not be immediately adjacent to a letter on either
side) and deserves its own dedicated pass rather than folding into this
one silently.

### Standard diagnostics, local-cc064

**Executive summary table:** same 8 theme figures as every prior run this
session (no metric computation changed) -- Financial Access 43.9% |
Poverty Likelihood 12.4% | Business & Household Impact 92.2% | Child
Wellbeing 93.5% (among caregivers) | Client Protection 75.0% | Agency
85.1% | Resilience 67.5% | Client Satisfaction NPS 68.8 [MFI Index 58.0].
**Its own analysis_text is one of the 13 corrupted blocks** -- see above.

**Gates:** `raise_on_meta_text_leaks`, `raise_on_unknown_theme_references`,
`raise_on_missing_caregiver_scope` all clean. `find_dangling_attributions`
(soft): empty.

**Grounding:** `ungrounded_quotes` 0, `partial_quotes` 2 (4-insight,
8.2 -- both real verbatims quoted only in fragment, for a reviewer to
check), `misattributed_quotes` 0, `ungrounded_percentages` 8 (known
CC-008 coverage/complement class), `orphan_markers` 0,
`banned_punctuation` 0.

**Word cap:** 12 of 34 over cap, 2 severely (5-insight +39.3%, an outlier
even against this session's own history; gender-insight +21.3%) --
pre-existing, not touched this round.

**CC-048, re-checked:** the Zambia "wonderful services" quote is back to
**1 occurrence** (`client_satisfaction.insight_verbatims` only) --
non-deterministic citation choice, not a regression; still well within
tolerance.

Full test suite: **341 passed.** Report: `Core_Credit_Impact_Report_local-cc064.docx`
(carries the 13-occurrence "da" corruption -- not recommended for
circulation as-is until that's fixed).

## CC-065: word-boundary substitution, a minimum length for selection, four QA fixes, item 6 declined, clean regeneration

### Item 1: word-boundary matching, reusing CC-006 directly

`translate_verbatims.py::_inline_glossed_text` matched a verbatim's quote
with plain `str.find`, no word-boundary check -- how a 2-character
verbatim ("da") corrupted 13 places across 9 blocks (CC-064). Fixed by
reusing `grounding.py`'s own CC-006 mechanism directly rather than
inventing a second one: `re.search(r"(?<!\w)" + re.escape(quote) +
r"(?!\w)", text)` in place of `str.find`, and verbatims shorter than
`grounding.py`'s own `_MIN_QUOTE_LEN` (25, imported directly -- one
source of truth, not a duplicated constant) are never attempted at all,
since word boundaries alone don't stop a short quote that legitimately
**is** a whole word ("da" bounded by spaces would still wrongly gloss
every stand-alone "da" a respondent typed elsewhere). 4 tests updated
(several existing fixtures used quotes under 25 characters and would have
silently stopped testing what they claimed to, now exclusively testing
the occupied-span mechanism with quotes that clear the floor) plus 3 new
regression tests for the exact incident. 344 passed after this item alone.

### Item 2: a minimum length for verbatim *selection*, evidence-based, not copied from grounding.py

Sorted all 512 distinct verbatims in a real run by length before choosing
anything. The bottom of that list was far worse than one bad "da": `B`,
`L`, `b`, `da`, `We`, `how`, `Ggĥ`, `sfs`, `nema`, `MMMM`, `Mucho`,
`shume`, `Normal`, `ne zna`/`Ne zna`, `Fffffgt` -- fifteen entries at 7
characters or under, all unusable as an illustrative client voice,
several outright keyboard-mashing or OCR-looking garbage. Legitimate
short-but-complete phrases only started appearing at 9-12 characters
("Todo mejora," "MAS INGRESOS," "Good service," "BUEN SERVICIO" /
"HUDUMA NZURI," both meaning "good service" in Spanish/Swahili).

**Floor chosen: 10 characters, not grounding.py's 25.** Confirmed the
lower number is right, not just convenient: 25 would exclude 104 of 512
verbatims in that same run (20%), including real, complete, legitimately
citable sentiments already published in past reports -- "Interest is too
high" (21 chars), "They are older" (14), "Good service" (12). Grounding's
25 answers "is this substantial enough to fact-check as a claimed quote";
selection's question is the much lower bar of "is this substantial enough
to name as a voice at all." 10 sits exactly at the break in the real data
between clear junk (<=7 chars, all of it) and a mixed-but-mostly-legitimate
zone (9+ chars). At 10 exactly, 18 of 512 verbatims are excluded.

**Length alone doesn't solve everything, reported not hidden:** `9999999999`
(10 digits, keyboard-mashed) and explicit non-answers like `no comments`
and `No reason` clear a length floor just fine -- a separate,
content-quality problem, not addressed here.

**The four other very short verbatims, as asked, confirmed still present
and still a live risk:** `Mucho` (5, Spanish), `shume` (5, Albanian),
`nema` (4, Swahili in this run's tagging -- likely misdetected, matches
the pattern that mistagged "da" as Indonesian instead of Montenegrin),
`Ggĥ` (3, language "Unknown," gloss literally `<UNKNOWN>` -- itself a
smaller, separate data-quality flag worth a future look).

**Implemented at the single choke point every selection path passes
through:** `qualitative_agent/agent.py::pick_diverse_verbatims`. Every
`representative_verbatims` list in the pipeline -- per-batch theme tagging
always gets re-selected through `merge_batches`' call to this same
function, `build_client_voices.py`'s green/red picks, and
`build_gender_scorecard.py`'s CC-059 pool -- passes through this one
function, so fixing it here closes every path without touching each call
site separately. 4 new tests (excludes the real "da" incident, excludes
even with no usable fallback rather than citing noise, keeps a real short
sentiment above the floor) plus fixes to 3 existing tests whose fixtures
used single-letter/single-word quotes that would have gone silently empty
under the new floor. 347 passed after this item.

### Item 3: four QA fixes, one declined

1. **Part 3's "lower...above" contradiction**: added an explicit rule to
   `chain.py` SYSTEM_PROMPT, citing the exact incident, right next to the
   existing "our own figure on the same basis" rule it's a variant of --
   naming the comparable figure's value first, then comparing it to the
   benchmark alone, never describing it as "lower" (against the overall
   figure) in the same breath as "above" (against the benchmark).
2. **"in 7.2" cross-reference**: this was a literal instruction in
   `VF_REDUCED_SHOCK_SEVERITY`'s own prompt (`section_prompts.py`), not an
   LLM drafting choice -- replaced "in 7.2" with "reported above" directly
   in the prompt text.
3. **Unnamed 27.8% collision**: `RESILIENCE_INSIGHT`'s prompt now requires
   naming the metric ("our own savings figure on the stricter basis") when
   giving this comparison, citing the real coincidence with Part 6's
   unrelated 27.8% as a past incident rather than hardcoding the number
   itself (which is tied to this wave's data and wouldn't still be true
   after a future wave's numbers change).
4. **"MFI Index by 60 Decibels benchmark"**: this was also a literal
   prompt instruction (`EXECUTIVE_SUMMARY_ANALYSIS`), the only prompt in
   the file naming the benchmark this way -- fixed to require the same
   "MFI Index benchmark" name every other section uses.

**Item 6 (softening the child wellbeing standardisation paragraph's
register) considered and declined, as instructed.** That paragraph is the
methodological correction two reviewers explicitly asked for (the
standardisation work itself, and the caregiver-vs-non-caregiver framing);
its precise, careful language is the point, not a defect to smooth over.
Not touched.

### Item 4: clean regeneration, `local-cc065`, 13.8 min

**All three requested confirmations, verified directly against the real
output, not inferred:**
- Doubled-quote occurrences: **0**.
- Mid-word substitution artifacts (a gloss marker immediately preceded by
  a letter rather than whitespace/punctuation, the exact shape of the
  "da" corruption): **0**, scanned across all 34 blocks.
- Verbatims below the new 10-character floor: **0** of 365 distinct
  verbatims in the final report.

**Standard diagnostics:** executive summary table unchanged (same 8
figures as every prior run this session -- no metric computation
touched). All three hard gates clean
(`raise_on_meta_text_leaks`/`raise_on_unknown_theme_references`/
`raise_on_missing_caregiver_scope`), `find_dangling_attributions` fired
once, correctly, on a sentence that *does* carry a real quote (informational
only, not an issue). Grounding: 0 ungrounded quotes, 3 partial quotes (all
real verbatims quoted only in fragment), 0 misattributed, 8 ungrounded
percentages (known CC-008 coverage/complement class), 0 orphan markers, 0
banned punctuation. Word cap: 9 of 34 over, 2 severely (5-insight +26.0%,
gender-insight +26.0%) -- persistent, pre-existing, not touched this round.

**Read-through, cross-checked against this run's own automated QA pass:**
all four CC-065 text fixes confirmed present and correctly worded in the
fresh generation (verified directly, not assumed). The phrase-variety fix
from CC-061 continues to hold -- roughly 6 forward-looking closers across
34 blocks this run, not concentrated in ordinary analysis paragraphs. One
new, minor finding from the QA pass worth recording: `gender_scorecard`'s
insight claims "men report the higher share... on improved child
wellbeing," but no gender-disaggregated child-wellbeing figure appears
anywhere in `child_wellbeing`'s own rendered text this run for a reader
to check it against -- the underlying number is real (computed
independently in `build_gender_scorecard.py`'s own table), but
untraceable from inside the document itself. Not fixed -- not asked
about this round. The recurring "12.4% below $1.90/day, 12.4% below
$2.15/day" near-duplicate-looking stat in `poverty_likelihood.insight_text`
persists, also pre-existing and not in scope here.

Full test suite: **347 passed.** Report: `Core_Credit_Impact_Report_local-cc065.docx`.

## CC-066: composite-score explanation, PPI coverage in the insight, child wellbeing gender split; regeneration blocked on API credits

### Item 1: explain the composite theme scores

Implemented as a rendering change, not a writer-prompt change -- deterministic
and guaranteed correct every run, rather than depending on the model to
restate it. `report_render/section_layout.py::render_executive_summary`
now adds two captions beneath the theme table: a general line ("Each theme
score above is the unweighted mean of its constituent indicators, as
defined in the Core Credit Dashboard specification; individual indicator
figures for each theme appear in the corresponding Part.") and, for every
theme whose `metric_label` indicates it's a composite, that label named
directly against the theme ("Agency: Unweighted mean of goal achievement
(in full or partially), household influence and community respect.", and
so on for Financial Access, Business & Household Impact, Client
Protection, and Resilience). Reused `ThemeScore.metric_label` verbatim --
CC-011 already wrote this exact "Unweighted mean of X and Y" text into the
data for exactly the composite themes, so this is surfacing existing data,
not deriving a second copy of it. Poverty Likelihood, Child Wellbeing, and
Client Satisfaction (single-indicator themes) are correctly excluded from
the constituent listing. 1 new test.

### Item 2: PPI coverage caveat carried into the insight

`POVERTY_LIKELIHOOD_INSIGHT`'s prompt now requires stating each poverty
line's own scored base whenever the $1.90/day and $2.15/day shares land on
the same or a similar percentage, naming the exact real incident
("12.4%... 12.4%...") as the reason. 2.1 already carried this distinction
correctly; only 2-insight was missing it.

### Item 3: the untraceable gender claim -- chose to surface it, not suppress it

**Decision: surface the child-wellbeing gender split in Part 4, not stop
gender_scorecard from citing it.** Checked first whether the underlying
number even existed anywhere: `child_wellbeing.improved_child_wellbeing.by_segment`
already carries a real, already-computed gender breakdown (Female 93.4%,
Male 93.8%, confirmed directly in a real run's output) -- gender_scorecard's
citation was never fabricated, it was just invisible from inside Part 4.
Given the row is real data (not noise, not thin, not a duplicate), removing
it from the gender scorecard would have deleted genuinely useful
information -- for a child-welfare-focused organization, whether there's a
gender gap in reported child-wellbeing outcomes is exactly the kind of
thing worth a reviewer being able to check -- just to close a traceability
gap that a one-line prompt addition solves for free (no new computation:
`IMPROVED_CHILD_WELLBEING`'s prompt now requires stating the female and
male shares alongside the overall figure). Suppressing gender_scorecard's
citation was the cheaper fix but would have thrown away real information
to hide a symptom rather than close the actual gap.

### Item 6 (QA pass) declined a second time, as instructed

Same paragraph as CC-065's decline (`child_wellbeing.caregiver_vs_other_analysis`'s
standardisation register), flagged again by this round's own QA pass under
a different item number. Declined again for the same reason: this is the
methodological correction two reviewers explicitly asked for: precise
language is the point, not a defect. Recording the second decline here, as
asked. Items 2, 3, and 7 (wording preferences, and the deliberate landing
point of five stock closing phrases across 34 blocks) left alone, also as
instructed.

### Item 4: regeneration blocked on API credits, not attempted past the point of failure

3 fixes verified via the full test suite (**348 passed**) before
attempting a fresh run. Kicked off `run_orchestrator.py --run-id
local-cc066` (fresh, not a resume) -- ran cleanly through 8 of 12
sections (agency, child_wellbeing, client_profile, client_protection,
client_satisfaction, financial_access, poverty_likelihood, resilience)
over 2.4 minutes, then hit the same `BadRequestError: Your credit balance
is too low to access the Anthropic API` seen in earlier rounds, mid-way
through `business_household_impact`'s insight step. Confirmed directly
with a minimal live call before reporting rather than assuming: credits
are genuinely exhausted again, not a transient error. Did not attempt to
resume or work around this -- the run is checkpointed under
`local-cc066` and ready to resume the moment credits are available
(`python agent/orchestrator/run_orchestrator.py <raw_csv> --run-id
local-cc066`), which will pick up the remaining 4 sections
(business_household_impact, executive_summary, gender_scorecard,
client_voices) without recomputing the 8 already done. None of the three
fixes above have been verified against a real end-to-end regeneration
yet -- that verification is what's blocked, not the fixes themselves.

## CC-067: local-cc066 completed, all three fixes verified live

Credits restored. Resumed (not re-run from scratch) `local-cc066` -- the 8
sections already built under CC-066's code did not need recomputing;
completed the remaining 4 (business_household_impact, executive_summary,
gender_scorecard, client_voices) in 12.5 min.

**All three fixes confirmed directly against the real output, not
assumed:**
- **Composite scores**: confirmed in the actual rendered `.docx` (not
  just the JSON, since this is a render-time caption) -- both captions
  present beneath the executive summary table, constituents named
  correctly for the five composite themes, the three single-indicator
  themes correctly excluded.
- **PPI coverage**: `poverty_likelihood.insight_text` now states both
  scored bases and explicitly calls the matching 12.4%/12.4% figures
  "coincidental rather than a repeated calculation."
- **Child wellbeing gender split**: `4.1` now states "female caregivers
  at 93.4% and male caregivers at 93.8%," making `gender_scorecard`'s
  citation traceable for the first time.

**Standard diagnostics:** executive summary table unchanged (same 8
figures as every run this session). All three hard gates clean; the
soft `find_dangling_attributions` check is empty (one real attribution
in `3-insight` has substantial content after "described" and correctly
does not fire). Grounding: 0 ungrounded quotes, 0 partial quotes, 0
misattributed, 9 ungrounded percentages (known CC-008 class), 0 orphan
markers, 0 banned punctuation. Word cap: 11 of 34 over cap, **0 severely
over (>20%)** -- the best word-cap performance of any run this session.
CC-017 doubled-quote check and the CC-065 substring/floor checks: all
still clean (0 occurrences, 0 verbatims below the 10-character floor).

**Read-through, cross-checked against this run's own QA pass:** a new,
legitimate observation surfaced -- now that the child-wellbeing gender
split is visible (per this round's own fix), a reader can see that
`gender_scorecard.insight_text` groups it with "men report the higher
share" alongside genuinely significant gaps, without flagging that this
one is a 0.4-point difference by comparison. Real, but not asked about
this round -- reported, not fixed. The child-wellbeing standardisation
register was flagged by the QA pass a third time; not acted on, per the
standing decline. The two previously-disclosed residual cross-Part
duplicates (`gender_scorecard`-vs-`business_household_impact`'s own
`qol_drivers` list, and `client_protection`-vs-`client_voices`) are both
still present, unchanged from CC-057's original disclosure -- neither is
new, and neither was asked about this round.

Full test suite: **348 passed.** Report: `Core_Credit_Impact_Report_local-cc066.docx`.
