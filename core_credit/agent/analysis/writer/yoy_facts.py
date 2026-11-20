"""CC-096: year-over-year FACT lines for the writer, from <run>_yoy_deltas.json (CC-094).

Active only when CC_YOY_DELTAS names a deltas file (run_orchestrator.py --yoy sets it). Each
block gets the changes for its own metrics, computed in code:
  - analysis subsections: portfolio and gender changes of the metrics they report;
  - Insights: portfolio changes of their section's metrics;
  - the Executive Summary: every headline metric and the NPS score.
Only significant changes are stated as FACTs; the rest are listed as "similar to 2025". Country
and loan-cycle changes are never given to the writer: they live in the YoY table (CC-097), and
swing-flagged figures (CC-095) only in its review list. Values arrive already rounded, and every
figure is added to the block's accepted percentages so grounding does not flag them.
"""

from __future__ import annotations

import json
import os
import re
from functools import lru_cache
from typing import Optional

ENV = "CC_YOY_DELTAS"

# Blocks whose metrics are not in a section config's subsection_metric_ids.
_EXTRA_BLOCKS = {
    "4.1": ("improved_child_wellbeing",),
    "4-insight": ("improved_child_wellbeing",),
    "7.1": ("savings_increased",),
    "7.4": ("vf_reduced_shock_severity",),
    "7-insight": ("savings_increased", "vf_reduced_shock_severity"),
    "8.1": ("nps_promoter",),
}
_NPS_BLOCKS = {"8.1", "8-insight", "executive-summary"}
_GENDER_BLOCKS_EXCLUDED = {"executive-summary"}  # it stays at the portfolio level

RULES = (
    "How to use these year-over-year facts: they compare clients surveyed in 2026 with clients "
    "surveyed in 2025, in the same countries. They are two different groups of clients, not the "
    "same clients followed over time. Mention at most the one or two that matter most for this "
    "block, worded like \"62.0% of clients surveyed in 2026, compared with 69.5% in 2025\". Never "
    "say clients improved or declined, and do not use rose, fell, grew, dropped, up from or down "
    "from: keep the \"compared with\" wording. If the sentence already gives the 2026 figure, add "
    "only \", compared with Y% in 2025\" and do not repeat the 2026 figure. Put each "
    "year-over-year fact in its own sentence, "
    "never joined to a client quote or to another metric. Never give a reason for a change, never "
    "call a figure under \"similar to 2025\" a change, and never describe a change that is not "
    "listed here."
)


@lru_cache(maxsize=4)
def _load(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _deltas() -> Optional[dict]:
    path = os.environ.get(ENV)
    return _load(path) if path else None


@lru_cache(maxsize=1)
def _block_metrics() -> dict:
    from section_configs.registry import SECTION_CONFIGS

    out: dict = {}
    for cfg in SECTION_CONFIGS.values():
        for sub_id, ids in cfg.subsection_metric_ids.items():
            out.setdefault(sub_id, []).extend(ids)
        out.setdefault(cfg.insight_prompt.subsection_id, []).extend(cfg.insight_metric_ids)
    for sub_id, ids in _EXTRA_BLOCKS.items():
        out.setdefault(sub_id, []).extend(ids)
    return {k: tuple(dict.fromkeys(v)) for k, v in out.items()}


def _pct(v: float) -> str:
    return f"{v * 100:.1f}%"


def _fact(label: str, population: str, c: dict, split: Optional[str] = None) -> str:
    who = f"{population}, split by gender: {split}" if split else population
    return (
        f"  - [YOY FACT: {label} ({who}): {_pct(c['value_2026'])} in 2026 compared with "
        f"{_pct(c['value_2025'])} in 2025, {c['change_pts']:+.1f} points, a statistically significant change]"
    )


def facts_for(subsection_id: str) -> tuple[str, set]:
    """(text block to append to the data summary, accepted percentages). Empty without a
    deltas file or when the block has nothing to compare."""
    d = _deltas()
    if not d:
        return "", set()
    metrics = {m["metric_id"]: m for m in d["metrics"]}
    if subsection_id == "executive-summary":
        ids = tuple(m["metric_id"] for m in d["metrics"] if m["headline"] and m["metric_id"] != "cut_food_to_repay")
    else:
        ids = _block_metrics().get(subsection_id, ())
    with_nps = subsection_id in _NPS_BLOCKS
    theme_sets = [q for q in d.get("themes", []) if q["block"] == subsection_id and not q["counts_only"]]
    if not ids and not with_nps and not theme_sets:
        return "", set()

    lines, similar, accepted = [], [], set()

    def accept(c):
        for v in (c["value_2025"], c["value_2026"]):
            accepted.update({round(v * 100, 1), round(v * 100)})
        accepted.update({round(abs(c["change_pts"]), 1), round(abs(c["change_pts"]))})

    for metric_id in ids:
        m = metrics.get(metric_id)
        if m is None:
            continue
        p = m["portfolio"]
        if p["significant"] and not p.get("mix_flag"):
            lines.append(_fact(m["label"], m["population"], p))
            accept(p)
        else:
            similar.append(m["label"])
        if not subsection_id.endswith("-insight") and subsection_id not in _GENDER_BLOCKS_EXCLUDED:
            for split, g in m["by_gender"].items():
                if g["significant"]:
                    lines.append(_fact(m["label"], m["population"], g, split))
                    accept(g)
    if with_nps:
        n = d["nps_score"]["portfolio"]
        if n["significant"]:
            lines.append(
                f"  - [YOY FACT: Net Promoter Score (all clients): {n['value_2026']:.1f} in 2026 compared "
                f"with {n['value_2025']:.1f} in 2025, {n['change_pts']:+.1f} points, a statistically significant change]"
            )
        else:
            similar.append("Net Promoter Score")

    for q in theme_sets:  # CC-099
        for t in q["themes"]:
            if t["significant"]:
                lines.append(
                    f"  - [YOY FACT: theme \"{t['label']}\" ({q['group']}): {_pct(t['value_2026'])} of answers in 2026 "
                    f"compared with {_pct(t['value_2025'])} in 2025, {t['change_pts']:+.1f} points, a statistically significant change]"
                )
                accept(t)
        quiet = [t["label"] for t in q["themes"] if not t["significant"] and (t["count_2025"] or t["count_2026"])]
        if quiet:
            similar.append(f"themes among {q['group']}: " + ", ".join(quiet))

    countries = len(d["comparison_countries"])
    status = []
    if d.get("provisional"):
        status.append("provisional, 2026 collection still open")
    if d.get("partial_countries"):
        status.append(f"2026 still partial in {', '.join(_names(d['partial_countries']))}")
    head = f"Year-over-year comparison, {countries} countries surveyed in both waves" + (f" ({'; '.join(status)})" if status else "") + ":"
    body = lines + ([f"  - Similar to 2025 (no significant change): {'; '.join(similar)}"] if similar else [])
    return "\n".join([head, *body, RULES]), accepted


# YoY2: "down from 95.3%" and "up from 93.9%" got past the rules paragraph, so the wording is
# also checked in code and drives the writer's corrective rewrite.
_TREND_RE = re.compile(r"\b(rose|risen|fell|fallen|grew|grown|dropped|climbed|declined|up from|down from)\b", re.IGNORECASE)
_QUOTED_RE = re.compile(r'"[^"]*"|\u201c[^\u201d]*\u201d')
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")


def wording_violations(text: str) -> list[str]:
    """Year-over-year sentences (they name 2025) that use trend wording. Empty unless a deltas
    file is active; client quotes are ignored."""
    if not _deltas():
        return []
    return [
        s.strip()
        for s in _SENTENCE_RE.split(_QUOTED_RE.sub('""', text or ""))
        if "2025" in s and _TREND_RE.search(s)
    ]


def _names(codes: list) -> list:
    from benchmark_module.mapping import country_display_name

    return [country_display_name(c) for c in codes]
