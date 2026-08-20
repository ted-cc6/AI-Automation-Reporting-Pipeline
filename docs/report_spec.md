# LACRO Insurance Impact Report: Change Specification

**Baseline artifact:** `LAC_Insurance_Impact_Report_default_2026_Q2_Test9.pdf` (generated 17 August 2026)
**Reviewers:** Lorenz M (LM1 to LM11), second reviewer HO (HO2R1)
**Spec owner:** Binjie Wang
**Status:** draft, pending reviewer confirmation on R-002, R-006, R-008, R-014

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

---

# Phase 1: Data and config

Changes here alter figures downstream, so they land first.

## R-001 Period label matches fieldwork dates

**Source:** self identified (report already emits `period_label_mismatch` flag)
**Layer:** `data_config`
**Priority:** high

**Current behaviour**
The run is labelled 2026 Q2 while recorded fieldwork spans 26 June 2026 to 4 August 2026, crossing from Q2 into Q3. The pipeline detects this and emits a warning, but still renders the mismatched label in the title, the running header and the output filename.

**Intended behaviour**
The reporting period label is derived from the fieldwork date range rather than entered by hand. Where the range crosses a quarter boundary, the label expresses the range rather than a single quarter.

**Rule**
```
period_label = derive_from(min(fieldwork_date), max(fieldwork_date))
  single quarter  -> "2026 Q3"
  spanning        -> "2026 Q2 to Q3"
An operator supplied label that conflicts with the derived label
is a hard failure, not a warning.
```

**Verification**
- `assert derived_period_label in report.title`
- `assert not warnings.contains("period_label_mismatch")`

**Open question for reviewer**
Confirm whether the intended reporting period is Q3 (most fieldwork falls there) or a spanning label. Ask Lorenz on the next call.

---

## R-002 Executive summary metric list is configurable

**Source:** LM1a, "why the focus on only these 4 metrics in the table?"
**Layer:** `data_config`
**Priority:** medium

**Current behaviour**
Four metrics are hardcoded: Net Promoter Score, Children's Wellbeing Improved, First Time Access to Insurance, Filed a Claim. The selection is not documented and cannot be changed without a code edit.

Two secondary defects in the same table:
- The N column mixes bases. Three rows show the full sample (1,721) while Filed a Claim shows 124, which is the count of clients who experienced an insured event, not the denominator used for the 44.4 percent figure.
- Filed a Claim as a headline metric is ambiguous without its funnel context, since 44.4 percent is the conversion from event to claim, not the share of the portfolio that claimed (which is 3.2 percent).

**Intended behaviour**
The summary metric list moves to config as an ordered list of metric IDs. The N column always shows the denominator of the stated percentage. Any metric whose denominator differs from the full sample carries a short base label in the table.

**Rule**
```yaml
executive_summary:
  metrics:
    - net_promoter_score
    - child_wellbeing_improved
    - first_time_access
    - worth_premium          # candidate replacement, pending review
  show_base_label_when_restricted: true
```

**Verification**
- `assert len(summary.metrics) == len(config.executive_summary.metrics)`
- For each row: `assert row.n == metric.denominator`
- `assert all(row.base_label for row in summary.metrics if row.n != total_n)`

**Open question for reviewer**
Which metrics does Lorenz want in the table? Propose a set covering understanding, value, claims and wellbeing rather than four measures that lean on satisfaction.

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
| LM1 (metrics) | R-002 | | |
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
