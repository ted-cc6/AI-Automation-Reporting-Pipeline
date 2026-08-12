"""Builds ExecutiveSummarySection -- the cross-cutting "headline read across all eight themes."

The schema commits to exactly one headline_value per theme (ThemeScore), so this file's one
real editorial decision is which single metric represents each of the 8 Parts:

  Financial Access            -> first-time access (Part 1's own "headline inclusion metric")
  Poverty Likelihood          -> below $1.90/day (2011 PPP), the most standard global line
  Business & Household Impact -> quality of life improved (the "so what" of the two 3.x metrics)
  Child Wellbeing             -> improved child wellbeing
  Client Protection           -> no unfair treatment (the most conduct-central of its 6 metrics)
  Agency                      -> fully achieved loan purpose
  Resilience                  -> savings increased (portfolio-wide base, unlike the
                                  shock-severity metric which only covers shock-affected clients)
  Client Satisfaction         -> NPS (score, -100..100 -- NOT a percentage; ThemeScore.is_percentage
                                  is False for this one and the prompt tells the writer never to
                                  compare it directly against the other seven shares)

Every benchmark shown is carried through unchanged from that metric's own already-computed
BenchmarkComparison -- nothing here re-fetches or recomputes a benchmark.

This is also the reason Executive Summary had to wait: it's the only cross-cutting section that
reads ALL EIGHT sections' finished output, so it couldn't be built before Client Protection and
Agency had real runs to read.

Usage: python build_executive_summary.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_peoject

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from schemas.executive_summary import ExecutiveSummarySection, ThemeScore  # noqa: E402
from synthesis.loader import load_section  # noqa: E402
from writer.chain import write_subsection  # noqa: E402
from writer.section_prompts import EXECUTIVE_SUMMARY_ANALYSIS  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"
_QUARTER_RE = re.compile(r"(\d{4})Q(\d)")


def _reporting_period(client_profile) -> str:
    """Confirmed the hard way that guessing the reporting period from the uploaded filename's
    YYYYQN pattern fails silently to "unknown period" the moment a file isn't named that way
    (e.g. a real run named "Test4_..."). client_profile.fieldwork_start_date/end_date are
    derived from every respondent's real 'start'/'end' timestamps instead, so they're always
    available regardless of what the uploaded file was called -- preferred whenever present,
    with the old filename guess kept only as a last-resort fallback.
    """
    start, end = client_profile.fieldwork_start_date, client_profile.fieldwork_end_date
    if start and end:
        start_label = datetime.strptime(start, "%Y-%m-%d").strftime("%b %Y")
        end_label = datetime.strptime(end, "%Y-%m-%d").strftime("%b %Y")
        return start_label if start_label == end_label else f"{start_label} - {end_label}"

    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    match = _QUARTER_RE.search(candidates[-1].name) if candidates else None
    return f"{match.group(1)} Q{match.group(2)}" if match else "unknown period"


def _load(section_id: str, sections: Optional[dict]):
    """`sections`, when given, is an already-built {section_id: Section} map (e.g. from the
    orchestrator's graph state) -- used instead of re-reading each section's canonical output
    file. Standalone/CLI usage (sections=None) is unchanged.
    """
    return sections[section_id] if sections is not None else load_section(section_id)


def _theme_scores(sections: Optional[dict] = None) -> list:
    financial_access = _load("financial_access", sections)
    poverty_likelihood = _load("poverty_likelihood", sections)
    business_household_impact = _load("business_household_impact", sections)
    child_wellbeing = _load("child_wellbeing", sections)
    client_protection = _load("client_protection", sections)
    agency = _load("agency", sections)
    resilience = _load("resilience", sections)
    client_satisfaction = _load("client_satisfaction", sections)

    poverty_190 = next(
        m for m in poverty_likelihood.poverty_line_shares if m.metric_id == "poverty_likelihood_USD190day2011PPP"
    )

    def _comparable(metric_result) -> Optional[float]:
        cv = metric_result.benchmark_comparable_value
        return cv.share if cv is not None else None

    return [
        ThemeScore(
            theme_name="Financial Access",
            metric_label="First-time access to credit",
            headline_value=financial_access.first_time_access.overall.share,
            benchmark=financial_access.first_time_access.benchmark,
        ),
        ThemeScore(
            theme_name="Poverty Likelihood",
            metric_label="Below $1.90/day (2011 PPP)",
            headline_value=poverty_190.overall.share,
            benchmark=poverty_190.benchmark,
        ),
        ThemeScore(
            theme_name="Business & Household Impact",
            metric_label="Quality of life improved",
            headline_value=business_household_impact.quality_of_life_change.overall.share,
            benchmark=business_household_impact.quality_of_life_change.benchmark,
            benchmark_comparable_value=_comparable(business_household_impact.quality_of_life_change),
        ),
        ThemeScore(
            theme_name="Child Wellbeing",
            metric_label="Improved child wellbeing",
            headline_value=child_wellbeing.improved_child_wellbeing.overall.share,
            benchmark=child_wellbeing.improved_child_wellbeing.benchmark,
        ),
        ThemeScore(
            theme_name="Client Protection",
            metric_label="Experienced no unfair treatment",
            headline_value=client_protection.no_unfair_treatment.overall.share,
            benchmark=client_protection.no_unfair_treatment.benchmark,
        ),
        ThemeScore(
            theme_name="Agency",
            metric_label="Fully achieved loan purpose",
            headline_value=agency.loan_purpose_achieved_fully.overall.share,
            benchmark=agency.loan_purpose_achieved_fully.benchmark,
        ),
        ThemeScore(
            theme_name="Resilience",
            metric_label="Savings increased",
            headline_value=resilience.savings_increased.overall.share,
            benchmark=resilience.savings_increased.benchmark,
            benchmark_comparable_value=_comparable(resilience.savings_increased),
        ),
        ThemeScore(
            theme_name="Client Satisfaction",
            metric_label="Net Promoter Score",
            headline_value=client_satisfaction.nps.score,
            is_percentage=False,
            benchmark=client_satisfaction.nps.benchmark,
        ),
    ]


def _format_theme_scores(scores: list) -> str:
    lines = ["Eight theme scores:"]
    for s in scores:
        value = f"{s.headline_value:.0f} (NPS scale, -100..100)" if not s.is_percentage else f"{s.headline_value:.1%}"
        line = f"  - {s.theme_name} -- {s.metric_label}: {value}"
        if s.benchmark and s.benchmark.external_mfi_index is not None:
            bench = s.benchmark.external_mfi_index if not s.is_percentage else s.benchmark.external_mfi_index * 100
            unit = "" if not s.is_percentage else "%"
            line += f" [MFI Index benchmark: {bench:.1f}{unit} ({s.benchmark.external_mfi_index_year})]"
            if s.benchmark_comparable_value is not None:
                line += (
                    f" -- compare against our OWN figure on the SAME basis as that benchmark "
                    f"(use this, not the headline value above): {s.benchmark_comparable_value:.1%}"
                )
        lines.append(line)
    return "\n".join(lines)


def _acceptable_percentages(scores: list) -> set:
    acceptable = set()
    for s in scores:
        if s.is_percentage:
            acceptable |= {round(s.headline_value * 100), round(s.headline_value * 100, 1)}
            if s.benchmark_comparable_value is not None:
                acceptable |= {round(s.benchmark_comparable_value * 100), round(s.benchmark_comparable_value * 100, 1)}
            if s.benchmark and s.benchmark.external_mfi_index is not None:
                acceptable |= {round(s.benchmark.external_mfi_index * 100), round(s.benchmark.external_mfi_index * 100, 1)}
        else:
            acceptable |= {round(s.headline_value), round(s.headline_value, 1)}
            if s.benchmark and s.benchmark.external_mfi_index is not None:
                acceptable |= {round(s.benchmark.external_mfi_index), round(s.benchmark.external_mfi_index, 1)}
    return acceptable


def build_section(sections: Optional[dict] = None) -> ExecutiveSummarySection:
    client_profile = _load("client_profile", sections)
    scores = _theme_scores(sections)
    print("Step 1/2 done: 8 theme scores assembled from real, already-published sections (no LLM).")

    summary = _format_theme_scores(scores)
    acceptable = _acceptable_percentages(scores)

    print("Step 2/2: writing the Executive Summary...")
    analysis_text = write_subsection(EXECUTIVE_SUMMARY_ANALYSIS, summary, acceptable_percentages=acceptable)
    print("Step 2/2 done.")

    return ExecutiveSummarySection(
        theme_scores=scores,
        n_respondents=client_profile.n_respondents,
        n_mfis=client_profile.n_mfis,
        n_countries=client_profile.n_countries,
        reporting_period=_reporting_period(client_profile),
        generated_date=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        analysis_text=analysis_text,
    )


def _print_summary(section: ExecutiveSummarySection) -> None:
    print("\n" + "=" * 70)
    print(f"Core Credit Impact Report -- Global Portfolio, {section.reporting_period}")
    print(f"Covering {section.n_respondents} client responses across {section.n_mfis} VisionFund "
          f"MFIs in {section.n_countries} countries. Generated: {section.generated_date}.\n")
    print(_format_theme_scores(section.theme_scores))
    print("\nExecutive Summary")
    print(section.analysis_text.text)
    print(f"[{section.analysis_text.word_count} words, within_cap={section.analysis_text.within_cap}, "
          f"ungrounded={section.analysis_text.ungrounded_percentages}]")


def main() -> None:
    section = build_section()

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"executive_summary_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
