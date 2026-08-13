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

SEVERITY RUBRIC (apply these impact criteria to the specific case FIRST — do
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
  part1 — Product Understanding: coverage/claims knowledge gaps, education
  part2 — Claims Experience: filing experience, challenges, coping
  part3 — Financial Inclusion: first insurance access, safety net
  part4 — Client Voice: NPS drivers, promoter/detractor reasons, value
  part5 — Child Wellbeing: impact on children, family, caregivers
  part6 — Claimant Outcomes: lived experience of making a claim
  part7 — Gender: gendered experience, female or male-specific challenges"""

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
    "sample) analyzed together as one combined client portfolio — it is not a\n"
    "single-country survey."
)

_SINGLE_COUNTRY_FRAMING = (
    "This report is scoped to a single country programme for this run — "
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

### TASK 1 — NPS Theme Tagging
For each response assign 1-3 theme codes from the THEME TAXONOMY below.
Return compact arrays: ["row_id", ["theme1", "theme2"]], bucketed by each
record's own nps_group into "promoters"/"passives"/"detractors".

### TASK 2 — Protection Flag Scan
Scan every response in this batch for the PROTECTION FLAG TAXONOMY below.

### TASK 3 — Verbatim Candidate Shortlist
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

### TASK 4 — "Not Worth It" Classification
For every record in this batch with not_worth_it=true, classify it as
"pricing" (concerns about premium cost or value perception) or "service"
(concerns about claims process, delays, unclear coverage, staff), with a
one-sentence reason. A later synthesis pass clusters these across every
batch into the final ranked themes -- you are only classifying this batch's
own records, not deciding the final theme list.

{_THEME_TAXONOMY_BLOCK}

{_PROTECTION_FLAG_TAXONOMY_BLOCK}

{_REPORT_SECTIONS_BLOCK}

## OUTPUT SCHEMA

Return ONLY valid JSON. No markdown, no explanation, no extra keys.

{{
  "nps_tags": {{
    "promoters": [["row_0042", ["staff_service", "general_satisfaction"]], ...],
    "passives":  [["row_0105", ["financial_relief"]], ...],
    "detractors":[["row_0201", ["claims_process", "staff_service"]], ...]
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

def _build_synthesis_prompt(is_single_country: bool) -> str:
    framing = _SINGLE_COUNTRY_FRAMING if is_single_country else _MULTI_COUNTRY_FRAMING
    diversity = _SINGLE_COUNTRY_FINAL_PICK_DIVERSITY if is_single_country else _MULTI_COUNTRY_FINAL_PICK_DIVERSITY

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

## YOUR TASKS

### TASK 1 — Claims Other Tagging
Read every response in claim_no_reason_other and claim_challenges_other_support.
For each assign:
  - 1-3 theme codes from the THEME TAXONOMY below
  - sentiment: "positive" | "negative" | "neutral"
  - protection_flag: one flag code from the PROTECTION FLAG TAXONOMY below, or null
Return full objects (not compact arrays) because volume is low.

### TASK 2 — "Not Worth It" Sub-themes
Cluster not_worth_it_candidates (every one already classified pricing vs
service by the earlier pass) into the top improvement themes, separately
for "pricing" and "service". Return up to 5 themes total with: label, type
("pricing"|"service"), summary (1 sentence), representative_ids (2-3 row
IDs drawn from not_worth_it_candidates). If fewer than 3 candidates exist,
return what you have.

### TASK 3 — "Other" Column Sub-themes
For claim_no_reason_other and claim_challenges_other_support, identify sub-themes.
Use RAW COUNTS not percentages (volume is low).
Flag claim_challenges sub-themes that suggest client protection or staff conduct
concerns with is_protection_concern: true.
Return: label, count, is_protection_concern, representative_ids (1-2 row IDs).

### TASK 4 — Final Verbatim Selection + Section Insights

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
  - top_drivers: 1-2 short labels for the biggest driver(s) behind that theme.
    Use a THEME TAXONOMY code if one genuinely fits; otherwise a short
    freeform label (e.g. "slow payout", "lack of premium clarity")
  - sentiment_split: your best-judgment approximate counts of
    {{"positive": n, "negative": n, "neutral": n}} among the material you
    reviewed for this section. Low counts are fine for low-volume sections
    (report what you actually see, do not pad numbers)

{_REPORT_SECTIONS_BLOCK}

### TASK 5 — Protection Flags (remaining groups)
Scan claim_no_reason_other, claim_challenges_other_support, and sparse_other
(NOT the NPS groups -- those were already scanned) for the PROTECTION FLAG
TAXONOMY below.

### TASK 6 — Executive Summary
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
    (e.g. not "improve communication").

{_THEME_TAXONOMY_BLOCK}

{_PROTECTION_FLAG_TAXONOMY_BLOCK}

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
                max_output_tokens=65536, temperature=0.2, model=model,
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
            merged_nps_tags[grp].extend(nps_tags.get(grp, []))

        for flag in batch_result.get("protection_flags", []):
            rec = by_id.get(flag.get("id"))
            column = NPS_GROUP_TO_COLUMN.get(rec.get("nps_group")) if rec else None
            nps_protection_flags.append({**flag, "column": column or "nps"})

        for section, candidates in (batch_result.get("verbatim_candidates") or {}).items():
            if section not in pooled_candidates:
                continue
            for cand in candidates:
                rec = by_id.get(cand.get("id"))
                if rec is None:
                    continue
                pooled_candidates[section].append({**rec, "note": cand.get("note", "")})

        for nwi in batch_result.get("not_worth_it_candidates", []):
            rec = by_id.get(nwi.get("id"))
            if rec is None:
                continue
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
            if isinstance(entry, list) and len(entry) == 2 and isinstance(entry[1], list):
                counter.update(entry[1])
        nps_theme_counts[grp] = dict(counter.most_common())

    # ---- Phase 2: synthesis -------------------------------------------------
    synthesis_prompt = _build_synthesis_prompt(single_country)
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
        max_output_tokens=65536, temperature=0.2, model=model,
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

    final = {
        "nps_tags": merged_nps_tags,
        "claims_other_tagged": synthesis.get("claims_other_tagged", {}),
        "not_worth_it_themes": synthesis.get("not_worth_it_themes", []),
        "other_subthemes": synthesis.get("other_subthemes", {}),
        "section_verbatims": synthesis.get("section_verbatims", {}),
        "section_insights": synthesis.get("section_insights", {}),
        "protection_flags": nps_protection_flags + synthesis.get("protection_flags", []),
        "executive_summary": synthesis.get("executive_summary", ""),
        "top_findings": synthesis.get("top_findings", []),
        "top_actions": synthesis.get("top_actions", []),
    }

    raw_response_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Final merged qualitative response saved to {raw_response_path}")

    return final
