"""CC-093: split a multi-wave export into survey waves and fix the comparison country set.

One export holds both waves on the same form (CC-092). A wave is the calendar year of
`_submission_time`: 2025 ran Jul to Dec 2025, 2026 from Aug 2026. Everything here is
deterministic and LLM-free; prepare_waves.py wires it around the existing data-prep agents.

The comparison set is the countries with at least MIN_COUNTRY_N rows in every wave (India,
with no 2026 rows, falls out). Portfolio figures for both years are computed on that same set,
so a country present in only one wave can't pass for a year-over-year change. A country is
"partial" when its latest wave holds more than PARTIAL_SHORTFALL fewer rows than the earlier
one, which while collection is open means it is still being surveyed (Mali, Senegal).
"""

from __future__ import annotations

from typing import Optional

import pandas as pd

SUBMISSION_TIME_COL = "_submission_time"
COUNTRY_COL = "Introduction/${Country_question}"

MIN_COUNTRY_N = 150
PARTIAL_SHORTFALL = 0.20


def wave_of(submission_times: pd.Series) -> pd.Series:
    """The wave (calendar year) of each row. Unparseable times come back as <NA>."""
    return pd.to_datetime(submission_times, errors="coerce", utc=True).dt.year.astype("Int64")


def split_waves(df: pd.DataFrame) -> dict[int, pd.DataFrame]:
    """{wave year: that wave's rows}, original column order and index kept. Rows with no
    readable submission time belong to no wave; the caller reports how many."""
    waves = wave_of(df[SUBMISSION_TIME_COL])
    return {int(y): df[waves == y] for y in sorted(waves.dropna().unique())}


def country_counts(df: pd.DataFrame) -> dict[str, int]:
    counts = df[COUNTRY_COL].fillna("").astype(str).str.strip()
    counts = counts[counts != ""].value_counts()
    return {str(k): int(v) for k, v in sorted(counts.items())}


def comparison_countries(counts_by_wave: dict[int, dict[str, int]], min_n: int = MIN_COUNTRY_N) -> list[str]:
    """Countries with at least `min_n` rows in every wave, sorted."""
    waves = list(counts_by_wave.values())
    if not waves:
        return []
    common = set.intersection(*(set(c) for c in waves))
    return sorted(c for c in common if all(w.get(c, 0) >= min_n for w in waves))


def partial_countries(
    earlier: dict[str, int], latest: dict[str, int], shortfall: float = PARTIAL_SHORTFALL
) -> list[str]:
    """Countries present in both waves whose latest count is more than `shortfall` below the
    earlier one."""
    return sorted(c for c in latest if c in earlier and earlier[c] and latest[c] < earlier[c] * (1 - shortfall))


def build_manifest(
    counts_by_wave: dict[int, dict[str, int]],
    paths_by_wave: dict[int, str],
    source_export: str,
    last_submission: Optional[str],
    rows_without_wave: int = 0,
    collection_open: bool = True,
) -> dict:
    """The wave manifest every later YoY step reads instead of re-deriving the country set."""
    years = sorted(counts_by_wave)
    earlier, latest = (counts_by_wave[years[0]], counts_by_wave[years[-1]]) if years else ({}, {})
    compared = comparison_countries(counts_by_wave)
    all_countries = sorted(set().union(*(set(c) for c in counts_by_wave.values()))) if years else []
    return {
        "source_export": source_export,
        "waves": [
            {
                "year": y,
                "analysis_ready_csv": paths_by_wave.get(y),
                "rows": sum(counts_by_wave[y].values()),
                "rows_by_country": counts_by_wave[y],
            }
            for y in years
        ],
        "report_wave": years[-1] if years else None,
        "comparison_wave": years[0] if len(years) > 1 else None,
        "comparison_countries": compared,
        "excluded_countries": {
            c: _exclusion_reason(c, counts_by_wave) for c in all_countries if c not in compared
        },
        "partial_countries": partial_countries(earlier, latest) if len(years) > 1 else [],
        "min_country_n": MIN_COUNTRY_N,
        "rows_without_wave": rows_without_wave,
        "last_submission": last_submission,
        "provisional": collection_open,
    }


def _exclusion_reason(country: str, counts_by_wave: dict[int, dict[str, int]]) -> str:
    missing = [str(y) for y, c in counts_by_wave.items() if c.get(country, 0) == 0]
    if missing:
        return f"no rows in {', '.join(missing)}"
    low = [f"{y}: {c[country]}" for y, c in counts_by_wave.items() if c.get(country, 0) < MIN_COUNTRY_N]
    return f"below {MIN_COUNTRY_N} rows ({'; '.join(low)})"
