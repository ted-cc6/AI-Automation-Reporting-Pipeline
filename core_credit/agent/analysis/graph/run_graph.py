"""CLI entry point for the generic, config-driven section graph -- builds any section in the
section_configs registry, not just Business & Household Impact.

Checkpointed to a SQLite file (checkpoints.db, next to this script) so a run can be resumed
under the same --thread-id without recomputing already-finished steps.

Usage:
    python run_graph.py business_household_impact                       # fresh run, full dataset
    python run_graph.py financial_access --thread-id my-run              # explicit thread id
    python run_graph.py financial_access --sample 40 --batch-size 20     # fast smoke test
    python run_graph.py --list                                          # show available sections
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
PROJECT_ROOT = Path(__file__).resolve().parents[3]  # core_credit

sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from graph.checkpointing import sqlite_checkpointer  # noqa: E402
from graph.graph import compile_graph  # noqa: E402
from section_configs.registry import SECTION_CONFIGS  # noqa: E402

CHECKPOINT_DB = str(Path(__file__).resolve().parent / "checkpoints.db")
OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def find_latest_analysis_ready_csv() -> Path:
    candidates = sorted((PROJECT_ROOT / "processed_data").glob("*_analysis_ready.csv"))
    if not candidates:
        raise FileNotFoundError("No *_analysis_ready.csv found under processed_data/")
    return candidates[-1]


def _print_summary(section_id: str, section) -> None:
    config = SECTION_CONFIGS[section_id]
    print("\n" + "=" * 70)
    for prompt_config in config.subsection_prompts:
        field = config.written_text_fields[prompt_config.subsection_id]
        analysis = getattr(section, field)
        print(f"\n{prompt_config.subsection_id} {prompt_config.title}")
        print(analysis.text)
        print(f"[{analysis.word_count} words, within_cap={analysis.within_cap}, ungrounded={analysis.ungrounded_percentages}]")

    print(f"\n{config.insight_prompt.title}")
    insight = getattr(section, config.insight_text_field)
    print(insight.text)
    print(f"[{insight.word_count} words, within_cap={insight.within_cap}, ungrounded={insight.ungrounded_percentages}]")

    verbatims = getattr(section, config.insight_verbatims_field)
    print(f"\ninsight_verbatims ({len(verbatims)}):")
    for v in verbatims:
        tags = ", ".join(v.segment_tags) if v.segment_tags else "no segment tags"
        print(f'  "{v.quote}" -- {v.gender}, {v.country}, {tags}')

    if config.qualitative_schema_field:
        qual = getattr(section, config.qualitative_schema_field)
        print(f"\n{config.qualitative.section_label} -- {len(qual.themes)} themes, base_n={qual.base_n}")
        for t in qual.themes[:5]:
            print(f"  - {t.theme} (n={t.frequency})")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("section_id", nargs="?", help="Key from section_configs.registry.SECTION_CONFIGS")
    parser.add_argument("--list", action="store_true", help="List available section ids and exit")
    parser.add_argument("--thread-id", default=None)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--sample", type=int, default=None, help="Limit qualitative responses to the first N -- for a fast smoke test")
    args = parser.parse_args()

    if args.list or not args.section_id:
        print("Available sections:")
        for section_id, config in SECTION_CONFIGS.items():
            status = "validated" if config.validated else "DRAFT -- not yet run against real data"
            print(f"  {section_id}  ({status})")
        return

    if args.section_id not in SECTION_CONFIGS:
        print(f"Unknown section_id {args.section_id!r}. Run with --list to see options.", file=sys.stderr)
        sys.exit(1)

    config = SECTION_CONFIGS[args.section_id]
    thread_id = args.thread_id or args.section_id

    with sqlite_checkpointer(CHECKPOINT_DB) as checkpointer:
        graph = compile_graph(checkpointer=checkpointer)
        graph_config = {"configurable": {"thread_id": thread_id}}

        existing = graph.get_state(graph_config)
        started = time.monotonic()
        if existing.values:
            print(f"Found an existing checkpoint for thread_id={thread_id!r} (next steps: {existing.next}) -- resuming.")
            result = graph.invoke(None, config=graph_config)
        else:
            csv_path = find_latest_analysis_ready_csv()
            print(f"Starting fresh run: section={args.section_id!r}, thread_id={thread_id!r}, data={csv_path.name}")
            if not config.validated:
                print("NOTE: this section's config is a draft, not yet validated against real data -- review the output carefully.")
            inputs = {
                "section_config": config,
                "csv_path": str(csv_path),
                "benchmarks_path": str(PROJECT_ROOT / "External Benchmarks.xlsx"),
                "batch_size": args.batch_size,
                "reasoning_effort": args.reasoning_effort,
                "sample": args.sample,
            }
            result = graph.invoke(inputs, config=graph_config)
        print(f"Graph run finished in {time.monotonic() - started:.0f}s")

        section = result["section"]

        OUTPUT_DIR.mkdir(exist_ok=True)
        out_path = OUTPUT_DIR / f"{args.section_id}_{thread_id}.json"
        out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
        print(f"Wrote {out_path}")

        _print_summary(args.section_id, section)


if __name__ == "__main__":
    main()
