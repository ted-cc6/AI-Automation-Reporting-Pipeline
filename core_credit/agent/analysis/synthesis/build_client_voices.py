"""Builds ClientVoicesSection -- a curated verbatim bank, no new computation and no LLM call.

The template's own instructions for this section are pure curation ("lead with the green light
themes that recur, then the red flags that detractors raise most... let the voices carry the
qualitative story"), and Client Satisfaction already produced exactly the raw material needed:
three theme-tagged bands (promoters/passives/detractors) with real, grounded Verbatim objects,
already ranked by frequency, with severity already flagged on any client-protection-relevant
theme. There's nothing left to compute or write in prose -- just select.

Green lights: verbatims from the promoter band's most-recurring theme(s).
Red flags: verbatims from the detractor band, but sorted by severity first and frequency
second, not frequency alone -- "flag any signal of poor conduct... however low the volume" is
the same standard the qualitative agent's own tagging already applies (see
qualitative_agent/agent.py's SYSTEM_PROMPT), so a high-severity theme with fewer mentions
outranks a larger but merely-annoying one. In the real run behind this section, that reordering
is what actually surfaces "short repayment periods, rigid terms... no flexibility during
hardship" (severity=high, n=48) ahead of the numerically larger "interest rates too high"
theme (n=111, no severity) -- exactly the case this design choice exists for.

Usage: python build_client_voices.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

ANALYSIS_ROOT = Path(__file__).resolve().parents[1]  # agent/analysis
sys.path.insert(0, str(ANALYSIS_ROOT))

from qualitative_agent.agent import SEVERITY_RANK, pick_diverse_verbatims  # noqa: E402
from schemas.client_voices import ClientVoicesSection  # noqa: E402
from synthesis.loader import load_section  # noqa: E402

TOP_N_THEMES = 2
VERBATIMS_PER_SIDE = 3

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def _dedup_key(v):
    return v.client_id or v.quote.strip()


def _pool_top_themes(themes: list, key, exclude: set) -> list:
    top = sorted(themes, key=key, reverse=True)[:TOP_N_THEMES]
    pool = []
    for t in top:
        pool.extend(v for v in t.representative_verbatims if _dedup_key(v) not in exclude)
    return pool


def build_section(sections: Optional[dict] = None) -> ClientVoicesSection:
    """`sections`, when given, is an already-built {section_id: Section} map (e.g. from the
    orchestrator's graph state) -- used instead of re-reading client_satisfaction's canonical
    output file. Standalone/CLI usage (sections=None) is unchanged: falls back to
    synthesis.loader.load_section(), same as before this was wired into the orchestrator.
    """
    client_satisfaction = sections["client_satisfaction"] if sections is not None else load_section("client_satisfaction")
    promoters, _passives, detractors = client_satisfaction.nps_followup_themes

    # CC-048: this pool IS client_satisfaction's own theme pool (see the docstring above) --
    # confirmed live, the Zambia "wonderful services" quote independently surfaced here after
    # client_satisfaction's own Insight had already cited it in Part 8, one section before a
    # reader reaches this one. Excluding what client_satisfaction already rendered in its own
    # insight_verbatims is safe, not just cosmetic: that pool is thousands of tagged responses
    # deep and only ~2% of it is ever cited anywhere (see docs/core_credit_report_spec.md
    # CC-048), so there is always another real candidate to fall back to.
    already_cited = {_dedup_key(v) for v in client_satisfaction.insight_verbatims}

    green_pool = _pool_top_themes(promoters.themes, key=lambda t: t.frequency, exclude=already_cited)
    green_lights = pick_diverse_verbatims(green_pool, k=VERBATIMS_PER_SIDE)

    red_pool = _pool_top_themes(detractors.themes, key=lambda t: (SEVERITY_RANK.get(t.severity, 0), t.frequency), exclude=already_cited)
    red_flags = pick_diverse_verbatims(red_pool, k=VERBATIMS_PER_SIDE)

    return ClientVoicesSection(green_lights=green_lights, red_flags=red_flags)


def _print_summary(section: ClientVoicesSection) -> None:
    print("Green lights (promoters):")
    for v in section.green_lights:
        print(f'  "{v.quote}" -- {v.gender}, {v.country}, {", ".join(v.segment_tags) if v.segment_tags else "no segment tags"}')

    print("\nRed flags (detractors):")
    for v in section.red_flags:
        print(f'  "{v.quote}" -- {v.gender}, {v.country}, {", ".join(v.segment_tags) if v.segment_tags else "no segment tags"}')


def main() -> None:
    section = build_section()

    OUTPUT_DIR.mkdir(exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = OUTPUT_DIR / f"client_voices_{timestamp}.json"
    out_path.write_text(json.dumps(section.model_dump(), indent=2, default=str), encoding="utf-8")
    print(f"Wrote {out_path}\n")

    _print_summary(section)


if __name__ == "__main__":
    main()
