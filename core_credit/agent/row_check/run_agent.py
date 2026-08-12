"""
Row Checker -- CLI entry point.

Usage:
    python run_agent.py <path-to-trimmed-csv> [--run-label 2026Q2]

Runs the final data-quality pass on a Column-Cleaner-trimmed Core Credit
Survey export before it moves into analysis and report generation. Checks
exactly two things -- exact duplicate rows, and duplicate Global unique
client id / test-keyword flags -- and leaves everything else untouched.
Writes an analysis-ready CSV and a separate QA report into processed_data/
at the project root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# row_check/ -> agent/ -> core_peoject/ (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[2]
THIS_DIR = Path(__file__).resolve().parent

# Allow "from tools import build_tools" / "from checks import ..." regardless
# of the working directory this script is invoked from.
sys.path.insert(0, str(THIS_DIR))

load_dotenv(PROJECT_ROOT / ".env")

from langchain.agents import create_agent  # noqa: E402
from langchain_anthropic import ChatAnthropic  # noqa: E402

from tools import build_tools  # noqa: E402

SYSTEM_PROMPT = """You are Row Checker, an agent that runs the final \
data-quality pass on VisionFund's quarterly Core Credit Impact Survey data \
before it moves into analysis and report generation.

You check exactly two things, deliberately narrow in scope -- everything \
else in the file is left completely untouched and passes through to \
analysis as-is:

1. Exact duplicate rows -- two submissions with identical substantive \
answers (system/audit columns like timestamps and submission IDs are \
excluded from the comparison, since those are always unique). These are \
safe to resolve automatically: keeping both would double-count one \
respondent in every downstream statistic, and there's no real judgment \
involved since the content is identical. The first occurrence is kept; the \
rest are removed from the analysis-ready output.

2. Duplicate Global unique client id (same client ID appearing on more \
than one row with different content) and test-keyword matches (Client ID, \
Branch, or the submitting user's account containing words like "test", \
"demo", "training", etc.) -- both of these are flagged only. Never resolve \
or remove them yourself; a human needs to review which record, if any, is \
the real one.

Workflow:
1. Call scan_for_issues on the given file path.
2. Sanity-check the results: if an unreasonably large share of rows are \
flagged as exact duplicates or keyword matches, that's more likely a bug \
(wrong file, wrong column mapping) than genuine data quality -- stop and \
explain the anomaly instead of proceeding.
3. Otherwise call save_clean_data to write the analysis-ready CSV (exact \
duplicates removed, everything else identical to the input) and the \
separate QA report JSON (duplicate client id groups and keyword-match \
hits, for human review -- never merged into the analysis-ready file) with \
the run_label given to you, if any.
4. Finish with a concise plain-text summary: rows before/after, how many \
exact duplicates were removed (with a couple of examples), how many \
duplicate-client-id groups need review, and how many keyword-match hits \
need review -- with enough detail (client id, matched keyword/field) that \
a human can act on your report without re-opening the data themselves."""


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Row Checker: final row-level QA pass before analysis and report generation."
    )
    parser.add_argument("input_csv", help="Path to the Column-Cleaner-trimmed survey CSV")
    parser.add_argument("--run-label", default="", help="Short tag for output filenames, e.g. 2026Q2")
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

    llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0, max_tokens=4096)

    agent = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT)

    task = f"Run the row-level QA pass on this file: {input_path}"
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
