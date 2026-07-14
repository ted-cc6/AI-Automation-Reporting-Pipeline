"""data_loader/mapping_diff.py

Structural diff between column_mapping.csv and a live CSV's header row.

This is a *diagnostic* counterpart to data_loader_transformer.py's
build_index_resolver(): both match columns by header text first, falling
back to raw_index only when text can't disambiguate. But where the
transformer's resolver is built to run at transform time (self-heal what it
safely can, raise loudly on genuine ambiguity), this module never raises --
it's meant to produce a full report of what matched, what moved, and what's
residual, for a human/LLM reconciliation step to act on *before* any
transform is attempted.
"""
import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

DEFAULT_DIFF_CATEGORIES = frozenset({
    "keep_metadata", "keep_identity", "question_ref",
    "multi_select_child", "free_text_child",
})

RowMatchStatus = Literal["matched_unchanged", "matched_moved", "unmatched"]
ColMatchStatus = Literal["claimed", "unmatched_new"]


@dataclass
class MappingRowStatus:
    raw_index: int
    header: str
    category: str
    question_ref: str
    parent_ref: str
    response_type: str
    status: RowMatchStatus
    matched_csv_index: int | None


@dataclass
class CsvColumnStatus:
    csv_index: int
    header: str
    status: ColMatchStatus


@dataclass
class MappingDiffResult:
    row_statuses: list[MappingRowStatus] = field(default_factory=list)
    csv_statuses: list[CsvColumnStatus] = field(default_factory=list)

    @property
    def has_residual(self) -> bool:
        return bool(self.unmatched_rows()) or bool(self.unmatched_csv_columns())

    def unmatched_rows(self) -> list[MappingRowStatus]:
        return [r for r in self.row_statuses if r.status == "unmatched"]

    def unmatched_csv_columns(self) -> list[CsvColumnStatus]:
        return [c for c in self.csv_statuses if c.status == "unmatched_new"]

    def moved_rows(self) -> list[MappingRowStatus]:
        return [r for r in self.row_statuses if r.status == "matched_moved"]


def read_csv_header_row(csv_path: Path, delimiter: str = ";") -> list[str]:
    """Literal header row via csv.reader -- NOT pandas.read_csv().columns.

    pandas auto-mangles duplicate column names on read (adds .1/.2/...
    suffixes), which would corrupt the exact-text comparison this module
    relies on for the small number of genuinely-duplicated headers (e.g. the
    generic "If other, please specify:" free-text prompts that recur
    verbatim across many unrelated questions). col_names passed to
    diff_columns() must come from this function, not load_raw(csv_path).columns.
    """
    with open(csv_path, newline="", encoding="utf-8") as f:
        return next(csv.reader(f, delimiter=delimiter))


def diff_columns(
    mapping: pd.DataFrame,
    col_names: list[str],
    categories: frozenset[str] = DEFAULT_DIFF_CATEGORIES,
) -> MappingDiffResult:
    """Classify every mapping row and every live CSV column.

    col_names must be literal header text (see read_csv_header_row) -- not
    pandas-mangled column names -- or the duplicate-header fallback below
    will spuriously report unchanged rows as unmatched.

    Pass 1 claims columns across ALL mapping rows (including drop_scaffold/
    drop_system), not just `categories`, so boilerplate section-header text
    is never mistaken for a genuinely new question -- only rows in
    `categories` are surfaced in the returned row_statuses, but every row's
    claim still occupies a live index and keeps that index off the
    unmatched-CSV-columns list.
    """
    header_counts: dict[str, int] = {}
    for h in mapping["raw_column_header"]:
        header_counts[h] = header_counts.get(h, 0) + 1

    live_positions: dict[str, list[int]] = {}
    for i, h in enumerate(col_names):
        live_positions.setdefault(h, []).append(i)

    claimed_by: dict[int, int] = {}  # csv_index -> raw_index
    all_row_results: dict[int, tuple[RowMatchStatus, int | None]] = {}

    for _, row in mapping.iterrows():
        raw_idx = int(row["raw_index"])
        header = row["raw_column_header"].strip()

        found: int | None = None
        if header_counts.get(header, 0) == 1:
            candidates = live_positions.get(header)
            if candidates and len(candidates) == 1:
                found = candidates[0]

        if found is None:
            # Duplicate or absent header text -- only trust raw_index if the
            # live text at that exact position still matches verbatim.
            if raw_idx < len(col_names) and col_names[raw_idx].strip() == header:
                found = raw_idx

        if found is None:
            all_row_results[raw_idx] = ("unmatched", None)
            continue

        prior = claimed_by.get(found)
        if prior is not None and prior != raw_idx:
            # Two different rows landed on the same live column -- neither
            # claim is trustworthy; mark both unmatched instead of guessing.
            all_row_results[raw_idx] = ("unmatched", None)
            if prior in all_row_results:
                all_row_results[prior] = ("unmatched", None)
            continue

        claimed_by[found] = raw_idx
        status: RowMatchStatus = "matched_unchanged" if found == raw_idx else "matched_moved"
        all_row_results[raw_idx] = (status, found)

    row_statuses = []
    for _, row in mapping.iterrows():
        if row["category"] not in categories:
            continue
        raw_idx = int(row["raw_index"])
        status, matched_idx = all_row_results.get(raw_idx, ("unmatched", None))
        row_statuses.append(MappingRowStatus(
            raw_index=raw_idx,
            header=row["raw_column_header"].strip(),
            category=row["category"],
            question_ref=row.get("question_ref", "").strip(),
            parent_ref=row.get("parent_ref", "").strip(),
            response_type=row.get("response_type", "").strip(),
            status=status,
            matched_csv_index=matched_idx,
        ))

    # Derive claimed indices strictly from non-unmatched final results, since
    # the collision-repair branch above can revoke a claim without removing
    # it from claimed_by.
    claimed_indices = {
        matched_idx
        for status, matched_idx in all_row_results.values()
        if status in ("matched_unchanged", "matched_moved") and matched_idx is not None
    }

    csv_statuses = [
        CsvColumnStatus(
            csv_index=i,
            header=h,
            status="claimed" if i in claimed_indices else "unmatched_new",
        )
        for i, h in enumerate(col_names)
    ]

    return MappingDiffResult(row_statuses=row_statuses, csv_statuses=csv_statuses)
