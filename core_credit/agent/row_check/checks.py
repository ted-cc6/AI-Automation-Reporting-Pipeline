"""
Row-level QA checks for Row Checker.

Deliberately narrow scope -- only two things are checked:

1. Exact duplicate rows: two submissions whose substantive answers are
   byte-for-byte identical (system/audit columns -- timestamps, submission
   IDs -- are excluded from the comparison, since those are always unique
   even for a genuine double-submission). These are safe to resolve
   automatically: keeping both would double-count one respondent in every
   downstream statistic, and there's no real judgment involved since the
   content is identical.

2. Duplicate Global unique client id, and test-keyword matches in identity
   fields. Both are detected here but never resolved -- the caller decides
   what to do with them.

Nothing else about the data is inspected. Everything not covered by these
two checks passes through untouched.
"""

from __future__ import annotations

import pandas as pd


def find_exact_duplicates(
    df: pd.DataFrame, exclude_columns: list[str], uuid_col: str
) -> tuple[pd.Series, dict[str, str]]:
    """Detect rows whose substantive content exactly matches an earlier row.

    Returns (mask, duplicate_to_original):
      mask                 -- True for every row after the first occurrence
                               of a given content (in file order).
      duplicate_to_original -- maps each duplicate row's uuid to the uuid of
                               the first (kept) row with the same content.
    """
    compare_cols = [c for c in df.columns if c not in exclude_columns]
    # Sentinel fill so missing values compare equal to each other without
    # relying on float-NaN hashing/equality quirks.
    cmp_df = df[compare_cols].fillna("\x00NULL\x00")

    seen: dict[tuple, str] = {}
    is_duplicate = [False] * len(df)
    duplicate_to_original: dict[str, str] = {}
    uuids = df[uuid_col].tolist()

    for i, key in enumerate(cmp_df.itertuples(index=False, name=None)):
        if key in seen:
            is_duplicate[i] = True
            duplicate_to_original[uuids[i]] = seen[key]
        else:
            seen[key] = uuids[i]

    return pd.Series(is_duplicate, index=df.index), duplicate_to_original


def find_duplicate_client_ids(
    df: pd.DataFrame, client_id_col: str, uuid_col: str
) -> list[dict]:
    """Return one entry per client id that appears on more than one row.
    Blank/missing client ids are never grouped together as "duplicates"."""
    non_null = df[df[client_id_col].notna()]
    non_blank = non_null[non_null[client_id_col].astype(str).str.strip() != ""]

    groups = []
    for client_id, sub in non_blank.groupby(client_id_col):
        if len(sub) > 1:
            groups.append(
                {
                    "client_id": client_id,
                    "row_count": int(len(sub)),
                    "uuids": sub[uuid_col].tolist(),
                }
            )
    return groups


def find_keyword_matches(
    df: pd.DataFrame, columns: list[str], keywords: list[str], uuid_col: str
) -> list[dict]:
    """Return one entry per (row, column) whose value contains a configured
    test keyword (case-insensitive substring match). One hit per matching
    cell -- multiple keyword hits in the same cell aren't double-counted."""
    hits = []
    lowered_keywords = [k.lower() for k in keywords]
    for col in columns:
        if col not in df.columns:
            continue
        for idx, value in df[col].items():
            if pd.isna(value):
                continue
            value_lower = str(value).lower()
            for kw in lowered_keywords:
                if kw in value_lower:
                    hits.append(
                        {
                            "uuid": df.at[idx, uuid_col],
                            "column": col,
                            "value": value,
                            "matched_keyword": kw,
                        }
                    )
                    break
    return hits
