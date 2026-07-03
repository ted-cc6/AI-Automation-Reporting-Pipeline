# Developer Prompt — Track D Revert: Restore top_two_box and standard NPS threshold
# Files: analysis_engine/sections/part_1.py,
#        analysis_engine/sections/part_3.py,
#        analysis_engine/stats.py (NPS only),
#        run_analysis.py (SCHEMA_VERSION only)

---

## Context

Track D (Dashboard Alignment) introduced four changes that are conceptually wrong and
must be reverted:

1. `part_1.py` — `coverage_understanding`, `claim_process_understanding`, and
   `renewal_intent` were switched from `top_two_box` to `bottom_two_box`
2. `part_3.py` — `confidence_pay` was switched from `top_two_box` to `bottom_two_box`
3. `stats.py` — the NPS detractor threshold was changed from `≤ 6` to `≤ 5`
4. `run_analysis.py` — `SCHEMA_VERSION` was bumped to `"1.5"`

**Why these are wrong:**
- "Good Understanding of Coverage/Claim Process", "Likelihood to Renew", and
  "Confidence in Pay-out" are positive attributes measured on a Likert scale where
  higher = better. `top_two_box` captures the proportion who responded positively
  (agree/strongly agree). Switching to `bottom_two_box` would measure the proportion
  who responded negatively — the conceptually opposite thing.
- Standard NPS defines detractors as scores 0–6 (i.e. `<= 6`). Changing to `<= 5`
  is non-standard and incorrect.
- Because these changes altered the analysis outputs, `SCHEMA_VERSION` was bumped
  incorrectly. After reverting, the outputs will be identical to the pre-Track-D
  state, so the version must return to `"1.4"`.

**What to keep unchanged:**
- `dashboard_alignment/indicator_map.yaml` — keep as-is
- `dashboard_alignment/check_alignment.py` — keep as-is
- The `bottom_two_box()` function in `stats.py` — keep the function definition itself;
  it is a valid utility that may be used correctly in future tracks. Only revert the
  call sites in `part_1.py` and `part_3.py`.

---

## STEP 1 — Revert `part_1.py`

Find every call to `bottom_two_box` in `part_1.py` that was changed from
`top_two_box` during Track D, and switch it back to `top_two_box`.

The three affected metrics are:
- `coverage_understanding` (column `q_coverage_understanding`)
- `claim_process_understanding` (column `q_claim_process_understanding`)
- `renewal_intent` (column `q_renewal_intent`)

No other changes to `part_1.py`.

---

## STEP 2 — Revert `part_3.py`

Find the call to `bottom_two_box` on `confidence_pay` (column `q_confidence_pay`)
that was changed from `top_two_box` during Track D, and switch it back to
`top_two_box`.

No other changes to `part_3.py`.

---

## STEP 3 — Revert NPS detractor threshold in `stats.py`

In the `nps_score()` function (or wherever the detractor threshold is defined),
revert the detractor condition back to `score <= 6`. The standard NPS definition
is: promoters = 9–10, passives = 7–8, detractors = 0–6.

Do not remove or modify `bottom_two_box()` itself.

---

## STEP 4 — Revert `SCHEMA_VERSION` in `run_analysis.py`

```python
SCHEMA_VERSION = "1.4"   # reverted — Track D wrong changes undone; schema unchanged from Track C
```

---

## STEP 5 — Verify

1. Run `python run_analysis.py --run-id 2026_Q2` and confirm it exits 0 with all
   8 sections showing OK.
2. Run `python dashboard_alignment/check_alignment.py` and paste the full output
   table — we need to see the updated comparison numbers after the revert.

---

## What NOT to do

- Do not investigate or attempt to fix the remaining alignment gaps (Claim Process,
  First Time Access, Child Wellbeing) — those require further information and will
  be addressed in a separate prompt.
- Do not remove `bottom_two_box()` from `stats.py`.
- Do not modify `dashboard_alignment/indicator_map.yaml` or
  `dashboard_alignment/check_alignment.py`.
- Do not touch `part_2.py`, `part_4.py` through `part_8.py`, `stats.py` (beyond
  the NPS threshold), or any other file not listed above.

---

## Acceptance criteria

1. `python run_analysis.py --run-id 2026_Q2` exits 0; all 8 parts show OK.
2. `meta.schema_version == "1.4"` in `runs/2026_Q2/analysis_results.json`.
3. In `part_1.py`, the calls for `coverage_understanding`,
   `claim_process_understanding`, and `renewal_intent` all use `top_two_box`.
4. In `part_3.py`, the call for `confidence_pay` uses `top_two_box`.
5. In `stats.py`, the NPS detractor threshold is `<= 6`.
6. The output of `python dashboard_alignment/check_alignment.py` is posted in full
   so the updated comparison can be reviewed.
