# Phase A — Column Mapping & Profiling

## Your task

You are building Phase A of a data loader for a VisionFund Insurance Client Survey.
Phase A has one job: understand the raw CSV file before any transformation is written.
You must produce two deliverables:

1. **`column_mapping.csv`** — a literal CSV block in your response (one row per column,
   133 rows total). This is a human-review checkpoint; it must be complete and accurate
   before any Phase B code is written.

2. **`phase_a_profiler.py`** — a Python script that reads the CSV and the mapping file
   and produces a per-column profile report (`profile_report.md`).

Do not write any cleaning or transformation logic. Do not transform values. This phase
is read-only analysis only.

---

## File facts

- **Path:** `data/Insurance_Survey_2026_-_LIVE_-_latest_version_-_English_en_-_2026-06-25-16-53-33.csv`
- **Delimiter:** semicolon (`;`) — NOT comma. Default CSV parsers will produce one column.
- **Encoding:** UTF-8
- **Shape:** 133 columns, ~2,111 data rows (row 0 is the header)
- **Format:** KoBoToolbox export. System metadata columns appear at the end (cols 124–132).

---

## Complete column list (indices 0–132)

```
0:   Device Info
1:   start
2:   end
3:   Username
4:   Region
5:   Country
6:   What is the client's ID number in our systems?
7:   To which branch does the client belong?
8:   Insurance_Type
9:   Before we start, I would like to explain this survey. [long consent text] Do you agree to participate in this survey?
10:  This section includes questions on the extent to which you understand the terms of insurance and claims.
11:  How would you rate your understanding of what your insurance covers?
12:  How you would you rate your understanding of how to make a claim?
13:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?
14:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/a. In-person explanation from MFI staff/loan officer
15:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/b. Group meeting
16:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/c. SMS/WhatsApp messages from the MFI
17:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/d. Printed materials (leaflets, posters, brochures)
18:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/e. Phone call from the MFI
19:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/f. Email from the MFI
20:  Which communication channel is the most effective in increasing your awareness and understanding of the claims process?/g. Other (please specify)
21:  If other, please specify:
22:  Which channel do you prefer most for submitting insurance claims?
23:  If other, please specify:
24:  I will now ask you questions regarding your experience when making an insurance claim.
25:  In the last 12 months, did you experience an event that might be covered by your insurance?
26:  [If Yes] Did you submit an insurance claim for that event?
27:  [If No, did not submit an insurance claim] What was the main reason you did not submit an insurance claim for this event?
28:  If other, please specify:
29:  [If Yes, submitted a claim] What was the result of the claim?
30:  If [Claim was approved and paid] Considering all costs related to the event, how much of the cost did the insurance payout cover?
31:  [If filed a claim] Have you experienced any challenges with the claim process?
32:  [If yes] What challenges did you experience with the claim process?
33:  [If yes] What challenges did you experience with the claim process?/a. Claim documents were difficult to collect from hospitals or authorities
34:  [If yes] What challenges did you experience with the claim process?/b. Claim documents were difficult to submit
35:  [If yes] What challenges did you experience with the claim process?/c. It was difficult to know the status of the claim once documents were submitted
36:  [If yes] What challenges did you experience with the claim process?/d. It took a long time to receive the claim amount
37:  [If yes] What challenges did you experience with the claim process?/e. I did not receive enough support or guidance on the claim process
38:  [If yes] What challenges did you experience with the claim process?/f. Other (specify)
39:  If other, please specify:
40:  [If e] What specific support would you need to make the claims process easier?
41:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?
42:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/a. Use savings
43:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/b. Borrow money
44:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/c. Sell assets or livestock
45:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/d. Reduce food consumption or essential spending
46:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/e. Take your children out of school
47:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/f. Closed business temporarily
48:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/g. None of the above
49:  [If yes to experiencing an insured event] Because of the event, did you have to do any of the following?/h. Other (specify)
50:  If other, please specify:
51:  This section includes questions related to additional services offered in the insurance.
52:  In the past 12 months, which of the following services did you use?
53:  In the past 12 months, which of the following services did you use?/a. Teleconsultation - doctor by phone (general or specialized such as psychologist, nutritionist)
54:  In the past 12 months, which of the following services did you use?/b. Face to face consultations (general or specialized such as dental, ophthalmology)
55:  In the past 12 months, which of the following services did you use?/c. Access to medicines (discounts or free)
56:  In the past 12 months, which of the following services did you use?/d. Lab examination/lab test
57:  In the past 12 months, which of the following services did you use?/e. Health events (mobile clinic, orange ambulance, medical brigades, etc.)
58:  In the past 12 months, which of the following services did you use?/f. None
59:  In the past 12 months, which of the following services did you use?/g. Other: please specify
60:  If other, please specify:
61:  If [did access the services] did the services help you as you wanted?
62:  I will now ask you questions on how the insurance has impacted the wellbeing of your children and finances.
63:  How much does the insurance help reduce your financial stress?
64:  Since taking the insurance product from VisionFund, has the wellbeing of the children you support improved?
65:  [If a] What improved for your children since having the insurance product?
66:  [If a] What improved for your children since having the insurance product?/a. Improved access to healthcare treatment and diagnosis
67:  [If a] What improved for your children since having the insurance product?/b. Reduced out-of-pocket expenses that helped us maintain nutritious and sufficient meals
68:  [If a] What improved for your children since having the insurance product?/c. Fewer school days missed due to improved health
69:  [If a] What improved for your children since having the insurance product?/d. Reduced need to work extra hours after a shock, allowing more time to spend with children
70:  [If a] What improved for your children since having the insurance product?/e. Ability to continue normal daily activities (play, social life, learning)
71:  [If a] What improved for your children since having the insurance product?/f. Increased savings after loss helped meet the children's needs including clothing, shoes, and school supplies
72:  [If a] What improved for your children since having the insurance product?/g. Other (please specify)
73:  If other, please specify:
74:  This section includes questions on your level of satisfaction with your interaction with VisionFund, their products or services.
75:  On a scale of 0-10, how likely are you to recommend the VisionFund Insurance to a friend or family member, where 0 is not at all likely and 10 is extremely likely?
76:  [If 0-6] What actions could VisionFund take to make you more likely to recommend the insurance product to a friend or family member?
77:  [If 7-8] What specifically about the VisionFund Insurance caused you to give it the score that you did?
78:  [If 9-10] What specifically about the VisionFund Insurance would cause you to recommend it to a friend or family member?
79:  Considering the benefits and the cost of your insurance, do you feel the insurance is worth what you pay?
80:  If you had to pay the full insurance premium yourself, in the amount of 700,000 VND/hectare per year, would you renew this policy after it expires?
81:  How confident are you that the insurance will pay when something serious happens?
82:  I will now ask you questions about your levels of access to insurance services before and after VisionFund.
83:  Before VisionFund, did you have access to an insurance like VisionFund provides?
84:  If you could no longer access insurance from VisionFund, how easily could you get a comparable insurance product with another organization?
85:  This section includes specific questions related to your health insurance.
86:  Since having the insurance, were you or any member of your household able to seek medical care more easily?
87:  Compared to a similar illness before you had insurance, have your out-of-pocket medical costs changed because of the insurance? It has become...
88:  This section includes specific questions related to your Crop insurance.
89:  After the weather shock, since having the insurance, how quickly were you able to recover and continue earning income?
90:  Since having a crop insurance, has your approach to farming changed (e.g., choice of crops, input investment, or planting practices)?
91:  This section includes specific questions related to your Credit Life insurance.
92:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?
93:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?/a. Help with medical or hospital costs
94:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?/b. Help when crops or income are affected by weather (drought, flood, etc.)
95:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?/c. Help when property or business assets are damaged
96:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?/d. No other benefits are included
97:  Besides the protection in case of death or disability, which other insurance benefits are included with your Credit insurance?/e. I am not sure
98:  Most MFIs that provide a Credit Insurance only cover the outstanding loan amount in case of the death or disability of the borrower. How valuable are the additional benefits of this enhanced credit insurance to you?
99:  Lastly, I will be asking questions about you and your household.
100: What is the client's age?
101: What is the client's education level?
102: What is the client's household size?
103: What is the client's sex?
104: Does anyone in your household experience serious difficulty in any of the following areas: seeing, hearing, walking or climbing steps, remembering or concentrating, self-care, or communicating?
105: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?
106: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/a. Loans
107: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/b. Savings Accounts
108: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/c. Financial Education
109: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/d. Health Services (telemedicine, education etc.)
110: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/e. None
111: In the last 6 months, which services have you received from VisionFund apart from your insurance policy?/f. Other (please specify)
112: If other, please specify:
113: What are your main sources of income?
114: What are your main sources of income?/a. Crop agriculture business
115: What are your main sources of income?/b. Livestock agriculture business
116: What are your main sources of income?/c. Trading/Wholesale/Retail (e.g., retail shop)
117: What are your main sources of income?/d. Manufacturing (e.g., maker of furniture)
118: What are your main sources of income?/e. Service provision business (e.g., salon, skilled/casual laborer, or transport business)
119: What are your main sources of income?/f. Salaried wage-earner
120: What are your main sources of income?/g. Remittances, donations, and government subsidy/assistance
121: What are your main sources of income?/h. Other (please specify)
122: If other, please specify:
123: Thank you very much for your time. We will use this information to improve our services to you and future clients. Have a great day!
124: _id
125: _uuid
126: _submission_time
127: _validation_status
128: _notes
129: _status
130: _submitted_by
131: _tags
132: _index
```

---

## Known question_refs — use these EXACT slugs

The report spec has declared 18 question_refs. Where a CSV column matches one of these,
use the slug exactly as shown. Do not invent alternatives.

```
q_alternative_access      → col 84   (single_select)
q_child_wellbeing         → col 64   (single_select)
q_claim_process_understanding → col 12  (likert_4)
q_claim_result            → col 29   (single_select)
q_claim_submitted         → col 26   (binary)
q_confidence_pay          → col 81   (likert_5)
q_coping_mechanisms       → col 41   (multi_select_n — parent; cols 42–49 are its children)
q_coverage_understanding  → col 11   (likert_4)
q_financial_stress        → col 63   (likert_5)
q_healthcare_access       → col 86   (single_select)
q_insured_event_12m       → col 25   (binary)
q_nps_detractor_followup  → col 76   (open_text)
q_nps_passive_followup    → col 77   (open_text)
q_nps_promoter_followup   → col 78   (open_text)
q_nps_score               → col 75   (numeric_open)
q_prior_access            → col 83   (binary)
q_sex                     → col 103  (binary)
q_worth_premium           → col 79   (likert_5)
```

Columns not in this list still need a `question_ref` slug if they are real questions
(see slug rules below). Leave `question_ref` empty for all non-`question_ref` categories.

---

## Seven column categories — classification rules

Classify every column into exactly one of these seven categories.

### `question_ref`
A real survey question answered by respondents. Includes:
- Single-select, Likert, binary, numeric, and open-text standalone questions.
- **Multi-select parent columns** (the column whose header is the question stem,
  before the `/a. /b. /c.` splits). These columns may contain a concatenated string
  of selected options or be empty — they are still `question_ref`.

### `multi_select_child`
A split column derived from a multi-select parent. Identified by `/a.`, `/b.`, `/c.`
(etc.) at the end of the column header. The `parent_ref` field must contain the
`question_ref` of the parent column.

### `free_text_child`
An "If other, please specify:" open-text follow-up to a specific question or option.
The `parent_ref` must contain the `question_ref` of the question it follows up.
Special cases:
- Col 40 is a free_text_child of the `/e` option of col 32 (`q_claim_challenges`);
  set `parent_ref = q_claim_challenges`.
- Cols 76–78 are already classified as `question_ref` (they have spec slugs above),
  NOT as free_text_child — they are conditional questions, not "other specify" fields.

### `drop_scaffold`
Section-header or transition text inserted by the survey tool. Contains no respondent
answer. Classify here if the column is a survey introduction, section label, transition
sentence, or closing message. Respondents cannot answer these columns.

### `keep_identity`
KoBoToolbox system columns needed downstream for deduplication, audit, or linking:
`_id`, `_uuid`, `_submission_time`, `_index`.

### `drop_system`
KoBoToolbox system columns NOT needed downstream:
`_validation_status`, `_notes`, `_status`, `_submitted_by`, `_tags`.

### `keep_metadata`
Interviewer or fieldwork columns kept for context but not used as analysis variables:
`Device Info`, `start`, `end`, `Username`, `Region`, `Country`,
client ID (col 6), branch (col 7), `Insurance_Type` (col 8).

---

## Slug naming rules (for new question_refs not in the known list)

- Format: `q_` + short snake_case descriptor, max ~4 words, no stop words.
- Describe the construct measured, not the question wording.
- Examples:
  - "How would you rate your understanding of what your insurance covers?" → already `q_coverage_understanding`
  - "Which communication channel is the most effective..." → `q_comm_channel_effective`
  - "Which channel do you prefer most for submitting insurance claims?" → `q_claim_channel_preferred`
  - "What was the main reason you did not submit a claim?" → `q_no_claim_reason`
  - "Considering all costs, how much did the payout cover?" → `q_payout_cost_coverage`
  - "Have you experienced any challenges with the claim process?" → `q_claim_challenges_experienced`
  - "What challenges did you experience?" (parent multi-select) → `q_claim_challenges`
  - "What specific support would you need?" → `q_support_needed`
  - "Which additional services did you use in the past 12 months?" (parent) → `q_bundled_services_used`
  - "Did the services help you as you wanted?" → `q_services_helped`
  - "What improved for your children?" (parent multi-select) → `q_child_improvements`
  - "Would you renew this policy?" → `q_renewal_intent`
  - "Before VisionFund, did you have access to insurance?" → already `q_prior_access`
  - "Since having insurance, how quickly were you able to recover?" (crop) → `q_crop_recovery_speed`
  - "Has your approach to farming changed?" → `q_crop_farming_change`
  - "Besides death/disability, what other benefits are included?" (parent) → `q_credit_other_benefits`
  - "How valuable are the additional benefits?" → `q_credit_additional_value`
  - "What are your main sources of income?" (parent) → `q_income_sources`
  - "Which VisionFund services have you received in the last 6 months?" (parent) → `q_vf_services_received`

Consent (col 9): classify as `drop_scaffold` — all respondents in the dataset
consented, so this column is constant and not analytically useful.

---

## Deliverable 1: column_mapping.csv

Produce this as a literal fenced CSV block. Every row must be present (133 rows,
not counting the header). Column order:

```
raw_index,raw_column_header,category,question_ref,parent_ref,notes
```

Rules:
- `raw_column_header`: copy the header text exactly as given in the column list above.
  Truncate to ~80 characters with `...` if very long.
- `category`: one of the seven category names above.
- `question_ref`: the slug if category is `question_ref`; empty otherwise.
- `parent_ref`: the parent's `question_ref` if category is `multi_select_child` or
  `free_text_child`; empty otherwise.
- `notes`: one short note where something is non-obvious (e.g., insurance-type scope,
  conditional logic, ambiguous classification). Leave empty if nothing to flag.
- Wrap any field containing a comma in double quotes.

---

## Deliverable 2: phase_a_profiler.py

A Python script that:

1. Loads the CSV file with `delimiter=";"` and `encoding="utf-8"`.
2. Loads `column_mapping.csv`.
3. Joins on `raw_index` to know each column's category and question_ref.
4. For every column where `category` is NOT `drop_scaffold` or `drop_system`,
   computes:
   - **fill_rate**: % of rows with a non-empty, non-null value
   - **distinct_count**: number of unique non-null values
   - **top_5_values**: the five most frequent values with their counts
   - **warning**: `WARN_LOW_FILL` if fill_rate < 80%, `WARN_VERY_LOW_FILL` if < 50%
5. Outputs `profile_report.md` with:
   - A summary table (one row per profiled column): `raw_index | question_ref | category | fill_rate | distinct_count | warning`
   - A detailed block per column with top-5 values
   - A warnings section at the top listing all columns that triggered a warning
6. Also prints a one-line summary to stdout on completion.

Requirements:
- Use only Python stdlib + `pandas`. No other dependencies.
- Gracefully handle columns whose `raw_column_header` in the mapping does not
  exactly match the CSV header (log a warning and skip, don't crash).
- Save `profile_report.md` in the same directory as the script.
- The script must be runnable as: `python phase_a_profiler.py`
  (paths to CSV and mapping are hardcoded relative to the script location,
   or accepted as optional CLI args with those as defaults).

---

## Important: do not skip columns

The mapping must contain exactly 133 rows. If you are unsure about a column's
classification, make your best judgment and add a note in the `notes` field.
A complete mapping with some uncertain notes is more useful than a mapping
with missing rows.
