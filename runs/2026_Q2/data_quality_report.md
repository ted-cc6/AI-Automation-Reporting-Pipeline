# Data Quality Report — VisionFund Insurance Survey
Generated: 2026-06-29 15:07:27

## Summary
- Dataset: 2,111 rows × 130 columns
- Spec: 18 source questions, 17 metric variables referenced
- Result: **PASS** (0 error(s), 1 warning(s))

### Warnings
- Check 1: q_sex stored as 'category' (Male/Female labels) — intentional deviation from binary spec type

## Check 1: Spec Alignment

| question_ref | spec_type | parquet_dtype | status | note |
|---|---|---|---|---|
| `q_worth_premium` | likert_5 | Int8 | PASS ✓ |  |
| `q_nps_score` | numeric_open | Int16 | PASS ✓ |  |
| `q_nps_detractor_followup` | open_text | string | PASS ✓ |  |
| `q_sex` | binary | category | WARN ⚠ | Intentional: stores labels Male/Female as category |
| `q_nps_passive_followup` | open_text | string | PASS ✓ |  |
| `q_nps_promoter_followup` | open_text | string | PASS ✓ |  |
| `q_confidence_pay` | likert_5 | Int8 | PASS ✓ |  |
| `q_financial_stress` | likert_5 | Int8 | PASS ✓ |  |
| `q_insured_event_12m` | binary | boolean | PASS ✓ |  |
| `q_claim_submitted` | binary | boolean | PASS ✓ |  |
| `q_claim_result` | single_select | category | PASS ✓ |  |
| `q_coverage_understanding` | likert_4 | Int8 | PASS ✓ |  |
| `q_claim_process_understanding` | likert_4 | Int8 | PASS ✓ |  |
| `q_coping_mechanisms` | multi_select_n | object | PASS ✓ |  |
| `q_prior_access` | binary | boolean | PASS ✓ |  |
| `q_alternative_access` | single_select | category | PASS ✓ |  |
| `q_child_wellbeing` | single_select | category | PASS ✓ |  |
| `q_healthcare_access` | single_select | category | PASS ✓ |  |

## Check 2: Value Ranges

| column | valid_range | violations | status |
|---|---|---|---|
| `q_nps_score` | 0–10 | 0 | PASS ✓ |
| `q_coverage_understanding` | 1–4 | 0 | PASS ✓ |
| `q_claim_process_understanding` | 1–4 | 0 | PASS ✓ |
| `q_financial_stress` | 1–5 | 0 | PASS ✓ |
| `q_confidence_pay` | 1–5 | 0 | PASS ✓ |
| `q_worth_premium` | 1–5 | 0 | PASS ✓ |
| `q_renewal_intent` | 1–5 | 0 | PASS ✓ |
| `q_client_age` | 18–100 | 0 | PASS ✓ |

## Check 3: Skip-Logic Consistency

_base_n = rows outside the valid scope. ERROR threshold: violation > 1% of base_n._

| check_id | description | base_n | violations | pct_of_base | status |
|---|---|---|---|---|---|
| SL-1 | q_claim_submitted non-null only where q_insured_event_12m == True | 1594 | 0 | 0.00% | PASS ✓ |
| SL-2 | q_no_claim_reason non-null only where q_claim_submitted == False | 153 | 0 | 0.00% | PASS ✓ |
| SL-3 | q_claim_result non-null only where q_claim_submitted == True | 210 | 0 | 0.00% | PASS ✓ |
| SL-4 | q_claim_challenges_experienced non-null only where q_claim_submitted == True | 210 | 0 | 0.00% | PASS ✓ |
| SL-5 | q_child_improvements non-empty list only where q_child_wellbeing == 'Yes' | 1436 | 0 | 0.00% | PASS ✓ |
| SL-6 | flag_negative_coping non-null only where q_insured_event_12m == True | 1594 | 0 | 0.00% | PASS ✓ |

## Check 4: Insurance-Type Scope

| column | scope | out_of_scope_non_null | status |
|---|---|---|---|
| `q_healthcare_access` | health | 0 | PASS ✓ |
| `q_medical_cost_change` | health | 0 | PASS ✓ |
| `q_crop_recovery_speed` | crop | 0 | PASS ✓ |
| `q_crop_farming_change` | crop | 0 | PASS ✓ |
| `q_renewal_intent` | crop | 0 | PASS ✓ |
| `q_credit_other_benefits` | credit_life | 0 | PASS ✓ |
| `q_credit_other_benefits__a` | credit_life | 0 | PASS ✓ |
| `q_credit_other_benefits__b` | credit_life | 0 | PASS ✓ |
| `q_credit_other_benefits__c` | credit_life | 0 | PASS ✓ |
| `q_credit_other_benefits__d` | credit_life | 0 | PASS ✓ |
| `q_credit_other_benefits__e` | credit_life | 0 | PASS ✓ |
| `q_credit_additional_value` | credit_life | 0 | PASS ✓ |

## Check 5: Derived Variable Sanity

| variable | expected | actual | status |
|---|---|---|---|
| flag_negative_coping — True count | > 0 | 73 | PASS ✓ |
| flag_negative_coping — non-NaN outside insured-event rows | = 0 violations | 0 | PASS ✓ |
| flag_promoter — dtype | boolean | boolean | PASS ✓ |
| flag_promoter — non-NaN where q_nps_score is NaN | = 0 violations | 0 | PASS ✓ |
| flag_paid_claimant — dtype | boolean | boolean | PASS ✓ |
| flag_child_wellbeing_denominator — NaN count | = 0 | 0 | PASS ✓ |
| insurance_type — valid slug values only | ⊆ {'health','crop','credit_life'} | ['credit_life', 'crop', 'health'] | PASS ✓ |

## Check 6: Fill Rates

| question_ref | scope | denominator_n | fill_rate | note |
|---|---|---|---|---|
| `q_worth_premium` | all | 2111 | 92.7% |  |
| `q_nps_score` | all | 2111 | 99.7% |  |
| `q_nps_detractor_followup` | NPS 0–6 | 571 | 100.0% | conditional on NPS ≤ 6 — low fill expected |
| `q_sex` | all | 2111 | 99.7% |  |
| `q_nps_passive_followup` | NPS 7–8 | 609 | 100.0% | conditional on NPS 7–8 — low fill expected |
| `q_nps_promoter_followup` | NPS 9–10 | 924 | 100.0% | conditional on NPS ≥ 9 — low fill expected |
| `q_confidence_pay` | all | 2111 | 99.7% |  |
| `q_financial_stress` | all | 2111 | 99.7% |  |
| `q_insured_event_12m` | all | 2111 | 92.7% |  |
| `q_claim_submitted` | insured event | 363 | 100.0% | conditional on insured event |
| `q_claim_result` | submitted claim | 153 | 100.0% | conditional — low fill expected |
| `q_coverage_understanding` | all | 2111 | 99.7% |  |
| `q_claim_process_understanding` | all | 2111 | 99.7% |  |
| `q_coping_mechanisms` | insured event | 363 | 100.0% | multi-select list; conditional on insured event |
| `q_prior_access` | all | 2111 | 99.7% |  |
| `q_alternative_access` | all | 2111 | 99.7% |  |
| `q_child_wellbeing` | all | 2111 | 99.7% |  |
| `q_healthcare_access` | health only | 1672 | 100.0% | health-insurance scope only |
| `flag_negative_coping` | insured event | 363 | 100.0% | NaN outside insured-event scope by design |
| `flag_promoter` | all | 2111 | 99.7% | NaN where q_nps_score is missing |
| `flag_paid_claimant` | all | 2111 | 7.2% |  |
| `flag_child_wellbeing_denominator` | all | 2111 | 100.0% | False for non-caregiver and NA rows |
