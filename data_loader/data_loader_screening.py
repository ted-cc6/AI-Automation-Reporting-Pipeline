"""
data_loader_screening.py — VisionFund Insurance Survey Data Loader
Step 3 of 5: Screen survey_clean.parquet for duplicate submissions and
test/QA entries before derived flags are computed, so every downstream
consumer (analysis engine, qualitative pipeline, generated report, and any
Power BI export built from the same parquet) counts the same clean N.

Runs after the transformer (typed columns needed for a reliable content
comparison) and before data_loader_derived.py (derived flags should never be
computed on rows we are about to discard).

Two independent screens, with different actions:
  1. Test/QA rows  -- client_id, enumerator, or branch matches a known test
     keyword. Removed entirely; never a real client.
  2. Duplicate submissions -- two rows identical on every substantive answer
     column (module-level KoBoToolbox identity/logistics columns excluded).
     One canonical copy is kept (earliest submission_time), the rest dropped.

A third check does NOT remove anything: rows that share a client_id but are
NOT exact-content duplicates (i.e. the same client_id was evidently reused
for what look like two different real interviews) are logged as a WARNING
for field-team reconciliation -- silently dropping one would delete a real
respondent's answers.

Usage:
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3
"""

import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

import pandas as pd

SCRIPT_DIR = Path(__file__).parent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# KoBoToolbox identity/logistics columns that legitimately differ between two
# copies of the same interview (server-assigned per-submission IDs, the local
# device clock, or which enumerator account happened to sync it) -- excluded
# from the "is this the same interview?" content comparison. Everything else
# (client_id, region, country, branch, insurance_type_raw, and every actual
# survey answer) must match exactly for two rows to count as duplicates.
CONTENT_EXCLUDE_COLS = frozenset({
    "kobotoolbox_id", "uuid", "submission_time", "kobotoolbox_index",
    "device_info", "interview_start", "interview_end", "enumerator",
})

# Fields checked for test/QA markers. Case-insensitive, word-boundary match
# (so e.g. "qa" doesn't false-positive inside "squat" or "quantity").
TEST_ID_COLS = ("client_id", "enumerator", "branch")
TEST_KEYWORDS = ("test", "demo", "training", "pilot", "qa")
_TEST_KEYWORD_PATTERN = r"\b(?:" + "|".join(TEST_KEYWORDS) + r")\b"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _hashable(val):
    """Convert one cell to a hashable, NaN-normalised value for equality
    comparison. Multi-select parent columns store Python lists (or PyArrow
    ListScalar on some read paths); both need converting to a hashable tuple.
    """
    if hasattr(val, "as_py"):
        val = val.as_py()
    if val is None:
        return None
    if isinstance(val, list):
        return tuple(_hashable(v) for v in val)
    if hasattr(val, "tolist"):   # numpy ndarray (multi-select list columns read back from parquet)
        return tuple(_hashable(v) for v in val.tolist())
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _content_key(row: pd.Series, content_cols: list[str]) -> tuple:
    return tuple(_hashable(row[c]) for c in content_cols)


def content_columns(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c not in CONTENT_EXCLUDE_COLS]


# ---------------------------------------------------------------------------
# Screen 1 — Test / QA rows
# ---------------------------------------------------------------------------

def find_test_rows(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: True where client_id, enumerator, or branch contains a
    known test/QA keyword as a whole word (case-insensitive)."""
    mask = pd.Series(False, index=df.index)
    for col in TEST_ID_COLS:
        if col not in df.columns:
            continue
        mask |= df[col].astype(str).str.contains(_TEST_KEYWORD_PATTERN, case=False, regex=True, na=False)
    return mask


# ---------------------------------------------------------------------------
# Screen 2 — Exact-content duplicate submissions
# ---------------------------------------------------------------------------

def find_duplicate_groups(df: pd.DataFrame, content_cols: "list[str] | None" = None) -> list[list]:
    """Return groups (each a list of index labels, len >= 2) of rows that are
    identical across every content column."""
    if content_cols is None:
        content_cols = content_columns(df)

    groups: dict[tuple, list] = {}
    for idx, row in df.iterrows():
        key = _content_key(row, content_cols)
        groups.setdefault(key, []).append(idx)

    return [idxs for idxs in groups.values() if len(idxs) > 1]


def choose_canonical_index(df: pd.DataFrame, group_idxs: list):
    """Pick the row to keep from a duplicate group: earliest submission_time,
    tie-broken by the lowest kobotoolbox_index. Falls back to the first index
    label if neither column is available."""
    sub = df.loc[group_idxs]

    if "submission_time" in sub.columns:
        parsed = pd.to_datetime(sub["submission_time"], errors="coerce")
        if parsed.notna().any():
            min_time = parsed.min()
            tied = [i for i in group_idxs if parsed[i] == min_time]
            if len(tied) == 1:
                return tied[0]
            group_idxs = tied

    if "kobotoolbox_index" in sub.columns:
        idx_vals = sub.loc[group_idxs, "kobotoolbox_index"]
        return idx_vals.idxmin()

    return group_idxs[0]


# ---------------------------------------------------------------------------
# Screen 3 (report-only) — client_id reused across non-identical content
# ---------------------------------------------------------------------------

def find_client_id_collisions(df: pd.DataFrame) -> dict:
    """After test rows and exact duplicates are removed, any client_id still
    appearing more than once means the same ID was used for what look like
    different interviews. Returns {client_id: [index labels]}. Never used to
    drop rows -- surfaced as a WARNING for field-team reconciliation only."""
    if "client_id" not in df.columns:
        return {}
    vc = df["client_id"].value_counts()
    dupe_ids = vc[vc > 1].index
    return {cid: list(df.index[df["client_id"] == cid]) for cid in dupe_ids}


# ---------------------------------------------------------------------------
# Screening result + report
# ---------------------------------------------------------------------------

class ScreeningResult:
    def __init__(self, df: pd.DataFrame, removed_test: list[dict],
                 removed_duplicates: list[dict], id_collisions: dict):
        self.df = df
        self.removed_test = removed_test
        self.removed_duplicates = removed_duplicates
        self.id_collisions = id_collisions


def _row_label(row: pd.Series) -> str:
    return (
        f"client_id={row.get('client_id')!r}, "
        f"kobotoolbox_id={row.get('kobotoolbox_id')!r}, "
        f"uuid={row.get('uuid')!r}"
    )


def screen(df: pd.DataFrame) -> ScreeningResult:
    working = df

    # 1. Test/QA rows -- removed entirely.
    test_mask = find_test_rows(working)
    removed_test = [
        {"client_id": r.get("client_id"), "kobotoolbox_id": r.get("kobotoolbox_id"),
         "uuid": r.get("uuid"), "reason": "test/QA keyword match"}
        for _, r in working[test_mask].iterrows()
    ]
    working = working[~test_mask]

    # 2. Exact-content duplicates -- keep one canonical copy per group.
    content_cols = content_columns(working)
    dup_groups = find_duplicate_groups(working, content_cols)
    drop_indices = []
    removed_duplicates = []
    for group_idxs in dup_groups:
        keep_idx = choose_canonical_index(working, group_idxs)
        kept_row = working.loc[keep_idx]
        for idx in group_idxs:
            if idx == keep_idx:
                continue
            drop_indices.append(idx)
            dropped_row = working.loc[idx]
            removed_duplicates.append({
                "client_id": dropped_row.get("client_id"),
                "kept_kobotoolbox_id": kept_row.get("kobotoolbox_id"),
                "dropped_kobotoolbox_id": dropped_row.get("kobotoolbox_id"),
                "kept_uuid": kept_row.get("uuid"),
                "dropped_uuid": dropped_row.get("uuid"),
            })
    working = working.drop(index=drop_indices)

    # 3. Client-ID reuse with differing content -- report only, never dropped.
    id_collisions = find_client_id_collisions(working)

    return ScreeningResult(working, removed_test, removed_duplicates, id_collisions)


def build_screening_report(result: ScreeningResult, n_start: int) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_test = len(result.removed_test)
    n_dup = len(result.removed_duplicates)
    n_end = len(result.df)

    lines: list[str] = [
        "# Duplicate & Test-Data Screening Report — VisionFund Insurance Survey",
        f"Generated: {ts}",
        "",
        "## Summary",
        f"- Rows in (post-transform): {n_start:,}",
        f"- Test/QA rows removed: {n_test}",
        f"- Duplicate-submission rows removed: {n_dup}",
        f"- Rows out (fed to derived flags + analysis): {n_end:,}",
        f"- Client-ID reuse warnings (NOT removed — needs field-team review): {len(result.id_collisions)}",
        "",
    ]

    lines.append("## Test/QA Rows Removed")
    if result.removed_test:
        lines.append("| client_id | kobotoolbox_id | uuid | reason |")
        lines.append("|---|---|---|---|")
        for r in result.removed_test:
            lines.append(f"| {r['client_id']} | {r['kobotoolbox_id']} | {r['uuid']} | {r['reason']} |")
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("## Duplicate Submissions Removed")
    lines.append(
        "_Two rows matched on every substantive answer column; one canonical "
        "copy (earliest submission_time) was kept._"
    )
    if result.removed_duplicates:
        lines.append("| client_id | kept kobotoolbox_id | dropped kobotoolbox_id | kept uuid | dropped uuid |")
        lines.append("|---|---|---|---|---|")
        for r in result.removed_duplicates:
            lines.append(
                f"| {r['client_id']} | {r['kept_kobotoolbox_id']} | {r['dropped_kobotoolbox_id']} "
                f"| {r['kept_uuid']} | {r['dropped_uuid']} |"
            )
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("## Client-ID Reuse Warnings (not removed)")
    lines.append(
        "_Same client_id appears more than once but the answers differ — likely "
        "two different respondents accidentally assigned the same ID. Rows are "
        "kept as-is; flag to the field team for reconciliation._"
    )
    if result.id_collisions:
        lines.append("| client_id | row count | kobotoolbox_ids |")
        lines.append("|---|---|---|")
        for cid, idxs in result.id_collisions.items():
            ids = ", ".join(str(result.df.loc[i, "kobotoolbox_id"]) for i in idxs)
            lines.append(f"| {cid} | {len(idxs)} | {ids} |")
    else:
        lines.append("None found.")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(output_dir: Path) -> None:
    parquet_path = output_dir / "survey_clean.parquet"
    report_path = output_dir / "screening_report.md"

    if not parquet_path.exists():
        log.error(f"Parquet not found: {parquet_path}")
        sys.exit(1)

    log.info(f"Loading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    n_start = len(df)
    log.info(f"  {n_start:,} rows, {len(df.columns)} columns")

    log.info("Screening for test/QA and duplicate submissions...")
    result = screen(df)

    report_md = build_screening_report(result, n_start)
    report_path.write_text(report_md, encoding="utf-8")

    out_df = result.df.reset_index(drop=True)
    log.info(f"Writing {parquet_path}")
    out_df.to_parquet(parquet_path, engine="pyarrow", index=False)

    print(
        f"\nScreening complete.\n"
        f"  Input rows              : {n_start:,}\n"
        f"  Test/QA rows removed    : {len(result.removed_test)}\n"
        f"  Duplicate rows removed  : {len(result.removed_duplicates)}\n"
        f"  Output rows             : {len(out_df):,}\n"
        f"  Client-ID reuse warnings: {len(result.id_collisions)} (not removed — see {report_path.name})\n"
        f"  Report                  : {report_path}"
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionFund Survey — Duplicate & Test-Data Screening")
    parser.add_argument(
        "--output-dir", type=Path, required=True,
        help="Run output directory containing survey_clean.parquet (modified in place)",
    )
    args = parser.parse_args()
    main(args.output_dir)
