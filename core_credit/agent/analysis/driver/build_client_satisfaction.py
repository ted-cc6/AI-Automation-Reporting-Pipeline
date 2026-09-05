"""Driver script: builds a complete, real ClientSatisfactionSection (Part 8) end to end.

Plain orchestration -- no agent, no tool-calling loop. Fixed call sequence:

  1. Load the CSV once.
  2. Compute NPS overall + by gender/country (metrics_engine, deterministic) and the MFI Index
     benchmark. The NPS scale/box-type questions raised earlier are now resolved -- Lorenz
     confirmed by email (2026-08-05) that the sheet's 0.58-style value is NPS 58 on our own
     -100..100 scale, not "58% promoters" -- see benchmark_module/mapping.py.
  3. Theme-tag the three NPS follow-up questions IN PARALLEL, each across its FULL respondent
     band: CLIENTSAT01a (promoters, ~4,370 responses), CLIENTSAT01c (passives, ~1,076),
     CLIENTSAT01b (detractors, ~370). Each of these is its own already-scoped-by-skip-logic
     survey column, not one column filtered three ways.
  4. Turn the promoter/detractor theme synthesis into ranked driver/pain-point lists.
  5. Write 8.1 and 8.2, then the Insight (which draws its verbatim pool from all three bands).
  6. Assemble everything into one ClientSatisfactionSection and write it to output/ as JSON.

Expect this to take longer than any prior driver -- three full-dataset theme-tagging passes
running concurrently, dominated by the promoter band's ~4,370 responses (roughly the same
volume as Business & Household Impact's single qualitative pass, which took ~12 minutes).

Usage: python build_client_satisfaction.py
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

from benchmark_module.lookup import get_mfi_index_benchmark  # noqa: E402
from metrics_engine.engine import nps, nps_by_segment  # noqa: E402
from metrics_engine.segments import country as country_series, gender as gender_series  # noqa: E402
from qualitative_agent.agent import theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_free_text_responses  # noqa: E402
from schemas.client_satisfaction import ClientSatisfactionSection, NPSResult  # noqa: E402
from schemas.common import QualitativeSynthesis, RankedOption, RankedOptions, SegmentAxis  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.formatting import format_nps_result, format_ranked_options  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import CLIENT_SATISFACTION_INSIGHT, NPS_AND_SPLIT, NPS_DRIVERS  # noqa: E402

NPS_SCORE_COL = "Client Satisfaction/CLIENTSAT01_resp_en"
PROMOTER_FOLLOWUP_COL = "Client Satisfaction/CLIENTSAT01a_resp_en"  # asked only of scores 9-10
PASSIVE_FOLLOWUP_COL = "Client Satisfaction/CLIENTSAT01c_resp_en"  # asked only of scores 7-8
DETRACTOR_FOLLOWUP_COL = "Client Satisfaction/CLIENTSAT01b_resp_en"  # asked only of scores 0-6

PROMOTER_TASK = (
    "These responses answer 'What specifically about VisionFund would cause you to recommend "
    "it to a friend or family member?', asked only of clients who scored 9 or 10. Theme-tag "
    "what they name as the reason to recommend."
)
PASSIVE_TASK = (
    "These responses answer 'What specifically about VisionFund caused you to give it the "
    "score you did?', asked only of clients who scored 7 or 8. Theme-tag what they raise."
)
DETRACTOR_TASK = (
    "These responses answer 'What actions could VisionFund take to make you more likely to "
    "recommend to a friend or family member?', asked only of clients who scored 0-6. Theme-tag "
    "the pain points and unmet asks they name."
)

BENCHMARKS_PATH = str(PROJECT_ROOT / "External Benchmarks.xlsx")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _themes_to_ranked_options(qualitative: QualitativeSynthesis) -> RankedOptions:
    options = [
        RankedOption(label=t.theme, share=(t.share_of_respondents or 0.0), n=t.frequency) for t in qualitative.themes
    ]
    return RankedOptions(base_n=qualitative.base_n, options=options)


def _merge_for_verbatim_pool(label: str, *syntheses: QualitativeSynthesis) -> QualitativeSynthesis:
    """A throwaway QualitativeSynthesis that only exists to pool every band's themes into one
    verbatim citation pool for write_insight() -- never stored on the section itself.
    """
    themes = [t for s in syntheses for t in s.themes]
    base_n = sum(s.base_n for s in syntheses)
    return QualitativeSynthesis(source_field=label, base_n=base_n, themes=themes)


def build_section(df: pd.DataFrame) -> ClientSatisfactionSection:
    scores = pd.to_numeric(df[NPS_SCORE_COL], errors="coerce")
    overall = nps(scores)
    by_segment = nps_by_segment(scores, gender_series(df), SegmentAxis.GENDER) + nps_by_segment(
        scores, country_series(df), SegmentAxis.COUNTRY
    )
    benchmark = get_mfi_index_benchmark("nps", BENCHMARKS_PATH)
    nps_result = NPSResult(
        score=overall.score,
        promoter_share=overall.promoter_share,
        passive_share=overall.passive_share,
        detractor_share=overall.detractor_share,
        n=overall.n,
        by_segment=by_segment,
        benchmark=benchmark,
    )
    print(f"Step 1/3 done: NPS={nps_result.score:.0f} (n={nps_result.n}), no LLM.")

    promoter_responses = load_free_text_responses(df, PROMOTER_FOLLOWUP_COL)
    passive_responses = load_free_text_responses(df, PASSIVE_FOLLOWUP_COL)
    detractor_responses = load_free_text_responses(df, DETRACTOR_FOLLOWUP_COL)

    print(
        f"Step 2/3: theme-tagging {len(promoter_responses)} promoter / {len(passive_responses)} passive / "
        f"{len(detractor_responses)} detractor responses concurrently..."
    )
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_promoters = pool.submit(theme_tag_full_dataset, "promoter_drivers", promoter_responses, PROMOTER_TASK)
        future_passives = pool.submit(theme_tag_full_dataset, "passive_followup", passive_responses, PASSIVE_TASK)
        future_detractors = pool.submit(
            theme_tag_full_dataset, "detractor_pain_points", detractor_responses, DETRACTOR_TASK
        )
        promoters_qual = future_promoters.result()
        passives_qual = future_passives.result()
        detractors_qual = future_detractors.result()
    print("Step 2/3 done.")

    nps_followup_themes = [promoters_qual, passives_qual, detractors_qual]
    promoter_drivers = _themes_to_ranked_options(promoters_qual)
    detractor_pain_points = _themes_to_ranked_options(detractors_qual)

    nps_summary = format_nps_result(nps_result)
    drivers_summary = (
        f"{format_ranked_options('Promoter drivers (theme-tagged)', promoter_drivers)}\n"
        f"{format_ranked_options('Detractor pain points (theme-tagged)', detractor_pain_points)}"
    )
    acceptable_8_1 = collect_acceptable_percentages(nps_result)
    acceptable_8_2 = collect_acceptable_percentages(promoter_drivers, detractor_pain_points)

    print("Step 3/3: writing 8.1 and 8.2 concurrently, then the Insight...")
    with ThreadPoolExecutor(max_workers=2) as pool:
        future_nps_text = pool.submit(write_subsection, NPS_AND_SPLIT, nps_summary, acceptable_percentages=acceptable_8_1)
        future_drivers_text = pool.submit(
            write_subsection,
            NPS_DRIVERS,
            drivers_summary,
            qualitative=_merge_for_verbatim_pool("nps_drivers_context", promoters_qual, detractors_qual),
            acceptable_percentages=acceptable_8_2,
        )
        nps_analysis = future_nps_text.result()
        drivers_analysis = future_drivers_text.result()

    combined_summary = f"{nps_summary}\n{drivers_summary}"
    all_bands_qual = _merge_for_verbatim_pool("client_satisfaction_insight", promoters_qual, passives_qual, detractors_qual)
    acceptable_insight = acceptable_8_1 | acceptable_8_2 | collect_acceptable_percentages(all_bands_qual)
    insight_text, insight_verbatims = write_insight(
        CLIENT_SATISFACTION_INSIGHT, combined_summary, qualitative=all_bands_qual, acceptable_percentages=acceptable_insight
    )
    print("Step 3/3 done.")

    return ClientSatisfactionSection(
        nps=nps_result,
        nps_analysis=nps_analysis,
        promoter_drivers=promoter_drivers,
        detractor_pain_points=detractor_pain_points,
        nps_followup_themes=nps_followup_themes,
        drivers_analysis=drivers_analysis,
        insight_text=insight_text,
        insight_verbatims=insight_verbatims,
    )


def _print_summary(section: ClientSatisfactionSection) -> None:
    print("\n" + "=" * 70)
    print("8.1 NPS and the split")
    print(section.nps_analysis.text)
    print(f"[{section.nps_analysis.word_count} words, within_cap={section.nps_analysis.within_cap}, "
          f"ungrounded={section.nps_analysis.ungrounded_percentages}]")

    print("\n8.2 Reasons clients gave for recommending or not recommending")
    print(section.drivers_analysis.text)
    print(f"[{section.drivers_analysis.word_count} words, within_cap={section.drivers_analysis.within_cap}, "
          f"ungrounded={section.drivers_analysis.ungrounded_percentages}]")
    print(f"\nTop promoter drivers: {[o.label for o in section.promoter_drivers.options[:5]]}")
    print(f"Top detractor pain points: {[o.label for o in section.detractor_pain_points.options[:5]]}")

    print("\nInsight for Client Satisfaction")
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
    out_path = OUTPUT_DIR / f"client_satisfaction_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
