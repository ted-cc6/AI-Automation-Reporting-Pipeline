"""Driver script: builds a complete, real BusinessHouseholdImpactSection (Part 3) end to end.

Plain orchestration -- no agent, no tool-calling loop. Fixed call sequence:

  1. Load the CSV once.
  2. Compute 3.1/3.2 metrics via metrics_engine + benchmark_module (deterministic).
  3. In parallel: theme-tag the FULL quality-of-life-driver dataset (qualitative_agent,
     ~700s), and write the 3.1/3.2 prose (writer, fast) -- these three are mutually
     independent, so they run concurrently via a plain ThreadPoolExecutor.
  4. Once qualitative tagging finishes, write the Insight (writer.write_insight), which
     depends on it for verbatim citations -- this step waits for step 3's qualitative work,
     nothing else.
  5. Assemble everything into one BusinessHouseholdImpactSection and write it to output/
     as JSON, alongside a human-readable summary on stdout.

Makes real LLM calls across the full dataset -- expect this to take roughly the same ~12
minutes as writer/run_validation.py did, since the qualitative pass dominates runtime.

Usage: python build_business_household_impact.py
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_credit

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from benchmark_module.lookup import get_mfi_index_benchmark  # noqa: E402
from metrics_engine.engine import metric_result, top_box_mask  # noqa: E402
from metrics_engine.segments import clean_blank_strings, standard_categorical_segments  # noqa: E402
from qualitative_agent.agent import QUALITY_OF_LIFE_DRIVERS_TASK, theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_quality_of_life_drivers  # noqa: E402
from schemas.business_household_impact import BusinessHouseholdImpactSection  # noqa: E402
from schemas.common import MetricResult  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.formatting import format_metric_result  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import (  # noqa: E402
    BUSINESS_HOUSEHOLD_IMPACT_INSIGHT,
    BUSINESS_INCOME_CHANGE,
    QUALITY_OF_LIFE_CHANGE,
)

TOP_2_BOX = {"a. Very much improved", "b. Slightly improved"}
VERY_MUCH_ONLY = {"a. Very much improved"}
INCOME_COL = "Impacts on Business, Household, and Children/IMPACT02_resp_en"
QOL_COL = "Impacts on Business, Household, and Children/IMPACT03_resp_en"
BENCHMARKS_PATH = str(PROJECT_ROOT / "External Benchmarks.xlsx")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _compute_metric(df: pd.DataFrame, col: str, metric_id: str, label: str, segments: dict) -> MetricResult:
    series = clean_blank_strings(df[col])
    mask = top_box_mask(series, TOP_2_BOX)
    very_much_mask = top_box_mask(series, VERY_MUCH_ONLY)  # matches the MFI Index's own box definition
    benchmark = get_mfi_index_benchmark(metric_id, BENCHMARKS_PATH)
    return metric_result(
        metric_id, label, mask, segments=segments, benchmark=benchmark, benchmark_comparable_mask=very_much_mask
    )


def build_section(df: pd.DataFrame) -> BusinessHouseholdImpactSection:
    segments = standard_categorical_segments(df)
    income_result = _compute_metric(df, INCOME_COL, "business_income_change", "Business income improved", segments)
    qol_result = _compute_metric(df, QOL_COL, "quality_of_life_change", "Quality of life improved", segments)
    print("Step 1/3 done: metrics computed (no LLM).")

    responses = load_quality_of_life_drivers(df)  # full dataset, no sampling
    acceptable = collect_acceptable_percentages(income_result, qol_result)

    print(f"Step 2/3: theme-tagging {len(responses)} responses and writing 3.1/3.2 concurrently...")
    started = time.monotonic()
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_income_text = pool.submit(
            write_subsection, BUSINESS_INCOME_CHANGE, format_metric_result(income_result), acceptable_percentages=acceptable
        )
        future_qol_text = pool.submit(
            write_subsection, QUALITY_OF_LIFE_CHANGE, format_metric_result(qol_result), acceptable_percentages=acceptable
        )
        future_qualitative = pool.submit(
            theme_tag_full_dataset, "quality_of_life_drivers", responses, QUALITY_OF_LIFE_DRIVERS_TASK
        )

        income_analysis = future_income_text.result()
        qol_analysis = future_qol_text.result()
        qualitative = future_qualitative.result()
    print(f"Step 2/3 done in {time.monotonic() - started:.0f}s.")

    print("Step 3/3: writing the Insight (depends on the qualitative pass above)...")
    combined_summary = f"{format_metric_result(income_result)}\n{format_metric_result(qol_result)}"
    acceptable_for_insight = collect_acceptable_percentages(income_result, qol_result, qualitative)
    insight_text, insight_verbatims = write_insight(
        BUSINESS_HOUSEHOLD_IMPACT_INSIGHT, combined_summary, qualitative=qualitative, acceptable_percentages=acceptable_for_insight
    )
    print("Step 3/3 done.")

    return BusinessHouseholdImpactSection(
        business_income_change=income_result,
        business_income_analysis=income_analysis,
        quality_of_life_change=qol_result,
        quality_of_life_analysis=qol_analysis,
        qol_drivers=qualitative,
        insight_text=insight_text,
        insight_verbatims=insight_verbatims,
    )


def _print_summary(section: BusinessHouseholdImpactSection) -> None:
    print("\n" + "=" * 70)
    print("3.1 Business income change")
    print(section.business_income_analysis.text)
    print(f"[{section.business_income_analysis.word_count} words, within_cap={section.business_income_analysis.within_cap}, "
          f"ungrounded={section.business_income_analysis.ungrounded_percentages}]")

    print("\n3.2 Change in quality of life")
    print(section.quality_of_life_analysis.text)
    print(f"[{section.quality_of_life_analysis.word_count} words, within_cap={section.quality_of_life_analysis.within_cap}, "
          f"ungrounded={section.quality_of_life_analysis.ungrounded_percentages}]")

    print(f"\n3.3 What drove the improvement -- {len(section.qol_drivers.themes)} themes, base_n={section.qol_drivers.base_n}")
    for t in section.qol_drivers.themes[:5]:
        print(f"  - {t.theme} (n={t.frequency})")
    if len(section.qol_drivers.themes) > 5:
        print(f"  ... and {len(section.qol_drivers.themes) - 5} more")

    print("\nInsight for Business and Household Impact")
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
    out_path = OUTPUT_DIR / f"business_household_impact_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
