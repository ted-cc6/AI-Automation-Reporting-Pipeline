"""Builds ExecutiveSummarySection -- the cross-cutting "headline read across all eight themes."

Theme scores follow the Core Credit Dashboard Design specification (section 3, spider-chart
table): each theme's headline is the UNWEIGHTED MEAN of its constituent indicator shares.

  Financial Access             -> mean of First Access, Access to Alternatives
  Poverty Likelihood           -> below $1.90/day (2011 PPP)                    [single indicator]
  Business & Household Impact  -> mean of Business Income, Quality of Life
  Child Wellbeing              -> improved child wellbeing                      [single indicator]
  Client Protection            -> mean of Financial Worry, Loan Understanding, Complaints
                                  Mechanism, Fair Treatment, Reporting Behavior, Reduced Food Intake
  Agency                       -> mean of Goal Achievement ("Yes, in full" OR "Yes, partially" --
                                  the combined loan_purpose_achieved metric, CC-010), Influence in
                                  Household, Respect in Community
  Resilience                   -> mean of Savings, Realized Preparedness
  Client Satisfaction          -> NPS (score, -100..100 -- NOT a percentage)   [single indicator]

Previous design (superseded, CC-011). The schema commits to one headline_value per theme, and
this file used to pick a SINGLE representative metric for each Part rather than average:

  Financial Access            -> first-time access (Part 1's headline inclusion metric)
  Business & Household Impact  -> quality of life improved (the "so what" of the two 3.x metrics)
  Client Protection            -> no unfair treatment (the most conduct-central of its 6 metrics)
  Agency                       -> fully achieved loan purpose ("Yes, in full" only)
  Resilience                   -> savings increased (portfolio-wide base, unlike shock severity)
  Poverty Likelihood / Child Wellbeing / Client Satisfaction -> single indicator, unchanged

That was an editorial call -- the "most representative" metric per theme -- forced by the schema
holding only one number. It has been superseded: the dashboard spec defines these themes as
indicator averages, three of the single-metric values disagreed with the published Power BI
dashboard (Agency 70.1 -> 85.1, Client Protection 95.4 -> 75.0, Resilience 77.5 -> 67.5), and
reviewers flagged the disagreement. The report now averages per the spec so the report and the
dashboard agree. (Resilience lands near 67.5% against the dashboard's 45%; that gap is expected
and open pending the reviewer's reply -- deliberately not reconciled here.)

Unavailable constituents (CC-011). If a constituent indicator is missing for a wave (e.g. a
section output produced before CC-010 carries no combined Goal Achievement metric), the theme
is the mean of the constituents that DO exist and metric_label records the count ("N of M
available this wave"). A theme with zero available constituents raises rather than emit a
meaningless number.

Benchmarks. An averaged theme carries NO MFI Index benchmark: the 60 Decibels figures are
per-indicator, each on its own box definition, so there is no single benchmark for a
multi-indicator mean, and CC-003 already bars loose benchmark comparison. The three
single-indicator themes keep whatever benchmark their one metric already carried (in practice
only Client Satisfaction's NPS has one).

Nothing here re-fetches or recomputes a metric or a benchmark -- every input is read from an
already-built section's finished output. This is also why Executive Summary runs last: it's the
only cross-cutting section that reads ALL EIGHT sections' finished output.

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
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_credit

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

    # Poverty Likelihood is a single-indicator theme, and Part 2 is omitted entirely when the
    # PPI reference workbooks are absent (build_poverty_likelihood emits a stub with no
    # poverty_line_shares). In that case the theme is simply left out of the scorecard rather
    # than shown as a zero -- Part 2's own text explains the omission.
    poverty_190 = next(
        (m for m in poverty_likelihood.poverty_line_shares if m.metric_id == "poverty_likelihood_USD190day2011PPP"),
        None,
    )
    poverty_score = (
        ThemeScore(
            theme_name="Poverty Likelihood",
            metric_label="Below $1.90/day (2011 PPP)",
            headline_value=poverty_190.overall.share,
            benchmark=poverty_190.benchmark,
        )
        if poverty_190 is not None and poverty_190.overall.share is not None
        else None
    )

    def _mean_theme(theme_name: str, label: str, constituents: list) -> ThemeScore:
        """Unweighted mean of the constituents that exist this wave, per the dashboard spec.
        `constituents` is a list of MetricResult-or-None; a missing metric or a null overall.share
        is dropped and metric_label records the count when fewer than all are used. An averaged
        theme carries no benchmark (see the module docstring).
        """
        shares = [c.overall.share for c in constituents if c is not None and c.overall.share is not None]
        if not shares:
            raise ValueError(f"{theme_name}: no constituent indicators available this wave")
        if len(shares) < len(constituents):
            label = f"{label} ({len(shares)} of {len(constituents)} available this wave)"
        return ThemeScore(theme_name=theme_name, metric_label=label, headline_value=sum(shares) / len(shares))

    ordered = [
        _mean_theme(
            "Financial Access",
            "Unweighted mean of first-time access and difficulty finding another lender",
            [financial_access.first_time_access, financial_access.alternative_lender_hard_to_find],
        ),
        poverty_score,
        _mean_theme(
            "Business & Household Impact",
            "Unweighted mean of business income change and quality-of-life change",
            [business_household_impact.business_income_change, business_household_impact.quality_of_life_change],
        ),
        ThemeScore(
            theme_name="Child Wellbeing",
            metric_label="Improved child wellbeing",
            headline_value=child_wellbeing.improved_child_wellbeing.overall.share,
            benchmark=child_wellbeing.improved_child_wellbeing.benchmark,
        ),
        _mean_theme(
            "Client Protection",
            "Unweighted mean of financial worry, loan understanding, complaints mechanism, "
            "fair treatment, reporting behaviour and reduced food intake",
            [
                client_protection.financial_worry_decreased,
                client_protection.loan_terms_clear,
                client_protection.complaints_mechanism_trusted,
                client_protection.no_unfair_treatment,
                client_protection.reported_when_unfair,
                client_protection.did_not_reduce_food,
            ],
        ),
        _mean_theme(
            "Agency",
            "Unweighted mean of goal achievement (in full or partially), household influence and community respect",
            [agency.loan_purpose_achieved, agency.household_influence_improved, agency.community_respect_improved],
        ),
        _mean_theme(
            "Resilience",
            "Unweighted mean of savings increase and realized preparedness",
            [resilience.savings_increased, resilience.vf_reduced_shock_severity],
        ),
        ThemeScore(
            theme_name="Client Satisfaction",
            metric_label="Net Promoter Score",
            headline_value=client_satisfaction.nps.score,
            is_percentage=False,
            benchmark=client_satisfaction.nps.benchmark,
        ),
    ]
    return [s for s in ordered if s is not None]


def _format_theme_scores(scores: list) -> str:
    lines = [f"{len(scores)} theme scores:"]
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
    print(f"Step 1/2 done: {len(scores)} theme scores assembled from real, already-published sections (no LLM).")

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
