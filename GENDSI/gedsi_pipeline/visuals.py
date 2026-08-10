"""
Stage 6 support -- renders chart images directly from response_frame data.

Charts are code-generated, never LLM-generated: the draft writer (Stage 5)
only ever outputs headline/paragraph text, so any figure the report shows
must be built here, from the same dataframe the quant engine uses, so it
can't show numbers that don't match the report's own tables.
"""
from __future__ import annotations

from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def render_understanding_by_product_chart(df: pd.DataFrame, out_path: Path) -> Path:
    """Grouped bar chart: % of Female vs Male clients reporting 'Very poor'
    understanding of their own coverage, one bar pair per insurance product."""
    itypes = sorted(df["insurance_type"].dropna().unique())
    female_pct, male_pct = [], []
    for itype in itypes:
        sub = df[df["insurance_type"] == itype]
        f = sub[sub["sex"] == "Female"]
        m = sub[sub["sex"] == "Male"]
        female_pct.append(100 * (f["understanding_coverage"] == "Very poor").sum() / len(f) if len(f) else 0)
        male_pct.append(100 * (m["understanding_coverage"] == "Very poor").sum() / len(m) if len(m) else 0)

    x = list(range(len(itypes)))
    width = 0.35
    fig, ax = plt.subplots(figsize=(6.5, 3.8))
    ax.bar([i - width / 2 for i in x], female_pct, width, label="Female", color="#8E44AD")
    ax.bar([i + width / 2 for i in x], male_pct, width, label="Male", color="#2E86C1")
    ax.set_xticks(x)
    ax.set_xticklabels(itypes)
    ax.set_ylabel('% reporting "very poor" understanding')
    ax.set_title("Coverage understanding by product and sex")
    ax.legend()
    for i, v in enumerate(female_pct):
        ax.text(i - width / 2, v + 0.5, f"{v:.0f}%", ha="center", fontsize=8)
    for i, v in enumerate(male_pct):
        ax.text(i + width / 2, v + 0.5, f"{v:.0f}%", ha="center", fontsize=8)
    fig.tight_layout()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    return out_path
