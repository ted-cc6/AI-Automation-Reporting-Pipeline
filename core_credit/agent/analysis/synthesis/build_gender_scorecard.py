"""Builds GenderScorecardSection -- the cross-cutting template page 9 table.

Same shape as driver/build_child_wellbeing.py's 4.2 table, splitting by gender instead of
caregiver status: every row's mask is re-derived straight from the analysis-ready CSV, using
box definitions imported from wherever they were already verified (section_configs for
Financial Access/Business & Household Impact/Client Protection/Agency; driver/build_resilience.py
and driver/build_child_wellbeing.py for the two rows that live outside section_configs). Nothing
here reads another section's computed OUTPUT for the table itself -- only the Insight step does,
to source real verbatims (see _verbatim_pool below).

9 of these 15 rows borrow definitions from Client Protection and Agency, which are still
validated=False -- a wider version of the same drift risk Child Wellbeing's 4.2 table carries.
Revisit if either config's box values change.

"Loan purpose achieved" uses fully-achieved-only, same default used for Child Wellbeing's
table, matching the confirmed benchmark definition. "Cut food to repay" is the deliberate
inverse of Client Protection's did_not_reduce_food -- built from the same CP06 column's other
four (non-"a") answer options, verified against the real data, not from a NOT-mask on a single
label (safer against a future new option being silently miscounted).

Usage: python build_gender_scorecard.py
"""

from __future__ import annotations

import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_peoject

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from driver.build_child_wellbeing import _nps_promoter_mask  # noqa: E402
from driver.build_resilience import SAVINGS_COL, SAVINGS_TOP_2, VF_SEVERITY_COL, VF_SEVERITY_TOP_2, _impacted_mask  # noqa: E402
from metrics_engine.engine import gap_comparison, top_box_mask  # noqa: E402
from metrics_engine.segments import caregiver_mask, clean_blank_strings, gender as gender_series  # noqa: E402
from schemas.common import QualitativeSynthesis, ThemeFinding  # noqa: E402
from schemas.gender_scorecard import GenderScorecardRow, GenderScorecardSection  # noqa: E402
from section_configs.sections.agency import AGENCY_CONFIG  # noqa: E402
from section_configs.sections.business_household_impact import BUSINESS_HOUSEHOLD_IMPACT_CONFIG  # noqa: E402
from section_configs.sections.client_protection import CLIENT_PROTECTION_CONFIG  # noqa: E402
from section_configs.sections.financial_access import FINANCIAL_ACCESS_CONFIG  # noqa: E402
from synthesis.loader import load_section  # noqa: E402
from writer.chain import write_insight, write_subsection  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import GENDER_INSIGHT, GENDER_SCORECARD_ANALYSIS  # noqa: E402

CHILD_WELLBEING_COL = "Impacts on Business, Household, and Children/IMPACT04_resp_en"
CUT_FOOD_COL = "Client Protection/CP06_resp_en"
CUT_FOOD_LABELS = frozenset(
    {
        "b. Borrowed food or relied on help from friends or relatives",
        "c. Reduced the number of meals eaten by the household",
        "d. Reduced portion sizes at meals for any household member",
        "e. Relied on less preferred foods",
    }
)

# Sections whose already-computed insight_verbatims feed the Insight step's citation pool --
# each one's Verbatim objects already carry .gender, so nothing new needs deriving for that.
VERBATIM_SOURCE_SECTIONS = ["business_household_impact", "resilience", "child_wellbeing", "client_satisfaction"]

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _metric_config(config, metric_id: str):
    return next(m for m in config.metrics if m.metric_id == metric_id)


def _top_box_mask_for(df: pd.DataFrame, config, metric_id: str) -> pd.Series:
    mc = _metric_config(config, metric_id)
    return top_box_mask(clean_blank_strings(df[mc.source_column]), set(mc.top_box_values))


def _child_wellbeing_mask(df: pd.DataFrame) -> pd.Series:
    return top_box_mask(clean_blank_strings(df[CHILD_WELLBEING_COL]), frozenset({"a. Yes"}))


def _cut_food_mask(df: pd.DataFrame) -> pd.Series:
    return top_box_mask(clean_blank_strings(df[CUT_FOOD_COL]), CUT_FOOD_LABELS)


ROWS = [
    ("No prior access, first-time borrower", lambda df: _top_box_mask_for(df, FINANCIAL_ACCESS_CONFIG, "first_time_access"), None),
    ("Finds another lender hard to find", lambda df: _top_box_mask_for(df, FINANCIAL_ACCESS_CONFIG, "alternative_lender_hard_to_find"), None),
    ("Business income improved", lambda df: _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "business_income_change"), None),
    ("Quality of life improved", lambda df: _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "quality_of_life_change"), None),
    ("Improved child wellbeing", _child_wellbeing_mask, caregiver_mask),
    ("Financial worry fell", lambda df: _top_box_mask_for(df, CLIENT_PROTECTION_CONFIG, "financial_worry_decreased"), None),
    ("Loan terms easy to understand", lambda df: _top_box_mask_for(df, CLIENT_PROTECTION_CONFIG, "loan_terms_clear"), None),
    ("No unfair treatment met", lambda df: _top_box_mask_for(df, CLIENT_PROTECTION_CONFIG, "no_unfair_treatment"), None),
    ("Cut food to repay (lower is better)", _cut_food_mask, None),
    ("Loan purpose fully achieved", lambda df: _top_box_mask_for(df, AGENCY_CONFIG, "loan_purpose_achieved_fully"), None),
    ("Household influence improved", lambda df: _top_box_mask_for(df, AGENCY_CONFIG, "household_influence_improved"), None),
    ("Community respect improved", lambda df: _top_box_mask_for(df, AGENCY_CONFIG, "community_respect_improved"), None),
    ("Savings rose", lambda df: top_box_mask(clean_blank_strings(df[SAVINGS_COL]), SAVINGS_TOP_2), None),
    ("VisionFund reduced shock severity", lambda df: top_box_mask(clean_blank_strings(df[VF_SEVERITY_COL]), VF_SEVERITY_TOP_2), _impacted_mask),
    ("Promoter on NPS", _nps_promoter_mask, None),
]


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def build_rows(df: pd.DataFrame) -> list:
    gender = gender_series(df)
    female = gender == "Female"
    male = gender == "Male"

    rows = []
    for label, mask_fn, base_fn in ROWS:
        mask = mask_fn(df)
        base = base_fn(df) if base_fn is not None else None
        gap = gap_comparison(mask, female, "Female", male, "Male", base=base)
        rows.append(
            GenderScorecardRow(
                metric_label=label,
                female_share=gap.group_a_share,
                male_share=gap.group_b_share,
                gap=gap.gap,
                significance=gap.significance,
            )
        )
    return rows


def _verbatim_pool(sections: Optional[dict] = None) -> QualitativeSynthesis:
    """Pools already-computed, already-gender-tagged Verbatim objects from other sections'
    insight_verbatims into one throwaway QualitativeSynthesis, purely so write_insight() has a
    real, grounded pool to cite from -- nothing here is a new computation.

    `sections`, when given, is an already-built {section_id: Section} map (e.g. from the
    orchestrator's graph state) -- used instead of re-reading each section's canonical output
    file. Standalone/CLI usage (sections=None) is unchanged.
    """
    verbatims = []
    for section_id in VERBATIM_SOURCE_SECTIONS:
        section = sections[section_id] if sections is not None else load_section(section_id)
        verbatims.extend(section.insight_verbatims)
    theme = ThemeFinding(theme="cross-section verbatims", frequency=len(verbatims), representative_verbatims=verbatims)
    return QualitativeSynthesis(source_field="gender_scorecard_verbatim_pool", base_n=len(verbatims), themes=[theme])


def _format_rows(rows: list) -> str:
    """Confirmed the hard way (twice, across two separate report runs) that stating two bare
    percentages and trusting the model to correctly work out which gender is higher is not
    reliable: the same row ("Finds another lender hard to find", Female 42.2% vs Male 50.5%)
    was narrated backwards both times, once directly ("women find it harder") and once by
    relabeling the metric itself ("find another lender easily") to make a backwards claim
    read as consistent. So the comparison direction is computed here, once, deterministically,
    and stated as a fact the model only has to narrate -- not a computation it has to redo.
    """
    lines = ["Gender scorecard:"]
    for row in rows:
        f = f"{row.female_share:.1%}" if row.female_share is not None else "no data"
        m = f"{row.male_share:.1%}" if row.male_share is not None else "no data"
        gap = f"{row.gap:+.1%}" if row.gap is not None else "n/a"
        sig = (
            f", significant ({row.significance.method}, p={row.significance.p_value:.3f})"
            if row.significance and row.significance.significant
            else ""
        )
        direction = ""
        if row.female_share is not None and row.male_share is not None:
            if row.female_share > row.male_share:
                direction = " [FACT: women have the HIGHER share on this metric than men]"
            elif row.male_share > row.female_share:
                direction = " [FACT: men have the HIGHER share on this metric than women]"
            else:
                direction = " [FACT: women and men have the same share on this metric]"
        lines.append(f"  - {row.metric_label}: Female {f} vs. Male {m} (gap {gap}{sig}){direction}")
    return "\n".join(lines)


def build_section(df: pd.DataFrame, sections: Optional[dict] = None) -> GenderScorecardSection:
    rows = build_rows(df)
    print("Step 1/2 done: 15-row gender scorecard computed (no LLM).")

    summary = _format_rows(rows)
    acceptable = set()
    for row in rows:
        if row.female_share is not None:
            acceptable |= {round(row.female_share * 100), round(row.female_share * 100, 1)}
        if row.male_share is not None:
            acceptable |= {round(row.male_share * 100), round(row.male_share * 100, 1)}

    print("Step 2/2: writing the Analysis and the Insight...")
    analysis_text = write_subsection(GENDER_SCORECARD_ANALYSIS, summary, acceptable_percentages=acceptable)

    pool = _verbatim_pool(sections)
    acceptable_insight = acceptable | collect_acceptable_percentages(pool)
    insight_text, insight_verbatims = write_insight(
        GENDER_INSIGHT, summary, qualitative=pool, acceptable_percentages=acceptable_insight
    )
    print("Step 2/2 done.")

    return GenderScorecardSection(
        rows=rows, analysis_text=analysis_text, insight_text=insight_text, insight_verbatims=insight_verbatims
    )


def _print_summary(section: GenderScorecardSection) -> None:
    print("\n" + "=" * 70)
    print(_format_rows(section.rows))

    print("\nGender scorecard analysis")
    print(section.analysis_text.text)
    print(f"[{section.analysis_text.word_count} words, within_cap={section.analysis_text.within_cap}, "
          f"ungrounded={section.analysis_text.ungrounded_percentages}]")

    print("\nInsight for Gender")
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
    out_path = OUTPUT_DIR / f"gender_scorecard_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
