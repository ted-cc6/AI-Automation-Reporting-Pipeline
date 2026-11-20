"""CC-097: build the year-over-year table from the deltas file and its wave manifest.

The headline rows are the 15 gender-scorecard metrics plus the NPS score, every one shown
whether or not it changed. Gender rows show significant changes on headline metrics. The
appendix rows hold what the writer is never given: significant loan-cycle and country changes
(99%), minus swing-flagged figures, which go to the review list instead (CC-095).
"""

from __future__ import annotations

import json
from pathlib import Path

from benchmark_module.mapping import country_display_name
from schemas.year_over_year import YearOverYearSection, YoYRow


def _row(label: str, group: str, c: dict, note=None, is_score: bool = False) -> YoYRow:
    return YoYRow(
        label=label, group=group, value_2025=c["value_2025"], value_2026=c["value_2026"],
        change_pts=c["change_pts"], significant=bool(c["significant"]), is_score=is_score, note=note,
    )


def _headline_note(m: dict):
    notes = []
    if m["lower_is_better"]:
        notes.append("lower is better")
    if m["portfolio"].get("mix_flag"):
        notes.append("change reflects country mix")
    return "; ".join(notes) or None


def build_yoy_section(deltas: dict, manifest: dict) -> YearOverYearSection:
    metrics = [m for m in deltas["metrics"]]
    headline = [m for m in metrics if m["headline"]]
    nps = deltas["nps_score"]

    rows = [_row(m["label"], m["population"], m["portfolio"], _headline_note(m)) for m in headline]
    rows.append(_row("Net Promoter Score", "all clients", nps["portfolio"], is_score=True))
    for r, m in zip(rows, headline):
        if m["portfolio"].get("mix_flag"):
            r.significant = False  # not presented as a change: standardising erased it

    gender = [
        _row(m["label"], f"{'women' if g == 'Female' else 'men'} ({m['population']})", c)
        for m in headline for g, c in m["by_gender"].items() if c["significant"]
    ]
    cycles = [
        _row(m["label"], f"{cycle} ({m['population']})", c)
        for m in headline for cycle, c in m["by_loan_cycle"].items() if c["significant"]
    ]
    countries = [
        _row(m["label"], country_display_name(cty), c)
        for m in headline for cty, c in m["by_country"].items() if c["significant"] and not c["swing_flag"]
    ]
    countries += [
        _row("Net Promoter Score", country_display_name(cty), c, is_score=True)
        for cty, c in nps["by_country"].items() if c["significant"] and not c["swing_flag"]
    ]
    countries.sort(key=lambda r: (r.group, -abs(r.change_pts)))
    review = [
        YoYRow(
            label=r["label"], group=country_display_name(r["country"]), value_2025=r["value_2025"],
            value_2026=r["value_2026"], change_pts=r["change_pts"], significant=False,
            is_score=r["metric_id"] == "nps_score", note="to confirm with the country team",
        )
        for r in deltas["swing_review"]
    ]

    compared = [country_display_name(c) for c in deltas["comparison_countries"]]
    excluded = {country_display_name(c): why for c, why in manifest.get("excluded_countries", {}).items()}
    partial = [country_display_name(c) for c in deltas.get("partial_countries", [])]
    a, b = deltas["waves"]["comparison"], deltas["waves"]["report"]
    return YearOverYearSection(
        comparison_wave=a, report_wave=b, comparison_countries=compared, excluded_countries=excluded,
        partial_countries=partial, provisional=bool(deltas.get("provisional")),
        note=_note(a, b, len(compared), excluded, partial, bool(deltas.get("provisional"))),
        headline_rows=rows, gender_rows=gender, loan_cycle_rows=cycles, country_rows=countries, review_rows=review,
    )


def _note(a, b, n, excluded, partial, provisional) -> str:
    parts = [
        f"These figures compare clients surveyed in {b} with clients surveyed in {a}, in the {n} "
        f"countries surveyed in both years. They are two different groups of clients, not the same "
        f"clients followed over time, so a change describes the client base, not how individual "
        f"clients fared."
    ]
    if excluded:
        parts.append("Not compared: " + "; ".join(f"{c} ({why})" for c, why in excluded.items()) + ".")
    if provisional:
        tail = f", and {' and '.join(partial)} {'is' if len(partial) == 1 else 'are'} still being surveyed" if partial else ""
        parts.append(f"{b} collection is still open{tail}, so every {b} figure here is provisional.")
    parts.append(
        "A change is marked significant when a two-sided test finds it unlikely to be chance: at 95% "
        "for all-client and gender rows, at 99% for loan-cycle and country rows, where many more "
        "comparisons are made. Country figures that moved by more than 30 points are not "
        "interpreted; they are listed at the end for review with the country teams. The table "
        "describes what changed, not why."
    )
    return " ".join(parts)


def load_yoy_section(deltas_path: str) -> YearOverYearSection:
    deltas = json.loads(Path(deltas_path).read_text(encoding="utf-8"))
    manifest = json.loads(Path(deltas["source_manifest"]).read_text(encoding="utf-8"))
    return build_yoy_section(deltas, manifest)
