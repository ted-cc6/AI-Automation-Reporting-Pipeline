"""Tier -1: raw survey export -> analysis-ready CSV, via the two already-built data-prep
agents (Column Cleaner, Row Checker). Both are genuine LangChain tool-calling agents (Claude
Haiku 4.5) -- unlike almost everything else this orchestrator wraps, these involve real
per-run judgment (classifying unrecognized columns, sanity-checking anomaly thresholds), so
they stay real agent invocations rather than being collapsed into deterministic code.

Column Cleaner and Row Checker live outside agent/analysis/ as standalone script directories
(no __init__.py -- each expects its own directory on sys.path) and both happen to have a file
literally named tools.py, so they can't both sit on sys.path at once without a bare `import
tools` becoming ambiguous. _import_build_tools loads each in turn and cleans up after itself.

Both agents can legitimately refuse to save (their own system prompts tell them to stop and
explain instead, if they detect a bad delimiter, no recognizable sections, or an implausible
duplicate rate) -- so success is detected by finding the tool's own "Wrote ...:" line in the
agent's message history, not assumed from a clean exit.

check_rows_node also verifies REQUIRED_COLUMNS survived column cleaning before declaring
data_ready -- a fail-fast safety net on top of column_clean/config.yaml's always_keep_column_names
fix, not a replacement for it. Real incident this guards against: Column Cleaner's own judgment
dropped Introduction/SurveyVersion as "an audit field, not impact data" (reasonable in
isolation, wrong for this pipeline), and the failure wasn't caught until build_poverty_likelihood
crashed ~10 minutes in, after Client Satisfaction had already spent real money on a full
qualitative pass. This check catches the same failure mode in seconds, before any of the 9
theme sections start.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import yaml
from langchain.agents import create_agent
from langchain_anthropic import ChatAnthropic

from .state import OrchestratorState

# Columns with no suffix pattern the column_clean rule engine recognizes (see rules.py) --
# everything ending in _resp_en/_resp_value/etc. is already robustly rule-protected, so this
# list only needs the handful of exceptions. Keep in sync with column_clean/config.yaml's
# always_keep_column_names -- this is the runtime check, that's the prevention.
REQUIRED_COLUMNS = (
    "Introduction/SurveyVersion",
    "Introduction/Global unique client id",
    "Introduction/${Country_question}",
)


def _missing_required_columns(csv_path: str) -> list:
    header = pd.read_csv(csv_path, nrows=0, dtype=str).columns
    return [c for c in REQUIRED_COLUMNS if c not in header]

AGENT_ROOT = Path(__file__).resolve().parents[1]  # agent/
PROJECT_ROOT = AGENT_ROOT.parent  # core_peoject
COLUMN_CLEAN_DIR = AGENT_ROOT / "column_clean"
ROW_CHECK_DIR = AGENT_ROOT / "row_check"

# Verbatim from column_clean/run_agent.py's own SYSTEM_PROMPT -- transcribed, not paraphrased,
# so this orchestrator node behaves identically to running that script by hand.
COLUMN_CLEAN_SYSTEM_PROMPT = """You are Column Cleaner, an agent that prepares VisionFund's \
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

# Verbatim from row_check/run_agent.py's own SYSTEM_PROMPT.
ROW_CHECK_SYSTEM_PROMPT = """You are Row Checker, an agent that runs the final \
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


def _import_build_tools(directory: Path, extra_module_names: tuple):
    """Imports `<directory>/tools.py` (plus whatever it needs, e.g. rules.py/checks.py) with
    `directory` temporarily on sys.path, grabs `build_tools`, then removes the path entry and
    the newly-imported module names -- see the module docstring for why this dance is needed.
    """
    directory_str = str(directory)
    sys.path.insert(0, directory_str)
    try:
        import tools as _tools  # type: ignore

        return _tools.build_tools
    finally:
        sys.path.remove(directory_str)
        for name in ("tools",) + extra_module_names:
            sys.modules.pop(name, None)


def _load_config(directory: Path) -> dict:
    with open(directory / "config.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_wrote_path(messages: list, label: str) -> Optional[str]:
    """Scans an agent's message history for the exact "Wrote <label>: <path>" line the
    matching save_* tool always emits on success. None means the tool was never called --
    the agent decided to stop instead, per its own anomaly-handling instructions.
    """
    pattern = re.compile(rf"Wrote {re.escape(label)}: (.+)")
    for msg in messages:
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            match = pattern.search(content)
            if match:
                return match.group(1).strip()
    return None


def clean_columns_node(state: OrchestratorState) -> dict:
    run_label = state.get("run_id", "")
    config = _load_config(COLUMN_CLEAN_DIR)
    build_tools = _import_build_tools(COLUMN_CLEAN_DIR, ("rules",))
    tools = build_tools(config, PROJECT_ROOT)

    llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0)
    agent = create_agent(llm, tools, system_prompt=COLUMN_CLEAN_SYSTEM_PROMPT)

    task = f"Process this quarterly survey export: {state['raw_csv_path']}"
    if run_label:
        task += f"\nUse run_label={run_label!r} for the output filenames."

    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 25, "run_name": f"clean_columns[{run_label or 'run'}]"},
    )
    messages = result["messages"]

    trimmed_csv_path = _find_wrote_path(messages, "trimmed CSV")
    manifest_path = _find_wrote_path(messages, "manifest")

    if trimmed_csv_path is None:
        return {
            "data_ready": False,
            "failure_reason": f"Column Cleaner did not save output:\n\n{messages[-1].content}",
        }
    return {"trimmed_csv_path": trimmed_csv_path, "column_manifest_path": manifest_path}


def check_rows_node(state: OrchestratorState) -> dict:
    if state.get("data_ready") is False:
        return {}  # Column Cleaner already failed -- nothing to check

    run_label = state.get("run_id", "")
    config = _load_config(ROW_CHECK_DIR)
    build_tools = _import_build_tools(ROW_CHECK_DIR, ("checks",))
    tools = build_tools(config, PROJECT_ROOT)

    llm = ChatAnthropic(model="claude-haiku-4-5", temperature=0, max_tokens=4096)
    agent = create_agent(llm, tools, system_prompt=ROW_CHECK_SYSTEM_PROMPT)

    task = f"Run the row-level QA pass on this file: {state['trimmed_csv_path']}"
    if run_label:
        task += f"\nUse run_label={run_label!r} for the output filenames."

    result = agent.invoke(
        {"messages": [{"role": "user", "content": task}]},
        config={"recursion_limit": 25, "run_name": f"check_rows[{run_label or 'run'}]"},
    )
    messages = result["messages"]

    analysis_ready_path = _find_wrote_path(messages, "analysis-ready CSV")
    qa_report_path = _find_wrote_path(messages, "QA report")

    if analysis_ready_path is None:
        return {
            "data_ready": False,
            "failure_reason": f"Row Checker did not save output:\n\n{messages[-1].content}",
        }

    missing = _missing_required_columns(analysis_ready_path)
    if missing:
        return {
            "data_ready": False,
            "failure_reason": (
                f"Column Cleaner dropped {missing} -- required by agent/analysis/ or "
                f"agent/row_check/ (see column_clean/config.yaml's always_keep_column_names "
                f"comment for exactly which code depends on each). Failing fast here, before "
                f"any of the 9 theme sections run, rather than partway through an expensive "
                f"section build -- this is exactly the failure mode a real run hit once "
                f"(Introduction/SurveyVersion dropped, caught only after Client Satisfaction had "
                f"already spent ~9 minutes of real LLM calls). If this is a genuinely new "
                f"dependency, add it to REQUIRED_COLUMNS below and to always_keep_column_names."
            ),
        }
    return {"csv_path": analysis_ready_path, "qa_report_path": qa_report_path, "data_ready": True}


def route_after_data_prep(state: OrchestratorState):
    """Conditional edge: fans out to every Tier 0 node at once (fixed, known set -- not a
    dynamic Send) if the data's ready, otherwise routes to the single `fail` node.
    """
    if state.get("data_ready") and state.get("csv_path"):
        return [
            "build_client_profile",
            "build_financial_access",
            "build_poverty_likelihood",
            "build_business_household_impact",
            "build_child_wellbeing",
            "build_client_protection",
            "build_agency",
            "build_resilience",
            "build_client_satisfaction",
        ]
    return "fail"


def fail_node(state: OrchestratorState) -> dict:
    reason = state.get("failure_reason", "Unknown failure during data preparation.")
    print(f"\nPIPELINE HALTED during data preparation:\n{reason}")
    return {}
