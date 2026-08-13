"""
data_loader_screening.py — VisionFund Insurance Survey Data Loader
Step 3 of 5: Screen survey_clean.parquet for duplicate submissions, test/QA
entries, non-consenting respondents, and out-of-scope-country respondents
before derived flags are computed, so every downstream consumer (analysis
engine, qualitative pipeline, generated report, and any Power BI export built
from the same parquet) counts the same clean N.

Runs after the transformer (typed columns needed for a reliable content
comparison, and for q_survey_consent to exist as a real column) and before
data_loader_derived.py (derived flags should never be computed on rows we are
about to discard).

Four independent screens, with different actions:
  1. Test/QA rows  -- client_id, enumerator, or branch matches a known test
     keyword. Removed entirely; never a real client.
  2. Duplicate submissions -- two rows identical on every substantive answer
     column (module-level KoBoToolbox identity/logistics columns excluded).
     One canonical copy is kept (earliest submission_time), the rest dropped.
  3. Non-consenting respondents -- q_survey_consent == False (answered "b. No"
     to the opening consent question). Removed entirely.
  4. Out-of-scope-country respondents -- country not in SCOPE_COUNTRIES (the
     study's 7 African country programmes + Vietnam, plus -- as of the 2026
     wave, which folded LARCO into this same schema -- Ecuador, Mexico,
     Guatemala, Honduras, Bolivia, and Dominican Republic). Removed entirely.

A fifth check does NOT remove anything: rows that share a client_id but are
NOT exact-content duplicates (i.e. the same client_id was evidently reused
for what look like two different real interviews) are logged as a WARNING
for field-team reconciliation -- silently dropping one would delete a real
respondent's answers.

An optional sixth step -- distinct from screen 4 above -- restricts the
dataset to a single caller-selected country, for a country-scoped report
(e.g. "generate the Vietnam report" instead of the default multi-country
portfolio rollup). This only runs when a target_country is explicitly
passed in; it is not part of the always-on scope check.

Usage:
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3 --country Vietnam
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

# The study's in-scope country programmes -- an allow-list (not a deny-list
# of specific out-of-scope countries) so any unexpected/future stray value is
# also caught, not just the ones seen in past quarters. Update the relevant
# set if VisionFund's insurance survey expands to a new country programme
# within an existing schema (a genuinely new source schema needs its own new
# set here, not an addition to one of these two -- see DATASET_SCHEMAS).
#
# 2026-08-13: LARCO's countries were folded into the Africa/Vietnam (133-col)
# instrument for the 2026 wave -- the 2026 "LIVE" export includes Ecuador/
# Mexico/Guatemala/Honduras/Bolivia/Dominican Republic rows in this same
# schema, NOT the separate 209-col LARCO instrument. Without these six here,
# every LARCO-country respondent in a 2026 africa_vietnam-schema run would be
# silently dropped as "out of scope". SCOPE_COUNTRIES_LARCO below is
# unchanged and still describes the older, differently-worded 2025 LARCO
# instrument (data_loader_larco/) -- kept only to reprocess that 2025 export
# as a Part 10 trend-comparison baseline, not for 2026+ ingestion.
SCOPE_COUNTRIES_AFRICA_VIETNAM = frozenset({
    "Rwanda", "Ghana", "Zambia", "Malawi", "Uganda", "Tanzania", "Kenya",
    "Vietnam", "Ecuador", "Mexico", "Guatemala", "Honduras", "Bolivia",
    "Dominican Republic",
})
SCOPE_COUNTRIES_LARCO = frozenset({
    "Ecuador", "Mexico", "Guatemala", "Honduras", "Bolivia",
})

# Keyed by the same dataset_schema strings used throughout the pipeline
# (data_loader_derived.py, run_pipeline.py, dashboard/api/pipeline_runner.py,
# run_metadata.yaml's "dataset_schema" field).
DATASET_SCHEMAS = {
    "africa_vietnam": SCOPE_COUNTRIES_AFRICA_VIETNAM,
    "larco": SCOPE_COUNTRIES_LARCO,
}
DEFAULT_DATASET_SCHEMA = "africa_vietnam"


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
# Screen — Non-consenting respondents
# ---------------------------------------------------------------------------

def find_non_consenting_rows(df: pd.DataFrame) -> pd.Series:
    """Boolean mask: True where the respondent answered "b. No" to the
    opening consent question (q_survey_consent == False).

    q_survey_consent is a nullable BooleanDtype column, so `== False` can
    itself produce NA (unknown) rather than True/False wherever the source
    value didn't decode -- e.g. an unmapped/unexpected raw answer. NA must
    never leak out of this function as a bare value: `df[mask]` treats an
    all-NA mask as "select nothing," but `~mask` on that same all-NA mask is
    ALSO all-NA (NOT of "unknown" is still "unknown"), which then makes
    `df[~mask]` in screen() ALSO select nothing -- silently emptying the
    entire dataset instead of just failing to flag the ambiguous rows. An
    unmapped/missing consent answer must default to "not flagged for
    removal" (never drop a respondent over ambiguous data), so any NA here
    is resolved to False before returning.
    """
    if "q_survey_consent" not in df.columns:
        return pd.Series(False, index=df.index)
    return (df["q_survey_consent"] == False).fillna(False)  # noqa: E712 (BooleanDtype requires `== False`, not `is False`)


# ---------------------------------------------------------------------------
# Screen — Out-of-scope-country respondents
# ---------------------------------------------------------------------------

def find_out_of_scope_country_rows(df: pd.DataFrame, scope_countries: frozenset) -> pd.Series:
    """Boolean mask: True where country is not one of scope_countries."""
    if "country" not in df.columns:
        return pd.Series(False, index=df.index)
    return ~df["country"].isin(scope_countries)


# ---------------------------------------------------------------------------
# Screen — Country selection (for a single-country-scoped report)
# ---------------------------------------------------------------------------
# Distinct from find_out_of_scope_country_rows() above: that one enforces the
# study-wide allow-list regardless of what's being generated. This one is
# only used when the caller has asked for a report scoped to one specific
# country -- it drops every OTHER in-scope country too. Comparison is
# case-insensitive since country_configs/*.yaml identifiers are lowercase
# slugs (e.g. "vietnam") while the survey data's country column is the
# title-cased value KoBoToolbox recorded (e.g. "Vietnam").

def find_unselected_country_rows(df: pd.DataFrame, target_country: str) -> pd.Series:
    """Boolean mask: True where country does not case-insensitively match target_country."""
    if "country" not in df.columns:
        return pd.Series(False, index=df.index)
    target = target_country.strip().lower()
    return df["country"].astype(str).str.strip().str.lower() != target


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
                 removed_duplicates: list[dict], id_collisions: dict,
                 removed_non_consenting: list[dict], removed_out_of_scope: list[dict],
                 removed_unselected_country: "list[dict] | None" = None):
        self.df = df
        self.removed_test = removed_test
        self.removed_duplicates = removed_duplicates
        self.id_collisions = id_collisions
        self.removed_non_consenting = removed_non_consenting
        self.removed_out_of_scope = removed_out_of_scope
        self.removed_unselected_country = removed_unselected_country or []


def _row_label(row: pd.Series) -> str:
    return (
        f"client_id={row.get('client_id')!r}, "
        f"kobotoolbox_id={row.get('kobotoolbox_id')!r}, "
        f"uuid={row.get('uuid')!r}"
    )


def screen(df: pd.DataFrame, target_country: "str | None" = None,
           dataset_schema: str = DEFAULT_DATASET_SCHEMA) -> ScreeningResult:
    working = df
    scope_countries = DATASET_SCHEMAS[dataset_schema]

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

    # 3. Non-consenting respondents -- removed entirely.
    consent_mask = find_non_consenting_rows(working)
    removed_non_consenting = [
        {"client_id": r.get("client_id"), "kobotoolbox_id": r.get("kobotoolbox_id"),
         "uuid": r.get("uuid"), "reason": "declined consent (q_survey_consent = No)"}
        for _, r in working[consent_mask].iterrows()
    ]
    working = working[~consent_mask]

    # 4. Out-of-scope-country respondents -- removed entirely.
    scope_mask = find_out_of_scope_country_rows(working, scope_countries)
    removed_out_of_scope = [
        {"client_id": r.get("client_id"), "kobotoolbox_id": r.get("kobotoolbox_id"),
         "uuid": r.get("uuid"), "country": r.get("country"),
         "reason": "country outside study scope"}
        for _, r in working[scope_mask].iterrows()
    ]
    working = working[~scope_mask]

    # 5. Country selection -- only when this run is scoped to one country.
    removed_unselected_country = []
    if target_country:
        selection_mask = find_unselected_country_rows(working, target_country)
        removed_unselected_country = [
            {"client_id": r.get("client_id"), "kobotoolbox_id": r.get("kobotoolbox_id"),
             "uuid": r.get("uuid"), "country": r.get("country"),
             "reason": f"report scoped to {target_country!r}"}
            for _, r in working[selection_mask].iterrows()
        ]
        working = working[~selection_mask]

    # 6. Client-ID reuse with differing content -- report only, never dropped.
    id_collisions = find_client_id_collisions(working)

    return ScreeningResult(
        working, removed_test, removed_duplicates, id_collisions,
        removed_non_consenting, removed_out_of_scope, removed_unselected_country,
    )


def build_screening_report(result: ScreeningResult, n_start: int,
                            target_country: "str | None" = None,
                            dataset_schema: str = DEFAULT_DATASET_SCHEMA) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_test = len(result.removed_test)
    n_dup = len(result.removed_duplicates)
    n_non_consenting = len(result.removed_non_consenting)
    n_out_of_scope = len(result.removed_out_of_scope)
    n_unselected = len(result.removed_unselected_country)
    n_end = len(result.df)

    lines: list[str] = [
        "# Duplicate & Test-Data Screening Report — VisionFund Insurance Survey",
        f"Generated: {ts}",
        "",
        "## Summary",
        f"- Rows in (post-transform): {n_start:,}",
        f"- Test/QA rows removed: {n_test}",
        f"- Duplicate-submission rows removed: {n_dup}",
        f"- Non-consenting rows removed: {n_non_consenting}",
        f"- Out-of-scope-country rows removed: {n_out_of_scope}",
    ]
    if target_country:
        lines.append(f"- Rows outside the selected country ({target_country!r}) removed: {n_unselected}")
    lines += [
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

    lines.append("## Non-Consenting Rows Removed")
    lines.append(
        "_Respondent answered \"b. No, I do not agree\" to the opening consent "
        "question (q_survey_consent)._"
    )
    if result.removed_non_consenting:
        lines.append("| client_id | kobotoolbox_id | uuid | reason |")
        lines.append("|---|---|---|---|")
        for r in result.removed_non_consenting:
            lines.append(f"| {r['client_id']} | {r['kobotoolbox_id']} | {r['uuid']} | {r['reason']} |")
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("## Out-of-Scope-Country Rows Removed")
    lines.append(
        f"_Country is not one of the study's scope ({dataset_schema}): "
        f"{', '.join(sorted(DATASET_SCHEMAS[dataset_schema]))}._"
    )
    if result.removed_out_of_scope:
        lines.append("| client_id | kobotoolbox_id | uuid | country | reason |")
        lines.append("|---|---|---|---|---|")
        for r in result.removed_out_of_scope:
            lines.append(
                f"| {r['client_id']} | {r['kobotoolbox_id']} | {r['uuid']} | {r['country']} | {r['reason']} |"
            )
    else:
        lines.append("None found.")
    lines.append("")

    if target_country:
        lines.append(f"## Country-Selection Rows Removed (report scoped to {target_country!r})")
        lines.append(
            "_This run was scoped to a single country; every respondent from any "
            "other country (including other in-scope study countries) was removed here._"
        )
        if result.removed_unselected_country:
            lines.append("| client_id | kobotoolbox_id | uuid | country | reason |")
            lines.append("|---|---|---|---|---|")
            for r in result.removed_unselected_country:
                lines.append(
                    f"| {r['client_id']} | {r['kobotoolbox_id']} | {r['uuid']} | {r['country']} | {r['reason']} |"
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

def main(output_dir: Path, target_country: "str | None" = None,
         dataset_schema: str = DEFAULT_DATASET_SCHEMA) -> None:
    parquet_path = output_dir / "survey_clean.parquet"
    report_path = output_dir / "screening_report.md"

    if dataset_schema not in DATASET_SCHEMAS:
        log.error(f"Unknown dataset_schema {dataset_schema!r} — expected one of {sorted(DATASET_SCHEMAS)}")
        sys.exit(1)

    if not parquet_path.exists():
        log.error(f"Parquet not found: {parquet_path}")
        sys.exit(1)

    log.info(f"Loading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    n_start = len(df)
    log.info(f"  {n_start:,} rows, {len(df.columns)} columns")

    if target_country:
        log.info(
            f"Screening for test/QA, duplicate submissions, and scoping to "
            f"country={target_country!r} (dataset_schema={dataset_schema!r})..."
        )
    else:
        log.info(f"Screening for test/QA and duplicate submissions (dataset_schema={dataset_schema!r})...")
    result = screen(df, target_country=target_country, dataset_schema=dataset_schema)

    report_md = build_screening_report(result, n_start, target_country=target_country,
                                        dataset_schema=dataset_schema)
    report_path.write_text(report_md, encoding="utf-8")

    out_df = result.df.reset_index(drop=True)

    if target_country and len(out_df) == 0:
        log.error(
            f"No rows remain for country={target_country!r} after screening — "
            "this country isn't present in the uploaded dataset (or every "
            f"matching row was already removed as test/duplicate/non-consenting). "
            f"See {report_path} for details."
        )
        sys.exit(1)

    log.info(f"Writing {parquet_path}")
    out_df.to_parquet(parquet_path, engine="pyarrow", index=False)

    print(
        f"\nScreening complete.\n"
        f"  Input rows                  : {n_start:,}\n"
        f"  Test/QA rows removed        : {len(result.removed_test)}\n"
        f"  Duplicate rows removed      : {len(result.removed_duplicates)}\n"
        f"  Non-consenting rows removed : {len(result.removed_non_consenting)}\n"
        f"  Out-of-scope-country removed: {len(result.removed_out_of_scope)}\n"
        + (f"  Outside selected country    : {len(result.removed_unselected_country)}\n" if target_country else "")
        + f"  Output rows                 : {len(out_df):,}\n"
        f"  Client-ID reuse warnings    : {len(result.id_collisions)} (not removed — see {report_path.name})\n"
        f"  Report                      : {report_path}"
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
    parser.add_argument(
        "--country", type=str, default=None, metavar="COUNTRY",
        help="If given, scope this run to a single country (e.g. 'Vietnam') instead of "
             "the full multi-country portfolio. Case-insensitive match against the "
             "country column.",
    )
    parser.add_argument(
        "--dataset-schema", type=str, default=DEFAULT_DATASET_SCHEMA,
        choices=sorted(DATASET_SCHEMAS), metavar="SCHEMA",
        help=f"Which source-survey schema's country allow-list to screen against. "
             f"Default: {DEFAULT_DATASET_SCHEMA!r}.",
    )
    args = parser.parse_args()
    main(args.output_dir, target_country=args.country, dataset_schema=args.dataset_schema)
