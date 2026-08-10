"""
gedsi_pipeline/screening.py

Duplicate/test-row/out-of-scope-country screening, aligned with the
Cupboard Week pipeline's data_loader_screening.py so both reports describe
the same population from the same raw export -- same screens, same
SCOPE_COUNTRIES, same test keywords, applied in the same order (test/QA ->
duplicates -> consent -> out-of-scope-country). See that module's docstring
for the full rationale; this is a from-scratch reimplementation against
GENDSI's own per-respondent frame (not a port of the code, since GENDSI's
column shapes -- friendly role names, not KoBoToolbox raw fields -- differ),
verified to exclude the exact same respondents (by _uuid) on the 2026-06-25
export: 2 test/QA + 4 duplicates + 7 non-consenting + 7 out-of-scope-country
= 20 removed, 2111 -> 2091.

Runs on the full per-respondent frame built by ingest.py, INCLUDING
non-consenting rows and the transient _client_id_raw/_enumerator_raw columns
-- duplicate detection must see the real consent answer and client ID to
match Cupboard Week's definition of "the same interview twice", and those
two transient columns are dropped again before the frame is returned, so
neither ever reaches response_frame.parquet or any report output.
"""
from __future__ import annotations

import pandas as pd

# Identical to data_loader/data_loader_screening.py's SCOPE_COUNTRIES --
# the study's 7 African country programmes + Vietnam.
SCOPE_COUNTRIES = frozenset({
    "Rwanda", "Ghana", "Zambia", "Malawi", "Uganda", "Tanzania", "Kenya",
    "Vietnam",
})

TEST_KEYWORDS = ("test", "demo", "training", "pilot", "qa")
_TEST_KEYWORD_PATTERN = r"\b(?:" + "|".join(TEST_KEYWORDS) + r")\b"

# Transient, screening-only columns: present on the frame screen() receives,
# never on the frame it returns, and excluded from the duplicate-content
# comparison the same way Cupboard Week excludes enumerator/device_info/
# timestamps -- a different enumerator submitting the identical interview
# shouldn't stop it from being flagged as a duplicate.
TRANSIENT_COLS = ("_client_id_raw", "_enumerator_raw")
_DUPLICATE_EXCLUDE_COLS = frozenset({"response_id", "_enumerator_raw"})


def _hashable(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def find_test_rows(df: pd.DataFrame) -> pd.Series:
    """True where client_id or enumerator contains a test/QA keyword as a
    whole word (case-insensitive). Branch isn't checked -- GENDSI's branch
    values are short codes (see profiling), not the free-text field
    Cupboard Week's branch column holds, so a keyword match there would be
    accidental rather than meaningful."""
    mask = pd.Series(False, index=df.index)
    for col in ("_client_id_raw", "_enumerator_raw"):
        if col in df.columns:
            mask |= df[col].astype(str).str.contains(_TEST_KEYWORD_PATTERN, case=False, regex=True, na=False)
    return mask


def find_duplicate_indices(df: pd.DataFrame) -> list[int]:
    """Indices to drop: for every group of rows identical across every
    content column (all columns except response_id and enumerator), keep
    the first occurrence (earliest raw row order) and mark the rest."""
    content_cols = [c for c in df.columns if c not in _DUPLICATE_EXCLUDE_COLS]
    groups: dict[tuple, list[int]] = {}
    for idx, row in df.iterrows():
        key = tuple(_hashable(row[c]) for c in content_cols)
        groups.setdefault(key, []).append(idx)

    drop: list[int] = []
    for idxs in groups.values():
        if len(idxs) > 1:
            drop.extend(sorted(idxs)[1:])  # keep the first, drop the rest
    return drop


def find_out_of_scope_country_rows(df: pd.DataFrame) -> pd.Series:
    if "country" not in df.columns:
        return pd.Series(False, index=df.index)
    return ~df["country"].isin(SCOPE_COUNTRIES)


def screen(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Applies all four screens in Cupboard Week's order and drops the
    transient screening-only columns before returning. Returns (screened_df,
    stats) where stats records how many rows each screen removed, for the
    report's Limitations & Methodology section."""
    working = df

    test_mask = find_test_rows(working)
    n_test = int(test_mask.sum())
    working = working[~test_mask]

    drop_idx = find_duplicate_indices(working)
    n_duplicates = len(drop_idx)
    working = working.drop(index=drop_idx)

    n_non_consenting = int((~working["_consent_ok"]).sum()) if "_consent_ok" in working.columns else 0
    if "_consent_ok" in working.columns:
        working = working[working["_consent_ok"]]

    scope_mask = find_out_of_scope_country_rows(working)
    n_out_of_scope = int(scope_mask.sum())
    working = working[~scope_mask]

    working = working.drop(columns=[c for c in TRANSIENT_COLS + ("_consent_ok",) if c in working.columns])
    working = working.reset_index(drop=True)

    stats = {
        "n_test_removed": n_test,
        "n_duplicates_removed": n_duplicates,
        "n_non_consenting_removed": n_non_consenting,
        "n_out_of_scope_removed": n_out_of_scope,
    }
    return working, stats
