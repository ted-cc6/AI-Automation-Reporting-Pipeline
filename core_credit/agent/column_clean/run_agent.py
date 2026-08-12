"""
Column Cleaner -- CLI entry point.

Usage:
    python run_agent.py <path-to-survey-csv> [--run-label 2026Q3]

Trims a raw quarterly Core Credit Survey export down to the columns the
report-generation pipeline actually needs, and writes the result (plus an
audit manifest) into processed_data/ at the project root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# column_clean/ -> agent/ -> core_peoject/ (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent

# Allow "from tools import build_tools" / "from rules import ..." regardless
# of the working directory this script is invoked from.
sys.path.insert(0, str(THIS_DIR))

load_dotenv(PROJECT_ROOT / ".env")

from langchain.agents import create_agent  # noqa: E402
from langchain_anthropic import ChatAnthropic  # noqa: E402

from tools import build_tools  # noqa: E402

SYSTEM_PROMPT = """You are Column Cleaner, an agent that prepares VisionFund's \
quarterly Core Credit Impact Survey exports for report generation.

The raw survey export is a KoboToolbox/ODK-style CSV where every question \
explodes into several columns (Section/CODE_desc, Section/CODE_question_en, \
Section/CODE_resp_value, ...). Most of that is static question-text metadata \
repeated on every row; only a fraction is real per-respondent data the Core \
Credit Impact Report needs. Your job each quarter is to trim the file down to \
just the columns the report-generation pipeline actually needs, without ever \
silently discarding a column that might carry real data.

Workflow:
1. Call profile_survey_csv on the given file path. It runs a deterministic \
rule engine and returns a compact report: totals, section list, and a list \
of any columns whose naming pattern the rule engine didn't recognize \
("NEEDS REVIEW"). Everything else has already been confidently classified \
by the rules -- trust that classification, you do not need to re-derive it.
2. For each NEEDS REVIEW column, decide keep or drop using judgment: does \
the column name, section, null rate, cardinality, and sample values suggest \
real survey-response data (keep) or leftover metadata/audit noise/language \
duplication (drop)? When genuinely unsure, leave it as the default (keep) -- \
never guess drop. Only override columns that appear in the NEEDS REVIEW \
list; you cannot and must not override a rule-confident column.
3. If the report includes an ANOMALY WARNING (very few columns kept, or no \
sections detected), do not proceed to save_trimmed_csv -- stop and explain \
the anomaly clearly in your final answer instead, since it likely means \
delimiter detection failed or this file doesn't match the expected format.
4. Otherwise, call save_trimmed_csv with any review_decisions you want to \
apply (omit entries you're leaving as the default keep) and the run_label \
given to you, if any.
5. Finish with a concise plain-text summary for the user: rows and columns \
before/after, file size reduction, which sections survived into the \
trimmed file, and a short list of anything you decided to drop from the \
review list (with why) -- so a human can spot-check your judgment calls \
even though this step runs automatically each quarter. For the sections \
list specifically, copy the "Sections included in output" line from \
save_trimmed_csv's return value verbatim -- do not reconstruct it yourself \
from profile_survey_csv's "Sections found" line, which lists every section \
in the raw file (including ones fully excluded by config) and will be \
wrong if you use it here.

Never invent or guess a column name -- only reference the index numbers the \
profile_survey_csv report gives you."""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Column Cleaner: trim a Core Credit Survey export for report generation."
    )
    parser.add_argument("input_csv", help="Path to the raw survey CSV export")
    parser.add_argument("--run-label", default="", help="Short tag for output filenames, e.g. 2026Q3")
    parser.add_argument(
        "--config", default=str(THIS_DIR / "config.yaml"), help="Path to config.yaml"
    )
    args = parser.parse_args()

    input_path = Path(args.input_csv).resolve()
    if not input_path.exists():
        print(f"ERROR: file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    with open(args.config, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)

    tools = build_tools(config, PROJECT_ROOT)

    llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0)

    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    task = f"Process this quarterly survey export: {input_path}"
    if args.run_label:
        task += f"\nUse run_label={args.run_label!r} for the output filenames."

    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 25},
    )

    final_message = result["messages"][-1]
    print("\n" + "=" * 70)
    print(final_message.content)


if __name__ == "__main__":
    main()
