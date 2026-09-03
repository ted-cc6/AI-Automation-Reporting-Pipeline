"""Driver script: builds a complete, real ChildWellbeingSection (Part 4) end to end.

Plain orchestration -- no agent, no tool-calling loop.

4.2's caregiver-vs-other table is the one piece that reaches outside this Part's own survey
questions: 5 of its 8 rows reuse box definitions already verified for Client Protection and
Agency (both drafted, validated=False -- see section_configs/sections/). Each mask below is
still re-derived directly from the analysis-ready CSV, not read from those sections' computed
output, so nothing here depends on those drivers having actually run. But the definitions
themselves are imported from their SectionConfig objects (not retyped) so this table can never
silently drift from what Client Protection/Agency will eventually publish -- if either config's
box values change, this file picks up the change automatically the next time it runs.

Sequence:
  1. Compute every deterministic metric (metrics_engine, no LLM).
  2. Theme-tag IMPACT04b's 57 "other improvements" free-text responses (small, single batch)
     concurrently with writing 4.1 and 4.2 (neither depends on the qualitative pass).
  3. Write the Insight, which cites verbatims from that same pool.

Usage: python build_child_wellbeing.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_credit

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from metrics_engine.engine import (  # noqa: E402
    LOW_N_THRESHOLD,
    directly_standardised_gap,
    gap_comparison,
    metric_result,
    multiselect_distribution,
    top_box_mask,
)
from metrics_engine.segments import (  # noqa: E402
    caregiver_mask,
    child_wellbeing_improved_mask,
    clean_blank_strings,
    standard_categorical_segments,
)
from metrics_engine.segments import country as country_series  # noqa: E402
from qualitative_agent.agent import theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_free_text_responses  # noqa: E402
from schemas.child_wellbeing import (  # noqa: E402
    CaregiverGapStandardisation,
    CaregiverStandardisationSupport,
    ChildWellbeingSection,
)
from section_configs.sections.agency import AGENCY_CONFIG  # noqa: E402
from section_configs.sections.business_household_impact import BUSINESS_HOUSEHOLD_IMPACT_CONFIG  # noqa: E402
from section_configs.sections.client_protection import CLIENT_PROTECTION_CONFIG  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.formatting import format_metric_result, format_ranked_options  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import CAREGIVER_VS_OTHER, CHILD_WELLBEING_INSIGHT, IMPROVED_CHILD_WELLBEING  # noqa: E402

WHAT_IMPROVED_COLS = [f"Impacts on Business, Household, and Children/IMPACT04a_resp_{i}_en" for i in range(1, 9)]
OTHER_IMPROVEMENTS_COL = "Impacts on Business, Household, and Children/IMPACT04b_resp_en"

# 7 and 8 aren't defined in any existing SectionConfig (Resilience is a bespoke driver, not a
# section_config; NPS promoter status is a threshold on a raw score, not a top-box column).
SAVINGS_COL = "Resilience/RESILIENCE02_resp_en"
SAVINGS_TOP_2 = frozenset({"a. Very much increased", "b. Slightly increased"})  # must match driver/build_resilience.py
NPS_SCORE_COL = "Client Satisfaction/CLIENTSAT01_resp_en"
NPS_PROMOTER_THRESHOLD = 9

OTHER_IMPROVEMENTS_TASK = (
    "These responses answer 'Specify other improvements', a free-text follow-up asked to "
    "caregivers who said their children's wellbeing improved because of the loan, after they "
    "selected 'Other' among a list of specific improvements. Theme-tag what they describe."
)

CAREGIVER_TABLE_LABELS = [
    "Improved quality of life",
    "Financial worry decreased",
    "Improved community respect",
    "Improved business income",
    "Loan goal fully achieved",
    "Improved household influence",
    "Increased savings",
    "Net Promoter Score (promoter)",
]

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _metric_config(config, metric_id: str):
    return next(m for m in config.metrics if m.metric_id == metric_id)


def _top_box_mask_for(df: pd.DataFrame, config, metric_id: str) -> pd.Series:
    mc = _metric_config(config, metric_id)
    return top_box_mask(clean_blank_strings(df[mc.source_column]), set(mc.top_box_values))


def _non_caregiver_mask(caregiver: pd.Series) -> pd.Series:
    return pd.Series([None if v is None else (not v) for v in caregiver.tolist()], index=caregiver.index, dtype=object)


def _nps_promoter_mask(df: pd.DataFrame) -> pd.Series:
    scores = pd.to_numeric(df[NPS_SCORE_COL], errors="coerce")
    return (scores >= NPS_PROMOTER_THRESHOLD).where(scores.notna())


def _outcome_masks(df: pd.DataFrame) -> list:
    """The eight 4.2 outcome masks, in CAREGIVER_TABLE_LABELS order -- shared by the raw
    comparison and the country standardisation so the two can never fall out of step."""
    return [
        _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "quality_of_life_change"),
        _top_box_mask_for(df, CLIENT_PROTECTION_CONFIG, "financial_worry_decreased"),
        _top_box_mask_for(df, AGENCY_CONFIG, "community_respect_improved"),
        _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "business_income_change"),
        _top_box_mask_for(df, AGENCY_CONFIG, "loan_purpose_achieved_fully"),
        _top_box_mask_for(df, AGENCY_CONFIG, "household_influence_improved"),
        top_box_mask(clean_blank_strings(df[SAVINGS_COL]), SAVINGS_TOP_2),
        _nps_promoter_mask(df),
    ]


def _caregiver_vs_other(df: pd.DataFrame) -> list:
    caregiver = caregiver_mask(df)
    non_caregiver = _non_caregiver_mask(caregiver)
    return [
        gap_comparison(mask, caregiver, "Caregiver", non_caregiver, "Non-caregiver")
        for mask in _outcome_masks(df)
    ]


def _country_weights(df: pd.DataFrame) -> dict:
    """country -> row count over the analysis-ready sample (blank country dropped). The
    standardisation weight basis: the population's own country mix."""
    ctry = country_series(df)
    valid = ctry.notna() & (ctry.astype(str).str.strip() != "")
    return {str(c): int((ctry == c).sum()) for c in ctry[valid].unique()}


def _caregiver_standardisation(df: pd.DataFrame, caregiver_vs_other: list):
    """CC-026: for each 4.2 outcome, the raw caregiver-vs-non-caregiver gap standardised to the
    full-sample country distribution, computed only over countries with a non-caregiver base of
    at least LOW_N_THRESHOLD. Returns (rows, support)."""
    ctry = country_series(df)
    weights = _country_weights(df)
    caregiver = caregiver_mask(df)
    non_caregiver = _non_caregiver_mask(caregiver)
    care_bool = caregiver.fillna(False).astype(bool)
    non_bool = non_caregiver.fillna(False).astype(bool)

    # Anchor raw_gap on the paired GapComparison.gap (the value the 4.2 table prints, already
    # rounded to display precision) so composition_share is exactly (raw - standardised) / raw
    # of the two numbers shown side by side, not of a fuller-precision raw the reader can't see.
    raw_by_outcome = dict(zip(CAREGIVER_TABLE_LABELS, (gc.gap for gc in caregiver_vs_other)))

    rows: list[CaregiverGapStandardisation] = []
    for label, mask in zip(CAREGIVER_TABLE_LABELS, _outcome_masks(df)):
        r = directly_standardised_gap(mask, caregiver, non_caregiver, ctry, weights, LOW_N_THRESHOLD)
        raw_gap = raw_by_outcome.get(label, r["raw_gap"])
        std_gap = r["standardised_gap"]
        composition_share = None
        if raw_gap is not None and std_gap is not None and abs(raw_gap) > 0.005:
            composition_share = (raw_gap - std_gap) / raw_gap
        rows.append(
            CaregiverGapStandardisation(
                outcome=label,
                raw_gap=raw_gap,
                standardised_gap=std_gap,
                composition_share=composition_share,
                top_composition_countries=list(r["contributions"])[:4],
            )
        )

    # Wave-level support: non-caregiver respondents per country, independent of any one outcome
    # (per-outcome item non-response can shift a marginal country across the line -- each row's
    # own included/excluded set in directly_standardised_gap reflects that; this is the summary).
    nc_by_country = {c: int((non_bool & (ctry == c)).sum()) for c in weights}
    included = {c: n for c, n in sorted(nc_by_country.items()) if n >= LOW_N_THRESHOLD}
    excluded = {c: n for c, n in sorted(nc_by_country.items()) if n < LOW_N_THRESHOLD}
    total_nc = sum(nc_by_country.values())
    top2 = sorted(included.items(), key=lambda kv: kv[1], reverse=True)[:2]
    concentration_note = ""
    if len(top2) == 2 and total_nc:
        share = (top2[0][1] + top2[1][1]) / total_nc
        concentration_note = (
            f"{top2[0][0]} and {top2[1][0]} hold {share:.0%} of the {total_nc} non-caregiver "
            f"respondents between them"
        )
    support = CaregiverStandardisationSupport(
        n_threshold=LOW_N_THRESHOLD,
        caregiver_n=int(care_bool.sum()),
        non_caregiver_n=int(non_bool.sum()),
        included=included,
        excluded=excluded,
        concentration_note=concentration_note,
    )
    return rows, support


def _format_comparison_summary(caregiver_vs_other, standardisation, support) -> str:
    """The 4.2 data block handed to the writer: a short factual header on the standardisation
    support, then one compact line per outcome carrying raw gap, significance and standardised
    gap. Framing/emphasis is the prompt's job -- this stays terse so the prose stays terse."""
    std_by_outcome = {r.outcome: r for r in standardisation}
    reversed_outcomes = [
        r.outcome
        for r in standardisation
        if r.raw_gap is not None and r.standardised_gap is not None and (r.raw_gap < 0) != (r.standardised_gap < 0)
    ]
    header = (
        f"Standardisation basis (CC-026): {support.non_caregiver_n} non-caregivers vs "
        f"{support.caregiver_n} caregivers; {support.concentration_note}. Country-standardised "
        f"gap = {support.method}, over the {len(support.included)} countries with a "
        f"non-caregiver base of {support.n_threshold}+ ({', '.join(support.included)}); excluded "
        f"(thin/absent non-caregiver base): {', '.join(f'{c} n={n}' for c, n in support.excluded.items())}. "
        f"Sign reverses under standardisation on: {', '.join(reversed_outcomes) or 'none'}.\n\n"
    )

    lines = []
    for label, row in zip(CAREGIVER_TABLE_LABELS, caregiver_vs_other):
        std = std_by_outcome.get(label)
        line = (
            f"{label}: caregiver {row.group_a_share:.1%} vs non-caregiver {row.group_b_share:.1%}, "
            f"raw gap {row.gap:+.1%}"
        )
        if row.significance and row.significance.significant:
            line += f" (sig, p={row.significance.p_value:.3f})"
        if std and std.standardised_gap is not None:
            line += f"; standardised {std.standardised_gap:+.1%}"
            if std.composition_share is not None:
                line += f" ({std.composition_share:.0%} composition)"
        else:
            line += "; standardised n/a this wave"
        lines.append(line)
    return header + "\n".join(lines)


def _standardisation_acceptable_percentages(standardisation, support) -> set:
    """Whitelist the standardised gaps, composition shares and the caregiver-share figure for
    the grounding check -- these numbers are real but live outside the MetricResult/GapComparison
    objects collect_acceptable_percentages() knows how to walk."""
    acceptable: set = set()

    def _add(value: float) -> None:
        acceptable.add(round(value))
        acceptable.add(round(value, 1))

    for r in standardisation:
        for value in (r.raw_gap, r.standardised_gap, r.composition_share):
            if value is not None:
                _add(abs(value) * 100)
    total = support.caregiver_n + support.non_caregiver_n
    if total:
        _add(support.caregiver_n / total * 100)
        _add(support.non_caregiver_n / total * 100)
    if support.non_caregiver_n:
        for n in support.included.values():
            _add(n / support.non_caregiver_n * 100)
        top2 = sorted(support.included.values(), reverse=True)[:2]
        if len(top2) == 2:
            _add(sum(top2) / support.non_caregiver_n * 100)
    return acceptable


def build_section(df: pd.DataFrame) -> ChildWellbeingSection:
    segments = standard_categorical_segments(df)
    caregivers = caregiver_mask(df)

    improved_child_wellbeing = metric_result(
        "improved_child_wellbeing",
        "Caregivers reporting improved child wellbeing",
        child_wellbeing_improved_mask(df),
        base=caregivers,
        segments=segments,
    )

    improved_base = child_wellbeing_improved_mask(df)
    what_improved_slots = [clean_blank_strings(df[c]) for c in WHAT_IMPROVED_COLS]
    what_improved = multiselect_distribution(what_improved_slots, base=improved_base)

    caregiver_vs_other = _caregiver_vs_other(df)
    caregiver_standardisation, caregiver_standardisation_support = _caregiver_standardisation(
        df, caregiver_vs_other
    )
    print("Step 1/2 done: metrics computed (no LLM).")

    other_improvements_responses = load_free_text_responses(df, OTHER_IMPROVEMENTS_COL)
    wellbeing_summary = f"{format_metric_result(improved_child_wellbeing)}\n{format_ranked_options('What improved', what_improved)}"
    comparison_summary = _format_comparison_summary(
        caregiver_vs_other, caregiver_standardisation, caregiver_standardisation_support
    )
    acceptable = collect_acceptable_percentages(improved_child_wellbeing, what_improved, *caregiver_vs_other)
    acceptable |= _standardisation_acceptable_percentages(
        caregiver_standardisation, caregiver_standardisation_support
    )

    print(f"Step 2/2: theme-tagging {len(other_improvements_responses)} other-improvement responses, writing 4.1/4.2 concurrently...")
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_qual = pool.submit(theme_tag_full_dataset, "other_child_improvements", other_improvements_responses, OTHER_IMPROVEMENTS_TASK)
        future_wellbeing_text = pool.submit(write_subsection, IMPROVED_CHILD_WELLBEING, wellbeing_summary, acceptable_percentages=acceptable)
        future_comparison_text = pool.submit(write_subsection, CAREGIVER_VS_OTHER, comparison_summary, acceptable_percentages=acceptable)

        other_improvements_qual = future_qual.result()
        improved_child_wellbeing_analysis = future_wellbeing_text.result()
        caregiver_vs_other_analysis = future_comparison_text.result()

    combined_summary = f"{wellbeing_summary}\n{comparison_summary}"
    acceptable_insight = acceptable | collect_acceptable_percentages(other_improvements_qual)
    insight_text, insight_verbatims = write_insight(
        CHILD_WELLBEING_INSIGHT, combined_summary, qualitative=other_improvements_qual, acceptable_percentages=acceptable_insight
    )
    print("Step 2/2 done.")

    return ChildWellbeingSection(
        improved_child_wellbeing=improved_child_wellbeing,
        what_improved=what_improved,
        other_improvements_qualitative=other_improvements_qual,
        improved_child_wellbeing_analysis=improved_child_wellbeing_analysis,
        caregiver_vs_other=caregiver_vs_other,
        caregiver_standardisation=caregiver_standardisation,
        caregiver_standardisation_support=caregiver_standardisation_support,
        caregiver_vs_other_analysis=caregiver_vs_other_analysis,
        insight_text=insight_text,
        insight_verbatims=insight_verbatims,
    )


def _print_summary(section: ChildWellbeingSection) -> None:
    print("\n" + "=" * 70)
    print("4.1 Improved child wellbeing and what improved")
    print(section.improved_child_wellbeing_analysis.text)
    print(f"[{section.improved_child_wellbeing_analysis.word_count} words, "
          f"within_cap={section.improved_child_wellbeing_analysis.within_cap}, "
          f"ungrounded={section.improved_child_wellbeing_analysis.ungrounded_percentages}]")
    print(f"Top items: {[o.label for o in section.what_improved.options[:5]]}")

    print("\n4.2 Caregivers against other clients")
    s = section.caregiver_standardisation_support
    if s:
        print(f"  standardisation support: {len(s.included)} countries included "
              f"({', '.join(f'{c}={n}' for c, n in s.included.items())})")
        print(f"                           {len(s.excluded)} excluded "
              f"({', '.join(f'{c}={n}' for c, n in s.excluded.items())})")
        print(f"  caregivers={s.caregiver_n}  non-caregivers={s.non_caregiver_n}  -- {s.concentration_note}")
    print(f"  {'outcome':>32} | {'raw gap':>9} {'std gap':>9} {'comp share':>11} | drivers")
    for r in section.caregiver_standardisation:
        rg = f"{r.raw_gap:+.1%}" if r.raw_gap is not None else "n/a"
        sg = f"{r.standardised_gap:+.1%}" if r.standardised_gap is not None else "n/a"
        cs = f"{r.composition_share:.0%}" if r.composition_share is not None else "n/a"
        print(f"  {r.outcome:>32} | {rg:>9} {sg:>9} {cs:>11} | {', '.join(r.top_composition_countries)}")
    print(section.caregiver_vs_other_analysis.text)
    print(f"[{section.caregiver_vs_other_analysis.word_count} words, "
          f"within_cap={section.caregiver_vs_other_analysis.within_cap}, "
          f"ungrounded={section.caregiver_vs_other_analysis.ungrounded_percentages}]")

    print("\nInsight for Child Wellbeing")
    print(section.insight_text.text)
    print(f"[{section.insight_text.word_count} words, within_cap={section.insight_text.within_cap}, "
          f"ungrounded={section.insight_text.ungrounded_percentages}]")
    print(f"\ninsight_verbatims ({len(section.insight_verbatims)}):")
    for v in section.insight_verbatims:
        print(f'  "{v.quote}" -- {v.gender}, {v.country}, {", ".join(v.segment_tags) if v.segment_tags else "no segment tags"}')


def main() -> None:
    csv_path = find_latest_analysis_ready_csv()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path.name}\n")

    section = build_section(df)

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"child_wellbeing_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
