# Known Issues and Tribal Knowledge

This document exists so that non-obvious fixes already made to this
codebase are not silently reverted or rediscovered from scratch by a future
maintainer. Each entry below was verified against actual git history and
current code, not reconstructed from memory. Where a commit hash is given,
it refers to the real development commit on `main`; this repository also
pushes squashed duplicate commits to a separate `space` remote for Hugging
Face deployment, so the same change can appear twice in `git log --all`
under different hashes and dates. Every commit in this repository's history
is authored by the same person and carries the same co-author trailer; that
is expected and not an anomaly.

## 1. Likert scale inversion (two separate bugs, do not conflate them)

**1a. The original inversion, predating tracked git history.** Four
questions in Part 1 (Client Understanding and Value Perception) are coded
on a scale where 1 means the best response, not the worst: coverage
understanding, claims-process understanding, confidence in payout, and one
more. Scoring these with `top_two_box` (which assumes higher numbers are
better) instead of `bottom_two_box` inverts the result. This fix, and the
`SCHEMA_VERSION` bump from `"1.4"` to `"1.5"` that records it, were already
present in this repository's very first tracked commit, so there is no
earlier state to diff against. The only surviving record is the inline
comment on `SCHEMA_VERSION` in `run_analysis.py` and a comment in
`analysis_engine/sections/part_1.py`. Do not "fix" these four questions
back to `top_two_box`; that would reintroduce the original bug.

**1b. A later, related but distinct bug: scale bounds inferred from a
subset instead of the true fixed scale.** Fixed 2026-08-11. Symptom: a
caregiver segment's "high financial stress" rate showed 48.6% instead of
the correct roughly 1.4%. Root cause: `top_two_box()`/`bottom_two_box()`
computed their "top N"/"bottom N" threshold from the maximum or minimum
value actually present in whatever subset was passed in, such as one
demographic segment or one country. If that subset happened never to
contain the survey's true worst or best value, the threshold silently
shifted to the wrong place. The fix added explicit `scale_max`/`scale_min`
parameters, so callers pass the question's true fixed scale bound rather
than letting the function infer it from a potentially incomplete subset.
The old auto-detect behavior is kept only as a fallback, and it now logs a
loud warning when used. Every call site across Parts 1, 4, and 5 was
updated to pass the explicit bound. Do not remove these explicit
parameters or add a new call site that omits them; that reintroduces this
bug for whatever new metric you add.

Files: `analysis_engine/stats.py`, `analysis_engine/sections/part_1.py`,
`part_4.py`, `part_5.py`, `tests/test_stats.py`.

## 2. worth_premium / renewal_intent population-scope fixes

Shipped 2026-08-14 as part of a batch of fixes found during a real review
of a generated LACRO report. This is not one bug but several distinct
population-scope mistakes bundled into the same commit:

- Population notes attached to the worth-of-premium metric (across Parts
  1, 4, 5, 6, and 7) and the renewal-intent methodology appendix example
  used hardcoded text such as "Health and credit-life clients only" or
  referenced Vietnam's crop-insurance clients, which is simply false for a
  LACRO report where the whole population is Health insurance and there
  are no Vietnamese respondents. Fixed by introducing a
  `_resolve_population()` helper that makes these notes conditional on the
  actual report scope instead of hardcoding a string written for one
  specific report.
- A Part 5 driver's population note had been copy-pasted from a
  neighboring driver's note because the correct one was simply missing.
- A healthcare-access metric's denominator was wrong: it read as roughly
  8.8% (152 out of 1,721) when it should have read roughly 33.9% (152 out
  of 448), because the respondents who said they "did not need care" were
  never excluded from the denominator, unlike a sibling metric
  (`medical_cost_change`) which already excluded them correctly.
- Part 6's "Non-Claimant" label was actively misleading: the group it
  described (n equal to 69) was actually clients who experienced an
  insured event but did not file a claim, not the full population of
  clients who never claimed at all (roughly 1,666 people). This happened
  because the underlying claim-submitted question is only asked of
  respondents who already reported an insured event, so a simple boolean
  mask can never match the much larger group of respondents who were
  never asked the question at all. Relabeled "Non-Claimant" to
  "Non-Filer" everywhere, including a matching wrong description in the
  segment registry and a copy of the same confusion that had leaked into
  Part 1's prose.

Files: `analysis_engine/sections/part_4.py`, `part_6.py`,
`analysis_engine/segments.py`, `generation/assembler.py`,
`generation/report_spec.yaml`, `generation/writer.py`,
`generation/executive_summary.py`, `generation/orchestrator.py`.

## 3. Dedup / test-row screening step

Added 2026-07-21. Before this existed, the pipeline counted every row that
survived transformation as a real respondent, including rows submitted by
field staff for testing and rows that were exact duplicates of another
submission. On the quarter's real CSV, adding this step took the row count
from 2,111 down to 2,105, a reduction of 2 test rows and 4 duplicates.

- Test and QA rows are identified by a case-insensitive, whole-word regex
  match of `test`, `demo`, `training`, `pilot`, or `qa` against the
  client ID, enumerator, or branch columns. The match is deliberately
  word-boundary-anchored so that, for example, "qa" does not falsely
  match inside an unrelated word.
- Exact-content duplicates are two rows that match on every column except
  a fixed list of KoBoToolbox logistics columns (submission ID, UUID,
  submission time, row index, device info, interview start and end time,
  enumerator). One canonical copy is kept: whichever has the earliest
  submission time, tie-broken by the lowest row index.
- Deliberately **not** auto-dropped: a client ID reused across rows with
  genuinely different answers. This is logged as a warning for the field
  team to reconcile by hand, specifically because automatically dropping
  it risks deleting a real respondent's real answers.

Two more checks were added later (2026-08-13, alongside the region-scoping
rollout, see entry 6 below) that are report-only and never remove rows on
their own: shared-UUID pairs with a similarity score, and interview
duration outliers. Also added at that time were two checks that do remove
rows: non-consenting respondents, and respondents outside the current
schema's country allow-list. With all four row-removing checks active, a
real smoke-test run shows the fuller sequence of 2,111 rows after
transform down to 2,091: 2 test/QA, 4 duplicates, 7 non-consenting, and 7
out-of-scope-country. If you see the figure 2,105 or 2,091 quoted on its
own elsewhere, check which set of checks was active for that run rather
than assuming one of the two numbers is simply wrong; both are correct for
their respective points in time, and the exact count always depends on the
specific upload.

A related, explicitly acknowledged gap: the original commit message notes
that the report's respondent count (2,111 at the time) still did not
exactly match the number shown in the existing Power BI dashboard (2,089),
and that most but not all of that gap was closed by this screening step.
The remainder was attributed to Power BI's own separate, independently
maintained deduplication logic, and was explicitly scoped out as something
this pipeline does not attempt to replicate.

Files: `data_loader/data_loader_screening.py` (new file),
`tests/test_screening.py` (15 new tests). Wired into both the CLI
(`run_pipeline.py`) and the dashboard (`pipeline_runner.py`).

## 4. LARCO folded into the unified Africa/Vietnam schema

LARCO was not built as a new schema from scratch; it went through two
stages. First (2026-08-11), LARCO was added as its own separate,
209-column source schema, with a same-day follow-up fixing quality issues
found in that standalone report (see entry 1b above, which was found
during this same review). Then (2026-08-13), the 2026 live export instead
folded LARCO's countries into the same 133-column schema used for
Africa/Vietnam since the project's first commit. The older 209-column
instrument is retained only for one purpose: reprocessing the 2025 LARCO
export as a Part 10 trend-comparison baseline for the new unified-schema
reports.

A naming note worth preserving: the internal code deliberately keeps the
name "LARCO," while every user-facing string uses "LACRO," the correct
regional acronym. This is intentional, documented directly in
`report_scopes.py`'s module docstring, and is not a typo to "fix" by
renaming the internal code.

The pivot to the unified schema surfaced four concrete bugs, all found and
fixed the same day (2026-08-13):

1. **Scope-countries.** The out-of-scope-country allow-list used by the
   dedup/screening step (entry 3 above) did not include Ecuador, Mexico,
   Guatemala, Honduras, Bolivia, or the Dominican Republic. Verified
   against the real export: without this fix, zero of 1,721 LARCO rows
   would have survived the out-of-scope-country screen, silently dropped
   as if they belonged to no valid country at all. Fixed by adding the
   six countries to the allow-list.
2. **PWD (people with disabilities) overrides.** Five country config
   files each carried an override saying the disability segment was
   unavailable. This was correct for the old 209-column instrument, which
   had no disability screener question, but wrong for the new
   133-column schema, which does include one. Left in place, this would
   have wrongly suppressed the disability segment for every LARCO
   country under the new schema. The override was removed.
3. **Missing Dominican Republic config.** No country config file existed
   for the Dominican Republic under either schema; one was added. A
   related, previously dormant bug was fixed at the same time: the
   country-config lookup key was not normalized, so a two-word country
   name like "Dominican Republic" did not reliably match a one-word
   filename convention that every other country up to that point had
   happened to satisfy by coincidence.
4. **Part 9 and Part 10 gating.** Both Part 9 (Additional Services) and
   Part 10 (Trend Comparison) were gated on the dataset schema literally
   equaling `"larco"`. Part 10's own calculation logic does not actually
   depend on which schema is active, only on the presence of certain
   canonical columns, but because 2026 LARCO countries now run on the
   `africa_vietnam` schema, the old gate meant Part 10 could never
   activate for a 2026 LARCO country at all. The fix made Part 9 and Part
   10 gate independently: Part 9 stays restricted to the LARCO schema,
   while Part 10 activates whenever a prior run ID is supplied, on any
   schema, or unconditionally whenever a `larco`-schema run happens (so a
   first-wave baseline run still stores its own snapshot for later use).
   Verified afterward: four of five trend indicators produced real,
   meaningful deltas across all five LARCO countries with a 2025
   baseline; the Dominican Republic, which has no 2025 baseline, degrades
   cleanly with no Part 10 section and no crash.

Files: `data_loader/data_loader_screening.py`,
`analysis_engine/country_config.py`, `country_configs/*.yaml`,
`run_analysis.py`, `generation/orchestrator.py`,
`dashboard/api/pipeline_runner.py`, `generation/run_generation.py`,
`generation/assembler.py`, `generation/report_spec.yaml`.

## 5. Qualitative batching redesign and hardcoded provider naming

Shipped 2026-08-13. Root cause was a genuine capacity ceiling, not a
parsing bug: the real 2026 unified dataset, after the LARCO merge, has
roughly 3,812 respondents and around 347,000 input tokens, with about
3,752 individual NPS follow-up responses each needing tagging. The compact
tagging output alone needed roughly 56,000 to 75,000 output tokens,
exceeding the model's 65,536-token output ceiling before it could even
reach the other tasks the old single-call design also asked for in the
same call. The visible symptom was every expected key missing from the
response, occurring even when the pipeline was configured to use Claude
rather than Gemini, which was the first clue that this was a capacity
problem rather than a provider-specific parsing bug.

The fix batches NPS tagging into groups of 600 records each (seven batches
on the real dataset), each batch producing per-record theme tags, a
protection-flag scan, a shortlist of verbatim candidates, and a
not-worth-it classification, followed by exactly one synthesis call that
handles the small remaining ungrouped free-text responses directly and
merges every batch's pooled output into the final verbatim selection,
theme clustering, section insights, and executive summary. The final
output shape is unchanged from the old single-call design, so no
downstream parsing, orchestration, writing, or assembly code needed to
change. One failed batch, after retries, is skipped with a warning rather
than failing the whole run.

A related, separate issue: **hardcoded "Gemini" wording** was fixed in two
passes, not one. The first pass, on 2026-07-16, generalized error messages
in `qualitative/llm_call.py` that had been hardcoded to say "Gemini,"
left over from before that module was renamed from a Gemini-specific file
to a provider-generic one. The second pass, discovered while working on
the batching redesign a month later, found this first fix had missed a
sibling file: `qualitative/parse_results.py` still hardcoded the string
"Gemini response missing keys" regardless of which provider actually
produced the response, and the output file's own metadata field
hardcoded the model name `"gemini-2.5-pro"` unconditionally, even when a
different provider had been used. Both are now threaded through from the
actual provider and model in use. If you add a new call site that reports
an LLM-related error, check whether it hardcodes a provider name before
assuming it is provider-generic.

Files: `qualitative/llm_call.py`, `qualitative/parse_results.py`,
`qualitative/run_qualitative.py`, `llm_providers.py`,
`dashboard/api/pipeline_runner.py`, `tests/test_llm_call.py` (fully
rewritten).

## 6. Region scoping rollout

Shipped as a sequence of commits on 2026-08-13 and 2026-08-14:

1. A Dockerfile fix: `report_scopes.py` and `data_quality_flags.py` had
   never actually been copied into the Docker image, causing an
   import-time failure on the deployed Space that would not have shown up
   in local development.
2. The main region-scoping commit, filtering the dataset by report scope
   before any statistic is computed; fixing a claims-funnel denominator
   bug where scopes that never asked Vietnam's crop-insurance clients a
   particular question had an inflated experienced-event rate; adding
   wave-over-wave trend comparability as a property of the data itself,
   where non-comparable indicators simply never expose a prior-wave
   value and comparable ones test their delta only across the countries
   common to both waves; adding `data_quality_flags.py`, which lets
   suspicious data be footnoted and excluded from headline claims without
   silently dropping it; adding a protection-flag appendix with
   cross-source deduplication; adding the em-dash writing rule (see
   below); and adding `generation/validate_output.py`, an advisory
   post-generation validation pass checking for internal row/theme-key
   leaks into prose, mentions of out-of-scope countries, comparative
   language used on indicators that are not actually comparable, and
   unverified quotes or numbers.
3. Exposing report scope selection in the dashboard UI: a new endpoint
   listing available scopes, a new field on the run-start request, and a
   frontend picker folded into the existing country and region dropdown.
4. The population-scope review fixes described in entry 2 above.

**How new sections get included or excluded per scope (the "module
manifest").** This is not a separate configuration file; it is the
section-gating logic inside `run_analysis.py`'s `build_sections()`
function, driven by `report_scopes.py`'s `REPORT_SCOPES` dictionary. Parts
9 and 10 gate on the report scope being `"lacro"`, or the dataset schema
being `"larco"`, with Part 10 additionally requiring a prior run ID. Parts
11 and 12 (Credit Life and Crop modules) gate on the report scope being
`"africa"` only, with no LARCO-schema fallback, since neither product
exists in LACRO's entirely-Health-insurance population. See
[extension-guide.md](extension-guide.md) for the full recipe on adding a
new scope.

**The em-dash writing rule, and how it is actually enforced.** This is
directly relevant if you are ever asked to apply the same house style to
something outside the generated reports, as happened with these very
maintenance documents. In the Cupboard Week pipeline, the rule is purely a
prompt instruction, not a lint rule or a post-processing filter. The exact
instruction sent to the LLM, from `generation/writer.py`'s house-voice
system prompt, is: "Never use an em dash or en dash anywhere in your
writing. Use a comma, colon, semicolon, parentheses, or a new sentence
instead." There is no code anywhere in `generation/` that checks the
LLM's output for dash characters, no retry triggered by a violation, and
no strip-before-render step. It relies entirely on the model following the
instruction.

This is worth contrasting with the separate Core Credit pipeline, which
enforces the same style rule far more strictly: `core_credit/agent/analysis/writer/`
counts every banned punctuation occurrence in a draft, and if any are
found, triggers an actual retry with an explicit rewrite instruction. Its
own test suite references a real production incident in which a generated
report was found to contain 297 em dashes despite the same kind of
prompt-only instruction being in place at the time. If a future maintainer
wants the Cupboard Week pipeline's dash rule to have real teeth instead of
relying on the model's compliance, the Core Credit pipeline's
`check_banned_punctuation()` approach is the pattern to copy, not
something that already exists to be reused directly.

## 7. Prior-run picker refresh bug, then the whole picker was removed

These are the two most recent commits on `main` as of this writing, both
from 2026-08-14, roughly half an hour apart.

The first commit fixed a real user-visible bug: a dropdown for picking a
previously completed run as a trend-comparison baseline only refreshed its
list when the Country/Region field's LACRO-ness was toggled, not when a
run actually finished. This meant a natural workflow, building a baseline
run with the "analysis only" option and then immediately configuring the
next run in the same browser session, would not show the just-finished
baseline in the dropdown without a full page reload. The fix made the
dropdown also refresh whenever a run's status changed.

Roughly half an hour later, a second commit removed the dropdown this fix
had just repaired, replacing the entire manual-baseline-run workflow with
the single second-CSV-upload flow described in
[quick-start.md](../user-guide/quick-start.md) and
[pipeline-data-flow.md](pipeline-data-flow.md). The old flow required
uploading last year's CSV, running it separately with "analysis only"
checked, then manually picking that finished run from a dropdown before
starting the real run. The new flow uploads the prior-year CSV alongside
the main one and does everything automatically on a single "Generate"
click. Importantly, the underlying machinery from the old flow was not
removed, only its manual, user-facing steps: the commit message states
explicitly that the existing prior-run-ID and dataset-schema-detection
machinery is unchanged and still used underneath. What changed is that
building the baseline run is now triggered automatically as an untracked
side-run during the main "Generate" click, rather than being a separate,
user-visible, manually-triggered, then manually-selected step. The
"analysis only" checkbox itself was kept, since it is still useful on its
own, but its help text no longer references the now-deleted dropdown.

Practical consequence for a future maintainer: the first commit's fix now
targets a UI element that the second commit deleted. It is not wrong, just
moot. If you go looking for that dropdown to apply a similar fix
elsewhere, or wonder why the fix from the first commit appears to do
nothing, this is why.

## An unresolved item worth tracking, not yet a "known issue" with a fix

[architecture-overview.md](architecture-overview.md) documents one
architectural inconsistency that was found during research for these
documents but has not been resolved: the LARCO dataset schema skips
Stage 1's `report_spec` alignment check (there being no LARCO-equivalent
governance spec), but Stage 2's `load_survey_data()` still unconditionally
loads and depends on the Africa/Vietnam-oriented governance spec
regardless of which schema is active. This may be intentional, but no
schema-conditional branch was found in that function to confirm it is.
Confirm with the team before assuming either that it is a bug or that it
is fine as-is.
