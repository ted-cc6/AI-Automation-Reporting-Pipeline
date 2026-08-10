"""
gedsi_pipeline/mapping_diff.py

Structural diff between column_mapping.csv and a live CSV's header row.

Mirrors the Cupboard Week pipeline's data_loader/mapping_diff.py: matches
columns by header text first (only trusting header text when it's unique
across the mapping), falling back to raw_index only when text can't
disambiguate -- GENDSI's export repeats generic header text ("If other,
please specify:") across many unrelated columns for the same reason
Cupboard Week's does. Never raises; produces a full report of what matched,
what moved, and what's residual, for a human/LLM reconciliation step (see
dashboard/api/gedsi_reconciliation.py) to act on before any ingest is
attempted.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import pandas as pd

# Role types surfaced as reconciliation candidates when unmatched. pii_drop
# and unused rows still CLAIM their live position in the matching pass below
# (so they're never mistaken for a genuinely new column) but are never
# themselves surfaced as "missing" -- losing a PII column or a Kobo
# scaffold/system field is harmless, nothing downstream reads them.
SURFACED_ROLE_TYPES = frozenset({
    "demographic", "consent", "system_uuid", "quant_indicator",
    "multiselect_parent", "multiselect_option", "qual_primary", "qual_supplementary",
})

RowMatchStatus = Literal["matched_unchanged", "matched_moved", "unmatched"]
ColMatchStatus = Literal["claimed", "unmatched_new"]

MAPPING_FIELDNAMES = [
    "raw_index", "raw_column_header", "role_type", "role_name",
    "group_name", "option_label", "applies_to", "notes",
]


@dataclass
class MappingRowStatus:
    raw_index: int
    header: str
    role_type: str
    role_name: str
    group_name: str
    option_label: str
    applies_to: str
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
    # EVERY mapping row's match result, regardless of role_type -- including
    # pii_drop/unused rows that row_statuses filters out of the human/LLM-
    # facing surface. A "matched_moved" row here needs no judgment call (it
    # was resolved unambiguously by unique header text); a reconciliation
    # apply step should silently auto-correct these positions for every row,
    # not just the surfaced ones -- otherwise an unsurfaced row like the
    # platform's _uuid column can silently end up with a stale raw_index
    # after some earlier, unrelated column shifts everything after it.
    all_rows: list[MappingRowStatus] = field(default_factory=list)

    @property
    def has_residual(self) -> bool:
        return bool(self.unmatched_rows()) or bool(self.unmatched_csv_columns())

    def unmatched_rows(self) -> list[MappingRowStatus]:
        return [r for r in self.row_statuses if r.status == "unmatched"]

    def unmatched_csv_columns(self) -> list[CsvColumnStatus]:
        return [c for c in self.csv_statuses if c.status == "unmatched_new"]

    def moved_rows(self) -> list[MappingRowStatus]:
        return [r for r in self.row_statuses if r.status == "matched_moved"]

    def all_moved_rows(self) -> list[MappingRowStatus]:
        """Every auto-resolvable moved row, including unsurfaced role types
        (pii_drop, unused) that never appear in row_statuses."""
        return [r for r in self.all_rows if r.status == "matched_moved"]


def read_csv_header_row(csv_path: Path, delimiter: str = ";") -> list[str]:
    """Literal header row via csv.reader -- NOT pandas.read_csv().columns,
    which auto-mangles duplicate column names (adds .1/.2/... suffixes) and
    would corrupt the exact-text comparison this module relies on."""
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        return next(csv.reader(f, delimiter=delimiter))


def load_mapping_table(path: Path) -> pd.DataFrame:
    """Read column_mapping.csv as a DataFrame for diffing/patching. Distinct
    from mapping.load_role_map(), which reads the same file into the
    dict-shaped RoleMap the pipeline actually runs against -- this one keeps
    every row as an editable record, for reconciliation to add/drop/rename."""
    df = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    df["raw_index"] = df["raw_index"].astype(int)
    return df


def diff_columns(
    mapping: pd.DataFrame,
    col_names: list[str],
    surfaced_role_types: frozenset[str] = SURFACED_ROLE_TYPES,
) -> MappingDiffResult:
    """Classify every mapping row and every live CSV column.

    col_names must be literal header text (see read_csv_header_row), not
    pandas-mangled column names.

    Pass 1 claims columns across EVERY mapping row (including pii_drop and
    unused), not just surfaced_role_types, so a scaffold/system column is
    never mistaken for a genuinely new one -- only rows in
    surfaced_role_types are returned in row_statuses, but every row's claim
    still occupies a live index and keeps that index off the
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
    all_rows = []
    for _, row in mapping.iterrows():
        raw_idx = int(row["raw_index"])
        status, matched_idx = all_row_results.get(raw_idx, ("unmatched", None))
        entry = MappingRowStatus(
            raw_index=raw_idx,
            header=row["raw_column_header"].strip(),
            role_type=row["role_type"],
            role_name=row.get("role_name", "").strip(),
            group_name=row.get("group_name", "").strip(),
            option_label=row.get("option_label", "").strip(),
            applies_to=row.get("applies_to", "").strip(),
            status=status,
            matched_csv_index=matched_idx,
        )
        all_rows.append(entry)
        if row["role_type"] in surfaced_role_types:
            row_statuses.append(entry)

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

    return MappingDiffResult(row_statuses=row_statuses, csv_statuses=csv_statuses, all_rows=all_rows)
