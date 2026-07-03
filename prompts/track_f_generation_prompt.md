# Track F/G — Report Generation Layer: Development Plan

> **Context**: Tracks A–E are complete. `runs/2026_Q2/analysis_results.json` (SCHEMA_VERSION 1.5)
> and `runs/2026_Q2/qualitative_results.json` contain all quantitative and qualitative data.
> This track builds Box 4 (Orchestration) and Box 5 (Generation Layer) that produce a
> human-readable Word document report.

---

## Overview of What You Are Building

Seven files in total:

| File | Role |
|------|------|
| `utils.py` (project root) | Shared: `get_nested()`, `format_value()`, `word_count()`, `truncate_to_limit()` |
| `generation/__init__.py` | Empty package marker |
| `generation/report_spec.yaml` | Master config: every section → data paths, word limits, visual filenames |
| `generation/orchestrator.py` | Extracts and packages all data for each of 7 report parts |
| `generation/writer.py` | 7 Gemini 2.5 Pro calls (one per part); house-voice system prompt |
| `generation/assembler.py` | Builds the final `.docx` using python-docx |
| `generation/run_generation.py` | CLI: `--dry-run`, `--parts`, `--run-id` |

**Data flow:**
```
analysis_results.json ─┐
qualitative_results.json┤→ orchestrator.py → part packages → writer.py → text blocks ─┐
runs/*/visuals/*.png ───┘                                                               ├→ assembler.py → report.docx
                                                                                        └──────────────────────────────┘
```

**Gemini calls:** exactly 7 (one per report part), each returning a JSON dict of text blocks.

**Security constraint:** `GEMINI_API_KEY` must never be hardcoded. Always use
`os.environ.get("GEMINI_API_KEY")`. Raise a clear error if it is not set.

---

## Prerequisites

Install if not already present:
```
pip install python-docx google-genai
```

Verify both result files exist before starting any step:
- `runs/2026_Q2/analysis_results.json` (SCHEMA_VERSION 1.5)
- `runs/2026_Q2/qualitative_results.json`

Images live at `runs/2026_Q2/visuals/*.png`. They are manually exported from PowerBI.
If a visual file is absent, the assembler inserts a text placeholder — it never errors.

---

## Step 1 — `utils.py` (project root)

Create `utils.py` at the project root. Four functions only — no extras.

### 1a. `get_nested(d, path, default=None)`

Traverse a nested dict using a dot-separated path string.
Returns `default` if any key is missing or the value at path is `None`.

```python
def get_nested(d: dict, path: str, default=None):
    keys = path.split(".")
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default
```

### 1b. `format_value(v, fmt: str, suppressed: bool = False) -> str`

Convert raw numbers to display strings. Gemini sees these formatted strings, never raw floats.

```python
def format_value(v, fmt: str, suppressed: bool = False) -> str:
    if suppressed or v is None:
        return "SUPPRESSED"
    if fmt == "pct":
        return f"{v * 100:.1f}%"
    if fmt == "pct1":      # one decimal already → e.g. NPS components
        return f"{v * 100:.1f}%"
    if fmt == "score":     # 0–100 index score
        return f"{v * 100:.1f}"
    if fmt == "count":
        return str(int(round(v)))
    if fmt == "rho":
        return f"{v:+.3f}"
    if fmt == "nps":       # NPS is already a -100 to +100 number
        return f"{v:.1f}"
    return str(v)
```

### 1c. `word_count(text: str) -> int`

```python
def word_count(text: str) -> int:
    return len(text.split())
```

### 1d. `truncate_to_limit(text: str, limit: int) -> str`

If `word_count(text) > limit * 1.15`, truncate at the last sentence boundary
(`.`, `?`, `!`) that keeps the text within `limit` words.
If no sentence boundary found, hard-truncate at the word limit and append `"…"`.

```python
import re

def truncate_to_limit(text: str, limit: int) -> str:
    if word_count(text) <= int(limit * 1.15):
        return text
    words = text.split()
    candidate = " ".join(words[:limit])
    # Find last sentence end
    match = re.search(r'[.?!][^.?!]*$', candidate)
    if match:
        return candidate[:match.start() + 1].strip()
    return candidate + "…"
```

---

## Step 2 — `generation/__init__.py`

Create an empty file. Content: one comment `# generation package`.

---

## Step 3 — `generation/report_spec.yaml`

This is the master config. The orchestrator reads it to know what data to extract for each section.

### Key design rules:
- `path`: dotted path into `analysis_results.json` (use `get_nested`)
- `fmt`: format type for `format_value()` — `"pct"`, `"count"`, `"rho"`, `"nps"`, `"score"`
- `suppressed_path`: dotted path to the boolean `suppressed` flag for this metric
- `visuals`: list of filenames in `runs/{run_id}/visuals/` the assembler should insert
- `word_limit`: Gemini word limit for this text block
- `verbatim_section`: key in `qualitative_results.section_verbatims` (e.g. `"part1"`)
- `qualitative_keys`: keys from `qualitative_results` to pass to Gemini for this section

Write the full YAML below. Every path has been verified against
`runs/2026_Q2/analysis_results.json` (SCHEMA_VERSION 1.5).

```yaml
# generation/report_spec.yaml
# Maps each report section to analysis data paths and generation parameters.

schema_version: "1.0"
run_id_default: "2026_Q2"
output_filename: "VFI_Insurance_Impact_Report_2026_Q2.docx"
model: "gemini-2.5-pro"

parts:
  # ─────────────────────────────────────────────────────────────────
  # PART 1 — Product Understanding & Awareness
  # Template sections: 1.1, 1.2, 1.3 + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_1:
    title: "Product Understanding & Awareness"
    visuals:
      - file: "part1_coverage_bar.png"
        caption: "Coverage Understanding by Segment"
      - file: "part1_claims_process_bar.png"
        caption: "Claims Process Understanding by Segment"
    sections:
      s1_1:
        label: "Coverage Understanding"
        word_limit: 90
        metrics:
          coverage_understanding:
            path: "parts.part_1.metrics.coverage_understanding.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.coverage_understanding.headline.n_valid"
            suppressed_path: "parts.part_1.metrics.coverage_understanding.headline.suppressed"
          coverage_understanding_female:
            path: "parts.part_1.metrics.coverage_understanding.segments.female.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.coverage_understanding.segments.female.suppressed"
          coverage_understanding_male:
            path: "parts.part_1.metrics.coverage_understanding.segments.male.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.coverage_understanding.segments.male.suppressed"
          coverage_understanding_claimant:
            path: "parts.part_1.metrics.coverage_understanding.segments.claimant.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.coverage_understanding.segments.claimant.suppressed"
          coverage_understanding_non_claimant:
            path: "parts.part_1.metrics.coverage_understanding.segments.non_claimant.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.coverage_understanding.segments.non_claimant.suppressed"

      s1_2:
        label: "Claim Process Understanding"
        word_limit: 90
        metrics:
          claim_process_understanding:
            path: "parts.part_1.metrics.claim_process_understanding.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.claim_process_understanding.headline.n_valid"
            suppressed_path: "parts.part_1.metrics.claim_process_understanding.headline.suppressed"
          claim_process_understanding_female:
            path: "parts.part_1.metrics.claim_process_understanding.segments.female.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.claim_process_understanding.segments.female.suppressed"
          claim_process_understanding_male:
            path: "parts.part_1.metrics.claim_process_understanding.segments.male.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.claim_process_understanding.segments.male.suppressed"
          claim_process_understanding_claimant:
            path: "parts.part_1.metrics.claim_process_understanding.segments.claimant.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.claim_process_understanding.segments.claimant.suppressed"
          claim_process_understanding_non_claimant:
            path: "parts.part_1.metrics.claim_process_understanding.segments.non_claimant.value"
            fmt: "pct"
            suppressed_path: "parts.part_1.metrics.claim_process_understanding.segments.non_claimant.suppressed"

      s1_3:
        label: "Product Value and Renewal Intent"
        word_limit: 80
        metrics:
          worth_premium:
            path: "parts.part_1.metrics.worth_premium.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.worth_premium.headline.n_valid"
            suppressed_path: "parts.part_1.metrics.worth_premium.headline.suppressed"
          renewal_intent:
            path: "parts.part_1.metrics.renewal_intent.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.renewal_intent.headline.n_valid"
            suppressed_path: "parts.part_1.metrics.renewal_intent.headline.suppressed"
        note: "renewal_intent n=147 is small (only renewal-eligible clients). Mention this caveat."

      insight:
        word_limit: 120
        verbatim_section: "part1"

  # ─────────────────────────────────────────────────────────────────
  # PART 2 — Claims Experience
  # Template sections: 2.1 (funnel table), 2.2, 2.3, 2.4 + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_2:
    title: "Claims Experience"
    visuals:
      - file: "part2_funnel.png"
        caption: "Claims Funnel"
      - file: "part2_no_claim_reasons.png"
        caption: "Reasons for Not Claiming"
      - file: "part2_claim_challenges.png"
        caption: "Top Claims Challenges (% of claimants who challenged)"
    sections:
      s2_1:
        label: "Claims Funnel"
        word_limit: 100
        # Narrative accompanies the funnel table; table is built by assembler
        metrics:
          n_surveyed:
            path: "parts.part_2.claims_funnel.experienced_event.n_total"
            fmt: "count"
          n_experienced_event:
            path: "parts.part_2.claims_funnel.experienced_event.n"
            fmt: "count"
          pct_experienced_event:
            path: "parts.part_2.claims_funnel.experienced_event.pct_of_total"
            fmt: "pct"
          n_filed_claim:
            path: "parts.part_2.claims_funnel.filed_claim.n"
            fmt: "count"
          pct_filed_of_event:
            path: "parts.part_2.claims_funnel.filed_claim.pct_of_event_base"
            fmt: "pct"
          leakage_rate:
            path: "parts.part_2.claims_funnel.filed_claim.leakage"
            fmt: "pct"
          n_claim_paid:
            path: "parts.part_2.claims_funnel.claim_paid.n"
            fmt: "count"
          pct_claim_paid:
            path: "parts.part_2.claims_funnel.claim_paid.pct_of_claimants"
            fmt: "pct"
        funnel_table:
          # Assembler builds this table from the raw JSON paths above.
          # Include this block so the assembler knows a table is needed here.
          headers: ["Stage", "N", "Rate"]
          rows:
            - label: "Experienced insured event"
              n_key: "n_experienced_event"
              rate_key: "pct_experienced_event"
            - label: "Filed a claim"
              n_key: "n_filed_claim"
              rate_key: "pct_filed_of_event"
            - label: "Claim paid"
              n_key: "n_claim_paid"
              rate_key: "pct_claim_paid"

      s2_2:
        label: "Reasons for Not Claiming"
        word_limit: 70
        # distribution list (≤6 items) is passed as-is from analysis JSON
        # qualitative subthemes from claim_no_reason_other are also passed
        metrics:
          no_claim_reasons_base:
            path: "parts.part_2.no_claim_reasons.n_base"
            fmt: "count"
        distribution_path: "parts.part_2.no_claim_reasons.distribution"
        qualitative_keys:
          - "other_subthemes.claim_no_reason_other"

      s2_3:
        label: "Claim Challenges"
        word_limit: 80
        metrics:
          challenges_base:
            path: "parts.part_2.claim_challenges.n_base"
            fmt: "count"
        # ranked list is passed as-is (list of {option, n, pct})
        distribution_path: "parts.part_2.claim_challenges.ranked.ranked"
        qualitative_keys:
          - "other_subthemes.claim_challenges_other_support"
          - "protection_flags"
        note: "If any protection_flags were found, surface them briefly in this section."

      s2_4:
        label: "Claim Channel and Payout Outcomes"
        word_limit: 100
        metrics:
          channel_base:
            path: "parts.part_2.claim_channel_preferred.n_base"
            fmt: "count"
          claim_result_base:
            path: "parts.part_2.claim_result.n_base"
            fmt: "count"
          payout_cost_base:
            path: "parts.part_2.payout_cost_coverage.n_base"
            fmt: "count"
        distribution_path: "parts.part_2.claim_channel_preferred.distribution"
        extra_distributions:
          claim_result: "parts.part_2.claim_result.distribution"
          payout_cost_coverage: "parts.part_2.payout_cost_coverage.distribution"

      insight:
        word_limit: 120
        verbatim_section: "part2"

  # ─────────────────────────────────────────────────────────────────
  # PART 3 — Financial Protection
  # Template sections: 3.1, 3.2 + Insight box
  # Note: negative_coping and financial_stress_high have claimant base (n=363)
  # ─────────────────────────────────────────────────────────────────
  part_3:
    title: "Financial Protection"
    visuals:
      - file: "part3_financial_protection.png"
        caption: "Financial Protection Indicators"
    sections:
      s3_1:
        label: "Financial Stress and Coping"
        word_limit: 80
        metrics:
          negative_coping:
            path: "parts.part_3.metrics.negative_coping.headline.value"
            fmt: "pct"
            n_path: "parts.part_3.metrics.negative_coping.headline.n_valid"
            suppressed_path: "parts.part_3.metrics.negative_coping.headline.suppressed"
          financial_stress_high:
            path: "parts.part_3.metrics.financial_stress_high.headline.value"
            fmt: "pct"
            n_path: "parts.part_3.metrics.financial_stress_high.headline.n_valid"
            suppressed_path: "parts.part_3.metrics.financial_stress_high.headline.suppressed"
          alternative_access_difficult:
            path: "parts.part_3.metrics.alternative_access_difficult.headline.value"
            fmt: "pct"
            n_path: "parts.part_3.metrics.alternative_access_difficult.headline.n_valid"
            suppressed_path: "parts.part_3.metrics.alternative_access_difficult.headline.suppressed"
        note: >
          negative_coping and financial_stress_high are measured on the claimant base (n=363).
          alternative_access_difficult is measured on the full sample.
          These metrics use inverted Likert scale (lower = better coping/stress,
          higher alternative_access = more difficulty without this insurance).

      s3_2:
        label: "Confidence and Value"
        word_limit: 70
        metrics:
          confidence_pay:
            path: "parts.part_3.metrics.confidence_pay.headline.value"
            fmt: "pct"
            n_path: "parts.part_3.metrics.confidence_pay.headline.n_valid"
            suppressed_path: "parts.part_3.metrics.confidence_pay.headline.suppressed"
          worth_premium:
            path: "parts.part_1.metrics.worth_premium.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.worth_premium.headline.n_valid"
            suppressed_path: "parts.part_1.metrics.worth_premium.headline.suppressed"

      insight:
        word_limit: 120
        verbatim_section: "part3"

  # ─────────────────────────────────────────────────────────────────
  # PART 4 — Client Voice (NPS & Themes)
  # Template sections: 4.1, 4.2, 4.3 + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_4:
    title: "Client Voice"
    visuals:
      - file: "part4_nps.png"
        caption: "Net Promoter Score"
      - file: "part4_themes.png"
        caption: "Top NPS Theme Drivers"
    sections:
      s4_1:
        label: "Net Promoter Score"
        word_limit: 90
        metrics:
          nps_score:
            path: "parts.part_4.nps.result.value"
            fmt: "nps"
            n_path: "parts.part_4.nps.result.n_valid"
            suppressed_path: "parts.part_4.nps.result.suppressed"
          nps_promoter_n:
            path: "parts.part_4.nps.result.promoters.n"
            fmt: "count"
          nps_promoter_pct:
            path: "parts.part_4.nps.result.promoters.pct"
            fmt: "pct"
          nps_passive_n:
            path: "parts.part_4.nps.result.passives.n"
            fmt: "count"
          nps_passive_pct:
            path: "parts.part_4.nps.result.passives.pct"
            fmt: "pct"
          nps_detractor_n:
            path: "parts.part_4.nps.result.detractors.n"
            fmt: "count"
          nps_detractor_pct:
            path: "parts.part_4.nps.result.detractors.pct"
            fmt: "pct"
        qualitative_keys:
          - "not_worth_it_themes"
        note: >
          not_worth_it_themes from qualitative identifies why clients who rated the
          premium as 'not worth it' (worth_premium_value >= 4) feel this way.
          Mention top 1-2 themes if available.

      s4_2:
        label: "Promoter and Detractor Themes"
        word_limit: 90
        qualitative_keys:
          - "theme_counts.promoters"
          - "theme_counts.detractors"
        note: >
          theme_counts are Python-counted from Gemini's compact NPS tag arrays.
          Report top 3 promoter themes and top 3 detractor themes by count.

      s4_3:
        label: "Value and Wellbeing Outcomes"
        word_limit: 80
        metrics:
          worth_premium:
            path: "parts.part_1.metrics.worth_premium.headline.value"
            fmt: "pct"
            n_path: "parts.part_1.metrics.worth_premium.headline.n_valid"
          child_wellbeing:
            path: "parts.part_4.child_wellbeing.headline.value"
            fmt: "pct"
            n_path: "parts.part_4.child_wellbeing.headline.n_valid"
            suppressed_path: "parts.part_4.child_wellbeing.headline.suppressed"
          healthcare_access:
            path: "parts.part_4.healthcare_access.headline.value"
            fmt: "pct"
            n_path: "parts.part_4.healthcare_access.headline.n_valid"
            suppressed_path: "parts.part_4.healthcare_access.headline.suppressed"

      insight:
        word_limit: 120
        verbatim_section: "part4"

  # ─────────────────────────────────────────────────────────────────
  # PART 5 — Child Wellbeing
  # Template sections: 5.1 (drivers + table), 5.2 + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_5:
    title: "Child Wellbeing"
    visuals:
      - file: "part5_drivers.png"
        caption: "Child Wellbeing Drivers (Spearman Correlation)"
      - file: "part5_healthcare.png"
        caption: "Healthcare Access and Medical Cost Impact"
    sections:
      s5_1:
        label: "Child Wellbeing Drivers"
        word_limit: 90
        metrics:
          cwb_headline:
            path: "parts.part_4.child_wellbeing.headline.value"
            fmt: "pct"
            n_path: "parts.part_4.child_wellbeing.headline.n_valid"
        # All 7 Spearman drivers — pass rho and p_value for each
        # suppressed means the driver's value is None in the JSON
        drivers:
          financial_stress:
            rho_path: "parts.part_5.drivers.financial_stress.value"
            p_path: "parts.part_5.drivers.financial_stress.p_value"
            n_path: "parts.part_5.drivers.financial_stress.n_valid"
            suppressed_path: "parts.part_5.drivers.financial_stress.suppressed"
          coverage_understanding:
            rho_path: "parts.part_5.drivers.coverage_understanding.value"
            p_path: "parts.part_5.drivers.coverage_understanding.p_value"
            n_path: "parts.part_5.drivers.coverage_understanding.n_valid"
            suppressed_path: "parts.part_5.drivers.coverage_understanding.suppressed"
          claim_process_understanding:
            rho_path: "parts.part_5.drivers.claim_process_understanding.value"
            p_path: "parts.part_5.drivers.claim_process_understanding.p_value"
            n_path: "parts.part_5.drivers.claim_process_understanding.n_valid"
            suppressed_path: "parts.part_5.drivers.claim_process_understanding.suppressed"
          worth_premium:
            rho_path: "parts.part_5.drivers.worth_premium.value"
            p_path: "parts.part_5.drivers.worth_premium.p_value"
            n_path: "parts.part_5.drivers.worth_premium.n_valid"
            suppressed_path: "parts.part_5.drivers.worth_premium.suppressed"
          renewal_intent:
            rho_path: "parts.part_5.drivers.renewal_intent.value"
            p_path: "parts.part_5.drivers.renewal_intent.p_value"
            n_path: "parts.part_5.drivers.renewal_intent.n_valid"
            suppressed_path: "parts.part_5.drivers.renewal_intent.suppressed"
          confidence_pay:
            rho_path: "parts.part_5.drivers.confidence_pay.value"
            p_path: "parts.part_5.drivers.confidence_pay.p_value"
            n_path: "parts.part_5.drivers.confidence_pay.n_valid"
            suppressed_path: "parts.part_5.drivers.confidence_pay.suppressed"
          nps_score:
            rho_path: "parts.part_5.drivers.nps_score.value"
            p_path: "parts.part_5.drivers.nps_score.p_value"
            n_path: "parts.part_5.drivers.nps_score.n_valid"
            suppressed_path: "parts.part_5.drivers.nps_score.suppressed"
        drivers_table:
          # Assembler builds this table. Rows = driver variables, sorted by |rho|.
          # Column headers: ["Driver", "ρ (Spearman)", "p-value", "N"]
          headers: ["Driver", "ρ (Spearman)", "p-value", "N"]
        note: >
          All correlations are Spearman. financial_stress uses top_two_box (high stress);
          all other drivers use bottom_two_box (positive response).
          A negative rho for financial_stress means higher stress → lower CWB score (correct direction).
          A driver with a null value in the JSON is suppressed — show "SUPPRESSED" in the table.

      s5_2:
        label: "Healthcare Access and Medical Cost"
        word_limit: 80
        metrics:
          healthcare_access:
            path: "parts.part_4.healthcare_access.headline.value"
            fmt: "pct"
            n_path: "parts.part_4.healthcare_access.headline.n_valid"
            suppressed_path: "parts.part_4.healthcare_access.headline.suppressed"
          medical_cost_change:
            path: "parts.part_4.medical_cost_change.headline.value"
            fmt: "pct"
            n_path: "parts.part_4.medical_cost_change.headline.n_valid"
            suppressed_path: "parts.part_4.medical_cost_change.headline.suppressed"
        note: >
          healthcare_access: % who said access to care improved (among those who needed care, n≈1,672).
          medical_cost_change: % who said medical costs decreased after claim (claimants with
          medical costs, n≈926). n_total for medical_cost_change includes only claimants who sought care.

      insight:
        word_limit: 120
        verbatim_section: "part5"

  # ─────────────────────────────────────────────────────────────────
  # PART 6 — Claimant vs Non-Claimant Comparison
  # Template: scorecard table (7 metrics × 2 groups) + narrative + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_6:
    title: "Claimant vs. Non-Claimant Outcomes"
    visuals:
      - file: "part6_scorecard.png"
        caption: "Key Metrics: Claimants vs. Non-Claimants"
    scorecard_metrics:
      # Assembler builds the table; orchestrator extracts all values.
      # Metrics in parts.part_6.metrics — each has .claimant, .non_claimant, .significance.p_value
      - key: coverage_understanding
        label: "Coverage Understanding"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.coverage_understanding.claimant.value"
        non_claimant_path: "parts.part_6.metrics.coverage_understanding.non_claimant.value"
        sig_path: "parts.part_6.metrics.coverage_understanding.significance.p_value"
        claimant_sup: "parts.part_6.metrics.coverage_understanding.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.coverage_understanding.non_claimant.suppressed"
      - key: claim_process_understanding
        label: "Claim Process Understanding"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.claim_process_understanding.claimant.value"
        non_claimant_path: "parts.part_6.metrics.claim_process_understanding.non_claimant.value"
        sig_path: "parts.part_6.metrics.claim_process_understanding.significance.p_value"
        claimant_sup: "parts.part_6.metrics.claim_process_understanding.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.claim_process_understanding.non_claimant.suppressed"
      - key: worth_premium
        label: "Worth Premium"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.worth_premium.claimant.value"
        non_claimant_path: "parts.part_6.metrics.worth_premium.non_claimant.value"
        sig_path: "parts.part_6.metrics.worth_premium.significance.p_value"
        claimant_sup: "parts.part_6.metrics.worth_premium.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.worth_premium.non_claimant.suppressed"
      - key: renewal_intent
        label: "Renewal Intent"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.renewal_intent.claimant.value"
        non_claimant_path: "parts.part_6.metrics.renewal_intent.non_claimant.value"
        sig_path: "parts.part_6.metrics.renewal_intent.significance.p_value"
        claimant_sup: "parts.part_6.metrics.renewal_intent.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.renewal_intent.non_claimant.suppressed"
      - key: negative_coping
        label: "Negative Coping (↓ better)"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.negative_coping.claimant.value"
        non_claimant_path: "parts.part_6.metrics.negative_coping.non_claimant.value"
        sig_path: "parts.part_6.metrics.negative_coping.significance.p_value"
        claimant_sup: "parts.part_6.metrics.negative_coping.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.negative_coping.non_claimant.suppressed"
      - key: financial_stress_high
        label: "High Financial Stress (↓ better)"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.financial_stress_high.claimant.value"
        non_claimant_path: "parts.part_6.metrics.financial_stress_high.non_claimant.value"
        sig_path: "parts.part_6.metrics.financial_stress_high.significance.p_value"
        claimant_sup: "parts.part_6.metrics.financial_stress_high.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.financial_stress_high.non_claimant.suppressed"
      - key: confidence_pay
        label: "Confidence in Next Premium Payment"
        fmt: "pct"
        claimant_path: "parts.part_6.metrics.confidence_pay.claimant.value"
        non_claimant_path: "parts.part_6.metrics.confidence_pay.non_claimant.value"
        sig_path: "parts.part_6.metrics.confidence_pay.significance.p_value"
        claimant_sup: "parts.part_6.metrics.confidence_pay.claimant.suppressed"
        non_claimant_sup: "parts.part_6.metrics.confidence_pay.non_claimant.suppressed"
    sections:
      narrative:
        word_limit: 100
        note: >
          Significance threshold: p < 0.05 = statistically significant, mark with *.
          The note about negative_coping and financial_stress_high being on the claimant
          base (not both groups equally) should be mentioned if relevant.
      insight:
        word_limit: 120
        verbatim_section: "part6"

  # ─────────────────────────────────────────────────────────────────
  # PART 7 — Gender Comparison
  # Template: scorecard table (7 metrics × female/male) + narrative + Insight box
  # ─────────────────────────────────────────────────────────────────
  part_7:
    title: "Gender Analysis"
    visuals:
      - file: "part7_scorecard.png"
        caption: "Key Metrics by Gender"
    scorecard_metrics:
      # Same 7 metrics from parts.part_7.metrics — each has .female, .male, .significance.p_value
      - key: coverage_understanding
        label: "Coverage Understanding"
        fmt: "pct"
        female_path: "parts.part_7.metrics.coverage_understanding.female.value"
        male_path: "parts.part_7.metrics.coverage_understanding.male.value"
        sig_path: "parts.part_7.metrics.coverage_understanding.significance.p_value"
        female_sup: "parts.part_7.metrics.coverage_understanding.female.suppressed"
        male_sup: "parts.part_7.metrics.coverage_understanding.male.suppressed"
      - key: claim_process_understanding
        label: "Claim Process Understanding"
        fmt: "pct"
        female_path: "parts.part_7.metrics.claim_process_understanding.female.value"
        male_path: "parts.part_7.metrics.claim_process_understanding.male.value"
        sig_path: "parts.part_7.metrics.claim_process_understanding.significance.p_value"
        female_sup: "parts.part_7.metrics.claim_process_understanding.female.suppressed"
        male_sup: "parts.part_7.metrics.claim_process_understanding.male.suppressed"
      - key: worth_premium
        label: "Worth Premium"
        fmt: "pct"
        female_path: "parts.part_7.metrics.worth_premium.female.value"
        male_path: "parts.part_7.metrics.worth_premium.male.value"
        sig_path: "parts.part_7.metrics.worth_premium.significance.p_value"
        female_sup: "parts.part_7.metrics.worth_premium.female.suppressed"
        male_sup: "parts.part_7.metrics.worth_premium.male.suppressed"
      - key: renewal_intent
        label: "Renewal Intent"
        fmt: "pct"
        female_path: "parts.part_7.metrics.renewal_intent.female.value"
        male_path: "parts.part_7.metrics.renewal_intent.male.value"
        sig_path: "parts.part_7.metrics.renewal_intent.significance.p_value"
        female_sup: "parts.part_7.metrics.renewal_intent.female.suppressed"
        male_sup: "parts.part_7.metrics.renewal_intent.male.suppressed"
      - key: negative_coping
        label: "Negative Coping (↓ better)"
        fmt: "pct"
        female_path: "parts.part_7.metrics.negative_coping.female.value"
        male_path: "parts.part_7.metrics.negative_coping.male.value"
        sig_path: "parts.part_7.metrics.negative_coping.significance.p_value"
        female_sup: "parts.part_7.metrics.negative_coping.female.suppressed"
        male_sup: "parts.part_7.metrics.negative_coping.male.suppressed"
      - key: financial_stress_high
        label: "High Financial Stress (↓ better)"
        fmt: "pct"
        female_path: "parts.part_7.metrics.financial_stress_high.female.value"
        male_path: "parts.part_7.metrics.financial_stress_high.male.value"
        sig_path: "parts.part_7.metrics.financial_stress_high.significance.p_value"
        female_sup: "parts.part_7.metrics.financial_stress_high.female.suppressed"
        male_sup: "parts.part_7.metrics.financial_stress_high.male.suppressed"
      - key: confidence_pay
        label: "Confidence in Next Premium Payment"
        fmt: "pct"
        female_path: "parts.part_7.metrics.confidence_pay.female.value"
        male_path: "parts.part_7.metrics.confidence_pay.male.value"
        sig_path: "parts.part_7.metrics.confidence_pay.significance.p_value"
        female_sup: "parts.part_7.metrics.confidence_pay.female.suppressed"
        male_sup: "parts.part_7.metrics.confidence_pay.male.suppressed"
    sections:
      narrative:
        word_limit: 100
        note: >
          Significance threshold: p < 0.05 = statistically significant, mark with *.
          The female sample is dominant (n≈1,518 vs male n≈586); note this if relevant.
      insight:
        word_limit: 120
        verbatim_section: "part7"
```

---

## Step 4 — `generation/orchestrator.py`

The orchestrator extracts all data, builds one **part package** dict per report part,
and checks visual file availability.

### 4a. Imports and constants

```python
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from utils import get_nested, format_value

SPEC_PATH = ROOT / "generation" / "report_spec.yaml"
```

### 4b. `preflight_check(run_id: str) -> dict`

Returns `{"ok": True/False, "errors": [...], "warnings": [...]}`.

Errors (abort):
- `runs/{run_id}/analysis_results.json` missing
- `runs/{run_id}/qualitative_results.json` missing

Warnings (proceed):
- Any visual file listed in report_spec.yaml is absent → list missing filenames

Print errors as `[ERROR]` and warnings as `[WARN]`.

### 4c. `load_data(run_id: str) -> tuple[dict, dict]`

Load and return `(analysis, qualitative)` dicts from JSON files.
Verify `analysis["meta"]["schema_version"] == "1.5"` — raise `ValueError` if wrong.

### 4d. `extract_metrics(analysis: dict, qual: dict, section_spec: dict) -> dict`

Build a flat dict of `{key: formatted_string}` for a single section.

Algorithm:
1. For each entry in `section_spec.get("metrics", {})`:
   - `v = get_nested(analysis, entry["path"])`
   - `sup = get_nested(analysis, entry.get("suppressed_path", ""), default=False)`
   - `formatted = format_value(v, entry["fmt"], suppressed=bool(sup))`
   - Store as `result[metric_key] = formatted`
   - If `n_path` exists, also store `result[metric_key + "_n"] = format_value(get_nested(analysis, entry["n_path"]), "count")`
2. For `drivers` (Part 5 only): iterate `section_spec.get("drivers", {})` similarly,
   storing `{driver_key}_rho`, `{driver_key}_p`, `{driver_key}_n`.
3. For `scorecard_metrics` (Parts 6 & 7): extract claimant/non_claimant or female/male
   values and significance p-values. Store as `{key}_claimant`, `{key}_non_claimant`,
   `{key}_sig_p` (or `{key}_female`, `{key}_male`).

### 4e. `extract_qualitative(qual: dict, section_spec: dict) -> dict`

Build a dict of qualitative data for a section.

For each key in `section_spec.get("qualitative_keys", [])`:
- Navigate the key path in `qual` using `get_nested` (replace `.` with nested access)
- Example: `"theme_counts.promoters"` → `qual["theme_counts"]["promoters"]`
- Include the raw object as-is (Gemini will interpret it)

For `verbatim_section`:
- Extract `qual["section_verbatims"][section_key]` — list of `{id, text, profile}`
- Include the full list (up to 3 items)

Return `{"themes": ..., "verbatims": ..., "flags": ..., ...}` as appropriate.

### 4f. `extract_distribution(analysis: dict, path: str) -> list`

Use `get_nested(analysis, path)` and return the list. Returns `[]` if path not found.
For `claim_challenges.ranked.ranked`, the result is inside a nested `ranked` key —
handle this by just using the full path `"parts.part_2.claim_challenges.ranked.ranked"`.

### 4g. `check_visual(run_id: str, filename: str) -> Path | None`

Return full `Path` if `runs/{run_id}/visuals/{filename}` exists, else `None`.

### 4h. `build_part_package(part_key: str, analysis: dict, qual: dict, spec: dict, run_id: str) -> dict`

Assemble a complete data package for one part. This dict is what gets sent to the writer.

Structure:
```python
{
    "part": part_key,               # e.g. "part_1"
    "title": spec_part["title"],
    "sections": {                   # one sub-dict per section key
        "s1_1": {
            "label": "Coverage Understanding",
            "word_limit": 90,
            "metrics": {...},       # formatted strings from extract_metrics
            "distributions": [...], # raw distribution lists where applicable
            "qualitative": {...},   # from extract_qualitative
            "note": "...",
        },
        ...
        "insight": {
            "word_limit": 120,
            "verbatims": [...],     # enriched verbatim objects
        }
    },
    "scorecard": [...],             # Parts 6 & 7 only: list of scorecard row dicts
    "visuals": [                    # one entry per visual
        {"file": "part1_coverage_bar.png", "path": "runs/.../visuals/...", "exists": True},
        ...
    ],
}
```

For Parts 6 and 7, iterate `spec_part["scorecard_metrics"]` and build:
```python
scorecard_rows = [
    {
        "label": "Coverage Understanding",
        "group_a_label": "Claimant",   # or "Female"
        "group_a_value": "94.8%",
        "group_b_label": "Non-Claimant",  # or "Male"
        "group_b_value": "61.9%",
        "sig_p": 5.38e-13,
        "significant": True,           # p < 0.05
    },
    ...
]
```

### 4i. `orchestrate(run_id: str, parts_filter: list = None) -> list[dict]`

Main function. Load spec and data, build packages for all 7 parts
(or only those in `parts_filter`). Return list of packages.

```python
def orchestrate(run_id, parts_filter=None):
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    analysis, qual = load_data(run_id)
    packages = []
    for part_key, part_spec in spec["parts"].items():
        if parts_filter and part_key not in parts_filter:
            continue
        pkg = build_part_package(part_key, analysis, qual, part_spec, run_id)
        packages.append(pkg)
    return packages
```

---

## Step 5 — `generation/writer.py`

Seven Gemini calls — one per report part — each returning a JSON dict of text blocks.

### 5a. `HOUSE_VOICE` constant (module-level)

```python
HOUSE_VOICE = """
You are writing the VisionFund International Insurance Impact Report — Vietnam 2026 Q2.

AUDIENCE: Senior MFI leaders, impact investors, and programme managers. 
Assume they understand financial inclusion concepts but not statistical methods.

VOICE RULES:
- Professional, empathetic, evidence-based
- Active voice. Past tense for findings ("revealed", "showed"), present for implications ("suggests", "indicates")
- No bullet points, no headers, no markdown in narrative text — flowing prose only
- Do not use academic jargon (no "statistically significant" — say "the difference is meaningful" or cite the p-value)
- Every statistic you cite MUST come from the data package. Never invent or round figures beyond what is provided.
- Suppressed values (marked "SUPPRESSED") must be noted as "data suppressed due to small sample size" — never estimate or interpolate
- When a note field is present, incorporate its guidance into the narrative

WORD LIMITS (strictly enforced):
- If a section specifies word_limit: 90, write AT MOST 90 words. Aim for 85-90.
- insight blocks: 120 words maximum. Aim for 110-120.
- narrative blocks (Parts 6, 7): 100 words maximum.
- Precision matters more than hitting the limit exactly. A tight 80-word paragraph is better than a padded 90-word one.

OUTPUT FORMAT:
Return ONLY valid JSON with the exact keys listed in the user message.
No markdown code fences, no explanation text outside the JSON.
"""
```

### 5b. `_build_part_prompt(package: dict, part_key: str) -> str`

Build the user message for one Gemini call. Include:
1. The part title and part number
2. For each section: label, word limit, all metric key-value pairs, distributions (summarised to top 5 items), qualitative data
3. The expected JSON output keys and their word limits
4. The verbatim data (text + profile) for the insight box

**Format the data concisely.** Convert nested dicts to readable lines.
Example metric block:
```
SECTION s1_1 — Coverage Understanding (word_limit: 90 words)
  coverage_understanding: 76.6%  (n=2,104)
  coverage_understanding_female: 75.5%
  coverage_understanding_male: 79.4%
  coverage_understanding_claimant: 94.8%
  coverage_understanding_non_claimant: 61.9%
```

For distributions, list each item as `"value (n=N, pct%)"`

For verbatims, list each as:
```
VERBATIM 1: "text" [Female, age 34, Ha Noi branch, non-claimant]
VERBATIM 2: ...
```

For qualitative theme counts, list top 5 by count:
```
TOP PROMOTER THEMES: staff_service (312), general_satisfaction (198), financial_relief (145), ...
TOP DETRACTOR THEMES: claims_process (89), product_value (67), claims_speed (54), ...
```

End with the exact required JSON output schema:
```
REQUIRED OUTPUT JSON KEYS:
{
  "s1_1": "...",  // ≤90 words
  "s1_2": "...",  // ≤90 words
  "s1_3": "...",  // ≤80 words
  "insight": "..."  // ≤120 words
}
```

### 5c. Output schemas per part

**Part 1:** `{"s1_1": "...", "s1_2": "...", "s1_3": "...", "insight": "..."}`

**Part 2:** `{"s2_1": "...", "s2_2": "...", "s2_3": "...", "s2_4": "...", "insight": "..."}`

**Part 3:** `{"s3_1": "...", "s3_2": "...", "insight": "..."}`

**Part 4:** `{"s4_1": "...", "s4_2": "...", "s4_3": "...", "insight": "..."}`

**Part 5:** `{"s5_1": "...", "s5_2": "...", "insight": "..."}`

**Part 6:** `{"narrative": "...", "insight": "..."}`

**Part 7:** `{"narrative": "...", "insight": "..."}`

### 5d. `write_part(package: dict, part_key: str, client, model: str) -> dict`

```python
def write_part(package, part_key, client, model):
    user_message = _build_part_prompt(package, part_key)
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=HOUSE_VOICE,
            response_mime_type="application/json",
            max_output_tokens=8192,
            temperature=0.3,
        ),
    )
    raw_text = response.text
    return json.loads(raw_text)
```

### 5e. Word-limit enforcement after each call

After `write_part`, check every text value:
```python
from utils import word_count, truncate_to_limit

WORD_LIMITS = {
    "s1_1": 90, "s1_2": 90, "s1_3": 80,
    "s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100,
    "s3_1": 80, "s3_2": 70,
    "s4_1": 90, "s4_2": 90, "s4_3": 80,
    "s5_1": 90, "s5_2": 80,
    "narrative": 100,
    "insight": 120,
}

def enforce_word_limits(texts: dict) -> dict:
    enforced = {}
    for key, text in texts.items():
        if key in WORD_LIMITS:
            limit = WORD_LIMITS[key]
            if word_count(text) > int(limit * 1.15):
                original_count = word_count(text)
                text = truncate_to_limit(text, limit)
                print(f"  [WARN] {key}: truncated {original_count} → {word_count(text)} words")
        enforced[key] = text
    return enforced
```

### 5f. `write_all_parts(packages: list, run_id: str, model: str) -> dict`

Iterates all packages, calls `write_part`, enforces word limits.
Saves each raw Gemini response to `runs/{run_id}/writer_raw_{part_key}.json` (for debugging/re-run).
Also saves the final text collection to `runs/{run_id}/written_texts.json`.

Returns `{part_key: text_dict}` — e.g. `{"part_1": {"s1_1": "...", ...}, "part_2": {...}, ...}`.

Requires `GEMINI_API_KEY` environment variable — raise `EnvironmentError` with clear message if absent.

---

## Step 6 — `generation/assembler.py`

Builds the final `.docx`. Uses `python-docx` only. No Gemini calls here.

### 6a. Imports

```python
from docx import Document
from docx.shared import Inches, Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
```

### 6b. Helper: `_format_profile(profile: dict) -> str`

```python
def _format_profile(profile: dict) -> str:
    parts = []
    if profile.get("sex"):
        parts.append(profile["sex"])
    if profile.get("age"):
        parts.append(f"age {profile['age']}")
    if profile.get("branch"):
        parts.append(profile["branch"])
    flags = []
    if profile.get("is_claimant"):
        flags.append("claimant")
    if profile.get("is_caregiver"):
        flags.append("caregiver")
    if flags:
        parts.append(", ".join(flags))
    return " | ".join(parts) if parts else "anonymous"
```

### 6c. Helper: `_add_heading(doc, text, level)`

Standard `doc.add_heading(text, level=level)`.

### 6d. Helper: `_add_paragraph(doc, text, style=None)`

Standard `doc.add_paragraph(text, style=style)`.

### 6e. Helper: `_add_insight_box(doc, insight_text: str, verbatims: list)`

1. Add a styled heading `"Key Insight"` (level 3 or "Heading 3")
2. Add `insight_text` as a paragraph
3. For each verbatim in `verbatims` (up to 3):
   - Add a `"Quote"` style paragraph: `f'"{v["text"]}"'`
   - Add a smaller italic paragraph: `f'— {_format_profile(v["profile"])}'`

If docx "Quote" style isn't available, create a paragraph with left indent.

### 6f. Helper: `_add_image_or_placeholder(doc, visual_info: dict)`

```python
def _add_image_or_placeholder(doc, visual_info):
    if visual_info["exists"] and visual_info["path"]:
        doc.add_picture(str(visual_info["path"]), width=Inches(5.5))
        p = doc.add_paragraph(visual_info.get("caption", ""), style="Caption")
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p = doc.add_paragraph(
            f'[VISUAL PENDING: {visual_info["file"]} — {visual_info.get("caption", "")}]'
        )
        p.runs[0].italic = True
```

### 6g. Helper: `_add_table(doc, headers: list, rows: list[list]) -> Table`

Create a standard docx table. First row = header row (bold). Each subsequent row = data row.
Apply a basic table style (`"Table Grid"` or `"Light Grid"`).

```python
def _add_table(doc, headers, rows):
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    table.style = "Table Grid"
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        cell.paragraphs[0].runs[0].bold = True
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            table.rows[r_idx + 1].cells[c_idx].text = str(val)
    return table
```

### 6h. Part builder: `build_part_1(doc, package, texts)`

Builds Part 1 content into `doc`:

1. `_add_heading(doc, f"Part 1: {package['title']}", level=1)`
2. For each of s1_1, s1_2, s1_3:
   - `_add_heading(doc, section_label, level=2)`
   - `_add_paragraph(doc, texts[section_key])`
   - `_add_image_or_placeholder(doc, package["visuals"][i])`
3. `_add_insight_box(doc, texts["insight"], package["sections"]["insight"]["verbatims"])`

### 6i. Part builder: `build_part_2(doc, package, texts)`

1. Heading (level 1)
2. Section 2.1:
   - Heading, narrative text, then funnel table built from `package["sections"]["s2_1"]`
   - Funnel table rows: Experienced Event, Filed Claim, Claim Paid
   - Image for part2_funnel.png
3. Section 2.2: Heading, narrative, image for no_claim_reasons.png
4. Section 2.3: Heading, narrative, image for claim_challenges.png
   - If `package["sections"]["s2_3"]["qualitative"]["protection_flags"]` is non-empty:
     - Add a "Client Protection Signals" sub-heading (level 4)
     - Add one line per flag: `[SEVERITY] flag_type — reason (row_id)`
5. Section 2.4: Heading, narrative
6. Insight box

### 6j. Part builder: `build_part_3(doc, package, texts)`

1. Heading (level 1)
2. Section 3.1: Heading, narrative, image
3. Section 3.2: Heading, narrative
4. Insight box

### 6k. Part builder: `build_part_4(doc, package, texts)`

1. Heading (level 1)
2. Section 4.1: Heading, narrative, NPS image
3. Section 4.2: Heading, narrative, themes image
4. Section 4.3: Heading, narrative
5. Insight box

### 6l. Part builder: `build_part_5(doc, package, texts)`

1. Heading (level 1)
2. Section 5.1: Heading, narrative, then drivers table:
   - Build from `package["sections"]["s5_1"]["drivers_data"]`
   - Columns: Driver, ρ (Spearman), p-value, N
   - Sort rows by `abs(rho)` descending (SUPPRESSED rows go to bottom)
   - Driver image
3. Section 5.2: Heading, narrative, healthcare image
4. Insight box

For the drivers table, the orchestrator should pre-compute a `drivers_data` list
(list of dicts with label, rho, p_value, n_valid, suppressed) so the assembler
doesn't need to re-parse the spec.

### 6m. Part builder: `build_part_6(doc, package, texts)`

1. Heading (level 1)
2. Scorecard table:
   - Columns: `["Metric", "Claimant", "Non-Claimant", "Sig.*"]`
   - For each row in `package["scorecard"]`:
     - Sig. cell: `"*"` if `row["significant"]` else `""`
     - For inverted metrics (negative_coping, financial_stress_high), add `"↓"` indicator in label
   - Add footnote paragraph: `"* p < 0.05 (chi-squared or Fisher's exact test)"`
3. Image for part6_scorecard.png
4. Narrative text
5. Insight box

### 6n. Part builder: `build_part_7(doc, package, texts)`

Same as Part 6 but columns: `["Metric", "Female", "Male", "Sig.*"]`

### 6o. `assemble(packages: list, written_texts: dict, run_id: str, output_path: Path)`

Main entrypoint:
```python
def assemble(packages, written_texts, run_id, output_path):
    doc = Document()
    _set_default_font(doc, "Calibri", 11)  # or Arial 11

    # Cover information
    doc.add_heading("VisionFund International", level=0)
    doc.add_heading("Insurance Impact Report — Vietnam 2026 Q2", level=1)
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%d %B %Y')}")
    doc.add_page_break()

    builders = {
        "part_1": build_part_1,
        "part_2": build_part_2,
        "part_3": build_part_3,
        "part_4": build_part_4,
        "part_5": build_part_5,
        "part_6": build_part_6,
        "part_7": build_part_7,
    }

    for package in packages:
        part_key = package["part"]
        texts = written_texts.get(part_key, {})
        builder = builders[part_key]
        builder(doc, package, texts)
        doc.add_page_break()

    doc.save(str(output_path))
    print(f"  Report saved: {output_path}")
```

Add `_set_default_font(doc, name, size)` helper to set document default font:
```python
def _set_default_font(doc, name, size):
    from docx.shared import Pt
    style = doc.styles["Normal"]
    font = style.font
    font.name = name
    font.size = Pt(size)
```

---

## Step 7 — `generation/run_generation.py`

CLI entrypoint.

```
python generation/run_generation.py --run-id 2026_Q2
python generation/run_generation.py --run-id 2026_Q2 --dry-run
python generation/run_generation.py --run-id 2026_Q2 --parts 1,4,5
```

Arguments:
- `--run-id` (default: `2026_Q2`): the run directory
- `--dry-run`: build all packages, print a data summary for each part, save to
  `runs/{run_id}/dry_run_packages.json`, then exit without calling Gemini or assembler
- `--parts`: comma-separated part numbers to run (e.g. `1,4` → only `part_1` and `part_4`)
- `--skip-assembly`: run Gemini writer but skip docx assembly (useful for text QA)

Full flow:
```python
def main():
    args = parse_args()
    run_id = args.run_id
    parts_filter = [f"part_{p.strip()}" for p in args.parts.split(",")] if args.parts else None

    print(f"\n── Generation Pipeline | run_id={run_id} ───────────────────────")

    # Phase 1: Preflight
    result = preflight_check(run_id)
    if not result["ok"]:
        for e in result["errors"]:
            print(f"  [ERROR] {e}")
        sys.exit(1)
    for w in result["warnings"]:
        print(f"  [WARN] {w}")

    # Phase 2: Orchestrate (data extraction)
    print("\nPhase 2 — Extracting data packages...")
    packages = orchestrate(run_id, parts_filter)
    print(f"  Packages built: {[p['part'] for p in packages]}")

    if args.dry_run:
        out = ROOT / "runs" / run_id / "dry_run_packages.json"
        out.write_text(json.dumps(packages, indent=2, default=str), encoding="utf-8")
        print(f"\n[dry-run] Packages saved to {out}. Exiting without Gemini call.")
        # Print summary of what would be sent
        for pkg in packages:
            print(f"\n  {pkg['part']} — {pkg['title']}")
            for s_key, s_data in pkg.get("sections", {}).items():
                n_metrics = len(s_data.get("metrics", {}))
                n_verbatims = len(s_data.get("verbatims", []))
                wl = s_data.get("word_limit", "?")
                print(f"    {s_key}: {n_metrics} metrics, {n_verbatims} verbatims, word_limit={wl}")
        return

    # Phase 3: Write (Gemini calls)
    print("\nPhase 3 — Writing report sections (Gemini)...")
    spec = yaml.safe_load((ROOT / "generation" / "report_spec.yaml").read_text(encoding="utf-8"))
    written_texts = write_all_parts(packages, run_id, model=spec["model"])
    print(f"  All {len(packages)} parts written.")

    if args.skip_assembly:
        print("\n[skip-assembly] Exiting before docx build.")
        return

    # Phase 4: Assemble
    print("\nPhase 4 — Assembling .docx...")
    output_filename = spec.get("output_filename", f"report_{run_id}.docx")
    output_path = ROOT / "runs" / run_id / output_filename
    assemble(packages, written_texts, run_id, output_path)

    print(f"\n── Report complete ─────────────────────────────────────────────")
    print(f"  Output: {output_path}")
    print("────────────────────────────────────────────────────────────────\n")
```

---

## Step 8 — Verify

Run these checks in order. Each must pass before proceeding to the next.

### Check 1: Dry-run exits 0

```powershell
python generation/run_generation.py --run-id 2026_Q2 --dry-run
```

Expected: prints a data summary for all 7 parts, saves `dry_run_packages.json`, exits 0.
Verify `dry_run_packages.json` contains all 7 part keys and no `null` metric values
for non-suppressed metrics.

### Check 2: Single-part test with Gemini

```powershell
$env:GEMINI_API_KEY = "your_key_here"
python generation/run_generation.py --run-id 2026_Q2 --parts 1 --skip-assembly
```

Expected: one Gemini call, `written_texts.json` saved with `part_1` key,
all 4 text blocks present (s1_1, s1_2, s1_3, insight), none empty.

### Check 3: Word count compliance

After Check 2, verify word counts on Part 1:
```python
import json
from utils import word_count
texts = json.load(open("runs/2026_Q2/written_texts.json"))["part_1"]
for key, text in texts.items():
    print(f"  {key}: {word_count(text)} words")
```

Expected: s1_1 ≤ 90, s1_2 ≤ 90, s1_3 ≤ 80, insight ≤ 120.

### Check 4: Full run

```powershell
python generation/run_generation.py --run-id 2026_Q2
```

Expected: all 7 Gemini calls succeed, `.docx` written to
`runs/2026_Q2/VFI_Insurance_Impact_Report_2026_Q2.docx`.

### Check 5: Document integrity

Open the `.docx` in Word (or verify with python-docx):
```python
from docx import Document
doc = Document("runs/2026_Q2/VFI_Insurance_Impact_Report_2026_Q2.docx")
for p in doc.paragraphs[:20]:
    if p.text.strip():
        print(p.text[:80])
```

Expected: readable paragraphs, no `"None"` strings, no `"SUPPRESSED"` where
values exist in the data, tables present for Parts 2, 5, 6, 7.

---

## Acceptance Criteria

1. **Dry-run exits 0** and prints per-section metric counts for all 7 parts.
2. **No hardcoded API key** — `GEMINI_API_KEY` is always read from environment.
3. **All 28 text blocks present** in the final written_texts.json (no empty strings).
4. **Word limits respected**: every text block ≤ its limit (enforced by `truncate_to_limit`).
5. **All statistics cited match** the source data — no invented or rounded-differently figures.
6. **Funnel table** in Part 2 has 3 data rows with correct values from `claims_funnel`.
7. **Drivers table** in Part 5 has all 7 rows sorted by |rho|, SUPPRESSED rows shown.
8. **Scorecard tables** in Parts 6 and 7 show significance markers where p < 0.05.
9. **Verbatim blocks** in all 7 insight boxes include profile attribution (sex, age, branch, claimant status).
10. **Protection flags** (if any in qualitative_results.json) appear in Part 2 Section 2.3.
11. **Visual images inserted** where files exist in `runs/2026_Q2/visuals/`; placeholder text where absent.
12. **`--parts 4` flag** runs only Part 4 — no other parts written or assembled.
13. **`runs/2026_Q2/writer_raw_{part_key}.json`** saved for each part (enables re-run without API call).
14. **Docx opens without errors** in python-docx and (if available) in Word.

---

## Visual Naming Convention for Manual PowerBI Export

Save all chart exports to `runs/2026_Q2/visuals/` with these exact filenames:

| Filename | Chart description |
|----------|-------------------|
| `part1_coverage_bar.png` | Coverage understanding by segment (horizontal bar) |
| `part1_claims_process_bar.png` | Claims process understanding by segment |
| `part2_funnel.png` | Claims funnel (waterfall or bar) |
| `part2_no_claim_reasons.png` | Reasons for not claiming (bar chart) |
| `part2_claim_challenges.png` | Top claim challenges (horizontal bar, % of claimants) |
| `part3_financial_protection.png` | Financial protection indicators panel |
| `part4_nps.png` | NPS gauge or promoter/passive/detractor breakdown |
| `part4_themes.png` | NPS theme counts by group |
| `part5_drivers.png` | CWB Spearman correlation chart |
| `part5_healthcare.png` | Healthcare access and medical cost metrics |
| `part6_scorecard.png` | Claimant vs non-claimant comparison visual |
| `part7_scorecard.png` | Female vs male comparison visual |
| `kling_index.png` | Kling composite index (optional — for executive section) |

The assembler checks for each file and inserts a labelled placeholder if absent.
Charts can be added progressively; re-run the pipeline to incorporate new images.
