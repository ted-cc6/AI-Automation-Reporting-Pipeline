"""
Column-role mapping: raw CSV column position -> analytical role.

Previously this lived as dict literals directly in config.py. It now lives in
an external, diffable table (column_mapping.csv, one row per raw column)
loaded through load_role_map(). Two things this unlocks:

  1. A different CSV export (different column order, added/removed/renamed
     questions) can be reconciled against the pipeline's expectations by
     editing/patching a data file instead of Python source.
  2. Every raw column position is accounted for -- including ones the
     pipeline doesn't use (role_type=unused: Kobo section-intro text,
     platform metadata, an "If other, please specify" field that was never
     wired to a theming role) -- so a future reconciliation diff never
     mistakes an always-irrelevant column for a genuinely new one.

config.py still owns paths and statistical thresholds; this module owns
nothing but the shape of the mapping table and how to load/validate it.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

ROLE_TYPES = frozenset({
    "demographic", "consent", "system_uuid", "pii_drop",
    "quant_indicator", "multiselect_parent", "multiselect_option",
    "qual_primary", "qual_supplementary", "unused",
})


@dataclass(frozen=True)
class RoleMap:
    demographic_cols: dict[str, int]           # role name -> raw index, e.g. "sex" -> 103
    consent_col: int
    uuid_col: int
    pii_drop_cols: list[int]
    quant_indicators: dict[str, tuple[int, str | None]]        # role -> (raw index, applies_to)
    multiselect_groups: dict[str, tuple[int, dict[str, int]]]  # group -> (parent index, {option label: raw index})
    qual_primary: dict[str, int]
    qual_supplementary: dict[str, int]
    header_checks: dict[int, str]               # raw index -> full expected header text (every mapped, non-unused role)


def _read_rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_role_map(path: Path) -> RoleMap:
    """Build a RoleMap from a column_mapping.csv-shaped file. Raises on any
    row with an unrecognized role_type or a multiselect option whose group
    has no parent row, so a malformed/hand-edited mapping fails loudly here
    rather than as a confusing KeyError deep in ingest."""
    rows = _read_rows(path)

    demographic_cols: dict[str, int] = {}
    consent_col: int | None = None
    uuid_col: int | None = None
    pii_drop_cols: list[int] = []
    quant_indicators: dict[str, tuple[int, str | None]] = {}
    multiselect_parents: dict[str, int] = {}
    multiselect_options: dict[str, dict[str, int]] = {}
    qual_primary: dict[str, int] = {}
    qual_supplementary: dict[str, int] = {}
    header_checks: dict[int, str] = {}

    for row in rows:
        idx = int(row["raw_index"])
        role_type = row["role_type"].strip()
        role_name = row["role_name"].strip()
        group_name = row["group_name"].strip()
        option_label = row["option_label"].strip()
        applies_to = row["applies_to"].strip() or None
        header = row["raw_column_header"]

        if role_type not in ROLE_TYPES:
            raise ValueError(f"{path}: unknown role_type {role_type!r} at raw_index {idx}")
        if role_type != "unused":
            header_checks[idx] = header

        if role_type == "demographic":
            demographic_cols[role_name] = idx
        elif role_type == "consent":
            consent_col = idx
        elif role_type == "system_uuid":
            uuid_col = idx
        elif role_type == "pii_drop":
            pii_drop_cols.append(idx)
        elif role_type == "quant_indicator":
            quant_indicators[role_name] = (idx, applies_to)
        elif role_type == "multiselect_parent":
            multiselect_parents[group_name] = idx
        elif role_type == "multiselect_option":
            multiselect_options.setdefault(group_name, {})[option_label] = idx
        elif role_type == "qual_primary":
            qual_primary[role_name] = idx
        elif role_type == "qual_supplementary":
            qual_supplementary[role_name] = idx
        # "unused" rows carry no role data.

    if consent_col is None:
        raise ValueError(f"{path}: no row with role_type=consent")
    if uuid_col is None:
        raise ValueError(f"{path}: no row with role_type=system_uuid")

    missing_parents = set(multiselect_options) - set(multiselect_parents)
    if missing_parents:
        raise ValueError(f"{path}: multiselect group(s) with options but no multiselect_parent row: {missing_parents}")

    multiselect_groups = {
        group: (multiselect_parents[group], options)
        for group, options in multiselect_options.items()
    }

    return RoleMap(
        demographic_cols=demographic_cols,
        consent_col=consent_col,
        uuid_col=uuid_col,
        pii_drop_cols=sorted(pii_drop_cols),
        quant_indicators=quant_indicators,
        multiselect_groups=multiselect_groups,
        qual_primary=qual_primary,
        qual_supplementary=qual_supplementary,
        header_checks=header_checks,
    )


def validate_role_map_against_csv(role_map: RoleMap, csv_path: Path, delimiter: str = ";") -> None:
    """Raise a clear error if the live CSV header no longer matches the
    positions this role map assumes, naming exactly which column moved."""
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        header = next(csv.reader(f, delimiter=delimiter))

    problems = []
    for idx, expected in sorted(role_map.header_checks.items()):
        expected_prefix = expected.split("\n")[0][:80].strip()
        if idx >= len(header):
            problems.append(f"col {idx}: expected header starting '{expected_prefix}' but file only has {len(header)} columns")
            continue
        actual = header[idx].strip()
        if not actual.startswith(expected_prefix):
            problems.append(f"col {idx}: expected header starting '{expected_prefix}', found '{actual[:80]}'")
    if problems:
        nearby = "\n".join(f"  [{i}] {h[:80]}" for i, h in enumerate(header))
        raise ValueError(
            "Column map validation failed against the live CSV header:\n"
            + "\n".join(problems)
            + "\n\nFull header for reference:\n" + nearby
        )
