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
