# Developer Prompt — Track D Scale Fix: Inverted Likert Correction
# Files: analysis_engine/sections/part_1.py,
#        analysis_engine/sections/part_3.py,
#        analysis_engine/sections/part_6.py,
#        analysis_engine/sections/part_7.py,
#        analysis_engine/sections/part_8.py,
#        run_analysis.py (SCHEMA_VERSION bump),
#        dashboard_alignment/indicator_map.yaml (notes update only)

---

## Context

Track D alignment investigation confirmed that every Likert-scale question in this survey
uses an **inverted numeric scale where 1 = best response**. Examples:

- `q_confidence_pay`: 1 = "Very confident", 5 = "Not at all confident"
- `q_coverage_understanding`: 1 = best understanding, 4 = worst
- `q_worth_premium`: 1 = "Definitely worth it", 5 = "Definitely not worth it"

The current engine uses `top_two_box()` for these questions, which captures the two
HIGHEST numeric values (the worst responses). This is why Perceived Trust shows as
3.28% — only 3.28% chose options 4 or 5, which are the low-confidence responses.

The fix is to use `bottom_two_box()` for all positive-outcome Likert metrics.
`bottom_two_box()` already exists in `stats.py` (added in Track D and retained).

**Two metrics are explicitly exempted from this fix:**
1. `q_financial_stress` in `part_6.py` ("Financial Stress High") — this intentionally
   measures the proportion at the WORST end of the scale (high stress). `top_two_box`
   is correct here.
2. `q_renewal_intent` in `part_1.py` — dashboard alignment already shows MATCH
   (0.12pp) with the current implementation. Do not touch it.

**Three alignment gaps remain unresolvable and must be documented, not fixed:**
- "Child Wellbeing Improved": dashboard uses a 948-person base not identifiable from
  any CleanDataset property (health=1672, insured_event_base=363,
  child_wellbeing_base=1928). Gap is a base-population difference in the dashboard's
  ETL. Cannot fix without access to the IndicatorScore preprocessing logic.
- "First Time Access to Insurance": dashboard measures first-time VisionFund clients
  (~98.6%); our `q_prior_access` measures first-time insurance ownership (~85.4%).
  Different definitions from different data sources. Cannot reconcile.
- "Good Understanding of Claim Process": dashboard's IndicatorScore table has
  coverage and claim-process questions labeled in reverse. Our column mapping is
  correct. This is a dashboard labeling error, not an engine error.

---

## STEP 1 — Read all affected files before making any changes

Read these files in full before editing:
- `analysis_engine/sections/part_1.py`
- `analysis_engine/sections/part_3.py`
- `analysis_engine/sections/part_6.py`
- `analysis_engine/sections/part_7.py`
- `analysis_engine/sections/part_8.py`

Confirm that `bottom_two_box` is importable from `analysis_engine.stats` before
proceeding. If it is not present in `stats.py`, add it as the mirror of `top_two_box`:

```python
def bottom_two_box(series: pd.Series) -> dict:
    """Proportion of non-null responses in the bottom two values of the scale.

    Used for inverted Likert scales where 1 = best response.
    """
    return top_two_box(series, bottom=True)   # if top_two_box supports a bottom kwarg
    # OR implement equivalently to top_two_box but selecting the lowest 2 unique values
```

Check the existing `bottom_two_box` implementation to understand exactly how it
selects values before assuming it is correct.

---

## STEP 2 — Update `part_1.py`

Add `bottom_two_box` to the import from `analysis_engine.stats`.

Switch from `top_two_box` to `bottom_two_box` for these three columns only:
- `q_coverage_understanding`
- `q_claim_process_understanding`
- `q_worth_premium`

**Leave unchanged:**
- `q_renewal_intent` — already produces correct alignment result; do not touch.
- `nps_score()` call — not a Likert question; do not touch.

---

## STEP 3 — Update `part_3.py`

Add `bottom_two_box` to the import from `analysis_engine.stats`.

Switch from `top_two_box` to `bottom_two_box` for:
- `q_confidence_pay`

**Leave unchanged:**
- `q_financial_stress` — if it is used in Part 3, leave it as `top_two_box`.
  Part 3 may use it to measure high financial stress (the bad end of the scale),
  which TTB correctly captures.

---

## STEP 4 — Update `part_6.py`

Add `bottom_two_box` to the import from `analysis_engine.stats`.

Part 6 (Claimant vs Non-Claimant Scorecard) uses these columns — switch each:
- `q_coverage_understanding` → `bottom_two_box`
- `q_claim_process_understanding` → `bottom_two_box`
- `q_confidence_pay` → `bottom_two_box`

**Leave unchanged:**
- `q_financial_stress` labeled "Financial Stress (High)" — this intentionally
  measures the proportion with HIGH stress (worst end = top numeric values).
  `top_two_box` is correct here and must not be changed.

---

## STEP 5 — Update `part_7.py`

Read `part_7.py` to identify every use of `top_two_box` on Likert questions.
Apply the same rule: switch positive-outcome understanding, trust, and value
metrics to `bottom_two_box`. Leave any metric explicitly measuring a negative
outcome (stress, difficulty, etc.) as `top_two_box`.

---

## STEP 6 — Update `part_8.py` (Kling Index)

The Kling Index dimension helpers call `top_two_box` on inverted-scale questions.
Switch each affected call:

In `_dim_product_understanding()`:
- `top_two_box(df[COL_COVERAGE_UNDERSTANDING])` → `bottom_two_box(...)`
- `top_two_box(df[COL_CLAIM_PROCESS_UNDERSTANDING])` → `bottom_two_box(...)`

In `_dim_trust()`:
- `top_two_box(df[COL_CONFIDENCE_PAY])` → `bottom_two_box(...)`

Add `bottom_two_box` to the import from `analysis_engine.stats`.

`_dim_claims_experience()` and `_dim_access()` do not use `top_two_box` — leave
them unchanged.

---

## STEP 7 — Bump `SCHEMA_VERSION` in `run_analysis.py`

```python
SCHEMA_VERSION = "1.5"   # was "1.4" — inverted Likert scale corrected:
                          # bottom_two_box replaces top_two_box for all
                          # positive-outcome Likert metrics (Track D scale fix)
```

---

## STEP 8 — Update `dashboard_alignment/indicator_map.yaml`

For the three unresolvable gaps, update their `status` field and add a `resolution`
note. Do not change any other entries.

```yaml
  - name: "Child Wellbeing Improved"
    status: INVESTIGATE
    resolution: >
      Dashboard uses a 948-respondent base not reproducible from any CleanDataset
      property (health=1672, insured_event_base=363, child_wellbeing_base=1928).
      Base population likely defined during dashboard ETL in the IndicatorScore
      preprocessing step. Gap is a methodology difference, not a calculation error.
      Numerator (675 Yes) matches exactly; only the denominator differs.

  - name: "First Time Access to Insurance"
    status: OUT_OF_SCOPE
    resolution: >
      Definition mismatch. Dashboard measures first-time VisionFund clients (98.6%);
      q_prior_access measures clients who never had any insurance before VisionFund
      (85.4%). Different data sources, cannot reconcile from survey data alone.

  - name: "Good Understanding of Claim Process"
    status: DASHBOARD_ERROR
    resolution: >
      Dashboard IndicatorScore table has coverage and claim-process questions labeled
      in reverse. Our column mapping (q_claim_process_understanding → claim process
      metric) is correct. The near-perfect match between our coverage_understanding
      BTB (0.7657) and dashboard "Claim Process" (0.7655) confirms the dashboard's
      labeling error. No engine change needed.
```

---

## STEP 9 — Verify

1. Run `python run_analysis.py --run-id 2026_Q2` — confirm exits 0, all 8 parts OK.
2. Run `python dashboard_alignment/check_alignment.py` — paste the full output.
3. Confirm `meta.schema_version == "1.5"` in `runs/2026_Q2/analysis_results.json`.

---

## What NOT to do

- Do not change `top_two_box` to `bottom_two_box` for `q_financial_stress` in
  Part 6 — it is intentionally measuring HIGH stress (the bad end of the scale).
- Do not touch `q_renewal_intent` in Part 1 — it already produces a MATCH result.
- Do not modify `part_2.py`, `part_4.py`, `part_5.py`, or `run_analysis.py` beyond
  the SCHEMA_VERSION line.
- Do not attempt to fix the Child Wellbeing base population or First Time Access
  definition — these are documented as unresolvable, not bugs.
- Do not remove `top_two_box` from `stats.py` — it is still used for financial
  stress and potentially other negative-outcome metrics.

---

## Acceptance criteria

1. `python run_analysis.py --run-id 2026_Q2` exits 0; all 8 parts show OK.
2. `meta.schema_version == "1.5"`.
3. `python dashboard_alignment/check_alignment.py` output shows:
   - "Perceived Trust": value ≈ 0.877 (was 0.033), MATCH or INVESTIGATE
   - "Good Understanding of Coverage": value ≈ 0.766, MATCH or INVESTIGATE
   - "Value for Money" (q_worth_premium): value increases from ~0.03 range
4. "Likelihood to Renew" result is unchanged from before this prompt (still MATCH).
5. In `part_6.py`, `q_financial_stress` still uses `top_two_box` (not `bottom_two_box`).
6. In `part_8.py`, `_dim_product_understanding` and `_dim_trust` use `bottom_two_box`.
7. `dashboard_alignment/indicator_map.yaml` has `INVESTIGATE`, `OUT_OF_SCOPE`, and
   `DASHBOARD_ERROR` statuses with resolution notes for the three unresolved gaps.
8. The full `check_alignment.py` output table is posted so the updated comparison
   can be reviewed.
