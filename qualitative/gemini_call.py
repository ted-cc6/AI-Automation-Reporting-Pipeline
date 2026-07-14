"""qualitative/gemini_call.py

Phase 2: Send payload to an LLM provider, save raw response, return parsed dict.
Provider/api_key are passed in explicitly by the caller (the dashboard backend
threads these through from the user's browser session; the CLI entrypoint in
run_qualitative.py falls back to GEMINI_API_KEY for standalone use).
"""
import json
import logging
import time
from pathlib import Path

from llm_providers import call_llm

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """
You are an expert microinsurance survey analyst for VisionFund International.
You are analyzing open-ended survey responses from the VisionFund Insurance
Impact Survey, 2026 Q2. This survey spans multiple country programmes (mostly
in Africa, plus a Vietnam crop-insurance programme and a small Latin America
sample) analyzed together as one combined client portfolio — it is not a
single-country survey. All responses are already in English.

## INPUT FORMAT

You will receive a JSON payload with these groups:
- nps_promoters: NPS score 9-10, "why did you give this score?"
- nps_passives:  NPS score 7-8
- nps_detractors: NPS score 0-6
- claim_no_reason_other: why client did not file a claim despite having an insured event
- claim_challenges_other_support: challenges experienced when claiming + support needed
- sparse_other: other open-ended questions (misc; low volume)

Each response has:
  id, text, sex, client_age, branch, is_claimant, is_caregiver, is_female
NPS responses additionally have:
  nps_score, worth_premium_value, not_worth_it (bool)

## YOUR TASKS

### TASK 1 — NPS Theme Tagging
Read every response in nps_promoters, nps_passives, and nps_detractors.
For each response assign 1-3 theme codes from the THEME TAXONOMY below.
Return compact arrays: ["row_id", ["theme1", "theme2"]]

### TASK 2 — Claims Other Tagging
Read every response in claim_no_reason_other and claim_challenges_other_support.
For each assign:
  - 1-3 theme codes
  - sentiment: "positive" | "negative" | "neutral"
  - protection_flag: one flag code from the PROTECTION FLAG TAXONOMY, or null
Return full objects (not compact arrays) because volume is low.

### TASK 3 — "Not Worth It" Sub-themes
Among ALL NPS responses where not_worth_it is true (worth_premium_value >= 4),
identify the top improvement themes.
Separate:
  - "pricing": concerns about premium cost or value perception
  - "service": concerns about claims process, delays, unclear coverage, staff
Return up to 5 themes with: label, type ("pricing"|"service"),
summary (1 sentence), representative_ids (2-3 row IDs).
If fewer than 3 "not worth it" responses exist, return what you have.

### TASK 4 — "Other" Column Sub-themes
For claim_no_reason_other and claim_challenges_other_support, identify sub-themes.
Use RAW COUNTS not percentages (volume is low).
Flag claim_challenges sub-themes that suggest client protection or staff conduct
concerns with is_protection_concern: true.
Return: label, count, is_protection_concern, representative_ids (1-2 row IDs).

### TASK 5 — Verbatim Nominations by Report Section
Nominate exactly 3 row IDs per report section (7 sections).
Selection criteria:
  - Text must be substantive (> 20 words, not generic praise)
  - Clearly relevant to the section topic
  - Diverse: where possible, vary sex, is_claimant, and is_caregiver
  - For part5 (child wellbeing): prefer is_caregiver=true responses
  - For part6 (claimant outcomes): prefer is_claimant=true responses
  - For part7 (gender): include at least 1 Female and 1 Male
  - Do NOT repeat the same row_id across sections
  - If fewer than 3 ideal responses exist for a section, nominate best available

Sections:
  part1 — Product Understanding: coverage/claims knowledge gaps, education
  part2 — Claims Experience: filing experience, challenges, coping
  part3 — Financial Inclusion: first insurance access, safety net
  part4 — Client Voice: NPS drivers, promoter/detractor reasons, value
  part5 — Child Wellbeing: impact on children, family, caregivers
  part6 — Claimant Outcomes: lived experience of making a claim
  part7 — Gender: gendered experience, female or male-specific challenges

### TASK 6 — Protection Flags
Scan ALL responses in ALL groups for these concerns:
  mis_selling:            promised benefits not delivered at claim time
  premium_without_consent: premium deducted without client's knowledge/consent
  coercion:               client felt pressured to purchase
  false_information:      agent gave false or misleading information
  unfair_claim_denial:    claim denied without valid explanation
  staff_misconduct:       negligent, unresponsive, or dishonest staff behavior
  data_privacy:           misuse of personal data

Report EVERY instance, even one. These are surfaced as signals, not quantified.
Include: id, column (e.g. "nps_detractors"), flag_type, severity ("high"|"medium"|"low"),
reason (1 sentence quoting or paraphrasing the key phrase).

### TASK 7 — Executive Summary
Write 3-5 sentences covering:
  1. What do promoters most value?
  2. What are detractors' main pain points?
  3. Any notable client protection signals?
  4. One forward-looking recommendation.

## THEME TAXONOMY (use ONLY these codes)

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
complaint_grievance: Specific grievance about service, product, or conduct

## OUTPUT SCHEMA

Return ONLY valid JSON. No markdown, no explanation, no extra keys.

{
  "nps_tags": {
    "promoters": [["row_0042", ["staff_service", "general_satisfaction"]], ...],
    "passives":  [["row_0105", ["financial_relief"]], ...],
    "detractors":[["row_0201", ["claims_process", "staff_service"]], ...]
  },
  "claims_other_tagged": {
    "claim_no_reason_other": [
      {"id": "row_...", "themes": ["..."], "sentiment": "...", "protection_flag": null}
    ],
    "claim_challenges_other_support": [
      {"id": "row_...", "themes": ["..."], "sentiment": "...", "protection_flag": "staff_misconduct"}
    ]
  },
  "not_worth_it_themes": [
    {
      "label": "descriptive name",
      "type": "pricing",
      "summary": "one sentence",
      "representative_ids": ["row_...", "row_..."]
    }
  ],
  "other_subthemes": {
    "claim_no_reason_other": [
      {"label": "...", "count": 8, "is_protection_concern": false, "representative_ids": ["row_..."]}
    ],
    "claim_challenges_other_support": [
      {"label": "...", "count": 5, "is_protection_concern": true, "representative_ids": ["row_..."]}
    ]
  },
  "section_verbatims": {
    "part1": ["row_...", "row_...", "row_..."],
    "part2": ["row_...", "row_...", "row_..."],
    "part3": ["row_...", "row_...", "row_..."],
    "part4": ["row_...", "row_...", "row_..."],
    "part5": ["row_...", "row_...", "row_..."],
    "part6": ["row_...", "row_...", "row_..."],
    "part7": ["row_...", "row_...", "row_..."]
  },
  "protection_flags": [
    {
      "id": "row_...",
      "column": "nps_detractors",
      "flag_type": "staff_misconduct",
      "severity": "medium",
      "reason": "one sentence"
    }
  ],
  "executive_summary": "3-5 sentences"
}
"""


def call_gemini(
    payload: dict,
    raw_response_path: Path,
    model: str | None = "gemini-2.5-pro",
    max_retries: int = 2,
    retry_delay_seconds: int = 30,
    provider: str = "gemini",
    api_key: str | None = None,
) -> dict:
    """
    Send the qualitative analysis payload to an LLM provider.
    Saves raw response JSON to raw_response_path before returning.

    Args:
        payload:            Dict built by prepare_payload.build_payload()
        raw_response_path:  Path to save the raw response (for debugging)
        model:              Model name (defaults per-provider if not given)
        max_retries:        Number of retry attempts on API error
        retry_delay_seconds: Seconds to wait between retries
        provider:           "gemini" | "anthropic" | "openai"
        api_key:            API key for the chosen provider. Falls back to the
                             GEMINI_API_KEY env var when provider="gemini" and
                             no key is passed, for standalone CLI use.

    Returns:
        Parsed dict from the provider's response text
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

    user_message = json.dumps(payload, ensure_ascii=False)

    for attempt in range(max_retries + 1):
        try:
            result_text = call_llm(
                provider=provider,
                api_key=api_key,
                system_prompt=SYSTEM_PROMPT,
                user_content=user_message,
                max_output_tokens=65536,
                temperature=0.2,
                model=model,
            )
            break

        except Exception as exc:
            if attempt < max_retries:
                delay = retry_delay_seconds * (2 ** attempt)
                log.warning(f"Attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                time.sleep(delay)
            else:
                raise RuntimeError(
                    f"Gemini call failed after {max_retries + 1} attempts: {exc}"
                ) from exc

    # Save raw response before parsing (allows re-parse without re-calling)
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(result_text, encoding="utf-8")
    log.info(f"Raw response saved to {raw_response_path}")

    try:
        return json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini response is not valid JSON. "
            f"Raw text saved to {raw_response_path}. Error: {exc}"
        ) from exc
