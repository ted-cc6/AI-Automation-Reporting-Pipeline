"""Validates the qualitative theme-tagging agent against the REAL, FULL Quality of Life
driver dataset (Business & Household Impact 3.3) -- every non-blank IMPACT03a/b/c response
this quarter (~5800), not a sample. Batches in parallel; makes ~30 real LLM calls plus one
merge call, so this takes a few minutes and costs more than a quick smoke test.

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

from qualitative_agent.agent import QUALITY_OF_LIFE_DRIVERS_TASK, theme_tag_full_dataset  # noqa: E402
from qualitative_agent.data_prep import load_quality_of_life_drivers  # noqa: E402


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def main() -> None:
    csv_path = find_latest_analysis_ready_csv()
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    print(f"Loaded {len(df)} rows from {csv_path.name}\n")

    responses = load_quality_of_life_drivers(df)  # full dataset, no sampling
    countries_covered = {r.country for r in responses if r.country}
    print(f"Loaded {len(responses)} non-blank quality-of-life-driver responses across {len(countries_covered)} countries.\n")

    started = time.monotonic()
    result = theme_tag_full_dataset("quality_of_life_drivers", responses, QUALITY_OF_LIFE_DRIVERS_TASK)
    elapsed = time.monotonic() - started
    print(f"Theme-tagging finished in {elapsed:.0f}s\n")

    print(f"{len(result.themes)} themes found, base_n={result.base_n}\n")
    total_tagged = 0
    verbatim_countries = set()
    for t in result.themes:
        total_tagged += t.frequency
        severity_tag = f"  [severity={t.severity}]" if t.severity else ""
        print(f"- {t.theme}  (n={t.frequency}, {t.share_of_respondents:.1%}){severity_tag}")
        for v in t.representative_verbatims:
            verbatim_countries.add(v.country)
            tags = f", {', '.join(v.segment_tags)}" if v.segment_tags else ""
            print(f'    "{v.quote}"')
            print(f"        -- {v.gender or '?'}, age {v.age or '?'}, {v.country or '?'}, loan cycle {v.loan_cycle or '?'}{tags}")
        print()

    print(f"Sum of theme frequencies: {total_tagged} (responses can count toward more than one theme, so this can exceed base_n={result.base_n})")
    print(f"Verbatims drawn from {len(verbatim_countries)} distinct countries: {sorted(c for c in verbatim_countries if c)}")

    given_texts = {r.text for r in responses}
    all_quotes = {v.quote for t in result.themes for v in t.representative_verbatims}
    ungrounded = all_quotes - given_texts
    if ungrounded:
        print(f"\nGROUNDING FAILURE -- quotes not present in the input data: {ungrounded}")
    else:
        print("\nGrounding check passed: every verbatim quote is an exact match to a real input response.")


if __name__ == "__main__":
    main()
