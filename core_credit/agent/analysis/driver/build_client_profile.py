"""Driver script: builds a complete, real ClientProfileSection (template page 1) end to end.

Plain orchestration -- no agent, no tool-calling loop. This section is structurally the
simplest built so far: one Analysis block, no per-metric subsections, no Insight, no
qualitative pass, no verbatims -- the template itself only asks for a single write step here.

  1. Load the CSV once.
  2. Compute every profile figure deterministically (metrics_engine, no LLM).
  3. Write the one Analysis block (writer, single call).
  4. Assemble everything into one ClientProfileSection and write it to output/ as JSON,
     alongside a human-readable summary on stdout.

Usage: python build_client_profile.py
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_peoject

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

import pandas as pd  # noqa: E402

from metrics_engine.engine import categorical_distribution, mean_value  # noqa: E402
from metrics_engine.segments import (  # noqa: E402
    age as age_series,
    clean_blank_strings,
    country as country_series,
    gender as gender_series,
    loan_cycle as loan_cycle_series,
    standard_categorical_segments,
)
from schemas.client_profile import ClientProfileSection  # noqa: E402
from schemas.common import MetricResult  # noqa: E402
from writer.chain import write_subsection  # noqa: E402
from writer.formatting import format_metric_result, format_ranked_options  # noqa: E402
from writer.grounding import collect_acceptable_percentages  # noqa: E402
from writer.section_prompts import CLIENT_PROFILE_ANALYSIS  # noqa: E402

HH_HEAD_COL = "Client Profile/PROFILE02_resp_en"
EDUCATION_COL = "Client Profile/PROFILE03_resp_en"
HH_ADULTS_COL = "Client Profile/PROFILE04a_resp_en"
HH_CHILDREN_U5_COL = "Client Profile/PROFILE04b_resp_en"
HH_CHILDREN_6_14_COL = "Client Profile/PROFILE04c_resp_en"
HH_CHILDREN_15_17_COL = "Client Profile/PROFILE04d_resp_en"
MAIN_INCOME_SOURCE_COL = "Client Profile/PROFILE06_resp_1_en"

UNAVAILABLE_SEGMENTS = [
    "Savings usage -- Voluntary Savings is reported on its own, not as part of the core credit "
    "report; it reaches only the deposit-taking MFIs (Bolivia, Ecuador, Mali, Rwanda, Tanzania, "
    "Myanmar) and its data comes from a separate survey module, per the template's own note."
]

_OPTION_PREFIX_RE = re.compile(r"^[A-Za-z]\.\s*")


def _fieldwork_date_range(df: pd.DataFrame) -> tuple[str, str] | tuple[None, None]:
    """Earliest 'start' and latest 'end' timestamp across every respondent, as plain dates.

    Deliberately NOT derived from the uploaded filename (the previous approach): a filename
    like "Test4_..." has no YYYYQN pattern to match, so that approach silently fell back to
    "unknown period" on the cover page for real production runs. Every respondent row has a
    real 'start'/'end' timestamp (kept by column_clean regardless of naming, since KoBo always
    populates them), so this is available on every run, not just ones with a conveniently
    named upload file.
    """
    if "start" not in df.columns or "end" not in df.columns:
        return None, None
    starts = pd.to_datetime(clean_blank_strings(df["start"]), utc=True, errors="coerce").dropna()
    ends = pd.to_datetime(clean_blank_strings(df["end"]), utc=True, errors="coerce").dropna()
    if starts.empty or ends.empty:
        return None, None
    return starts.min().strftime("%Y-%m-%d"), ends.max().strftime("%Y-%m-%d")


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _strip_option_prefix(series: pd.Series) -> pd.Series:
    """'a. Tertiary' -> 'Tertiary'. Blanks are already None by the time this runs (see
    clean_blank_strings), so only real answers ever reach the regex.
    """
    return series.map(lambda v: _OPTION_PREFIX_RE.sub("", v) if v is not None else None)


def _household_size_series(df: pd.DataFrame) -> pd.Series:
    """Including the client, how many people live in their home -- summed from the four age-band
    sub-questions (adults 18+, children <5, children 6-14, children 15-17), since the
    analysis-ready CSV never carries the parent question's own total as one column. A row only
    counts if all four sub-answers are present; in the current export every row that's missing
    one of them is missing all four (verified -- see ppi_module-style real-data checks elsewhere
    in this project), so this isn't discarding partially-answered rows.
    """
    cols = [HH_ADULTS_COL, HH_CHILDREN_U5_COL, HH_CHILDREN_6_14_COL, HH_CHILDREN_15_17_COL]
    cleaned = [clean_blank_strings(df[c]).tolist() for c in cols]
    values = [None if any(p is None for p in parts) else sum(int(p) for p in parts) for parts in zip(*cleaned)]
    return pd.to_numeric(pd.Series(values, index=df.index), errors="coerce")


def build_section(df: pd.DataFrame) -> ClientProfileSection:
    n_respondents = len(df)
    countries = country_series(df).dropna().unique()
    n_countries = len(countries)
    fieldwork_start_date, fieldwork_end_date = _fieldwork_date_range(df)

    gender_split = categorical_distribution(gender_series(df))
    age = MetricResult(metric_id="age", label="Client age (years)", overall=mean_value(age_series(df)))
    household_size = MetricResult(
        metric_id="household_size", label="Household size (people)", overall=mean_value(_household_size_series(df))
    )
    loan_cycle_mix = categorical_distribution(loan_cycle_series(df))
    household_head_status = categorical_distribution(_strip_option_prefix(clean_blank_strings(df[HH_HEAD_COL])))
    education_level = categorical_distribution(_strip_option_prefix(clean_blank_strings(df[EDUCATION_COL])))
    main_income_source = categorical_distribution(_strip_option_prefix(clean_blank_strings(df[MAIN_INCOME_SOURCE_COL])))

    populated_segments = [axis for axis, series in standard_categorical_segments(df).items() if series.notna().any()]
    print("Step 1/2 done: profile figures computed (no LLM).")

    data_summary = "\n".join(
        [
            f"Respondents: {n_respondents}",
            f"MFIs: {n_countries} (one MFI entity per country in this portfolio)",
            f"Countries: {n_countries}",
            format_ranked_options("Gender split", gender_split),
            format_metric_result(age),
            format_metric_result(household_size),
            format_ranked_options("Loan cycle mix", loan_cycle_mix),
            format_ranked_options("Household head status", household_head_status),
            format_ranked_options("Education level", education_level),
            format_ranked_options("Main income source", main_income_source),
            f"Standard segments populated this wave: {', '.join(a.value for a in populated_segments)}",
            f"Segments NOT available this wave: {'; '.join(UNAVAILABLE_SEGMENTS)}",
        ]
    )
    acceptable = collect_acceptable_percentages(gender_split, loan_cycle_mix, household_head_status, education_level, main_income_source)

    print("Step 2/2: writing the Analysis block...")
    analysis_text = write_subsection(CLIENT_PROFILE_ANALYSIS, data_summary, acceptable_percentages=acceptable)
    print("Step 2/2 done.")

    return ClientProfileSection(
        n_respondents=n_respondents,
        n_mfis=n_countries,
        n_countries=n_countries,
        gender_split=gender_split,
        age=age,
        household_size=household_size,
        loan_cycle_mix=loan_cycle_mix,
        household_head_status=household_head_status,
        education_level=education_level,
        main_income_source=main_income_source,
        populated_segments=populated_segments,
        unavailable_segments=UNAVAILABLE_SEGMENTS,
        analysis_text=analysis_text,
        fieldwork_start_date=fieldwork_start_date,
        fieldwork_end_date=fieldwork_end_date,
    )


def _print_summary(section: ClientProfileSection) -> None:
    print("\n" + "=" * 70)
    print("Client Profile & Methodology")
    print(section.analysis_text.text)
    print(f"[{section.analysis_text.word_count} words, within_cap={section.analysis_text.within_cap}, "
          f"ungrounded={section.analysis_text.ungrounded_percentages}]")
    print(f"\npopulated_segments: {[a.value for a in section.populated_segments]}")
    print(f"unavailable_segments: {section.unavailable_segments}")


def main() -> None:
    csv_path = find_latest_analysis_ready_csv()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path.name}\n")

    section = build_section(df)

    OUTPUT_DIR = Path(__file__).resolve().parent / "output"
    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"client_profile_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {out_path}")

    _print_summary(section)


if __name__ == "__main__":
    main()
