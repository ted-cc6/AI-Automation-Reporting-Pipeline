"""Driver script: builds a complete, real ResilienceSection (Part 7) end to end.

Plain orchestration -- no agent, no tool-calling loop.

Base populations were verified against the real data, not assumed from the survey text alone:
RESILIENCE03a/03b/03d are all asked to the SAME 1,178 clients -- shock-affected clients (2,103
of 5,818) MINUS the 925 who said the event "did not affect my household" in RESILIENCE03a.
That 1,178-client "impacted" base is what shock_impacts, coping_mechanisms,
negative_coping_share, and vf_reduced_shock_severity are all scoped to; shock_incidence itself
is scoped to everyone (it's the metric that measures who was shock-affected in the first place).

Sequence:
  1. Compute every deterministic metric (metrics_engine, no LLM).
  2. In parallel: theme-tag the 155 "other coping" free-text responses (full dataset, small),
     and write 7.1/7.2/7.4 (no dependency on the qualitative pass).
  3. Write 7.3 once the qualitative pass is in (it folds in that free text per the template).
  4. Write the Insight, which cites verbatims from the same 155-response pool.

Usage: python build_resilience.py
"""

from __future__ import annotations

import json
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_peoject

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from benchmark_module.lookup import get_mfi_index_benchmark  # noqa: E402
from metrics_engine.engine import metric_result, multiselect_distribution, top_box_mask  # noqa: E402
from metrics_engine.segments import clean_blank_strings, climate_shock_mask, standard_categorical_segments  # noqa: E402
from qualitative_agent.agent import theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_free_text_responses  # noqa: E402
from schemas.resilience import ResilienceSection  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.formatting import format_metric_result, format_ranked_options  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import (  # noqa: E402
    COPING_MECHANISMS,
    RESILIENCE_INSIGHT,
    SAVINGS_INCREASED,
    SHOCK_INCIDENCE_AND_IMPACT,
    VF_REDUCED_SHOCK_SEVERITY,
)

SAVINGS_COL = "Resilience/RESILIENCE02_resp_en"
SHOCK_IMPACT_COLS = [f"Resilience/RESILIENCE03a_resp_{i}_en" for i in range(1, 10)]
COPING_COLS = [f"Resilience/RESILIENCE03b_resp_{i}_en" for i in range(1, 5)]
OTHER_COPING_COL = "Resilience/RESILIENCE03c_resp_en"
VF_SEVERITY_COL = "Resilience/RESILIENCE03d_resp_en"

NO_IMPACT_LABEL = "a. None, event did not affect my household"
NEGATIVE_COPING_LABELS = {
    "a. Migration: some of all household members left home to earn income",
    "e. Reduction of expenses: on food, other essential items, postponed debt payment",
    "f. Sale of asset: household items, vehicles, land, or other productive assets",
    "i. Took children out of school",
}
SAVINGS_TOP_2 = {"a. Very much increased", "b. Slightly increased"}
SAVINGS_VERY_MUCH = {"a. Very much increased"}
VF_SEVERITY_TOP_2 = {"a. Significantly reduced the impact", "b. Somewhat reduced the impact"}

OTHER_COPING_TASK = (
    "These responses answer 'Specify other coping methods', a free-text follow-up asked to "
    "clients who selected 'Other' among how their household coped with an economic or climate "
    "shock. Theme-tag what coping method they describe."
)

BENCHMARKS_PATH = str(PROJECT_ROOT / "External Benchmarks.xlsx")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _impacted_mask(df: pd.DataFrame) -> pd.Series:
    """Shock-affected clients who also reported a real impact (excludes the 925 who said the
    event "did not affect my household") -- the real base RESILIENCE03a/03b/03d are asked
    against, confirmed by their non-blank counts matching this exactly (1,178) rather than the
    full shock-affected count (2,103).
    """
    shock = climate_shock_mask(df).tolist()
    slot1 = clean_blank_strings(df[SHOCK_IMPACT_COLS[0]]).tolist()
    out = [None if s is None else (False if s is False else v != NO_IMPACT_LABEL) for s, v in zip(shock, slot1)]
    return pd.Series(out, index=df.index, dtype=object)


def _negative_coping_mask(df: pd.DataFrame) -> pd.Series:
    cols = [clean_blank_strings(df[c]).tolist() for c in COPING_COLS]
    out = []
    for parts in zip(*cols):
        answered = [p for p in parts if p is not None]
        out.append(None if not answered else any(p in NEGATIVE_COPING_LABELS for p in answered))
    return pd.Series(out, index=df.index, dtype=object)


def build_section(df: pd.DataFrame) -> ResilienceSection:
    segments = standard_categorical_segments(df)
    impacted = _impacted_mask(df)

    savings_series = clean_blank_strings(df[SAVINGS_COL])
    savings_increased = metric_result(
        "savings_increased",
        "Savings increased",
        top_box_mask(savings_series, SAVINGS_TOP_2),
        segments=segments,
        benchmark=get_mfi_index_benchmark("savings_increased", BENCHMARKS_PATH),
        benchmark_comparable_mask=top_box_mask(savings_series, SAVINGS_VERY_MUCH),
    )

    shock_incidence = metric_result(
        "shock_incidence",
        "Met an economic or climate shock in the last 24 months",
        climate_shock_mask(df),
        segments=segments,
        benchmark=get_mfi_index_benchmark("shock_incidence", BENCHMARKS_PATH),
    )

    shock_impact_slots = [clean_blank_strings(df[c]) for c in SHOCK_IMPACT_COLS]
    shock_impacts = multiselect_distribution(shock_impact_slots, base=impacted, exclude_labels=frozenset({NO_IMPACT_LABEL}))

    coping_slots = [clean_blank_strings(df[c]) for c in COPING_COLS]
    coping_mechanisms = multiselect_distribution(
        coping_slots, base=impacted, exclude_labels=frozenset({"j. Did not need to deal with the event"})
    )

    negative_coping_share = metric_result(
        "negative_coping_share",
        "Used negative coping (cut food/spending, sold assets, took children out of school, or migrated)",
        _negative_coping_mask(df),
        base=impacted,
        segments=segments,
    )

    vf_severity_series = clean_blank_strings(df[VF_SEVERITY_COL])
    vf_reduced_shock_severity = metric_result(
        "vf_reduced_shock_severity",
        "VisionFund services reduced the severity of the shock",
        top_box_mask(vf_severity_series, VF_SEVERITY_TOP_2),
        base=impacted,
        segments=segments,
        benchmark=get_mfi_index_benchmark("vf_reduced_shock_severity", BENCHMARKS_PATH),
    )
    print("Step 1/3 done: metrics computed (no LLM).")

    other_coping_responses = load_free_text_responses(df, OTHER_COPING_COL)
    savings_summary = format_metric_result(savings_increased)
    shock_summary = f"{format_metric_result(shock_incidence)}\n{format_ranked_options('Main shock impacts', shock_impacts)}"
    severity_summary = format_metric_result(vf_reduced_shock_severity)
    acceptable_common = collect_acceptable_percentages(
        savings_increased, shock_incidence, shock_impacts, coping_mechanisms, negative_coping_share, vf_reduced_shock_severity
    )

    print(f"Step 2/3: theme-tagging {len(other_coping_responses)} other-coping responses, writing 7.1/7.2/7.4 concurrently...")
    with ThreadPoolExecutor(max_workers=4) as pool:
        future_qual = pool.submit(theme_tag_full_dataset, "other_coping", other_coping_responses, OTHER_COPING_TASK)
        future_savings_text = pool.submit(write_subsection, SAVINGS_INCREASED, savings_summary, acceptable_percentages=acceptable_common)
        future_shock_text = pool.submit(write_subsection, SHOCK_INCIDENCE_AND_IMPACT, shock_summary, acceptable_percentages=acceptable_common)
        future_severity_text = pool.submit(write_subsection, VF_REDUCED_SHOCK_SEVERITY, severity_summary, acceptable_percentages=acceptable_common)

        other_coping_qual = future_qual.result()
        savings_analysis = future_savings_text.result()
        shock_incidence_analysis = future_shock_text.result()
        vf_reduced_shock_severity_analysis = future_severity_text.result()
    print("Step 2/3 done.")

    coping_summary = f"{format_ranked_options('Coping mechanisms', coping_mechanisms)}\n{format_metric_result(negative_coping_share)}"
    acceptable_coping = acceptable_common | collect_acceptable_percentages(other_coping_qual)

    print("Step 3/3: writing 7.3 and the Insight...")
    coping_mechanisms_analysis = write_subsection(
        COPING_MECHANISMS, coping_summary, qualitative=other_coping_qual, acceptable_percentages=acceptable_coping
    )

    combined_summary = f"{savings_summary}\n{shock_summary}\n{coping_summary}\n{severity_summary}"
    insight_text, insight_verbatims = write_insight(
        RESILIENCE_INSIGHT, combined_summary, qualitative=other_coping_qual, acceptable_percentages=acceptable_coping
    )
    print("Step 3/3 done.")

    return ResilienceSection(
        savings_increased=savings_increased,
        savings_increased_analysis=savings_analysis,
        shock_incidence=shock_incidence,
        shock_impacts=shock_impacts,
        shock_incidence_analysis=shock_incidence_analysis,
        coping_mechanisms=coping_mechanisms,
        negative_coping_share=negative_coping_share,
        other_coping_qualitative=other_coping_qual,
        coping_mechanisms_analysis=coping_mechanisms_analysis,
        vf_reduced_shock_severity=vf_reduced_shock_severity,
        vf_reduced_shock_severity_analysis=vf_reduced_shock_severity_analysis,
        insight_text=insight_text,
        insight_verbatims=insight_verbatims,
    )


def _print_summary(section: ResilienceSection) -> None:
    print("\n" + "=" * 70)
    for title, analysis in [
        ("7.1 Change in savings", section.savings_increased_analysis),
        ("7.2 Shocks and their impact", section.shock_incidence_analysis),
        ("7.3 Coping mechanisms", section.coping_mechanisms_analysis),
        ("7.4 Effect of VisionFund on shock severity", section.vf_reduced_shock_severity_analysis),
    ]:
        print(f"\n{title}")
        print(analysis.text)
        print(f"[{analysis.word_count} words, within_cap={analysis.within_cap}, ungrounded={analysis.ungrounded_percentages}]")

    print(f"\nTop shock impacts: {[o.label for o in section.shock_impacts.options[:3]]}")
    print(f"Top coping mechanisms: {[o.label for o in section.coping_mechanisms.options[:3]]}")
    print(f"Negative coping share: {section.negative_coping_share.overall.share:.1%} (n={section.negative_coping_share.overall.n})")

    print("\nInsight for Resilience")
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
    out_path = OUTPUT_DIR / f"resilience_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
