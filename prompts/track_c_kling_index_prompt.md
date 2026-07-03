# Developer Prompt — Track C: Kling Index (Product Understanding, Claims Experience, Trust, Access)
# Files: analysis_engine/stats.py (one new function),
#        analysis_engine/sections/part_8.py (new file),
#        run_analysis.py (import + SECTIONS + version bump)

---

## Context

Tracks A (confidence intervals) and B (logistic regression) are complete.
Current `SCHEMA_VERSION` is `"1.3"`.

Track C adds the **Kling Index** — a composite product-outcome score — as a new Part 8
section. It combines four dimensions into a single 0–1 score, both at the overall
(all-respondents) level and disaggregated by every active segment.

**The four dimensions and their formulas (already locked, do not change):**

| Dimension | Formula | Base |
|---|---|---|
| Product Understanding | mean(TTB(coverage_understanding), TTB(claim_process_understanding)) | all_respondents |
| Claims Experience | claim_paid.pct_of_claimants from claims_funnel() | claimants only (within each scope) |
| Trust | mean(TTB(confidence_pay), (nps + 100) / 200) | all_respondents |
| Access | 1 − share_selecting(alternative_access, difficult_values) | all_respondents |

Composite = unweighted mean of the available 0–1 dimension scores. Minimum 2 of 4 dimensions
must be unsuppressed to produce a composite; if fewer than 2 are available the composite
is suppressed.

**Why Part 8 does NOT use `disaggregate()`:** `disaggregate()` wraps single-series stat
functions. The Kling Index needs to call `claims_funnel()` (a DataFrame-level function, not
a series function) per segment slice. Part 8 therefore loops over segment masks manually
and slices `ds.df` directly — the same pattern already used internally by Parts 6 and 7.

---

## What currently exists (do not modify unless specified)

```
analysis_engine/
    stats.py              ← MODIFY (add composite_index() at the end)
    sections/
        part_8.py         ← CREATE (new file)
        part_1.py … part_7.py   ← do not touch
run_analysis.py            ← MODIFY (add part_8 import + SECTIONS entry + version bump)
```

---

## STEP 1 — Add `composite_index()` to `stats.py`

Place it at the very end of the file, after `disaggregate()`, under a new section header:

```python
# --- Composite index ---

def composite_index(
    dimension_scores: "dict[str, dict]",
    min_dimensions: int = 2,
) -> dict:
    """Average a set of 0–1 dimension scores into a single composite index.

    Each dimension dict must contain:
        value:          float | None    the 0–1 score
        suppressed:     bool            True when value is None or unreliable

    Returns a result dict with:
        value:                  float | None    composite score 0–1 (None if suppressed)
        suppressed:             bool
        suppress_reason:        str | None
        dimensions_included:    list[str]       names of dimensions that contributed
        dimensions_excluded:    list[str]       names excluded (suppressed or missing value)
        n_dimensions:           int             total number of dimensions passed in
    """
    included = []
    excluded = []
    values   = []

    for dim_name, dim_result in dimension_scores.items():
        if dim_result.get("suppressed", True) or dim_result.get("value") is None:
            excluded.append(dim_name)
        else:
            included.append(dim_name)
            values.append(float(dim_result["value"]))

    suppressed = len(values) < min_dimensions
    return {
        "value": (sum(values) / len(values)) if not suppressed else None,
        "suppressed": suppressed,
        "suppress_reason": (
            f"only {len(values)} of {len(dimension_scores)} dimensions available "
            f"(minimum {min_dimensions} required)" if suppressed else None
        ),
        "dimensions_included": included,
        "dimensions_excluded": excluded,
        "n_dimensions": len(dimension_scores),
    }
```

---

## STEP 2 — Create `analysis_engine/sections/part_8.py`

Create this file in full. Do not copy-modify any existing section file.

### Imports

```python
"""analysis_engine/sections/part_8.py — Part 8: Kling Index — Product Outcomes."""
import logging

import pandas as pd

from analysis_engine.stats import (
    top_two_box,
    share_selecting,
    nps_score,
    claims_funnel,
    composite_index,
    LOW_N_THRESHOLD,
)

log = logging.getLogger("analysis_engine.sections.part_8")
```

### Column constants

```python
COL_COVERAGE_UNDERSTANDING      = "q_coverage_understanding"
COL_CLAIM_PROCESS_UNDERSTANDING = "q_claim_process_understanding"
COL_CONFIDENCE_PAY              = "q_confidence_pay"
COL_ALTERNATIVE_ACCESS          = "q_alternative_access"

_ALTERNATIVE_ACCESS_DIFFICULT = ["Very difficult", "Slightly difficult"]

_CLAIMS_EXPERIENCE_NOTE = (
    "Claims Experience is restricted to claimants (q_claim_submitted == True) within "
    "each scope. Segments with fewer than 30 claimants will have this dimension "
    "suppressed and excluded from the composite."
)
```

### Four dimension helpers

Each returns a dict with at minimum `value`, `suppressed`, `n_valid`, and `suppress_reason`,
so it can be passed directly to `composite_index()`.

```python
def _dim_product_understanding(df: pd.DataFrame) -> dict:
    """Mean TTB of coverage and claim-process understanding. Score: 0–1."""
    sub_scores: dict = {}
    available_values = []
    available_ns     = []

    for key, col in [
        ("coverage_understanding",      COL_COVERAGE_UNDERSTANDING),
        ("claim_process_understanding", COL_CLAIM_PROCESS_UNDERSTANDING),
    ]:
        if col not in df.columns:
            sub_scores[key] = {"value": None, "suppressed": True, "n_valid": 0,
                               "suppress_reason": f"column '{col}' missing"}
            continue
        r = top_two_box(df[col])
        sub_scores[key] = r
        if not r["suppressed"] and r["value"] is not None:
            available_values.append(r["value"])
            available_ns.append(r["n_valid"])

    if not available_values:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": "no sub-scores available", "sub_scores": sub_scores}

    return {
        "value":          sum(available_values) / len(available_values),
        "suppressed":     False,
        "n_valid":        min(available_ns),
        "suppress_reason": None,
        "sub_scores":     sub_scores,
    }


def _dim_claims_experience(df: pd.DataFrame) -> dict:
    """Proportion of claimants whose claim was paid. Score: 0–1."""
    funnel     = claims_funnel(df)
    n_claimants = funnel["claim_paid"]["n_total"]   # = n who submitted claims
    n_paid      = funnel["claim_paid"]["n"]
    suppressed  = n_claimants < LOW_N_THRESHOLD

    return {
        "value":          funnel["claim_paid"]["pct_of_claimants"] if not suppressed else None,
        "suppressed":     suppressed,
        "n_valid":        n_claimants,
        "suppress_reason": (
            f"n_valid={n_claimants} below threshold={LOW_N_THRESHOLD}" if suppressed else None
        ),
        "n_paid":         n_paid,
    }


def _dim_trust(df: pd.DataFrame) -> dict:
    """Mean of confidence_pay TTB and normalized NPS ((nps+100)/200). Score: 0–1."""
    sub_scores:      dict  = {}
    available_values: list = []
    available_ns:    list  = []

    if COL_CONFIDENCE_PAY in df.columns:
        cp = top_two_box(df[COL_CONFIDENCE_PAY])
        sub_scores["confidence_pay"] = cp
        if not cp["suppressed"] and cp["value"] is not None:
            available_values.append(cp["value"])
            available_ns.append(cp["n_valid"])

    nps = nps_score(df)
    if not nps["suppressed"] and nps["value"] is not None:
        nps_norm = (nps["value"] + 100) / 200
        sub_scores["nps_normalized"] = {
            "value":          nps_norm,
            "nps_raw":        nps["value"],
            "n_valid":        nps["n_valid"],
            "suppressed":     False,
            "suppress_reason": None,
        }
        available_values.append(nps_norm)
        available_ns.append(nps["n_valid"])
    else:
        sub_scores["nps_normalized"] = {
            "value":      None,
            "suppressed": True,
            "n_valid":    nps["n_valid"],
        }

    if not available_values:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": "no trust sub-scores available", "sub_scores": sub_scores}

    return {
        "value":          sum(available_values) / len(available_values),
        "suppressed":     False,
        "n_valid":        min(available_ns),
        "suppress_reason": None,
        "sub_scores":     sub_scores,
    }


def _dim_access(df: pd.DataFrame) -> dict:
    """Ease of getting alternative insurance: 1 − share finding it difficult. Score: 0–1."""
    if COL_ALTERNATIVE_ACCESS not in df.columns:
        return {"value": None, "suppressed": True, "n_valid": 0,
                "suppress_reason": f"column '{COL_ALTERNATIVE_ACCESS}' missing"}

    alt = share_selecting(df[COL_ALTERNATIVE_ACCESS], _ALTERNATIVE_ACCESS_DIFFICULT)
    if alt["suppressed"] or alt["value"] is None:
        return {"value": None, "suppressed": True, "n_valid": alt["n_valid"],
                "suppress_reason": alt.get("suppress_reason"), "sub_scores": {"difficulty_rate": alt}}

    return {
        "value":          1.0 - alt["value"],
        "suppressed":     False,
        "n_valid":        alt["n_valid"],
        "suppress_reason": None,
        "sub_scores": {"difficulty_rate": alt},
    }
```

### `_compute_kling()` — assembles all four dimensions for one DataFrame slice

```python
def _compute_kling(df: pd.DataFrame) -> dict:
    """Compute the four dimension scores and composite index for a given DataFrame scope."""
    dimension_results = {
        "product_understanding": _dim_product_understanding(df),
        "claims_experience":     _dim_claims_experience(df),
        "trust":                 _dim_trust(df),
        "access":                _dim_access(df),
    }
    composite = composite_index(dimension_results, min_dimensions=2)
    composite["dimensions_detail"] = dimension_results
    return composite
```

### `calculate()` — the public section entry point

```python
def calculate(ds, segment_masks: dict) -> dict:
    """Part 8: Kling Index — composite product-outcome score (overall + per segment)."""
    log.info(f"Part 8: computing Kling Index (n_base={len(ds.df)}, "
             f"n_segments={len(segment_masks)})")

    headline = _compute_kling(ds.df)
    log.info(
        f"Part 8: headline score={headline['value']}, "
        f"dims_included={headline['dimensions_included']}, "
        f"dims_excluded={headline['dimensions_excluded']}"
    )

    segments: dict = {}
    for seg_name, full_mask in segment_masks.items():
        seg_mask = full_mask.reindex(ds.df.index, fill_value=False)
        seg_df   = ds.df[seg_mask]
        segments[seg_name] = _compute_kling(seg_df)
        log.info(
            f"Part 8: segment '{seg_name}' (n={seg_mask.sum()}) "
            f"score={segments[seg_name]['value']}"
        )

    return {
        "base":                   "all_respondents",
        "n_base":                 len(ds.df),
        "dimensions":             ["product_understanding", "claims_experience",
                                   "trust", "access"],
        "method":                 "Unweighted mean of four 0–1 dimension scores (min 2 of 4 required)",
        "min_dimensions_required": 2,
        "claims_experience_note": _CLAIMS_EXPERIENCE_NOTE,
        "headline":               headline,
        "segments":               segments,
    }
```

---

## STEP 3 — Update `run_analysis.py`

### Update the import line

```python
# BEFORE:
from analysis_engine.sections import part_1, part_2, part_3, part_4, part_5, part_6, part_7

# AFTER:
from analysis_engine.sections import part_1, part_2, part_3, part_4, part_5, part_6, part_7, part_8
```

### Add `part_8` to the `SECTIONS` list

```python
SECTIONS = [
    ("part_1", "Client Understanding & Value Perception", part_1),
    ("part_2", "Claims Experience",                       part_2),
    ("part_3", "Financial Resilience",                    part_3),
    ("part_4", "Child Wellbeing Outcomes",                part_4),
    ("part_5", "CWB Drivers",                            part_5),
    ("part_6", "Claimant vs Non-Claimant Scorecard",     part_6),
    ("part_7", "Female vs Male Scorecard",               part_7),
    ("part_8", "Kling Index — Product Outcomes",         part_8),   # ← new line only
]
```

### Bump schema version

```python
SCHEMA_VERSION = "1.4"   # was "1.3" — adds parts.part_8 (Kling Index, Track C)
```

---

## Known data behaviour on the Vietnam dataset — read before verifying

**Claims Experience for the `climate_shock` segment will be suppressed.** Vietnam crop
clients received an automatic parametric payout — they did not file individual claims
(`q_claim_submitted == False`). When `claims_funnel()` is called on the 154-row crop slice,
`n_claimants == 0`, which is below `LOW_N_THRESHOLD`. The `claims_experience` dimension
will be `suppressed: True` and excluded from the climate_shock composite, which will
therefore be computed from 3 of 4 dimensions. This is **correct behaviour**, not a bug,
and is consistent with the `metric_notes.claims_funnel` note already in the output JSON.

---

## What NOT to do

- Do not modify any existing dimension formula (all four formulas are locked per the plan).
- Do not use `disaggregate()` anywhere in `part_8.py` — it cannot handle DataFrame-level
  functions like `claims_funnel()`. The manual mask-slice-loop is the correct pattern here.
- Do not change `part_1.py`–`part_7.py`, `stats.py` (beyond the new function), or any
  other file not listed above.
- Do not scale the final composite to 0–100 — keep it 0–1 throughout (the generation layer
  can reformat for display).
- Do not add a `min_dimensions` argument to `calculate()` or `_compute_kling()` — the
  constant 2 is baked in via the `composite_index()` call and is correct.
- Do not add `pytest` tests or a `__main__` block to `part_8.py`.

---

## Acceptance criteria (verify against `runs/2026_Q2/analysis_results.json`)

1. `python run_analysis.py --run-id 2026_Q2` exits 0, `parts.part_8` is present and
   non-null.
2. `meta.schema_version == "1.4"`.
3. Console summary shows `part_8  Kling Index — Product Outcomes  OK`.
4. `parts.part_8.headline.value` is a float between 0 and 1 inclusive.
5. `parts.part_8.headline.dimensions_included` contains all four dimension names
   (`product_understanding`, `claims_experience`, `trust`, `access`) — the overall
   all-respondents base has enough claimants (n≈153) to clear the threshold.
6. `parts.part_8.headline.dimensions_detail` has four entries, each with a `value`,
   `suppressed: false`, and `sub_scores` where applicable.
7. Each trust `sub_scores.nps_normalized.value` equals `(nps_raw + 100) / 200` exactly
   (verify the normalization arithmetic).
8. Each access `value` equals `1 − difficulty_rate.value` exactly (verify the inversion).
9. `parts.part_8.segments.bundled_service_client.suppressed == true` — n=9 is below
   the LOW_N_THRESHOLD (30) for every dimension, so the composite must be suppressed.
10. `parts.part_8.segments.climate_shock.dimensions_excluded` contains
    `"claims_experience"` and `dimensions_included` contains the other three — confirming
    the graceful exclusion of the claims dimension for crop clients who never filed claims.
11. `parts.part_8.segments.climate_shock.suppressed == false` — the composite is NOT
    suppressed despite losing one dimension, because 3 ≥ min_dimensions (2).
12. `parts.part_1` through `parts.part_7` are structurally unchanged from before this
    update (the existing part_1.py–part_7.py files were untouched).
