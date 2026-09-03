"""Driver script: builds a complete, real PovertyLikelihoodSection (Part 2) end to end.

Plain orchestration -- no agent, no tool-calling loop. Fixed call sequence:

  1. Load the CSV once.
  2. Score every country's PPI (ppi_module.pipeline, deterministic) and aggregate the
     three headline poverty lines into report-ready MetricResults (ppi_module.aggregate).
  3. Build the 2.2 national-comparison table (benchmark_module.lookup, deterministic).
  4. In parallel: write the 2.1 and 2.2 prose (writer, both fast, mutually independent).
  5. Write the Insight, which depends on both of the above for its combined summary.
  6. Assemble everything into one PovertyLikelihoodSection and write it to output/ as JSON,
     alongside a human-readable summary on stdout.

Unlike Part 3, there is no qualitative pass here -- Poverty Likelihood has no free-text
source and the template's own Insight instructions for this Part never ask for verbatims,
so this section's insight_verbatims is always []. Expect this run to take well under a
minute: three LLM calls total, no theme-tagging.

Usage: python build_poverty_likelihood.py
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

from benchmark_module.lookup import build_national_comparison  # noqa: E402
from benchmark_module.mapping import COUNTRY_CODE_TO_NAME  # noqa: E402
from ppi_module.aggregate import aggregate_poverty_line_shares, country_to_region_map  # noqa: E402
from ppi_module.country_policy import na_footnote  # noqa: E402
from ppi_module.pipeline import COUNTRY_COL, score_dataframe  # noqa: E402
from schemas.common import QualitativeSynthesis  # noqa: E402
from schemas.poverty_likelihood import PovertyLikelihoodSection  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.formatting import format_metric_result, format_national_comparison  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import (  # noqa: E402
    MFI_VS_NATIONAL_POVERTY_RATE,
    POVERTY_LIKELIHOOD_ACROSS_LINES,
    POVERTY_LIKELIHOOD_INSIGHT,
)

REGION_COL = "Introduction/Which region do you work in?"
SCORECARD_PATH = str(PROJECT_ROOT / "PPI_scorecards.xlsx")
LOOKUP_PATH = str(PROJECT_ROOT / "PPI_lookups.xlsx")
BENCHMARKS_PATH = str(PROJECT_ROOT / "External Benchmarks.xlsx")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"

EMPTY_QUALITATIVE = QualitativeSynthesis(source_field="poverty_likelihood", base_n=0, themes=[])


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def build_section(df: pd.DataFrame) -> PovertyLikelihoodSection:
    country_results = score_dataframe(df, SCORECARD_PATH, LOOKUP_PATH)
    country_to_region = country_to_region_map(df, COUNTRY_COL, REGION_COL)
    poverty_line_shares = aggregate_poverty_line_shares(country_results, country_to_region, COUNTRY_CODE_TO_NAME)
    national_comparison = build_national_comparison(country_results, BENCHMARKS_PATH)
    footnote = na_footnote(country_results)
    print(f"Step 1/3 done: {len(country_results)} countries scored (no LLM).")

    lines_summary = "\n".join(format_metric_result(m) for m in poverty_line_shares)
    national_summary = format_national_comparison(national_comparison)
    acceptable_2_1 = collect_acceptable_percentages(*poverty_line_shares)
    acceptable_2_2 = collect_acceptable_percentages(*national_comparison)

    print("Step 2/3: writing 2.1 and 2.2 concurrently...")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_lines_text = pool.submit(
            write_subsection, POVERTY_LIKELIHOOD_ACROSS_LINES, lines_summary, acceptable_percentages=acceptable_2_1
        )
        future_national_text = pool.submit(
            write_subsection, MFI_VS_NATIONAL_POVERTY_RATE, national_summary, acceptable_percentages=acceptable_2_2
        )
        lines_analysis = future_lines_text.result()
        national_analysis = future_national_text.result()
    print("Step 2/3 done.")

    print("Step 3/3: writing the Insight...")
    combined_summary = f"{lines_summary}\n{national_summary}"
    acceptable_for_insight = acceptable_2_1 | acceptable_2_2
    insight_text, insight_verbatims = write_insight(
        POVERTY_LIKELIHOOD_INSIGHT, combined_summary, qualitative=EMPTY_QUALITATIVE, acceptable_percentages=acceptable_for_insight
    )
    print("Step 3/3 done.")

    return PovertyLikelihoodSection(
        country_results=country_results,
        poverty_line_shares=poverty_line_shares,
        poverty_line_shares_analysis=lines_analysis,
        national_comparison=national_comparison,
        national_comparison_analysis=national_analysis,
        na_footnote=footnote,
        insight_text=insight_text,
        insight_verbatims=insight_verbatims,
    )


def _print_summary(section: PovertyLikelihoodSection) -> None:
    print("\n" + "=" * 70)
    print("2.1 Poverty likelihood across poverty lines")
    print(section.poverty_line_shares_analysis.text)
    print(f"[{section.poverty_line_shares_analysis.word_count} words, "
          f"within_cap={section.poverty_line_shares_analysis.within_cap}, "
          f"ungrounded={section.poverty_line_shares_analysis.ungrounded_percentages}]")

    print("\n2.2 The MFI against the national poverty rate")
    print(section.national_comparison_analysis.text)
    print(f"[{section.national_comparison_analysis.word_count} words, "
          f"within_cap={section.national_comparison_analysis.within_cap}, "
          f"ungrounded={section.national_comparison_analysis.ungrounded_percentages}]")

    if section.na_footnote:
        print(f"\nNA footnote: {section.na_footnote}")

    print("\nInsight for Poverty Likelihood")
    print(section.insight_text.text)
    print(f"[{section.insight_text.word_count} words, within_cap={section.insight_text.within_cap}, "
          f"ungrounded={section.insight_text.ungrounded_percentages}]")
    print(f"insight_verbatims: {section.insight_verbatims} (always empty -- no free-text source this Part)")


def main() -> None:
    csv_path = find_latest_analysis_ready_csv()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path.name}\n")

    section = build_section(df)

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"poverty_likelihood_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
