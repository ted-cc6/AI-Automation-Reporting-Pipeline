"""qualitative/llm_call.py

Phase 2: Send the qualitative-tagging payload to an LLM provider, save raw
responses, return a parsed dict matching parse_results.py's REQUIRED_TOP_KEYS
schema unchanged. Provider/api_key are passed in explicitly by the caller
(the dashboard backend threads these through from the user's browser
session; the CLI entrypoint in run_qualitative.py falls back to
GEMINI_API_KEY for standalone use).

ARCHITECTURE (rewritten 2026-08-13 -- see project_larco_2026_pivot memory):
the original design sent the ENTIRE payload in one call. That worked at the
~2,100-respondent scale this was built for (~52,600 input tokens), but the
2026 wave folding LARCO's countries into the main dataset pushed the unified
portfolio to ~3,800+ respondents -- the real payload now runs ~347,000
estimated input tokens, and just the compact NPS-tagging output for ~3,750
records alone needs roughly 56,000-75,000 tokens, which can exceed
max_output_tokens=65536 before the model even reaches the other six tasks
(or, for Claude, before it finishes internal reasoning and starts the actual
tool-call output at all) -- surfacing as "response missing keys" with EVERY
key missing, not a few.

Fix: split into two kinds of calls.
  1. N "batch" calls, each given a slice of ONLY the NPS follow-up records
     (the ~90%-of-volume group) -- per-record theme tagging, a protection-
     flag scan scoped to that slice, a per-section verbatim CANDIDATE
     shortlist (not final picks), and per-record pricing/service
     classification for records already flagged not_worth_it=true in the
     input. Batch size is chosen so a batch's output stays well under the
     token ceiling with a comfortable margin (see _NPS_BATCH_SIZE).
  2. One "synthesis" call, given the small claims_other/sparse_other groups
     directly (full text -- together under 500 records, no batching needed)
     plus the POOLED candidate output from every batch (already-tagged,
     already-shortlisted, enriched with text/profile in Python from the
     original records -- not re-read from scratch). This call does the
     tasks that need a whole-payload view: clustering not-worth-it
     candidates into ranked themes, picking the final 3 verbatims per
     section from the pooled candidates, section insights, the executive
     summary, and a protection-flag scan of the two small remaining groups.

Every batch and the synthesis call share the same theme/protection-flag
taxonomy and report-section definitions (see the _*_BLOCK constants) so
tagging stays consistent no matter which call produced it. The final merged
dict (built by call_gemini()) has the exact same top-level shape the
single-call design produced, so parse_results.py and everything downstream
needs zero changes.
"""
import json
import logging
import time
from pathlib import Path

from llm_providers import call_llm
from qualitative import tag_cache

log = logging.getLogger(__name__)

# Records per NPS batch call. Sized from the real 2026 dataset (~3,752 NPS
# records): at 600/batch, a batch's own tagging output is ~600 x ~25 tokens
# (row_id + 1-3 theme codes) = ~15,000 tokens, plus a handful of protection
# flags, up to 14 verbatim candidates (2 per section x 7 sections), and a
# fraction of the ~118 not_worth_it records -- comfortably under 65536 with
# roughly 4x headroom for estimation error and any per-model reasoning
# overhead. Tune down if a future wave's per-record text grows much longer
# (this bounds record COUNT, not token volume directly).
_NPS_BATCH_SIZE = 600

# Verbatim candidates a single batch may shortlist per report section --
# kept small so N batches' pooled candidates (up to N x this number per
# section) stay a manageable input for the synthesis call while still
# giving it a genuinely diverse pool to pick the final 3 from.
_CANDIDATES_PER_SECTION_PER_BATCH = 2

NPS_GROUP_TO_COLUMN = {
    "promoter": "nps_promoters",
    "passive": "nps_passives",
    "detractor": "nps_detractors",
}


# A non-NPS payload record's own "source_column" (prepare_payload.py) is
# the RAW survey column name (e.g. "q_claim_challenges__other_text") --
# NOT the payload GROUP name ("claim_challenges_other_support") a
# protection flag's "column" field actually uses (confirmed directly
# against this run's real synthesis output: {"id": "row_1015", "column":
# "claim_challenges_other_support", ...}). _record_column() needs the
# GROUP-name vocabulary to match flags, so raw source_column values are
# translated here. Mirrors prepare_payload.py's build_payload() group
# routing exactly (the "claims_other" group splits into two payload
# groups depending on which of these two columns; every other non-NPS
# column is "sparse_other") -- if a column is ever added or moved there,
# update this too.
_SOURCE_COLUMN_TO_GROUP = {
    "q_claim_challenges__other_text": "claim_challenges_other_support",
    "q_claim_challenges__support_text": "claim_challenges_other_support",
    "q_no_claim_reason__other_text": "claim_no_reason_other",
    "q_coping_mechanisms__other_text": "sparse_other",
    "q_income_sources__other_text": "sparse_other",
    "q_comm_channel_effective__other_text": "sparse_other",
    "q_claim_channel_preferred__other_text": "sparse_other",
    "q_vf_services_received__other_text": "sparse_other",
    "q_child_improvements__other_text": "sparse_other",
    "q_quality_of_life_text": "sparse_other",
    "q_claim_experience_rating__other_text": "sparse_other",
    "q_financial_security_belief__other_text": "sparse_other",
}


def _record_column(rec: dict) -> "str | None":
    """The payload GROUP a record belongs to, in the SAME vocabulary
    protection-flag "column" fields use (payload's own top-level keys:
    nps_promoters/nps_passives/nps_detractors/claim_no_reason_other/
    claim_challenges_other_support/sparse_other) -- both batch-origin
    flags (via NPS_GROUP_TO_COLUMN, added by call_gemini()) and
    synthesis-origin flags (the model already fills this in; the OUTPUT
    SCHEMA asks for it) already use this vocabulary, so this is what
    R-018's dedup key and R-029's found_by_id lookup need for a SCANNED
    RECORD to be compared against a flag correctly.

    NOT the same thing as the raw dataframe column a record's text came
    from (see parse_results.py's separate _raw_column_for_record(),
    which R-030's verbatim lookup needs instead -- deliberately two
    different helpers in two different vocabularies, not one shared
    function, since conflating them was a real bug caught before this
    shipped: "claim_challenges_other_support" is not a real dataframe
    column, and "q_claim_challenges__other_text" is not what a
    protection flag's "column" field ever contains.)

    row_id alone is one-per-RESPONDENT (prepare_payload.py's row_id =
    f"row_{idx:04d}"), not one-per-(respondent, column), so a respondent
    with text in two columns produces two records sharing an id; this is
    what actually tells them apart.
    """
    source_column = rec.get("source_column")
    if source_column:
        return _SOURCE_COLUMN_TO_GROUP.get(source_column, source_column)
    return NPS_GROUP_TO_COLUMN.get(rec.get("nps_group"))

# ---------------------------------------------------------------------------
# Shared taxonomy / section blocks -- identical text reused by both the
# batch and synthesis prompts so tagging never drifts depending on which
# call produced it.
# ---------------------------------------------------------------------------

_THEME_TAXONOMY_BLOCK = """## THEME TAXONOMY (use ONLY these codes)

staff_service:       Staff helpfulness, loan officer support, responsiveness
claims_speed:        Speed of claim payout; delays or fast resolution
claims_process:      Ease/difficulty of submitting a claim; documentation; guidance
product_value:       Worth the premium; pricing perception; value for money
product_understanding: Coverage knowledge; exclusions; how to claim; awareness gaps
payout_adequacy:     Whether payout was enough to cover the loss
financial_relief:    Financial stress relief; income smoothing; recovery
access_inclusion:    First insurance experience; reaching uninsured; safety net
child_family:        Impact on children's health/education; family stability
crop_agricultural:   Farming recovery; crop shock; agricultural outcomes
general_satisfaction: General positive sentiment; no specific driver
improvement_suggestion: Concrete suggestions to improve service or product
complaint_grievance: Specific grievance about service, product, or conduct"""

# Human-readable label for every _THEME_TAXONOMY_BLOCK code above -- used by
# qualitative/parse_results.py to relabel section_insights.*.top_drivers and
# theme_counts keys before they're written to qualitative_results.json.
# Needed because the synthesis prompt (see _build_synthesis_prompt()'s TASK
# 4B below) explicitly allows the model to use a raw taxonomy code as a
# top_drivers value ("Use a THEME TAXONOMY code if one genuinely fits"), and
# a real generated report shipped with the raw code "claims_process" sitting
# unlabeled in reader-facing prose as a result -- a prompt instruction alone
# already failed once here, so this is applied deterministically in code
# rather than left to model compliance a second time.
THEME_CODE_LABELS = {
    "staff_service": "staff service",
    "claims_speed": "claim payout speed",
    "claims_process": "the claims process",
    "product_value": "product value for money",
    "product_understanding": "product understanding",
    "payout_adequacy": "payout adequacy",
    "financial_relief": "financial relief",
    "access_inclusion": "access and inclusion",
    "child_family": "child and family impact",
    "crop_agricultural": "agricultural recovery",
    "general_satisfaction": "general satisfaction",
    "improvement_suggestion": "improvement suggestions",
    "complaint_grievance": "complaints and grievances",
}


def humanize_theme_label(value: str) -> str:
    """Map a raw taxonomy code to its human-readable label; pass through
    unchanged if it's already freeform text (the synthesis prompt allows
    both -- see THEME_CODE_LABELS's comment above)."""
    return THEME_CODE_LABELS.get(value, value)

_PROTECTION_FLAG_TAXONOMY_BLOCK = """## PROTECTION FLAG TAXONOMY

  mis_selling:            promised benefits not delivered at claim time
  premium_without_consent: premium deducted without client's knowledge/consent
  coercion:               client felt pressured to purchase
  false_information:      agent gave false or misleading information
  unfair_claim_denial:    claim denied without valid explanation
  staff_misconduct:       negligent, unresponsive, or dishonest staff behavior
  data_privacy:           misuse of personal data

Report EVERY instance, even one. These are surfaced as signals, not quantified.
Include: id, flag_type, severity ("high"|"medium"|"low"),
reason (1 sentence quoting or paraphrasing the key phrase).

SEVERITY RUBRIC (apply these impact criteria to the specific case FIRST; do
not just default to a flag_type's typical tier below when the actual
described impact points elsewhere):
  high:   direct financial loss to the client (claim wrongly denied, premium
          taken without consent and not refunded, payout withheld) OR a
          consent/rights violation (coercion into purchase, personal data
          misused without consent) OR the response describes a pattern of
          repeated/systemic conduct rather than one isolated incident.
  medium: misrepresentation or false information was given but the client
          caught it or it was corrected before causing financial harm, OR a
          notable service failure (unresponsive or negligent staff) delayed
          a legitimate outcome without ultimately denying it.
  low:    minor friction or dissatisfaction with staff interaction or
          communication style, with no financial harm or rights violation
          implied, and the client does not describe it as materially
          affecting their outcome.
Typical tier by flag_type, when the case has no distinguishing detail beyond
the flag_type itself: unfair_claim_denial, coercion, premium_without_consent,
and data_privacy default to high; mis_selling and false_information default
to medium; staff_misconduct defaults to medium but should be downgraded to
low for pure communication friction with no suggestion of harm."""

_REPORT_SECTIONS_BLOCK = """Sections:
  part1 (Product Understanding): coverage/claims knowledge gaps, education
  part2 (Claims Experience): filing experience, challenges, coping
  part3 (Financial Inclusion): first insurance access, safety net
  part4 (Client Voice): NPS drivers, promoter/detractor reasons, value
  part5 (Child Wellbeing): impact on children, family, caregivers
  part6 (Claimant Outcomes): lived experience of making a claim
  part7 (Gender): gendered experience, female or male-specific challenges"""

_VERBATIM_CRITERIA_BLOCK = """Selection criteria:
  - Text must be substantive: it names a specific reason, detail, or experience --
    not just a generic sentiment word or phrase ("good service", "no comment", and
    "muy bueno" are NOT substantive; "the agent explained the claim process clearly"
    and "el pago llegó en una semana" ARE). Typical response length varies a lot
    across countries and survey instruments -- do NOT use a word-count minimum as
    your bar. A short response with one specific concrete detail is MORE
    substantive than a longer but generic one, and must be preferred over it.
  - Clearly relevant to the section topic
  - For part5 (child wellbeing): prefer is_caregiver=true responses
  - For part6 (claimant outcomes): prefer is_claimant=true responses
  - For part7 (gender): include at least 1 Female and 1 Male where possible"""

# ---------------------------------------------------------------------------
# Single-country prompt variant. Both the batch and synthesis prompts state
# the survey's country scope and both carry country-diversity instructions
# (batch: local candidate shortlisting; synthesis: final verbatim pick) --
# swap targets exist for both, applied consistently from ONE payload-level
# decision (see _distinct_payload_countries), not re-derived per batch.
# ---------------------------------------------------------------------------

_MULTI_COUNTRY_FRAMING = (
    "This survey spans multiple country programmes (mostly\n"
    "in Africa, plus a Vietnam crop-insurance programme and a small Latin America\n"
    "sample) analyzed together as one combined client portfolio; it is not a\n"
    "single-country survey."
)

_SINGLE_COUNTRY_FRAMING = (
    "This report is scoped to a single country programme for this run; "
    "every response below is from that one country."
)

_MULTI_COUNTRY_CANDIDATE_DIVERSITY = (
    "  - Diverse: where possible, vary sex, is_claimant, is_caregiver, AND country"
)
_SINGLE_COUNTRY_CANDIDATE_DIVERSITY = (
    "  - Diverse: where possible, vary sex, is_claimant, and is_caregiver"
)

_MULTI_COUNTRY_FINAL_PICK_DIVERSITY = (
    "  - Diverse: where possible, vary sex, is_claimant, is_caregiver, AND country\n"
    "  - Do NOT pick all 3 verbatims for a section from the same country if\n"
    "    substantive, relevant candidates from other countries are available -- this\n"
    "    survey spans multiple country programmes and the report must reflect that,\n"
    "    not read as if it were about a single country\n"
    "  - Country diversity is secondary to topical relevance and substance -- never\n"
    "    pick a weaker or less relevant candidate purely to hit a different country"
)
_SINGLE_COUNTRY_FINAL_PICK_DIVERSITY = (
    "  - Diverse: where possible, vary sex, is_claimant, and is_caregiver"
)


def _distinct_payload_countries(payload: dict) -> set:
    """Every non-null `country` value appearing anywhere in the payload."""
    countries = set()
    for group in payload.values():
        if not isinstance(group, list):
            continue
        for rec in group:
            country = rec.get("country") if isinstance(rec, dict) else None
            if country:
                countries.add(country)
    return countries


def _is_single_country_payload(payload: dict) -> bool:
    return len(_distinct_payload_countries(payload)) == 1


# ---------------------------------------------------------------------------
# Batch tagging prompt (per-slice: NPS theme tagging, protection-flag scan,
# verbatim candidate shortlist, not-worth-it classification)
# ---------------------------------------------------------------------------

def _build_batch_prompt(is_single_country: bool) -> str:
    framing = _SINGLE_COUNTRY_FRAMING if is_single_country else _MULTI_COUNTRY_FRAMING
    diversity = _SINGLE_COUNTRY_CANDIDATE_DIVERSITY if is_single_country else _MULTI_COUNTRY_CANDIDATE_DIVERSITY

    return f"""
You are an expert microinsurance survey analyst for VisionFund International,
analyzing open-ended survey responses from the VisionFund Insurance Impact
Survey. {framing}

You are processing ONE BATCH of NPS follow-up responses ("Why did you give
this score?") out of several batches covering the full survey -- this is a
chunk, not the whole dataset. A later synthesis pass combines every batch's
output, so you do not need (and should not try) to see the whole picture.

## INPUT FORMAT

A JSON payload with one key, "nps_responses": a list of records, each with:
  id, text, sex, client_age, branch, country, is_claimant, is_caregiver,
  is_female, nps_group ("promoter"|"passive"|"detractor"), nps_score,
  worth_premium_value, not_worth_it (bool -- already computed, not something
  you need to determine)

All responses are already in English.

## YOUR TASKS (for every record in this batch)

### TASK 1: NPS Theme Tagging and Sentiment
For each response assign 1-3 theme codes from the THEME TAXONOMY below,
AND an overall sentiment: "positive", "negative", or "neutral". This is
the respondent's sentiment about VisionFund's insurance product or
service, judged from what they actually wrote -- NOT a shortcut from
their nps_group. A detractor's response can still be neutral or even
positive in tone (e.g. a specific, non-hostile suggestion); a promoter's
can carry a real complaint alongside the praise. Read the text.
Return compact arrays: ["row_id", ["theme1", "theme2"], "sentiment"],
bucketed by each record's own nps_group into
"promoters"/"passives"/"detractors".

### TASK 2: Protection Flag Scan
Scan every response in this batch for the PROTECTION FLAG TAXONOMY below.

### TASK 3: Verbatim Candidate Shortlist
For EACH of the 7 report sections below, shortlist up to {_CANDIDATES_PER_SECTION_PER_BATCH}
candidate row IDs from THIS BATCH that could be a good quote for that
section (a shortlist, not the final pick -- a later synthesis pass chooses
the final 3 per section from every batch's shortlist combined). It is fine
and expected to shortlist 0 for a section if nothing in this batch fits.
{_VERBATIM_CRITERIA_BLOCK}
{diversity}
  - Do NOT repeat the same row_id across sections

For each candidate, include a one-sentence "note" explaining why it fits
the section -- the synthesis pass will use this note (not just the id) to
make its final choice without re-reading your reasoning.

### TASK 4: "Not Worth It" Classification
For every record in this batch with not_worth_it=true, classify it as
"pricing" (concerns about premium cost or value perception) or "service"
(concerns about claims process, delays, unclear coverage, staff), with a
one-sentence reason. A later synthesis pass clusters these across every
batch into the final ranked themes -- you are only classifying this batch's
own records, not deciding the final theme list.

{_THEME_TAXONOMY_BLOCK}

{_PROTECTION_FLAG_TAXONOMY_BLOCK}

{_REPORT_SECTIONS_BLOCK}

## STYLE

In every free-text field you write (reason, note, one_line_reason), never use
an em dash or en dash. Use a comma, colon, semicolon, parentheses, or a new
sentence instead.

## OUTPUT SCHEMA

Return ONLY valid JSON. No markdown, no explanation, no extra keys.

{{
  "nps_tags": {{
    "promoters": [["row_0042", ["staff_service", "general_satisfaction"], "positive"], ...],
    "passives":  [["row_0105", ["financial_relief"], "neutral"], ...],
    "detractors":[["row_0201", ["claims_process", "staff_service"], "negative"], ...]
  }},
  "protection_flags": [
    {{"id": "row_...", "flag_type": "staff_misconduct", "severity": "medium", "reason": "one sentence"}}
  ],
  "verbatim_candidates": {{
    "part1": [{{"id": "row_...", "note": "why this fits part1"}}],
    "part2": [...], "part3": [...], "part4": [...], "part5": [...], "part6": [...], "part7": [...]
  }},
  "not_worth_it_candidates": [
    {{"id": "row_...", "type_guess": "pricing", "one_line_reason": "..."}}
  ]
}}
"""


# ---------------------------------------------------------------------------
# Synthesis prompt (whole-payload-view tasks, run once)
# ---------------------------------------------------------------------------

def _build_data_quality_flag_block(excluded_countries: "list[str] | None") -> str:
    """See data_quality_flags.py's module docstring: a flagged country's
    data stays in every aggregate figure, but is excluded from quote
    selection and from headline-claim citation pending human review.
    Empty string (no block at all) when no flags are active, so a normal
    run's prompt isn't cluttered with a section about nothing."""
    if not excluded_countries:
        return ""
    countries_str = ", ".join(excluded_countries)
    return f"""
## DATA QUALITY FLAG

The following countries have an active data-quality flag on this run: {countries_str}.
Their responses still count normally in nps_theme_counts and every aggregate
figure you were given -- do NOT exclude them from tagging, theme counts, or
sub-theme clustering; do NOT mention that a flag exists in your prose. However:
  - Do NOT select a row_id from these countries for section_verbatims, even
    from claim_no_reason_other/claim_challenges_other_support/sparse_other
    below -- pick the next-best candidate instead.
  - Do NOT cite these countries by name, or describe a specific finding
    sourced from them, in top_findings, executive_summary, or top_actions --
    a data quality concern flags their INDIVIDUAL responses for exclusion
    from headline/example use pending human review, though their data
    remains in every aggregate statistic you were given.
"""


def _build_synthesis_prompt(is_single_country: bool, excluded_countries: "list[str] | None" = None) -> str:
    framing = _SINGLE_COUNTRY_FRAMING if is_single_country else _MULTI_COUNTRY_FRAMING
    diversity = _SINGLE_COUNTRY_FINAL_PICK_DIVERSITY if is_single_country else _MULTI_COUNTRY_FINAL_PICK_DIVERSITY
    flag_block = _build_data_quality_flag_block(excluded_countries)

    return f"""
You are an expert microinsurance survey analyst for VisionFund International,
finishing the analysis of the VisionFund Insurance Impact Survey's
open-ended responses. {framing} All responses are already in English.

An earlier pass already read every NPS follow-up response (the largest
response group) in batches: it tagged themes, scanned for protection
flags, shortlisted verbatim candidates per report section, and classified
"not worth it" responses as pricing- or service-related. You are now given
that earlier pass's pooled output, PLUS the full text of the two remaining
(much smaller) response groups this survey collected, which nothing has
read yet. Your job is to finish the analysis using both.

## INPUT FORMAT

A JSON payload with:
- claim_no_reason_other: why client did not file a claim despite having an
  insured event (full records, unread so far)
- claim_challenges_other_support: challenges experienced when claiming +
  support needed (full records, unread so far)
- sparse_other: other open-ended questions, misc, low volume (full records,
  unread so far)
- verbatim_candidates: per report section, the pooled shortlist from every
  NPS batch (id, text, and enrichment fields, plus each batch's "note" on
  why it was shortlisted)
- not_worth_it_candidates: every not_worth_it=true NPS response (id, text,
  enrichment fields, plus the earlier pass's pricing/service classification
  and one-line reason)
- nps_protection_flags_found: protection flags already found among NPS
  responses by the earlier pass -- for your context only, informing the
  executive summary; do not re-flag these, you are not re-scanning NPS
  responses
- nps_theme_counts: theme code frequency among promoters/passives/detractors
  from the earlier pass -- for your context only, grounding the executive
  summary in the actual tagged distribution

Each claim_no_reason_other / claim_challenges_other_support /
sparse_other record has: id, text, source_column, sex, client_age, branch,
country, is_claimant, is_caregiver, is_female (sparse_other additionally has
question_context).
{flag_block}
## YOUR TASKS

### TASK 1: Claims Other Tagging
Read every response in claim_no_reason_other and claim_challenges_other_support.
For each assign:
  - 1-3 theme codes from the THEME TAXONOMY below
  - sentiment: "positive" | "negative" | "neutral"
  - protection_flag: one flag code from the PROTECTION FLAG TAXONOMY below, or null
Return full objects (not compact arrays) because volume is low.

### TASK 2: "Not Worth It" Sub-themes
Cluster not_worth_it_candidates (every one already classified pricing vs
service by the earlier pass) into the top improvement themes, separately
for "pricing" and "service". Return up to 5 themes total with: label, type
("pricing"|"service"), summary (1 sentence), representative_ids (2-3 row
IDs drawn from not_worth_it_candidates). If fewer than 3 candidates exist,
return what you have.

### TASK 3: "Other" Column Sub-themes
For claim_no_reason_other and claim_challenges_other_support, identify sub-themes.
Use RAW COUNTS not percentages (volume is low).
Flag claim_challenges sub-themes that suggest client protection or staff conduct
concerns with is_protection_concern: true.
Return: label, count, is_protection_concern, representative_ids (1-2 row IDs).

### TASK 4: Final Verbatim Selection + Section Insights

For EACH of the 7 report sections below, do two things:

**A. Pick exactly 3 row IDs (verbatim quotes)**, from EITHER source: the
section's pooled verbatim_candidates (drawn from NPS responses, each with
the earlier pass's note), OR your own direct reading of
claim_no_reason_other/claim_challenges_other_support/sparse_other above --
whichever produces the best 3 for that section.
{_VERBATIM_CRITERIA_BLOCK}
{diversity}
  - Do NOT repeat the same row_id across sections
  - If fewer than 3 good candidates exist across both sources, pick the best available

**B. Produce a section insight**, drawing on the pooled candidates' notes,
your own direct reading of the three small groups above, and
nps_theme_counts:
  - theme_summary: 1-2 sentences naming the dominant theme(s) for this section
  - top_drivers: 1-2 short, human-readable labels for the biggest driver(s)
    behind that theme (e.g. "product value for money", "slow payout",
    "lack of premium clarity"). Never write a raw THEME TAXONOMY code
    (e.g. "claims_process") as a label -- readers see this value directly,
    describe the driver in plain words even when a taxonomy code covers
    the same idea
  - sentiment_split: your best-judgment approximate counts of
    {{"positive": n, "negative": n, "neutral": n}} among the material you
    reviewed for this section. Low counts are fine for low-volume sections
    (report what you actually see, do not pad numbers)

{_REPORT_SECTIONS_BLOCK}

### TASK 5: Protection Flags (remaining groups)
Scan claim_no_reason_other, claim_challenges_other_support, and sparse_other
(NOT the NPS groups -- those were already scanned) for the PROTECTION FLAG
TAXONOMY below.

### TASK 6: Executive Summary
Write 3-5 sentences covering:
  1. What do promoters most value? (use nps_theme_counts + verbatim_candidates)
  2. What are detractors' main pain points? (use nps_theme_counts + verbatim_candidates)
  3. Any notable client protection signals? (consider nps_protection_flags_found
     AND whatever you found in Task 5)
  4. One forward-looking recommendation.

Also produce, separately from the prose above:
  top_findings: exactly 3 short (1 sentence each) qualitative findings, ranked
    most important first -- the biggest patterns across everything you
    reviewed (not just NPS), e.g. a recurring driver of dissatisfaction, a
    strong positive theme, or a notable gap in understanding. Each must be a
    specific, evidence-grounded observation, not a generic statement.
  top_actions: exactly 3 short (1 sentence each) recommended actions for
    VisionFund, ranked most important first, each one clearly traceable to
    one of your top_findings or a protection flag -- concrete and
    operational (e.g. "Retrain branch staff on X"), not vague aspirations
    (e.g. not "improve communication"). If an action names a specific
    country, it must be one this survey actually covers (see the opening
    paragraph above); never recommend an action for a country this survey
    does not cover.

{_THEME_TAXONOMY_BLOCK}

{_PROTECTION_FLAG_TAXONOMY_BLOCK}

## STYLE

In every free-text field you write (reason, summary, theme_summary,
executive_summary, top_findings, top_actions, label), never use an em dash
or en dash. Use a comma, colon, semicolon, parentheses, or a new sentence
instead.

Describe correlations and group differences as associations only, never as
one thing driving, causing, or determining another -- this is
cross-sectional survey data, and the design does not support causal
inference. Do not use, outside a quoted client verbatim: drive, drives,
drove, driver, cause, causes, caused, leads to, determines, improves,
reduces, strengthens, underpins, eases, translates into, lever, or impact
as a verb. Say "X is associated with Y," not "X drives Y." Say "the factor
most strongly associated," not "the strongest driver." Describe a group
difference as what was observed (e.g. "claimants reported higher child
wellbeing than those who did not file"), never as what one group's status
did to produce the other's outcome. This applies to executive_summary and
top_findings specifically, where a single-sentence claim about the whole
client base is most likely to overstate what the data supports.

## OUTPUT SCHEMA

Return ONLY valid JSON. No markdown, no explanation, no extra keys.

{{
  "claims_other_tagged": {{
    "claim_no_reason_other": [
      {{"id": "row_...", "themes": ["..."], "sentiment": "...", "protection_flag": null}}
    ],
    "claim_challenges_other_support": [
      {{"id": "row_...", "themes": ["..."], "sentiment": "...", "protection_flag": "staff_misconduct"}}
    ]
  }},
  "not_worth_it_themes": [
    {{"label": "descriptive name", "type": "pricing", "summary": "one sentence",
     "representative_ids": ["row_...", "row_..."]}}
  ],
  "other_subthemes": {{
    "claim_no_reason_other": [
      {{"label": "...", "count": 8, "is_protection_concern": false, "representative_ids": ["row_..."]}}
    ],
    "claim_challenges_other_support": [
      {{"label": "...", "count": 5, "is_protection_concern": true, "representative_ids": ["row_..."]}}
    ]
  }},
  "section_verbatims": {{
    "part1": ["row_...", "row_...", "row_..."],
    "part2": ["row_...", "row_...", "row_..."],
    "part3": ["row_...", "row_...", "row_..."],
    "part4": ["row_...", "row_...", "row_..."],
    "part5": ["row_...", "row_...", "row_..."],
    "part6": ["row_...", "row_...", "row_..."],
    "part7": ["row_...", "row_...", "row_..."]
  }},
  "section_insights": {{
    "part1": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part2": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part3": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part4": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part5": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part6": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}},
    "part7": {{"theme_summary": "...", "top_drivers": ["...", "..."],
              "sentiment_split": {{"positive": 0, "negative": 0, "neutral": 0}}}}
  }},
  "protection_flags": [
    {{"id": "row_...", "column": "sparse_other", "flag_type": "staff_misconduct",
     "severity": "medium", "reason": "one sentence"}}
  ],
  "executive_summary": "3-5 sentences",
  "top_findings": ["finding 1", "finding 2", "finding 3"],
  "top_actions": ["action 1", "action 2", "action 3"]
}}
"""


# ---------------------------------------------------------------------------
# LLM call helper with retry/backoff -- shared by every batch call and the
# synthesis call.
# ---------------------------------------------------------------------------

def _call_with_retries(
    provider: str, api_key: str, system_prompt: str, user_content: str,
    max_output_tokens: int, temperature: float, model: str,
    max_retries: int, retry_delay_seconds: int, call_label: str,
) -> str:
    last_exc = None
    for attempt in range(max_retries + 1):
        try:
            return call_llm(
                provider=provider, api_key=api_key, system_prompt=system_prompt,
                user_content=user_content, max_output_tokens=max_output_tokens,
                temperature=temperature, model=model,
            )
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries:
                delay = retry_delay_seconds * (2 ** attempt)
                log.warning(f"{call_label}: attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                log.error(f"{call_label}: all {max_retries + 1} attempts failed: {exc}")
    raise RuntimeError(f"{call_label} failed after {max_retries + 1} attempts: {last_exc}") from last_exc


def _chunk(items: list, size: int) -> list:
    return [items[i:i + size] for i in range(0, len(items), size)]


_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _dedupe_protection_flags(flags: list) -> list:
    """Collapse duplicate protection flags on the same (id, column, flag_type).

    The synthesis call is handed nps_protection_flags_found (flags the batch
    phase already scanned out of the NPS records) as context for its own
    whole-payload protection scan -- but nothing stops it from re-emitting
    the same case in its own protection_flags list, sometimes at a different
    severity than the batch phase assigned. Left unmerged, that produces the
    same client counted twice in the report's totals (once per source list),
    occasionally in two different severity tiers for the same underlying
    complaint. A genuinely distinct second concern about the same respondent
    (a different flag_type, OR the same flag_type from a different source
    column) is kept -- only the same (id, column, flag_type) triple is
    collapsed, keeping the higher-severity copy (ties keep whichever was
    seen first, which is the batch-phase copy since it's concatenated
    first).

    R-018 (docs/report_spec.md, session-9): "column" joined the key
    because "id" alone is one-per-RESPONDENT, not one-per-(respondent,
    column) -- prepare_payload.py's row_id = f"row_{idx:04d}" depends
    only on the respondent's dataframe index, so a respondent who answers
    two different open-ended questions produces two records sharing one
    id. Keying on (id, flag_type) alone silently collapsed two genuinely
    different concerns raised by the same respondent in two different
    source columns whenever they happened to share a flag_type -- found
    on real data (row_1015: an NPS-phase "could never use the insurance"
    complaint and a claims-other-phase complaint specifically naming a
    second affected person, the client's daughter, both unfair_claim_
    denial, collapsing to one and losing the daughter detail). Every flag
    dict reaching this function already carries "column" -- batch-phase
    flags get it from call_gemini() via NPS_GROUP_TO_COLUMN before this
    runs; synthesis-phase flags carry it directly, since the synthesis
    OUTPUT SCHEMA already asks for it and the model already complies --
    so this needed no prompt change.
    """
    best: dict[tuple, dict] = {}
    order: list[tuple] = []
    for flag in flags:
        key = (flag.get("id"), flag.get("column"), flag.get("flag_type"))
        existing = best.get(key)
        if existing is None:
            best[key] = flag
            order.append(key)
            continue
        existing_rank = _SEVERITY_RANK.get((existing.get("severity") or "").lower(), 0)
        new_rank = _SEVERITY_RANK.get((flag.get("severity") or "").lower(), 0)
        if new_rank > existing_rank:
            best[key] = flag
    return [best[key] for key in order]


# ---------------------------------------------------------------------------
# Per-record classification cache (see qualitative/tag_cache.py) -- applied
# to NPS theme tags and protection flags only, the two fields observed to
# drift between regenerations of identical data. A cached record's decision
# from a PRIOR run always overrides whatever this run's fresh LLM call just
# produced for it; a record seen for the first time has its fresh decision
# written to the cache so the NEXT run is stable too.
# ---------------------------------------------------------------------------

# Sentinel stored in the cache to mean "this record was scanned for a
# protection flag and confirmed to have none" -- distinct from "never
# scanned" (a plain cache miss, tag_cache.get() returns None either way a
# key is absent OR its value is JSON null, so an explicit marker is needed
# to make "no flag" itself a cacheable, stable fact rather than defaulting
# to "unknown, re-decide every time").
_NO_FLAG = {"_no_flag": True}


def _apply_theme_tag_cache(entries: list, by_id: dict, cache: dict) -> list:
    """entries: a batch's (or the merged) [row_id, [theme, ...], sentiment]
    triples. Returns the same shape with any previously-cached record's
    themes AND sentiment substituted in place of this run's fresh tags
    (both are cached together under one entry, since they come from the
    same Task 1 judgment call and should drift -- or not -- together), and
    populates the cache for records seen for the first time.

    A 2-element entry (no sentiment -- malformed model output, or a raw
    response saved before this field existed) is passed through
    unchanged, uncached: there is no sentiment value to cache or restore
    for it, and guessing one would defeat the point of a real base_n
    (R-006a, docs/report_spec.md)."""
    out = []
    for entry in entries:
        if not (isinstance(entry, list) and len(entry) == 3):
            out.append(entry)
            continue
        row_id, themes, sentiment = entry
        text = (by_id.get(row_id) or {}).get("text", "")
        cached = tag_cache.get(cache, "theme", row_id, text)
        if cached is not None:
            out.append([row_id, cached["themes"], cached["sentiment"]])
        else:
            tag_cache.put(cache, "theme", row_id, text, {"themes": themes, "sentiment": sentiment})
            out.append([row_id, themes, sentiment])
    return out


def _apply_protection_flag_cache(scanned_records: list, found_flags: list, cache: dict) -> list:
    """scanned_records: every record actually scanned for a protection flag
    this pass (regardless of outcome) -- must be the full scanned set, not
    just the flagged ones, so "checked, no flag" is itself a stable cached
    fact and a record can't silently gain a flag on a later run just
    because this pass's cache lookup only ever saw the flagged subset.
    found_flags: the flag dicts this pass's LLM call actually produced.
    Returns the flag list to use for this run, with any previously-cached
    record's flag decision (flagged or not) substituted for this run's
    fresh one.

    R-029 (docs/report_spec.md, session-9): found_by_id used to key on
    "id" alone -- weaker than R-018's (id, column, flag_type) dedup key
    it sits downstream of, and row_id is one-per-RESPONDENT, not
    one-per-(respondent, column) (see _record_column()'s docstring). A
    respondent with a record in two scanned groups (e.g. an NPS response
    and a claims-other response) appears twice in scanned_records; an
    id-only lookup handed BOTH instances the same flag object regardless
    of which one it actually came from, so a single real flag got
    appended to `out` twice. Observed live in this run's own saved
    output before this fix: row_0841 and row_1015 each appeared twice,
    byte-identical. Keyed by (id, column) now, using each scanned
    record's own resolved column, so only the record that actually
    matches a found flag's column claims it.
    """
    found_by_id = {(f["id"], f.get("column")): f for f in found_flags if f.get("id")}
    out = []
    for rec in scanned_records:
        record_id = rec.get("id")
        rec_column = _record_column(rec)
        text = rec.get("text", "")
        cached = tag_cache.get(cache, "flag", record_id, text)
        if cached is not None:
            if cached != _NO_FLAG:
                out.append(cached)
            continue
        fresh = found_by_id.get((record_id, rec_column))
        tag_cache.put(cache, "flag", record_id, text, fresh if fresh else _NO_FLAG)
        if fresh:
            out.append(fresh)
    return out


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def call_gemini(
    payload: dict,
    raw_response_path: Path,
    model: "str | None" = "gemini-2.5-pro",
    max_retries: int = 2,
    retry_delay_seconds: int = 30,
    provider: str = "gemini",
    api_key: "str | None" = None,
    excluded_countries: "list[str] | None" = None,
) -> dict:
    """
    Run the qualitative-tagging pipeline: batch-tag NPS responses, then
    synthesize everything (including the small remaining groups) into the
    final result. See this module's docstring for the full rationale.

    Args:
        payload:            Dict built by prepare_payload.build_payload()
        raw_response_path:  Path to save the FINAL merged raw dict (also
                             used by run_qualitative.py --parse-only). Each
                             sub-call's own raw response is additionally
                             saved alongside it as
                             "{stem}.batch_N.json" / "{stem}.synthesis.json"
                             for debugging.
        model:              Model name (defaults per-provider if not given)
        max_retries:        Retry attempts per sub-call (batch or synthesis)
        retry_delay_seconds: Seconds to wait between retries (exponential backoff)
        provider:           "gemini" | "anthropic" | "openai"
        api_key:            API key for the chosen provider. Falls back to the
                             GEMINI_API_KEY env var when provider="gemini" and
                             no key is passed, for standalone CLI use.
        excluded_countries: Countries with an active data_quality_flags.py
                             flag on this run (see that module's docstring).
                             Their tagging/theme-count contribution is
                             unaffected -- only quote/verbatim eligibility.
                             NPS-sourced candidate pools are filtered here in
                             Python (deterministic, not dependent on the
                             model following an instruction); the small
                             claims_other/sparse_other groups are sent to
                             synthesis un-filtered (still tagged normally)
                             with an explicit instruction not to quote from
                             them -- see _build_data_quality_flag_block().

    Returns:
        Final dict matching parse_results.REQUIRED_TOP_KEYS, unchanged shape
        from the original single-call design.
    """
    if api_key is None:
        if provider == "gemini":
            import os
            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "No API key provided for provider "
                f"{provider!r}. Pass api_key=..., or for Gemini set "
                "$env:GEMINI_API_KEY = 'your_key_here'"
            )

    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    single_country = _is_single_country_payload(payload)
    excluded_set = set(excluded_countries or [])
    if excluded_set:
        log.info(f"Data quality flags active -- excluding from quote selection: {sorted(excluded_set)}")

    tag_cache_data = tag_cache.load()
    cache_size_before = len(tag_cache_data)

    # ---- Phase 1: batch-tag the NPS responses -----------------------------
    all_nps = payload.get("nps_promoters", []) + payload.get("nps_passives", []) + payload.get("nps_detractors", [])
    by_id = {rec["id"]: rec for rec in all_nps}
    batches = _chunk(all_nps, _NPS_BATCH_SIZE)
    log.info(f"Qualitative: {len(all_nps)} NPS responses split into {len(batches)} batch(es) of up to {_NPS_BATCH_SIZE}")

    batch_prompt = _build_batch_prompt(single_country)
    merged_nps_tags = {"promoters": [], "passives": [], "detractors": []}
    nps_protection_flags = []
    pooled_candidates = {f"part{i}": [] for i in range(1, 8)}
    pooled_not_worth_it = []
    batch_failures = []

    for i, batch_records in enumerate(batches):
        batch_path = raw_response_path.with_name(f"{raw_response_path.stem}.batch_{i}.json")
        try:
            result_text = _call_with_retries(
                provider=provider, api_key=api_key, system_prompt=batch_prompt,
                user_content=json.dumps({"nps_responses": batch_records}, ensure_ascii=False),
                # temperature=0 (was 0.2): this is a classification task, not
                # creative writing -- lower temperature reduces first-time
                # tagging disagreement, complementing (not replacing) the
                # tag cache above, which is what actually guarantees
                # stability for a record already seen once.
                max_output_tokens=65536, temperature=0.0, model=model,
                max_retries=max_retries, retry_delay_seconds=retry_delay_seconds,
                call_label=f"NPS batch {i + 1}/{len(batches)}",
            )
        except Exception as exc:
            batch_failures.append((i, str(exc)))
            continue

        batch_path.write_text(result_text, encoding="utf-8")
        try:
            batch_result = json.loads(result_text)
        except json.JSONDecodeError as exc:
            batch_failures.append((i, f"invalid JSON: {exc}"))
            continue

        nps_tags = batch_result.get("nps_tags", {})
        for grp in ("promoters", "passives", "detractors"):
            fresh_entries = nps_tags.get(grp, [])
            merged_nps_tags[grp].extend(_apply_theme_tag_cache(fresh_entries, by_id, tag_cache_data))

        # Deliberately uncached here -- the SAME id can be re-flagged later
        # by the synthesis call too (it's handed nps_protection_flags_found
        # as context and can re-emit a case at a different severity; see
        # _dedupe_protection_flags()), so caching must happen once, after
        # both phases and after dedup reconciles same-id duplicates into
        # one canonical decision, not per-source (see below).
        for flag in batch_result.get("protection_flags", []):
            rec = by_id.get(flag.get("id"))
            column = NPS_GROUP_TO_COLUMN.get(rec.get("nps_group")) if rec else None
            nps_protection_flags.append({**flag, "column": column or "nps"})

        for section, candidates in (batch_result.get("verbatim_candidates") or {}).items():
            if section not in pooled_candidates:
                continue
            for cand in candidates:
                rec = by_id.get(cand.get("id"))
                if rec is None or rec.get("country") in excluded_set:
                    continue  # data-quality-flagged countries are never quote candidates
                pooled_candidates[section].append({**rec, "note": cand.get("note", "")})

        for nwi in batch_result.get("not_worth_it_candidates", []):
            rec = by_id.get(nwi.get("id"))
            if rec is None or rec.get("country") in excluded_set:
                continue  # same exclusion -- representative_ids are quote-like citations
            pooled_not_worth_it.append({
                **rec,
                "type_guess": nwi.get("type_guess"),
                "one_line_reason": nwi.get("one_line_reason", ""),
            })

        log.info(f"NPS batch {i + 1}/{len(batches)} tagged ({len(batch_records)} records)")

    if batch_failures and len(batch_failures) == len(batches):
        raise RuntimeError(f"All {len(batches)} NPS batches failed: {batch_failures}")
    if batch_failures:
        log.warning(
            f"{len(batch_failures)}/{len(batches)} NPS batches failed and were skipped "
            f"(partial NPS tagging coverage): {batch_failures}"
        )

    # theme_counts for executive-summary grounding -- cheap to compute here
    # in Python (same logic parse_results.py's _count_themes uses) rather
    # than asking the synthesis call to re-derive it from raw tags.
    from collections import Counter
    nps_theme_counts = {}
    for grp in ("promoters", "passives", "detractors"):
        counter = Counter()
        for entry in merged_nps_tags[grp]:
            if isinstance(entry, list) and len(entry) in (2, 3) and isinstance(entry[1], list):
                counter.update(entry[1])
        nps_theme_counts[grp] = dict(counter.most_common())

    # ---- Phase 2: synthesis -------------------------------------------------
    synthesis_prompt = _build_synthesis_prompt(single_country, excluded_countries=sorted(excluded_set) or None)
    synthesis_input = {
        "claim_no_reason_other": payload.get("claim_no_reason_other", []),
        "claim_challenges_other_support": payload.get("claim_challenges_other_support", []),
        "sparse_other": payload.get("sparse_other", []),
        "verbatim_candidates": pooled_candidates,
        "not_worth_it_candidates": pooled_not_worth_it,
        "nps_protection_flags_found": nps_protection_flags,
        "nps_theme_counts": nps_theme_counts,
    }

    result_text = _call_with_retries(
        provider=provider, api_key=api_key, system_prompt=synthesis_prompt,
        user_content=json.dumps(synthesis_input, ensure_ascii=False),
        max_output_tokens=65536, temperature=0.0, model=model,
        max_retries=max_retries, retry_delay_seconds=retry_delay_seconds,
        call_label="Qualitative synthesis",
    )
    synthesis_path = raw_response_path.with_name(f"{raw_response_path.stem}.synthesis.json")
    synthesis_path.write_text(result_text, encoding="utf-8")

    try:
        synthesis = json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"{provider} synthesis response is not valid JSON. "
            f"Raw text saved to {synthesis_path}. Error: {exc}"
        ) from exc

    # Reconcile same-id duplicates ACROSS sources first (a batch call and
    # the synthesis call can both flag the same id, sometimes at different
    # severities -- see _dedupe_protection_flags()), producing one
    # canonical fresh decision per id for this run. Cache stability is then
    # applied on top of that reconciled result, once, over the full
    # universe of records either phase could have scanned (every NPS
    # record, plus the three small "other" groups synthesis's Task 5
    # scans) -- not per-source, so a record can't be double-counted under
    # two different cache namespaces or have a cross-phase re-flag bypass
    # caching entirely.
    other_group_records = (
        payload.get("claim_no_reason_other", [])
        + payload.get("claim_challenges_other_support", [])
        + payload.get("sparse_other", [])
    )
    reconciled_flags = _dedupe_protection_flags(
        nps_protection_flags + synthesis.get("protection_flags", [])
    )
    stable_flags = _apply_protection_flag_cache(
        all_nps + other_group_records, reconciled_flags, tag_cache_data
    )

    final = {
        "nps_tags": merged_nps_tags,
        "claims_other_tagged": synthesis.get("claims_other_tagged", {}),
        "not_worth_it_themes": synthesis.get("not_worth_it_themes", []),
        "other_subthemes": synthesis.get("other_subthemes", {}),
        "section_verbatims": synthesis.get("section_verbatims", {}),
        "section_insights": synthesis.get("section_insights", {}),
        "protection_flags": stable_flags,
        "executive_summary": synthesis.get("executive_summary", ""),
        "top_findings": synthesis.get("top_findings", []),
        "top_actions": synthesis.get("top_actions", []),
    }

    raw_response_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Final merged qualitative response saved to {raw_response_path}")

    tag_cache.save(tag_cache_data)
    log.info(
        f"Qualitative tag cache: {cache_size_before} entries before this run, "
        f"{len(tag_cache_data)} after ({len(tag_cache_data) - cache_size_before} new)"
    )

    return final
