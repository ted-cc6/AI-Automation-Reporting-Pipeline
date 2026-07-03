# Developer Prompt — Track D: Dashboard Alignment Check
# Files: dashboard_alignment/indicator_map.yaml (new),
#        dashboard_alignment/check_alignment.py (new),
#        run_analysis.py (SCHEMA_VERSION bump only if fixes are needed)

---

## Context

Tracks A–C are complete. SCHEMA_VERSION is "1.4".

The Power BI dashboard for this project uses a structured **Indicator Scoring Framework** —
20 indicators across 9 themes, each with a pre-computed 0–1 score. Our Python analysis
engine must produce values consistent with the dashboard for all overlapping indicators
so the generated report and the interactive dashboard are internally consistent.

This track does three things:
1. Reads the current `analysis_results.json` to identify where each overlapping value lives
2. Compares our Python values against the known Vietnam dashboard values
3. Fixes any discrepancies (the dashboard is the reference)

No new analysis sections are added. This is a validation and correction task only.

---

## Dashboard methodology (extracted from DAX formulas)

The dashboard uses a pre-built `IndicatorScore` table with binary (0/1) scores per
respondent per indicator. Each indicator measure is essentially:

```
Score = SUM(IndicatorScore[Score] WHERE Indicator = "X") / COUNT(Respondents)
```

This is equivalent to our Python `share_true()` or `top_two_box()` patterns —
a proportion of respondents satisfying a condition.

**NPS scale difference — known, not a bug:**
Dashboard NPS formula: `DIVIDE(Promoters, Respondents) - DIVIDE(Detractors, Respondents)`
→ returns NPS as a proportion (e.g. 0.2414 = 24.14%)
Our `nps_score()` returns traditional scale (−100 to +100), so 24.14.
Same methodology, different scale. Divide our value by 100 before comparing.

**Access dimension direction difference — known, not a bug:**
Dashboard "No Access to Alternative Insurance" = raw difficulty rate (higher = worse access).
Our Kling Access dimension = `1 − difficulty_rate` (higher = better access).
For this alignment check, compare against the **raw difficulty_rate before inversion**,
which lives at `parts.part_8.headline.dimensions_detail.access.sub_scores.difficulty_rate.value`.

---

## Vietnam dashboard values (the reference numbers)

These are the `All_Indicator_Score` values extracted from the dashboard, filtered to Vietnam.

| Indicator | Theme | Dashboard Value | Status |
|---|---|---|---|
| Good Understanding of Insurance Coverage | Product Understanding | 0.7517 | Compare |
| Good Understanding of Claim Process | Product Understanding | 0.7655 | Compare |
| Perceived Trust | Trust | 0.8897 | Compare |
| Likelihood to Renew | Trust | 0.5862 | Compare |
| No Access to Alternative Insurance | Access | 0.6966 | Compare (raw difficulty_rate) |
| First Time Access to Insurance | Access | 0.9862 | Compare (compute from dataset) |
| Child Wellbeing Improved | Financial & Child Wellbeing | 0.7120 | Compare |
| Financial Worries Reduced | Financial & Child Wellbeing | 0.8000 | Compare (see note) |
| Net Promoter Score | Client Satisfaction | 0.2414 | Compare (÷100 scale factor) |
| Farming Practices Improved | Crop Insurance | 0.5034 | Expect OUT_OF_SCOPE |
| Livelihood Recovered Immediately | Crop Insurance | 0.3793 | Expect OUT_OF_SCOPE |

**Blank dashboard indicators (do not attempt to match — explained):**
- All 4 Claim Experience indicators: blank because Vietnam crop clients received automatic
  parametric payouts and never formally submitted claims (n_claimants ≈ 0). Our engine
  correctly suppresses these via LOW_N_THRESHOLD. Not a discrepancy.
- Health Insurance, Enhanced Credit Life indicators: not computed for Vietnam in the
  dashboard's data model. Not in scope for our engine either.
- Value for Money: blank in dashboard for unknown reason. Do not attempt to match.

---

## STEP 1 — Read `analysis_results.json` to locate each value

Before writing any code, read `runs/2026_Q2/analysis_results.json` and locate the exact
JSON path for each indicator. Use the guide below as a starting point, but **verify the
actual key names in the file** — do not assume they match exactly.

| Indicator | Where to look first |
|---|---|
| Good Understanding of Coverage | `parts.part_8.headline.dimensions_detail.product_understanding.sub_scores` |
| Good Understanding of Claim Process | same as above |
| Perceived Trust | `parts.part_8.headline.dimensions_detail.trust.sub_scores` |
| Likelihood to Renew | `parts.part_1` — find the renewal intent metric |
| No Access to Alternative Insurance | `parts.part_8.headline.dimensions_detail.access.sub_scores.difficulty_rate` |
| Child Wellbeing Improved | `parts.part_4` — find the child wellbeing improvement metric |
| Financial Worries Reduced | `parts.part_3` — find the metric closest to 0.8000 |
| Net Promoter Score | `parts.part_1` — find the NPS metric |
| First Time Access | not pre-computed — must be computed from dataset (see Step 2) |
| Farming Practices Improved | `parts.part_3` or anywhere — if absent, mark OUT_OF_SCOPE |
| Livelihood Recovered Immediately | same as above |

For each located path, record the exact dot-notation path (e.g.
`parts.part_1.renewal_intent.value`) for use in Step 3.

---

## STEP 2 — Create `dashboard_alignment/indicator_map.yaml`

Create the directory and file. Populate it using the exact JSON paths found in Step 1.
Use this structure:

```yaml
# dashboard_alignment/indicator_map.yaml
# Mapping of dashboard indicators to Python analysis engine values
# dashboard_value: Vietnam score from Power BI (0-1 scale)
# json_path: dot-notation path in analysis_results.json (null = compute from dataset)
# scale_factor: multiply our raw value by this before comparing (1.0 unless noted)
# status: COMPARE | OUT_OF_SCOPE

indicators:
  - name: "Good Understanding of Insurance Coverage"
    theme: "Product Understanding"
    dashboard_value: 0.7517
    json_path: "<fill in from Step 1>"
    scale_factor: 1.0
    status: COMPARE

  - name: "Good Understanding of Claim Process"
    theme: "Product Understanding"
    dashboard_value: 0.7655
    json_path: "<fill in from Step 1>"
    scale_factor: 1.0
    status: COMPARE

  - name: "Perceived Trust"
    theme: "Trust"
    dashboard_value: 0.8897
    json_path: "<fill in from Step 1>"
    scale_factor: 1.0
    status: COMPARE

  - name: "Likelihood to Renew"
    theme: "Trust"
    dashboard_value: 0.5862
    json_path: "<fill in from Step 1>"
    scale_factor: 1.0
    status: COMPARE

  - name: "No Access to Alternative Insurance"
    theme: "Access"
    dashboard_value: 0.6966
    json_path: "<fill in from Step 1 — use raw difficulty_rate, not the inverted Kling value>"
    scale_factor: 1.0
    status: COMPARE

  - name: "First Time Access to Insurance"
    theme: "Access"
    dashboard_value: 0.9862
    json_path: null
    compute: "share_of_respondents_where_q_prior_access_is_False"
    scale_factor: 1.0
    status: COMPARE

  - name: "Child Wellbeing Improved"
    theme: "Financial & Child Wellbeing"
    dashboard_value: 0.7120
    json_path: "<fill in from Step 1>"
    scale_factor: 1.0
    status: COMPARE

  - name: "Financial Worries Reduced"
    theme: "Financial & Child Wellbeing"
    dashboard_value: 0.8000
    json_path: "<fill in from Step 1 — use the Part 3 metric closest to 0.8000>"
    scale_factor: 1.0
    status: COMPARE
    note: >
      DAX uses a pre-computed IndicatorScore binary flag for 'Reduced Financial Stress'.
      Map to the Part 3 metric that best represents reduced financial worry. If no
      metric is within 5 percentage points of 0.8000, flag as INVESTIGATE in output.

  - name: "Net Promoter Score"
    theme: "Client Satisfaction"
    dashboard_value: 0.2414
    json_path: "<fill in from Step 1>"
    scale_factor: 0.01
    status: COMPARE
    note: >
      Dashboard returns NPS as a proportion (0.2414 = 24.14%).
      Our nps_score() returns traditional scale (-100 to +100).
      Apply scale_factor=0.01 before comparing. This is a known scale difference only.

  - name: "Farming Practices Improved"
    theme: "Crop Insurance"
    dashboard_value: 0.5034
    json_path: null
    scale_factor: 1.0
    status: OUT_OF_SCOPE
    note: >
      Crop-specific indicator using a crop-recovery question as the denominator.
      Not currently computed by the analysis engine. Not a bug.

  - name: "Livelihood Recovered Immediately"
    theme: "Crop Insurance"
    dashboard_value: 0.3793
    json_path: null
    scale_factor: 1.0
    status: OUT_OF_SCOPE
    note: >
      Same crop base as above. Not currently computed by the analysis engine. Not a bug.
```

---

## STEP 3 — Create `dashboard_alignment/check_alignment.py`

```python
"""dashboard_alignment/check_alignment.py

Compares analysis engine output against Vietnam Power BI dashboard values.
Run from the project root: python dashboard_alignment/check_alignment.py
"""
import json
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))
from data_loader.data_loader_api import load_survey_data

RUN_ID       = "2026_Q2"
RESULTS_PATH = Path(f"runs/{RUN_ID}/analysis_results.json")
MAP_PATH     = Path("dashboard_alignment/indicator_map.yaml")
TOLERANCE    = 0.005   # 0.5 pp — anything larger is flagged MISMATCH


def get_nested(d: dict, path: str):
    """Traverse a dot-separated path in a nested dict. Returns None on missing key."""
    for key in path.split("."):
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return None
    return d


def compute_first_time_access(ds) -> float:
    """Proportion of respondents whose q_prior_access indicates first-time insurance use."""
    col = "q_prior_access"
    if col not in ds.df.columns:
        return None
    # First-time access = those who had NO insurance before VisionFund
    return float((ds.df[col] == False).sum() / len(ds.df))   # noqa: E712


def main():
    results     = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    indicator_map = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))

    # Load dataset only if First Time Access needs computing
    needs_dataset = any(
        ind.get("compute") == "share_of_respondents_where_q_prior_access_is_False"
        for ind in indicator_map["indicators"]
        if ind.get("status") == "COMPARE"
    )
    ds = load_survey_data(RUN_ID) if needs_dataset else None

    header = f"\n{'Indicator':<48} {'Dashboard':>10} {'Ours':>10} {'Diff':>8}  Status"
    print(header)
    print("─" * len(header))

    mismatches  = []
    missing     = []
    out_of_scope = []

    for ind in indicator_map["indicators"]:
        name   = ind["name"]
        dash   = ind["dashboard_value"]
        scale  = ind.get("scale_factor", 1.0)
        status_flag = ind.get("status", "COMPARE")

        if status_flag == "OUT_OF_SCOPE":
            out_of_scope.append(name)
            print(f"{name:<48} {dash:>10.4f} {'—':>10} {'—':>8}  OUT_OF_SCOPE")
            continue

        our_raw = None
        json_path = ind.get("json_path")
        compute   = ind.get("compute")

        if compute == "share_of_respondents_where_q_prior_access_is_False" and ds is not None:
            our_raw = compute_first_time_access(ds)
        elif json_path:
            our_raw = get_nested(results, json_path)

        if our_raw is None:
            missing.append(name)
            print(f"{name:<48} {dash:>10.4f} {'—':>10} {'—':>8}  MISSING")
            continue

        our_val = float(our_raw) * scale
        diff    = abs(our_val - dash)

        if diff <= TOLERANCE:
            verdict = "MATCH"
        elif diff <= 0.05:
            verdict = "INVESTIGATE"
        else:
            verdict = "MISMATCH"
            mismatches.append((name, dash, our_val, diff))

        print(f"{name:<48} {dash:>10.4f} {our_val:>10.4f} {diff:>8.4f}  {verdict}")

    # Summary
    print("\n── Summary ─────────────────────────────────────────────────────────")
    print(f"  Out of scope (crop-specific, not in engine): {len(out_of_scope)}")
    print(f"  Missing (json_path not found):               {len(missing)}")
    print(f"  Mismatches requiring investigation:          {len(mismatches)}")
    if mismatches:
        print("\n  Mismatches:")
        for nm, dv, ov, df in mismatches:
            print(f"    {nm}: dashboard={dv:.4f}, ours={ov:.4f}, diff={df:.4f}")
    if missing:
        print("\n  Missing — update json_path in indicator_map.yaml:")
        for nm in missing:
            print(f"    {nm}")


if __name__ == "__main__":
    main()
```

---

## STEP 4 — Run, investigate, and fix

1. Run `python dashboard_alignment/check_alignment.py`

2. For any **MISSING** entries: the json_path in indicator_map.yaml is wrong.
   Read `runs/2026_Q2/analysis_results.json` directly to find the correct path,
   update indicator_map.yaml, and re-run.

3. For any **INVESTIGATE** or **MISMATCH** entries: determine root cause.
   Common causes:
   - Different denominator (e.g. all respondents vs. filtered base)
   - Different TTB threshold (top-2 vs. top-1)
   - Different column used (wrong survey question)
   - Rounding at a different step
   The dashboard is the reference. Fix the Python calculation to match.

4. **Financial Worries Reduced** requires special handling: read `parts.part_3`
   from analysis_results.json, identify which metric is closest to 0.8000, update
   indicator_map.yaml with that path, and document in the output which Part 3 metric
   was matched and the resulting diff. If no Part 3 metric is within 5 percentage
   points of 0.8000, output status INVESTIGATE with a note explaining the gap —
   do not guess or fabricate a mapping.

5. After all fixes: re-run `python run_analysis.py --run-id 2026_Q2` to confirm
   existing parts 1–8 are unchanged.

---

## What NOT to do

- Do not modify the Kling Index Access dimension inversion (`1 − difficulty_rate`).
  That inversion is correct for the composite score. Only the alignment check uses
  the raw difficulty_rate.
- Do not add Health Insurance, Enhanced Credit Life, or Crop Insurance indicator
  calculations to the analysis engine — they are out of scope for this track.
- Do not treat the NPS scale difference (÷100) as a methodology error.
- Do not attempt to produce values for the blank Claim Experience indicators —
  their absence is correct and expected behaviour.
- Do not modify any part_1.py through part_8.py file unless a confirmed MISMATCH
  in that section's calculation is found.

---

## Acceptance criteria

1. `dashboard_alignment/indicator_map.yaml` exists with all 11 entries, each with
   a filled `json_path` (or `compute` field) and correct `status`.
2. `python dashboard_alignment/check_alignment.py` runs without errors or exceptions.
3. The 7 high-confidence indicators all show **MATCH** (diff ≤ 0.005):
   Good Understanding of Coverage, Good Understanding of Claim Process,
   Perceived Trust, Likelihood to Renew, No Access to Alternative Insurance,
   Child Wellbeing Improved, and NPS (after ÷100 scale factor).
4. First Time Access shows **MATCH** after computing from `ds.df["q_prior_access"]`.
5. Financial Worries Reduced shows either **MATCH** or a documented **INVESTIGATE**
   note explaining which Part 3 metric was the closest candidate and the gap size.
6. Farming Practices Improved and Livelihood Recovered Immediately both show
   **OUT_OF_SCOPE** — this is the correct outcome, not a failure.
7. If any MISMATCH required a fix to the analysis engine: `python run_analysis.py
   --run-id 2026_Q2` exits 0 with all parts 1–8 showing OK, and SCHEMA_VERSION
   is bumped to `"1.5"`.
8. If no analysis engine fixes were needed: SCHEMA_VERSION remains `"1.4"`.
