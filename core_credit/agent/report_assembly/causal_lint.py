"""CC-085: runs writer/causal_lint.py over every narrative block of an assembled report.

Report-only for now: prints each hit with its section path, subsection id and sentence, plus a
count per tier, and always exits 0. CC-086 turns the hard tier into an enforcing gate.

Works on the saved report JSON as plain dicts, not by loading it into CoreCreditImpactReport, so
it can also baseline older runs (Test5) whose JSON predates later schema changes. A narrative
block is any object carrying both "subsection_id" and "text" -- the shape every WrittenText
serialises to.

Usage, from core_credit/agent/:
    python -m report_assembly.causal_lint report_assembly/output/core_credit_impact_report_<run>.json [--hard-only]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))

from writer.causal_lint import lint_text  # noqa: E402


@dataclass(frozen=True)
class ReportLintHit:
    path: str
    subsection_id: str
    term: str
    tier: str
    sentence: str


def _narrative_blocks(obj, path: str = ""):
    """Yields (path, subsection_id, text) for every serialised WrittenText found while
    recursing through dicts and lists.
    """
    if isinstance(obj, dict):
        if "subsection_id" in obj and isinstance(obj.get("text"), str):
            yield path, obj["subsection_id"], obj["text"]
            return
        for key, value in obj.items():
            yield from _narrative_blocks(value, f"{path}.{key}" if path else key)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from _narrative_blocks(item, f"{path}[{i}]")


def lint_report(report, include_review: bool = True) -> list[ReportLintHit]:
    """`report` is the report JSON as loaded dicts, or a CoreCreditImpactReport instance."""
    if hasattr(report, "model_dump"):
        report = report.model_dump(mode="json")
    hits = []
    for path, subsection_id, text in _narrative_blocks(report):
        for h in lint_text(text, include_review=include_review):
            hits.append(ReportLintHit(path=path, subsection_id=subsection_id, term=h.term, tier=h.tier, sentence=h.sentence))
    return hits


def format_hits(hits: list[ReportLintHit]) -> str:
    lines = []
    for tier in ("hard", "review"):
        tier_hits = [h for h in hits if h.tier == tier]
        terms = Counter(h.term for h in tier_hits)
        summary = ", ".join(f"{t} x{n}" for t, n in terms.most_common())
        lines.append(f"{tier.upper()}: {len(tier_hits)} hit(s){' -- ' + summary if summary else ''}")
        for h in tier_hits:
            lines.append(f"  [{h.term}] {h.subsection_id} ({h.path}): {h.sentence}")
    return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Causal-language lint over a Core Credit report JSON (report-only).")
    parser.add_argument("report_json", nargs="+", type=Path)
    parser.add_argument("--hard-only", action="store_true", help="skip the review tier")
    args = parser.parse_args(argv)
    for path in args.report_json:
        report = json.loads(path.read_text(encoding="utf-8"))
        hits = lint_report(report, include_review=not args.hard_only)
        print(f"=== {path.name}")
        print(format_hits(hits))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
