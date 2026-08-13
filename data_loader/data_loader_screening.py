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

A separate, independent optional step (5b) restricts the dataset to a named
REGION GROUP (see report_scopes.py, e.g. "lacro" or "africa") for a
region-scoped report -- orthogonal to dataset_schema (which schema/instrument
the raw CSV is parsed with) and to the single-country step above (which
narrows to one country, not a group). Only runs when report_scope is given.

Usage:
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3 --country Vietnam
    python data_loader/data_loader_screening.py --output-dir runs/2026_Q3 --report-scope lacro
"""

import json
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

# This script runs as a standalone subprocess (see run_pipeline.py's
# run_step()), not as part of the project's importable package -- sys.path[0]
# is data_loader/, not the project root, so report_scopes (a root-level
# module) needs an explicit path insert before it's importable. Matches
# run_analysis.py/data_loader_validator.py's PROJECT_ROOT injection for the
# same reason.
SCRIPT_DIR = Path(__file__).parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from report_scopes import REPORT_SCOPES  # noqa: E402

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
    # numpy ndarray (multi-select list columns read back from parquet) --
    # isinstance, not hasattr(val, "tolist"): a numpy SCALAR (e.g. np.bool_,
    # np.int64 -- what a boolean/int column's cells actually are when read
    # via .loc[] rather than iterrows()) also has .tolist(), but it returns
    # a bare Python scalar, not something iterable -- the old hasattr check
    # crashed on exactly that case the first time a caller other than
    # find_duplicate_groups()/iterrows() exercised this function.
    if isinstance(val, np.ndarray):
        return tuple(_hashable(v) for v in val.tolist())
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(val, np.generic):  # numpy scalar (np.bool_, np.int64, ...) -> plain Python
        return val.item()
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
# Screen — Report scope selection (for a region-group-scoped report, e.g.
# "lacro" or "africa" -- see report_scopes.py)
# ---------------------------------------------------------------------------
# Distinct from find_unselected_country_rows() above: that one narrows to a
# SINGLE country. This one narrows to every country within one or more
# Regions, for a report covering a whole region group. The two are
# independent filters (both may be combined in principle, though in
# practice a run picks one or the other) and are orthogonal to dataset_schema
# -- every current report_scope runs on the same "africa_vietnam" schema.

def find_unselected_region_rows(df: pd.DataFrame, regions: "list[str]") -> pd.Series:
    """Boolean mask: True where region does not case-insensitively match any of `regions`."""
    if "region" not in df.columns:
        return pd.Series(False, index=df.index)
    targets = {r.strip().lower() for r in regions}
    return ~df["region"].astype(str).str.strip().str.lower().isin(targets)


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
# Screen 4 (report-only) — shared KoBo _uuid, non-identical content
# ---------------------------------------------------------------------------
# A THIRD, independent signal from find_duplicate_groups() (exact-content
# match) and find_client_id_collisions() (same client_id, differing
# content): two rows sharing a device-assigned _uuid but carrying DIFFERENT
# client_ids and non-identical answers. Verified against the real 2026
# export: of 16 such pairs, zero are content-identical (find_duplicate_
# groups never sees them) and zero share a client_id (find_client_id_
# collisions never sees them either) -- only 1 of 32 rows overlaps with a
# client-ID-collision row at all. A shared Kobo instance _uuid with
# divergent content most likely means a form instance was cloned or
# re-edited on the device -- the likely failure mode is partial answer
# carryover from a previous client, not a whole duplicate record, which is
# why this is scored by similarity (how much of the content actually
# matches) rather than treated as a single yes/no flag. Never auto-dropped
# -- surfaced as a WARNING for field-team reconciliation only, same as
# client-ID collisions.

_UUID_PAIR_HIGH_SIMILARITY = 0.90   # >=90% identical fields: likely partial carryover
_UUID_PAIR_MEDIUM_SIMILARITY = 0.75  # 75-90%: notable overlap, still needs review
# below 0.75: informational -- shared uuid with mostly-different content is
# more likely a coincidental device/session reuse than a data-quality issue


def _uuid_pair_severity(similarity: float) -> str:
    if similarity >= _UUID_PAIR_HIGH_SIMILARITY:
        return "high"
    if similarity >= _UUID_PAIR_MEDIUM_SIMILARITY:
        return "medium"
    return "low"


def find_uuid_duplicate_pairs(df: pd.DataFrame, content_cols: "list[str] | None" = None) -> list[dict]:
    """Rows sharing a uuid but not already caught by exact-content dedup or
    client-ID collision detection. Returns a list of pair dicts with a
    similarity score (share of content_cols that match), sorted by
    similarity descending -- severity is driven by similarity, not treated
    uniformly, since a 96%-identical pair and a 69%-identical pair are very
    different findings."""
    if "uuid" not in df.columns:
        return []
    if content_cols is None:
        content_cols = content_columns(df)

    pairs = []
    vc = df["uuid"].value_counts()
    for u in vc[vc > 1].index:
        idxs = list(df.index[df["uuid"] == u])
        for i in range(len(idxs)):
            for j in range(i + 1, len(idxs)):
                r1, r2 = df.loc[idxs[i]], df.loc[idxs[j]]
                n_same = sum(1 for c in content_cols if _hashable(r1[c]) == _hashable(r2[c]))
                n_total = len(content_cols)
                similarity = (n_same / n_total) if n_total > 0 else 0.0
                pairs.append({
                    "uuid": u,
                    "client_id_a": r1.get("client_id"), "client_id_b": r2.get("client_id"),
                    "kobotoolbox_id_a": r1.get("kobotoolbox_id"), "kobotoolbox_id_b": r2.get("kobotoolbox_id"),
                    "country": r1.get("country"),
                    "similarity": similarity,
                    "n_fields_differ": n_total - n_same,
                    "n_fields_total": n_total,
                    "severity": _uuid_pair_severity(similarity),
                })
    pairs.sort(key=lambda p: -p["similarity"])
    return pairs


# ---------------------------------------------------------------------------
# Screen 5 (report-only) — interview-duration outliers, derived per run
# ---------------------------------------------------------------------------
# Data-quality flags (see data_quality_flags.py) need to be derivable, not
# only hand-typed -- a flag that only exists because someone remembered to
# write it down will not exist next wave. This computes, for the CURRENT
# scoped run, which countries have a share of unusually fast interviews
# elevated relative to the run's own median (not a fixed absolute minute
# count, which wouldn't generalise across waves/instruments), plus whether
# those fast interviews concentrate on one enumerator -- a single
# enumerator's outsized share is a much stronger signal than a spread-out
# pattern, which could just mean a genuinely quick population/instrument.

_DURATION_OUTLIER_THRESHOLD_FRACTION = 0.4   # flag interviews under 40% of the scope median
_DURATION_OUTLIER_COUNTRY_MULTIPLIER = 2.0   # a country's own outlier share must be >= 2x the scope-wide rate to surface
_DURATION_OUTLIER_MIN_N = 30                 # ignore countries too small to read a share from
_DURATION_OUTLIER_ENUMERATOR_CONCENTRATION = 0.5  # >=50% of a country's outliers from one enumerator = "concentrated"


def find_duration_outliers(df: pd.DataFrame) -> list[dict]:
    """Countries whose share of unusually-fast interviews is elevated
    relative to the run as a whole, with enumerator concentration among the
    flagged rows. Never drops anything -- report-only, same as the other
    screens in this section. See data_quality_flags.py for how a
    "concentrated" finding here becomes an actual report footnote."""
    required = {"interview_start", "interview_end", "country"}
    if not required.issubset(df.columns):
        return []

    start = pd.to_datetime(df["interview_start"], utc=True, errors="coerce")
    end = pd.to_datetime(df["interview_end"], utc=True, errors="coerce")
    duration_min = (end - start).dt.total_seconds() / 60
    valid = duration_min.notna()
    if valid.sum() == 0:
        return []

    scope_median = duration_min[valid].median()
    if not scope_median or scope_median <= 0:
        return []
    cutoff = scope_median * _DURATION_OUTLIER_THRESHOLD_FRACTION
    is_outlier = valid & (duration_min < cutoff)
    overall_share = is_outlier[valid].mean()

    findings = []
    for country, group_index in df.groupby("country").groups.items():
        mask = df.index.isin(group_index)
        n_total = int((mask & valid).sum())
        if n_total < _DURATION_OUTLIER_MIN_N:
            continue
        n_outliers = int((mask & is_outlier).sum())
        if n_outliers == 0:
            continue
        share = n_outliers / n_total
        if share < overall_share * _DURATION_OUTLIER_COUNTRY_MULTIPLIER:
            continue  # not elevated relative to the run as a whole

        outlier_rows = df[mask & is_outlier]
        if "enumerator" in df.columns:
            enum_counts = outlier_rows["enumerator"].value_counts()
        else:
            enum_counts = pd.Series(dtype=int)
        top_enumerator = enum_counts.index[0] if len(enum_counts) else None
        top_enumerator_n = int(enum_counts.iloc[0]) if len(enum_counts) else 0
        top_enumerator_share = (top_enumerator_n / n_outliers) if n_outliers else 0.0

        findings.append({
            "country": country,
            "n_total": n_total,
            "n_outliers": n_outliers,
            "outlier_share": share,
            "scope_median_minutes": round(float(scope_median), 1),
            "threshold_minutes": round(float(cutoff), 1),
            "overall_scope_outlier_share": round(float(overall_share), 3),
            "top_enumerator": top_enumerator,
            "top_enumerator_n": top_enumerator_n,
            "top_enumerator_share_of_outliers": round(top_enumerator_share, 3),
            "concentrated": top_enumerator_share >= _DURATION_OUTLIER_ENUMERATOR_CONCENTRATION,
        })

    findings.sort(key=lambda f: -f["outlier_share"])
    return findings


# ---------------------------------------------------------------------------
# Screening result + report
# ---------------------------------------------------------------------------

class ScreeningResult:
    def __init__(self, df: pd.DataFrame, removed_test: list[dict],
                 removed_duplicates: list[dict], id_collisions: dict,
                 removed_non_consenting: list[dict], removed_out_of_scope: list[dict],
                 removed_unselected_country: "list[dict] | None" = None,
                 removed_unselected_region: "list[dict] | None" = None,
                 uuid_duplicate_pairs: "list[dict] | None" = None,
                 duration_outliers: "list[dict] | None" = None):
        self.df = df
        self.removed_test = removed_test
        self.removed_duplicates = removed_duplicates
        self.id_collisions = id_collisions
        self.removed_non_consenting = removed_non_consenting
        self.removed_out_of_scope = removed_out_of_scope
        self.removed_unselected_country = removed_unselected_country or []
        self.removed_unselected_region = removed_unselected_region or []
        self.uuid_duplicate_pairs = uuid_duplicate_pairs or []
        self.duration_outliers = duration_outliers or []


def _row_label(row: pd.Series) -> str:
    return (
        f"client_id={row.get('client_id')!r}, "
        f"kobotoolbox_id={row.get('kobotoolbox_id')!r}, "
        f"uuid={row.get('uuid')!r}"
    )


def screen(df: pd.DataFrame, target_country: "str | None" = None,
           dataset_schema: str = DEFAULT_DATASET_SCHEMA,
           report_scope: "str | None" = None) -> ScreeningResult:
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

    # 5b. Report-scope selection -- only when this run is scoped to a
    # named region group (e.g. "lacro", "africa" -- see report_scopes.py).
    # Independent of step 5 above (single-country scoping); both may in
    # principle run in the same call, though normal usage picks one.
    removed_unselected_region = []
    if report_scope:
        regions = REPORT_SCOPES[report_scope]["regions"]
        region_mask = find_unselected_region_rows(working, regions)
        removed_unselected_region = [
            {"client_id": r.get("client_id"), "kobotoolbox_id": r.get("kobotoolbox_id"),
             "uuid": r.get("uuid"), "region": r.get("region"), "country": r.get("country"),
             "reason": f"report scoped to {report_scope!r} ({', '.join(regions)})"}
            for _, r in working[region_mask].iterrows()
        ]
        working = working[~region_mask]

    # 6. Client-ID reuse with differing content -- report only, never dropped.
    id_collisions = find_client_id_collisions(working)

    # 7. Shared uuid, differing content -- report only, never dropped.
    uuid_duplicate_pairs = find_uuid_duplicate_pairs(working)

    # 8. Interview-duration outliers -- report only, never dropped.
    duration_outliers = find_duration_outliers(working)

    return ScreeningResult(
        working, removed_test, removed_duplicates, id_collisions,
        removed_non_consenting, removed_out_of_scope, removed_unselected_country,
        removed_unselected_region, uuid_duplicate_pairs, duration_outliers,
    )


def build_screening_report(result: ScreeningResult, n_start: int,
                            target_country: "str | None" = None,
                            dataset_schema: str = DEFAULT_DATASET_SCHEMA,
                            report_scope: "str | None" = None) -> str:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    n_test = len(result.removed_test)
    n_dup = len(result.removed_duplicates)
    n_non_consenting = len(result.removed_non_consenting)
    n_out_of_scope = len(result.removed_out_of_scope)
    n_unselected = len(result.removed_unselected_country)
    n_unselected_region = len(result.removed_unselected_region)
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
    if report_scope:
        lines.append(f"- Rows outside report scope ({report_scope!r}) removed: {n_unselected_region}")
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

    if report_scope:
        regions = REPORT_SCOPES[report_scope]["regions"]
        lines.append(f"## Report-Scope Rows Removed (report scoped to {report_scope!r})")
        lines.append(
            f"_This run was scoped to region(s) {', '.join(regions)}; every "
            "respondent outside those regions (including other in-scope study "
            "countries) was removed here._"
        )
        if result.removed_unselected_region:
            lines.append("| client_id | kobotoolbox_id | uuid | region | country | reason |")
            lines.append("|---|---|---|---|---|---|")
            for r in result.removed_unselected_region:
                lines.append(
                    f"| {r['client_id']} | {r['kobotoolbox_id']} | {r['uuid']} | "
                    f"{r['region']} | {r['country']} | {r['reason']} |"
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

    lines.append("## Shared-uuid Pairs (not removed)")
    lines.append(
        "_Two rows share a KoBo _uuid but are NOT content-identical (already caught above) "
        "and do NOT share a client_id (a different signal from the client-ID reuse table "
        "above) -- most likely a form instance cloned or re-edited on the device, with "
        "partial answer carryover from a previous client. Rows are kept as-is; flag to the "
        "field team for reconciliation. Sorted by similarity -- a near-100% match is a much "
        "stronger signal than a low one._"
    )
    if result.uuid_duplicate_pairs:
        lines.append("| uuid | client_id A | client_id B | country | similarity | fields differing | severity |")
        lines.append("|---|---|---|---|---|---|---|")
        for p in result.uuid_duplicate_pairs:
            lines.append(
                f"| {p['uuid']} | {p['client_id_a']} | {p['client_id_b']} | {p['country']} "
                f"| {p['similarity']:.1%} | {p['n_fields_differ']} of {p['n_fields_total']} | {p['severity']} |"
            )
    else:
        lines.append("None found.")
    lines.append("")

    lines.append("## Interview-Duration Outliers (not removed)")
    lines.append(
        "_Countries whose share of unusually fast interviews (below "
        f"{_DURATION_OUTLIER_THRESHOLD_FRACTION:.0%} of this run's own median duration) is "
        "elevated relative to the run as a whole, with enumerator concentration among the "
        "flagged rows. Not evidence the records are invalid -- a data quality flag for human "
        "review, never auto-dropped or auto-excluded here (see data_quality_flags.py for how "
        "a concentrated finding becomes a report footnote)._"
    )
    if result.duration_outliers:
        lines.append("| country | outliers | share | scope median (min) | threshold (min) | top enumerator | enumerator share | concentrated |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for f in result.duration_outliers:
            lines.append(
                f"| {f['country']} | {f['n_outliers']} of {f['n_total']} | {f['outlier_share']:.1%} "
                f"| {f['scope_median_minutes']} | {f['threshold_minutes']} | {f['top_enumerator']} "
                f"| {f['top_enumerator_share_of_outliers']:.1%} | {'yes' if f['concentrated'] else 'no'} |"
            )
    else:
        lines.append("None found.")
    lines.append("")

    return "\n".join(lines)


def build_screening_summary(result: ScreeningResult, n_start: int,
                             target_country: "str | None" = None,
                             report_scope: "str | None" = None) -> dict:
    """Compact, structured exclusion summary -- written alongside the full
    markdown report as screening_summary.json. Read by
    analysis_engine/sections/about_survey.py so the generated .docx can
    state exclusion counts and the dedup rule in a short "Data Notes"
    section, instead of exclusions only ever existing in a side diagnostic
    file nobody reading the report sees (see project_region_scoping memory's
    Requirement 6 note: this was never a correctness bug, but the report
    stating nothing about it is what made it look like one).
    """
    return {
        "n_start": n_start,
        "n_end": len(result.df),
        "target_country": target_country,
        "report_scope": report_scope,
        "removed": {
            "test_qa": len(result.removed_test),
            "duplicate_submission": len(result.removed_duplicates),
            "non_consenting": len(result.removed_non_consenting),
            "out_of_scope_country": len(result.removed_out_of_scope),
            "unselected_country": len(result.removed_unselected_country),
            "unselected_region": len(result.removed_unselected_region),
        },
        "client_id_reuse_warnings": len(result.id_collisions),
        "uuid_duplicate_pairs": result.uuid_duplicate_pairs,
        "duration_outliers": result.duration_outliers,
        "rules": {
            "duplicate_submission": (
                "Two rows identical on every substantive answer column (KoBoToolbox "
                "identity/logistics columns excluded) are treated as one interview "
                "submitted twice; the earliest-submitted copy is kept, the rest dropped."
            ),
            "non_consenting": "Respondent declined the opening consent question; removed entirely.",
            "client_id_reuse_not_dropped": (
                "A client_id appearing more than once with DIFFERENT answers is not a "
                "duplicate submission (content differs) -- both rows are kept and logged "
                "as a warning for field-team reconciliation, never auto-dropped."
            ),
            "uuid_duplicate_pairs_not_dropped": (
                "Two rows sharing a KoBo _uuid but neither content-identical nor sharing "
                "a client_id are kept as-is and logged with a similarity score, never "
                "auto-dropped -- likely a cloned/re-edited device form instance, not "
                "necessarily a duplicate respondent."
            ),
            "duration_outliers_not_dropped": (
                "Countries with an elevated share of unusually fast interviews are "
                "logged as a data-quality flag, never auto-dropped or auto-excluded -- "
                "short duration alone is not evidence the records are invalid."
            ),
        },
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(output_dir: Path, target_country: "str | None" = None,
         dataset_schema: str = DEFAULT_DATASET_SCHEMA,
         report_scope: "str | None" = None) -> None:
    parquet_path = output_dir / "survey_clean.parquet"
    report_path = output_dir / "screening_report.md"
    summary_path = output_dir / "screening_summary.json"

    if dataset_schema not in DATASET_SCHEMAS:
        log.error(f"Unknown dataset_schema {dataset_schema!r} — expected one of {sorted(DATASET_SCHEMAS)}")
        sys.exit(1)

    if report_scope and report_scope not in REPORT_SCOPES:
        log.error(f"Unknown report_scope {report_scope!r} — expected one of {sorted(REPORT_SCOPES)}")
        sys.exit(1)

    if not parquet_path.exists():
        log.error(f"Parquet not found: {parquet_path}")
        sys.exit(1)

    log.info(f"Loading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    n_start = len(df)
    log.info(f"  {n_start:,} rows, {len(df.columns)} columns")

    scope_desc = f", report_scope={report_scope!r}" if report_scope else ""
    if target_country:
        log.info(
            f"Screening for test/QA, duplicate submissions, and scoping to "
            f"country={target_country!r} (dataset_schema={dataset_schema!r}{scope_desc})..."
        )
    else:
        log.info(f"Screening for test/QA and duplicate submissions (dataset_schema={dataset_schema!r}{scope_desc})...")
    result = screen(df, target_country=target_country, dataset_schema=dataset_schema, report_scope=report_scope)

    report_md = build_screening_report(result, n_start, target_country=target_country,
                                        dataset_schema=dataset_schema, report_scope=report_scope)
    report_path.write_text(report_md, encoding="utf-8")

    summary = build_screening_summary(result, n_start, target_country=target_country, report_scope=report_scope)
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    out_df = result.df.reset_index(drop=True)

    if target_country and len(out_df) == 0:
        log.error(
            f"No rows remain for country={target_country!r} after screening — "
            "this country isn't present in the uploaded dataset (or every "
            f"matching row was already removed as test/duplicate/non-consenting). "
            f"See {report_path} for details."
        )
        sys.exit(1)

    if report_scope and len(out_df) == 0:
        log.error(
            f"No rows remain for report_scope={report_scope!r} after screening — "
            f"see {report_path} for details."
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
        + (f"  Outside report scope        : {len(result.removed_unselected_region)}\n" if report_scope else "")
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
    parser.add_argument(
        "--report-scope", type=str, default=None,
        choices=sorted(REPORT_SCOPES), metavar="SCOPE",
        help="If given, scope this run to a named region group (see report_scopes.py) "
             "instead of the full multi-region portfolio.",
    )
    args = parser.parse_args()
    main(args.output_dir, target_country=args.country, dataset_schema=args.dataset_schema,
         report_scope=args.report_scope)
