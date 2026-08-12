"""Validates the writer chain against real Part 3 (Business & Household Impact) data:
computes real metrics via metrics_engine (with the MFI Index benchmark actually wired in this
time), theme-tags the FULL quality-of-life-driver dataset via the qualitative agent, writes
the actual template subsections, and checks word caps + grounding. Makes real LLM calls
across the full dataset, so this takes a few minutes.

Usage: python run_validation.py
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_peoject

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from benchmark_module.lookup import get_mfi_index_benchmark  # noqa: E402
from metrics_engine.engine import metric_result, top_box_mask  # noqa: E402
from metrics_engine.segments import clean_blank_strings, standard_categorical_segments  # noqa: E402
from qualitative_agent.agent import QUALITY_OF_LIFE_DRIVERS_TASK, theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_quality_of_life_drivers  # noqa: E402
from schemas.common import MetricResult  # noqa: E402
from writer.chain import write_subsection  # noqa: E402
from schemas.common import WrittenText  # noqa: E402
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


def _report(out: WrittenText) -> None:
    print(out.text)
    status = "OK" if out.within_cap else "OVER CAP"
    print(f"[{out.word_count} words -- {status}]", end="")
    if out.ungrounded_percentages:
        print(f"  UNGROUNDED: {out.ungrounded_percentages}")
    else:
        print("  grounding OK")
    print()


def main() -> None:
    csv_path = find_latest_analysis_ready_csv()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path.name}\n")

    segments = standard_categorical_segments(df)
    income_result = _compute_metric(df, INCOME_COL, "business_income_change", "Business income improved", segments)
    qol_result = _compute_metric(df, QOL_COL, "quality_of_life_change", "Quality of life improved", segments)

    print("=== Computed metrics (metrics_engine + benchmark_module, no LLM) ===")
    print(format_metric_result(income_result))
    print(format_metric_result(qol_result))
    print()

    print("=== Theme-tagging the FULL quality-of-life-driver dataset (qualitative_agent, real LLM calls) ===")
    responses = load_quality_of_life_drivers(df)  # full dataset, no sampling
    countries_covered = {r.country for r in responses if r.country}
    print(f"{len(responses)} non-blank responses across {len(countries_covered)} countries")
    started = time.monotonic()
    qualitative = theme_tag_full_dataset("quality_of_life_drivers", responses, QUALITY_OF_LIFE_DRIVERS_TASK)
    print(f"Theme-tagging finished in {time.monotonic() - started:.0f}s")
    for t in qualitative.themes:
        print(f"- {t.theme} (n={t.frequency})")
    print()

    acceptable = collect_acceptable_percentages(income_result, qol_result, qualitative)

    print("=== 3.1 Business income change ===")
    out_31 = write_subsection(BUSINESS_INCOME_CHANGE, format_metric_result(income_result), acceptable_percentages=acceptable)
    _report(out_31)

    print("=== 3.2 Change in quality of life ===")
    out_32 = write_subsection(QUALITY_OF_LIFE_CHANGE, format_metric_result(qol_result), acceptable_percentages=acceptable)
    _report(out_32)

    print("=== Insight for Business and Household Impact ===")
    combined_summary = f"{format_metric_result(income_result)}\n{format_metric_result(qol_result)}"
    out_insight = write_subsection(
        BUSINESS_HOUSEHOLD_IMPACT_INSIGHT,
        combined_summary,
        qualitative=qualitative,
        acceptable_percentages=acceptable,
    )
    _report(out_insight)


if __name__ == "__main__":
    main()
