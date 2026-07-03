# Developer Prompt — Track E: Qualitative Analysis Pipeline
# Files to create:
#   qualitative/__init__.py
#   qualitative/config.yaml
#   qualitative/prepare_payload.py
#   qualitative/gemini_call.py
#   qualitative/parse_results.py
#   qualitative/run_qualitative.py

---

## Context

Tracks A–D are complete. SCHEMA_VERSION is "1.5". The analysis engine in
`analysis_engine/` produces `runs/2026_Q2/analysis_results.json` covering
8 quantitative sections. This track adds the qualitative layer: a pipeline that
reads the same survey parquet, sends all open-ended text to Gemini 2.5 Pro in
a single API call, and writes `runs/2026_Q2/qualitative_results.json`.

The qualitative results are consumed by the report generation layer (Track F,
not built yet) to fill the "Insight" blocks and verbatim sections in the
report template (`Cupboard Week Insurance Report Template v2.0`).

The pipeline has three phases:
  Phase 1  — prepare_payload.py:  reads parquet, enriches responses with
             demographics and segment metadata, serialises to JSON payload
  Phase 2  — gemini_call.py:      sends payload + system prompt to Gemini
             2.5 Pro, saves raw response JSON, returns parsed dict
  Phase 3  — parse_results.py:    validates Gemini output, counts themes in
             Python, enriches verbatim nominations with profile from parquet,
             writes final qualitative_results.json

---

## Data facts — read these before writing any code

Parquet file: `data/survey_clean.parquet`  (2,111 rows × 130 columns)

**Open-ended columns and their volumes:**

| Column key                              | Non-null | Notes                         |
|-----------------------------------------|----------|-------------------------------|
| q_nps_promoter_followup                 | 924      | NPS group: score 9–10         |
| q_nps_passive_followup                  | 609      | NPS group: score 7–8          |
| q_nps_detractor_followup                | 571      | NPS group: score 0–6          |
| q_no_claim_reason__other_text           | 50       | Low volume — counts not %     |
| q_claim_challenges__other_text          | 7        | Low volume — counts not %     |
| q_claim_challenges__support_text        | 16       | Low volume — counts not %     |
| q_coping_mechanisms__other_text         | 27       | Low volume — counts not %     |
| q_income_sources__other_text            | 63       | Low volume — counts not %     |
| q_comm_channel_effective__other_text    | 25       | Low volume — counts not %     |
| q_claim_channel_preferred__other_text   | 59       | Low volume — counts not %     |
| q_vf_services_received__other_text      | 9        | Low volume — counts not %     |
| q_child_improvements__other_text        | 1        | Single response               |
| q_bundled_services_used__other_text     | 0        | Empty — skip entirely         |

**Key demographic / segment columns:**

| Column                  | Dtype  | Values / notes                                       |
|-------------------------|--------|------------------------------------------------------|
| q_sex                   | object | "Female" (1,518), "Male" (586)                      |
| q_client_age            | Int16  | Numeric age (e.g., 38, 32, 26)                      |
| branch                  | object | Branch names, may contain UTF-8 characters           |
| flag_paid_claimant      | bool   | True=58 (paid claimant), False=95 (non-paid or none)|
| flag_negative_coping    | bool   | True=73                                             |
| q_child_wellbeing       | object | "Yes"=675 → is_caregiver=True                       |
| q_worth_premium         | Int8   | 1=Definitely worth it … 5=Definitely not worth it   |
| q_nps_score             | Int8   | 0–10                                                |

**Derived segment flags (compute in prepare_payload.py):**

```python
nps_group:    "promoter"  if q_nps_score >= 9
              "passive"   if 7 <= q_nps_score <= 8
              "detractor" if q_nps_score <= 6

is_caregiver: True if q_child_wellbeing == "Yes"
is_claimant:  True if flag_paid_claimant == True
is_female:    True if q_sex == "Female"
not_worth_it: True if q_worth_premium >= 4
```

**Row ID format:** `f"row_{df.index[i]:04d}"` — use the DataFrame's integer index,
zero-padded to 4 digits (e.g., row_0042, row_1204).

---

## STEP 0 — Install dependency and create package

Run:
```
pip install google-genai pyyaml
```

Create the empty package marker:
```
qualitative/__init__.py   (empty file)
```

Do NOT hardcode the Gemini API key anywhere in the code. Read it exclusively
from the environment variable `GEMINI_API_KEY`. The key will be set by the
user before running.

---

## STEP 1 — Create `qualitative/config.yaml`

Write this file exactly. The pipeline reads it at runtime.

```yaml
# qualitative/config.yaml

model: "gemini-2.5-pro"
run_id_default: "2026_Q2"
min_text_length: 10          # characters — filter shorter responses before sending

# NPS score thresholds
nps_thresholds:
  promoter_min: 9
  passive_min: 7
  detractor_max: 6

# Open-ended columns grouped by analysis purpose
# group: "nps" | "claims_other" | "sparse_other"
# low_volume: true → instruct Gemini to report counts, not proportions
columns:
  - key: q_nps_promoter_followup
    group: nps
    nps_group: promoter
    question_context: "Why did you give this NPS score? (Promoters, score 9-10)"
    low_volume: false

  - key: q_nps_passive_followup
    group: nps
    nps_group: passive
    question_context: "Why did you give this NPS score? (Passives, score 7-8)"
    low_volume: false

  - key: q_nps_detractor_followup
    group: nps
    nps_group: detractor
    question_context: "Why did you give this NPS score? (Detractors, score 0-6)"
    low_volume: false

  - key: q_no_claim_reason__other_text
    group: claims_other
    question_context: "Other reason why the client did not file a claim despite having an insured event"
    low_volume: true

  - key: q_claim_challenges__other_text
    group: claims_other
    question_context: "Other challenge experienced when making a claim (specify)"
    low_volume: true

  - key: q_claim_challenges__support_text
    group: claims_other
    question_context: "What support would help you with the claims process?"
    low_volume: true

  - key: q_coping_mechanisms__other_text
    group: sparse_other
    question_context: "Other coping mechanism used after the insured event"
    low_volume: true

  - key: q_income_sources__other_text
    group: sparse_other
    question_context: "Other income source mentioned by the client"
    low_volume: true

  - key: q_comm_channel_effective__other_text
    group: sparse_other
    question_context: "Other communication channel preferred for learning about insurance"
    low_volume: true

  - key: q_claim_channel_preferred__other_text
    group: sparse_other
    question_context: "Other preferred channel for submitting a claim"
    low_volume: true

  - key: q_vf_services_received__other_text
    group: sparse_other
    question_context: "Other VisionFund service received by the client"
    low_volume: true

  - key: q_child_improvements__other_text
    group: sparse_other
    question_context: "Other child wellbeing improvement reported"
    low_volume: true

  # q_bundled_services_used__other_text is excluded (0 non-null responses)

# Theme taxonomy — Gemini must only use these codes
themes:
  - code: staff_service
    label: "Staff Helpfulness"
    description: "Quality of VisionFund staff support, loan officer helpfulness, responsiveness, communication quality"

  - code: claims_speed
    label: "Claim Payout Speed"
    description: "Speed of claim processing and receiving payout; delays or fast resolution"

  - code: claims_process
    label: "Claim Process Ease"
    description: "Ease or difficulty of submitting a claim, documentation requirements, guidance received or missing"

  - code: product_value
    label: "Value for Money"
    description: "Whether the insurance product is worth the premium cost; pricing perception"

  - code: product_understanding
    label: "Product Knowledge"
    description: "Understanding what the policy covers, exclusions, how to claim, awareness gaps"

  - code: payout_adequacy
    label: "Payout Adequacy"
    description: "Whether the payout amount was sufficient to cover the actual loss"

  - code: financial_relief
    label: "Financial Relief"
    description: "Reduction in financial stress, income smoothing, ability to recover from hardship"

  - code: access_inclusion
    label: "Access and Inclusion"
    description: "First insurance experience, reaching previously uninsured populations, safety net for the vulnerable"

  - code: child_family
    label: "Child and Family Wellbeing"
    description: "Impact on children's health, education, or family stability; caregiver outcomes"

  - code: crop_agricultural
    label: "Crop and Agricultural"
    description: "Farming recovery, agricultural practice changes, crop shock response"

  - code: general_satisfaction
    label: "General Satisfaction"
    description: "Positive sentiment with no specific driver cited; general thanks or approval"

  - code: improvement_suggestion
    label: "Improvement Suggestion"
    description: "Concrete suggestions for VisionFund to improve service, product, or communication"

  - code: complaint_grievance
    label: "Complaint or Grievance"
    description: "Specific grievance about service, product quality, or staff conduct"

# Protection flag taxonomy
protection_flags:
  - code: mis_selling
    label: "Mis-selling"
    description: "Client was promised benefits that were not delivered at claim time"

  - code: premium_without_consent
    label: "Premium Deducted Without Consent"
    description: "Premium was deducted without clear explanation, agreement, or knowledge of the client"

  - code: coercion
    label: "Coercion to Purchase"
    description: "Client felt pressured or coerced to purchase insurance by a staff member"

  - code: false_information
    label: "False Information"
    description: "Agent or officer provided false or misleading information about coverage or process"

  - code: unfair_claim_denial
    label: "Unfair Claim Denial"
    description: "Claim was denied without a valid reason that was explained to the client"

  - code: staff_misconduct
    label: "Staff Misconduct"
    description: "Inappropriate, unresponsive, negligent, or dishonest behavior by VisionFund staff"

  - code: data_privacy
    label: "Data Privacy"
    description: "Concerns about how personal or financial data is used or shared"

# Report sections for verbatim nominations
report_sections:
  - key: part1
    title: "Product Understanding"
    topic_hint: "Understanding of insurance coverage and claims process; education gaps; client confusion"

  - key: part2
    title: "Claims Experience"
    topic_hint: "Claims filing experience, challenges, support needed, coping after insured event"

  - key: part3
    title: "Financial Inclusion"
    topic_hint: "First insurance access, safety net value, financial relief from having coverage"

  - key: part4
    title: "Client Voice"
    topic_hint: "NPS drivers — why promoters recommend and detractors are dissatisfied; value for money"

  - key: part5
    title: "Child Wellbeing"
    topic_hint: "Impact on children's health or education; family wellbeing; caregiver outcomes"
    prefer_segment: is_caregiver

  - key: part6
    title: "Claimant Outcomes"
    topic_hint: "Lived experience of making a claim; outcomes for those who claimed"
    prefer_segment: is_claimant

  - key: part7
    title: "Gender"
    topic_hint: "Gendered experiences; female-specific challenges or benefits; equity"
    require_diversity: true   # must include both Female and Male
```

---

## STEP 2 — Create `qualitative/prepare_payload.py`

```python
"""qualitative/prepare_payload.py

Phase 1: Read survey parquet, build enriched JSON payload for Gemini.
"""
import json
import sys
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

CONFIG_PATH = ROOT / "qualitative" / "config.yaml"
PARQUET_PATH = ROOT / "data" / "survey_clean.parquet"


def load_config() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def _nps_group(score) -> str:
    if pd.isna(score):
        return None
    s = int(score)
    if s >= 9:
        return "promoter"
    if s >= 7:
        return "passive"
    return "detractor"


def _build_response_record(row_id: str, text: str, row: pd.Series,
                            col_cfg: dict) -> dict:
    """Build enriched response dict for one respondent's answer."""
    rec = {
        "id": row_id,
        "text": str(text).strip(),
        "sex": str(row.get("q_sex", "")) or None,
        "client_age": (None if pd.isna(row.get("q_client_age"))
                       else int(row["q_client_age"])),
        "branch": str(row.get("branch", "")) or None,
        "is_claimant": bool(row.get("flag_paid_claimant", False)),
        "is_caregiver": (str(row.get("q_child_wellbeing", "")) == "Yes"),
        "is_female": (str(row.get("q_sex", "")) == "Female"),
    }
    # NPS-specific enrichment
    if col_cfg["group"] == "nps":
        rec["nps_group"] = col_cfg["nps_group"]
        rec["nps_score"] = (None if pd.isna(row.get("q_nps_score"))
                            else int(row["q_nps_score"]))
        rec["worth_premium_value"] = (
            None if pd.isna(row.get("q_worth_premium"))
            else int(row["q_worth_premium"]))
        rec["not_worth_it"] = (
            False if pd.isna(row.get("q_worth_premium"))
            else int(row["q_worth_premium"]) >= 4)
    return rec


def build_payload(df: pd.DataFrame, config: dict,
                  min_len: int = None) -> dict:
    """Build the complete payload dict to send to Gemini."""
    if min_len is None:
        min_len = config.get("min_text_length", 10)

    payload = {
        "nps_promoters": [],
        "nps_passives": [],
        "nps_detractors": [],
        "claim_no_reason_other": [],
        "claim_challenges_other_support": [],
        "sparse_other": [],
    }

    for col_cfg in config["columns"]:
        key = col_cfg["key"]
        if key not in df.columns:
            continue

        group = col_cfg["group"]

        for idx in df.index:
            raw = df.at[idx, key]
            if pd.isna(raw):
                continue
            text = str(raw).strip()
            if len(text) < min_len:
                continue

            row_id = f"row_{idx:04d}"
            rec = _build_response_record(row_id, text, df.loc[idx], col_cfg)

            if group == "nps":
                nps_grp = col_cfg["nps_group"]
                if nps_grp == "promoter":
                    payload["nps_promoters"].append(rec)
                elif nps_grp == "passive":
                    payload["nps_passives"].append(rec)
                else:
                    payload["nps_detractors"].append(rec)

            elif group == "claims_other":
                if key in ("q_claim_challenges__other_text",
                           "q_claim_challenges__support_text"):
                    rec["source_column"] = key
                    payload["claim_challenges_other_support"].append(rec)
                else:
                    rec["source_column"] = key
                    payload["claim_no_reason_other"].append(rec)

            else:  # sparse_other
                rec["source_column"] = key
                rec["question_context"] = col_cfg["question_context"]
                payload["sparse_other"].append(rec)

    return payload


def print_payload_stats(payload: dict) -> None:
    total_responses = sum(len(v) for v in payload.values())
    total_chars = len(json.dumps(payload, ensure_ascii=False))
    print("── Payload statistics ───────────────────────────────")
    for group, items in payload.items():
        print(f"  {group:<35}: {len(items):>4} responses")
    print(f"  {'TOTAL responses':<35}: {total_responses:>4}")
    print(f"  {'Total characters':<35}: {total_chars:>8,}")
    print(f"  {'Estimated input tokens (~4 chars)':<35}: {total_chars // 4:>8,}")
    print("─────────────────────────────────────────────────────")


if __name__ == "__main__":
    config = load_config()
    df = pd.read_parquet(PARQUET_PATH)
    payload = build_payload(df, config)
    print_payload_stats(payload)
```

---

## STEP 3 — Build the Gemini system prompt (inside `gemini_call.py`)

The system prompt is the most critical component. It instructs Gemini on what
to return and in what exact format. Write it as a constant string in
`gemini_call.py`. The full system prompt text is below — copy it exactly:

```
SYSTEM_PROMPT = """
You are an expert microinsurance survey analyst for VisionFund International.
You are analyzing open-ended survey responses from the VisionFund Insurance
Impact Survey (Vietnam, 2026 Q2). All responses are already in English.

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
```

---

## STEP 4 — Create `qualitative/gemini_call.py`

```python
"""qualitative/gemini_call.py

Phase 2: Send payload to Gemini 2.5 Pro, save raw response, return parsed dict.
Requires GEMINI_API_KEY environment variable.
"""
import json
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

# System prompt is defined as a constant here (see STEP 3 above)
SYSTEM_PROMPT = """..."""  # paste full system prompt text from STEP 3


def call_gemini(
    payload: dict,
    raw_response_path: Path,
    model: str = "gemini-2.5-pro",
    max_retries: int = 2,
    retry_delay_seconds: int = 30,
) -> dict:
    """
    Send the qualitative analysis payload to Gemini.
    Saves raw response JSON to raw_response_path before returning.

    Args:
        payload:            Dict built by prepare_payload.build_payload()
        raw_response_path:  Path to save the raw Gemini response (for debugging)
        model:              Gemini model name
        max_retries:        Number of retry attempts on API error
        retry_delay_seconds: Seconds to wait between retries

    Returns:
        Parsed dict from Gemini response text
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it before running: $env:GEMINI_API_KEY = 'your_key_here'"
        )

    client = genai.Client(api_key=api_key)

    user_message = json.dumps(payload, ensure_ascii=False)

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_message,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    max_output_tokens=65536,
                    temperature=0.2,
                ),
            )
            result_text = response.text
            break

        except Exception as exc:
            if attempt < max_retries:
                print(f"  Attempt {attempt + 1} failed: {exc}. "
                      f"Retrying in {retry_delay_seconds}s...")
                time.sleep(retry_delay_seconds)
            else:
                raise RuntimeError(
                    f"Gemini call failed after {max_retries + 1} attempts: {exc}"
                ) from exc

    # Save raw response before parsing (allows re-parse without re-calling)
    raw_response_path.parent.mkdir(parents=True, exist_ok=True)
    raw_response_path.write_text(result_text, encoding="utf-8")
    print(f"  Raw response saved to {raw_response_path}")

    try:
        return json.loads(result_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Gemini response is not valid JSON. "
            f"Raw text saved to {raw_response_path}. Error: {exc}"
        ) from exc
```

---

## STEP 5 — Create `qualitative/parse_results.py`

```python
"""qualitative/parse_results.py

Phase 3: Validate Gemini output, count themes in Python, enrich verbatims
with profile from parquet, write qualitative_results.json.
"""
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


REQUIRED_TOP_KEYS = {
    "nps_tags", "claims_other_tagged", "not_worth_it_themes",
    "other_subthemes", "section_verbatims", "protection_flags",
    "executive_summary",
}

REQUIRED_SECTION_KEYS = {
    "part1", "part2", "part3", "part4", "part5", "part6", "part7"
}

NPS_GROUPS = ("promoters", "passives", "detractors")


def _validate(raw: dict) -> None:
    missing = REQUIRED_TOP_KEYS - set(raw.keys())
    if missing:
        raise ValueError(f"Gemini response missing keys: {missing}")

    nps_tags = raw["nps_tags"]
    for grp in NPS_GROUPS:
        if grp not in nps_tags:
            raise ValueError(f"nps_tags missing group: {grp}")

    sv = raw["section_verbatims"]
    missing_sections = REQUIRED_SECTION_KEYS - set(sv.keys())
    if missing_sections:
        raise ValueError(f"section_verbatims missing sections: {missing_sections}")

    for section, ids in sv.items():
        if not isinstance(ids, list) or len(ids) == 0:
            raise ValueError(f"section_verbatims[{section}] is empty")


def _count_themes(nps_tags: dict) -> dict:
    """Count theme frequency per NPS group from compact tag arrays."""
    counts = {}
    for grp in NPS_GROUPS:
        counter = Counter()
        for entry in nps_tags.get(grp, []):
            if isinstance(entry, list) and len(entry) == 2:
                themes = entry[1]
                if isinstance(themes, list):
                    counter.update(themes)
        counts[grp] = dict(counter.most_common())
    return counts


def _lookup_profile(row_id: str, df: pd.DataFrame) -> dict:
    """Return demographic profile for a row_id string like 'row_0042'."""
    try:
        idx = int(row_id.split("_")[1])
    except (IndexError, ValueError):
        return {}

    if idx not in df.index:
        return {}

    row = df.loc[idx]
    return {
        "sex": str(row.get("q_sex", "")) or None,
        "age": (None if pd.isna(row.get("q_client_age"))
                else int(row["q_client_age"])),
        "branch": str(row.get("branch", "")) or None,
        "is_claimant": bool(row.get("flag_paid_claimant", False)),
        "is_caregiver": str(row.get("q_child_wellbeing", "")) == "Yes",
    }


def _lookup_text(row_id: str, df: pd.DataFrame, text_cols: list) -> str:
    """Find the open-ended text for a row_id across all text columns."""
    try:
        idx = int(row_id.split("_")[1])
    except (IndexError, ValueError):
        return ""

    if idx not in df.index:
        return ""

    row = df.loc[idx]
    for col in text_cols:
        if col in df.columns:
            val = row.get(col)
            if not pd.isna(val) and str(val).strip():
                return str(val).strip()
    return ""


def _enrich_section_verbatims(
    section_verbatims: dict,
    df: pd.DataFrame,
    text_cols: list,
) -> dict:
    """Replace row_id lists with enriched verbatim objects including text + profile."""
    enriched = {}
    for section, ids in section_verbatims.items():
        enriched[section] = []
        for row_id in ids:
            text = _lookup_text(row_id, df, text_cols)
            profile = _lookup_profile(row_id, df)
            enriched[section].append({
                "id": row_id,
                "text": text,
                "profile": profile,
            })
    return enriched


def _enrich_protection_flags(flags: list, df: pd.DataFrame) -> list:
    """Add profile to each protection flag."""
    enriched = []
    for flag in flags:
        row_id = flag.get("id", "")
        enriched.append({
            **flag,
            "profile": _lookup_profile(row_id, df),
        })
    return enriched


def parse_and_save(
    raw_gemini: dict,
    df: pd.DataFrame,
    run_id: str,
    meta_extra: dict = None,
) -> dict:
    """
    Validate, enrich, and assemble final qualitative_results.json.

    Args:
        raw_gemini:  Parsed dict from gemini_call.call_gemini()
        df:          Full survey DataFrame (for profile lookups)
        run_id:      Run identifier (e.g. "2026_Q2")
        meta_extra:  Optional dict with token counts etc. from the API response

    Returns:
        Final qualitative results dict (also written to disk)
    """
    _validate(raw_gemini)

    # All text columns (for verbatim text lookup)
    text_cols = [
        "q_nps_promoter_followup", "q_nps_passive_followup",
        "q_nps_detractor_followup", "q_no_claim_reason__other_text",
        "q_claim_challenges__other_text", "q_claim_challenges__support_text",
        "q_coping_mechanisms__other_text", "q_income_sources__other_text",
        "q_comm_channel_effective__other_text",
        "q_claim_channel_preferred__other_text",
        "q_vf_services_received__other_text",
        "q_child_improvements__other_text",
    ]

    theme_counts = _count_themes(raw_gemini["nps_tags"])

    enriched_verbatims = _enrich_section_verbatims(
        raw_gemini["section_verbatims"], df, text_cols
    )

    enriched_flags = _enrich_protection_flags(
        raw_gemini.get("protection_flags", []), df
    )

    result = {
        "meta": {
            "schema_version": "1.0",
            "model": "gemini-2.5-pro",
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **(meta_extra or {}),
        },
        "theme_counts": theme_counts,
        "nps_tags_raw": raw_gemini["nps_tags"],
        "claims_other_tagged": raw_gemini.get("claims_other_tagged", {}),
        "not_worth_it_themes": raw_gemini.get("not_worth_it_themes", []),
        "other_subthemes": raw_gemini.get("other_subthemes", {}),
        "section_verbatims": enriched_verbatims,
        "protection_flags": enriched_flags,
        "executive_summary": raw_gemini.get("executive_summary", ""),
    }

    out_path = Path("runs") / run_id / "qualitative_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"  qualitative_results.json written to {out_path}")

    return result
```

---

## STEP 6 — Create `qualitative/run_qualitative.py`

```python
"""qualitative/run_qualitative.py

Orchestrator for the qualitative analysis pipeline.

Usage:
    python qualitative/run_qualitative.py --run-id 2026_Q2
    python qualitative/run_qualitative.py --run-id 2026_Q2 --dry-run
    python qualitative/run_qualitative.py --run-id 2026_Q2 --parse-only

Options:
    --dry-run:    Build and print payload stats; do NOT call Gemini.
    --parse-only: Skip payload build and Gemini call; re-parse the existing
                  raw response from runs/{run_id}/gemini_raw_response.json.
                  Useful if the API call succeeded but parsing failed.
"""
import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from qualitative.prepare_payload import load_config, build_payload, print_payload_stats
from qualitative.gemini_call import call_gemini
from qualitative.parse_results import parse_and_save

PARQUET_PATH = ROOT / "data" / "survey_clean.parquet"


def main():
    parser = argparse.ArgumentParser(description="Run qualitative analysis pipeline")
    parser.add_argument("--run-id", default="2026_Q2",
                        help="Run identifier (default: 2026_Q2)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Build payload and print stats; do not call Gemini")
    parser.add_argument("--parse-only", action="store_true",
                        help="Re-parse existing raw response without calling Gemini")
    args = parser.parse_args()

    run_id = args.run_id
    raw_response_path = ROOT / "runs" / run_id / "gemini_raw_response.json"

    print(f"\n── Qualitative Pipeline | run_id={run_id} ────────────────────")

    # Load data
    print("Loading survey data...")
    df = pd.read_parquet(PARQUET_PATH)
    config = load_config()

    if args.parse_only:
        # Re-parse existing raw response
        if not raw_response_path.exists():
            print(f"ERROR: {raw_response_path} not found. Run without --parse-only first.")
            sys.exit(1)
        print(f"Loading raw response from {raw_response_path}...")
        raw_gemini = json.loads(raw_response_path.read_text(encoding="utf-8"))

    else:
        # Phase 1 — Build payload
        print("\nPhase 1 — Building payload...")
        payload = build_payload(df, config)
        print_payload_stats(payload)

        if args.dry_run:
            print("\n[dry-run] Payload built successfully. Exiting without Gemini call.")
            return

        # Phase 2 — Call Gemini
        print(f"\nPhase 2 — Calling {config['model']}...")
        raw_gemini = call_gemini(
            payload=payload,
            raw_response_path=raw_response_path,
            model=config["model"],
        )
        print("  Gemini call complete.")

    # Phase 3 — Parse and save
    print("\nPhase 3 — Parsing and enriching results...")
    result = parse_and_save(
        raw_gemini=raw_gemini,
        df=df,
        run_id=run_id,
    )

    # Print summary
    print("\n── Results summary ──────────────────────────────────────────")
    tc = result.get("theme_counts", {})
    for grp in ("promoters", "passives", "detractors"):
        top = list((tc.get(grp) or {}).items())[:3]
        print(f"  {grp} top themes: {top}")

    sv = result.get("section_verbatims", {})
    print(f"  Section verbatim sets: {len(sv)}/7")

    flags = result.get("protection_flags", [])
    print(f"  Protection flags found: {len(flags)}")
    for f in flags:
        print(f"    [{f.get('severity','?').upper()}] {f.get('flag_type')} — {f.get('id')}")

    print(f"\n  Output: runs/{run_id}/qualitative_results.json")
    print("─────────────────────────────────────────────────────────────\n")


if __name__ == "__main__":
    main()
```

---

## STEP 7 — Verify

**7a. Dry run (no API call required):**
```
python qualitative/run_qualitative.py --run-id 2026_Q2 --dry-run
```
Confirm: payload stats print without error, token estimate is < 80,000.

**7b. Set API key (PowerShell):**
```
$env:GEMINI_API_KEY = "your_key_here"
```

**7c. Full run:**
```
python qualitative/run_qualitative.py --run-id 2026_Q2
```
Confirm: exits 0 with results summary printed.

**7d. Paste the following output and verify:**
- The results summary block (theme counts, section verbatim count, protection flags)
- The first `section_verbatims.part4.text` value (confirm it's a real NPS response)
- The `protection_flags` list in full

---

## Acceptance criteria

1. `python qualitative/run_qualitative.py --run-id 2026_Q2 --dry-run` exits 0;
   prints payload stats showing nps_promoters ≈ 924, nps_detractors ≈ 571.

2. `python qualitative/run_qualitative.py --run-id 2026_Q2` exits 0.

3. `runs/2026_Q2/gemini_raw_response.json` exists and is valid JSON.

4. `runs/2026_Q2/qualitative_results.json` exists and is valid JSON.

5. `qualitative_results.json` contains all 7 section keys in `section_verbatims`
   (part1 through part7), each with 3 items.

6. Each item in `section_verbatims` has `id`, `text` (non-empty string),
   and `profile` (with `sex`, `age`, `branch`, `is_claimant`).

7. `theme_counts` contains three keys: "promoters", "passives", "detractors",
   each mapping theme codes to integer counts.

8. `protection_flags` is a list (may be empty if no flags found); any flags
   present have `id`, `column`, `flag_type`, `severity`, `reason`, `profile`.

9. `runs/2026_Q2/gemini_raw_response.json` is a separate file from
   `qualitative_results.json` (raw backup, not the final output).

10. No Gemini API key appears anywhere in any source file. The key is read
    only from `os.environ["GEMINI_API_KEY"]`.

---

## What NOT to do

- Do not hardcode the API key in any file.
- Do not create a separate system_prompt.py file — keep SYSTEM_PROMPT as a
  constant in gemini_call.py so the prompt and the API call stay together.
- Do not modify any file outside the `qualitative/` directory.
- Do not attempt to run `run_analysis.py` — the quantitative engine is complete
  and must not be changed by this track.
- Do not use `google-generativeai` (older SDK) — use `google-genai` as specified.
- Do not attempt to add `response_schema` parameter to the Gemini call — the
  schema is enforced via the system prompt text. The `response_mime_type` alone
  is sufficient to guarantee JSON output.
- Do not merge the output into `analysis_results.json` — write a separate
  `qualitative_results.json` file.
- Do not add error recovery logic for Gemini returning partial JSON — if the
  response is invalid JSON, raise the error clearly so the user can inspect
  `gemini_raw_response.json` and re-run with `--parse-only` after fixing.
