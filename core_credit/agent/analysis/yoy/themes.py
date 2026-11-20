"""CC-099: year-over-year change in theme shares, for every theme pass on an approved codebook.

Both waves are coded against the same approved codebook (CC-089, CC-098), on the same
comparison countries, so a theme's share can be compared like any other figure. Cached codes
are reused; only answers never coded before call the LLM. A theme's share is its answers over
every answer to that question set in the wave, as the report states it. Significance: the
same 95% two-proportion test as the portfolio metrics.

Protection signals are counts only: a handful of answers per theme cannot carry a trend, and
"harassment reports changed" would invite a reading the data cannot support. They go to the
YoY table as counts and are never given to the writer.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import pandas as pd

from metrics_engine.engine import two_proportion_ztest
from qualitative_agent.codebook import load_approved_codebook, tag_with_codebook
from qualitative_agent.data_prep import QUALITY_OF_LIFE_DRIVER_COLS, load_free_text_responses_multi
from yoy.deltas import PORTFOLIO_ALPHA, _in_set

# A theme set is only tested when at least this many clients answered in each wave. YoY1: other
# child improvements had 51 and 53 answers and "Schooling" moved 29% to 60%; at that size a few
# answers swing a share by many points.
MIN_THEME_BASE = 100


@dataclass(frozen=True)
class ThemeSource:
    question: str  # codebook name
    group: str  # how the table and the writer name who answered
    columns: tuple
    task: str
    block: Optional[str]  # the writer block that discusses these themes; None = table only
    counts_only: bool = False


def theme_sources() -> list[ThemeSource]:
    import driver.build_client_satisfaction as cs
    from driver.build_child_wellbeing import OTHER_IMPROVEMENTS_COL, OTHER_IMPROVEMENTS_TASK
    from driver.build_resilience import OTHER_COPING_COL, OTHER_COPING_TASK
    from qualitative_agent.agent import PROTECTION_SIGNALS_TASK, QUALITY_OF_LIFE_DRIVERS_TASK
    from section_configs.sections.client_protection import PROTECTION_SIGNAL_SOURCE_COLS

    return [
        ThemeSource(cs.PROMOTER_CODEBOOK, "promoters' reasons", (cs.PROMOTER_FOLLOWUP_COL,), cs.PROMOTER_TASK, "8.2"),
        ThemeSource(cs.PASSIVE_CODEBOOK, "passives' reasons", (cs.PASSIVE_FOLLOWUP_COL,), cs.PASSIVE_TASK, None),
        ThemeSource(cs.DETRACTOR_CODEBOOK, "detractors' reasons", (cs.DETRACTOR_FOLLOWUP_COL,), cs.DETRACTOR_TASK, "8.2"),
        ThemeSource("quality_of_life_drivers", "quality-of-life answers", tuple(QUALITY_OF_LIFE_DRIVER_COLS), QUALITY_OF_LIFE_DRIVERS_TASK, "3-insight"),
        ThemeSource("other_coping", "other ways of coping", (OTHER_COPING_COL,), OTHER_COPING_TASK, "7.3"),
        ThemeSource("other_child_improvements", "other child improvements", (OTHER_IMPROVEMENTS_COL,), OTHER_IMPROVEMENTS_TASK, "4-insight"),
        ThemeSource("protection_signals", "protection signals", tuple(PROTECTION_SIGNAL_SOURCE_COLS), PROTECTION_SIGNALS_TASK, None, counts_only=True),
    ]


def theme_change(label: str, x_a: int, n_a: int, x_b: int, n_b: int, test: bool = True) -> dict:
    out = {
        "label": label, "count_2025": x_a, "count_2026": x_b, "n_2025": n_a, "n_2026": n_b,
        "value_2025": x_a / n_a if n_a else None, "value_2026": x_b / n_b if n_b else None,
        "change_pts": None, "p_value": None, "significant": False,
    }
    if n_a and n_b:
        out["change_pts"] = (out["value_2026"] - out["value_2025"]) * 100
        if test and (x_a + x_b) > 0:
            sig = two_proportion_ztest(x_b, n_b, x_a, n_a, alpha=PORTFOLIO_ALPHA)
            out["p_value"], out["significant"] = sig.p_value, sig.significant
    return out


def _counts(source: ThemeSource, df: pd.DataFrame, codebook: dict) -> tuple[dict, int]:
    responses = load_free_text_responses_multi(df, source.columns)
    synth = tag_with_codebook(source.question, source.question, responses, codebook, source.task)
    return {t.theme: t.frequency for t in synth.themes}, synth.base_n


def compute_theme_deltas(df_2025: pd.DataFrame, df_2026: pd.DataFrame, comparison_countries: list[str]) -> list[dict]:
    a, b = _in_set(df_2025, comparison_countries), _in_set(df_2026, comparison_countries)
    out = []
    for source in theme_sources():
        codebook = load_approved_codebook(source.question)
        if codebook is None:
            continue  # open coding cannot be compared across runs, let alone waves
        counts_a, n_a = _counts(source, a, codebook)
        counts_b, n_b = _counts(source, b, codebook)
        labels = [t["label"] for t in codebook["themes"]]
        small_base = min(n_a, n_b) < MIN_THEME_BASE
        test = not source.counts_only and not small_base
        themes = [theme_change(lbl, counts_a.get(lbl, 0), n_a, counts_b.get(lbl, 0), n_b, test=test) for lbl in labels]
        out.append(
            {
                "question": source.question, "group": source.group, "block": source.block,
                "counts_only": source.counts_only, "small_base": small_base, "codebook_version": codebook["version"],
                "n_2025": n_a, "n_2026": n_b, "themes": themes,
            }
        )
    return out
