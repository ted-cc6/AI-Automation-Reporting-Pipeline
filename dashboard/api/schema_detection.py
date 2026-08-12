"""dashboard/api/schema_detection.py

Detects which source-survey schema an uploaded CSV matches, by diffing its
header row against each known schema's canonical column_mapping.csv (the
same deterministic diff dashboard/api/reconciliation.py's LLM-assisted
reconciliation flow already uses for finding *residual* drift within one
schema) and picking whichever has the higher matched-row ratio.

This does not decide whether an upload needs reconciliation -- it decides
which of the pipeline's known schemas (and therefore which canonical
mapping / reconcile endpoint / SCOPE_COUNTRIES allow-list / etc.) an upload
belongs to in the first place. A genuinely new, third schema -- or a badly
corrupted file -- should come back "unknown" rather than be silently forced
onto whichever known schema happens to match best.
"""
from pathlib import Path

from data_loader.data_loader_transformer import load_mapping
from data_loader.mapping_diff import diff_columns, read_csv_header_row

from dashboard.api.config import PROJECT_ROOT

DATA_LOADER_DIR = PROJECT_ROOT / "data_loader"
DATA_LOADER_LARCO_DIR = PROJECT_ROOT / "data_loader_larco"

# Keyed by the same dataset_schema strings used throughout the pipeline
# (data_loader_screening.py's SCOPE_COUNTRIES, run_pipeline.py's
# DATASET_SCHEMA_PATHS, run_metadata.yaml's "dataset_schema" field).
SCHEMA_MAPPING_PATHS = {
    "africa_vietnam": DATA_LOADER_DIR / "column_mapping.csv",
    "larco": DATA_LOADER_LARCO_DIR / "column_mapping.csv",
}

# Below this matched-row ratio against the BEST-matching known schema,
# report "unknown" instead of forcing a bad match -- a real third schema
# (or a corrupted/unrelated CSV) should never be silently mis-detected as
# whichever of the two current schemas happens to share the most
# boilerplate (Device Info/start/end/Region/Country columns are identical
# text in both, so even a totally unrelated CSV can clear a low bar).
UNKNOWN_THRESHOLD = 0.5


def _match_ratio(mapping_path: Path, col_names: list[str]) -> float:
    mapping = load_mapping(mapping_path)
    diff = diff_columns(mapping, col_names)
    total = len(diff.row_statuses)
    if total == 0:
        return 0.0
    matched = total - len(diff.unmatched_rows())
    return matched / total


def schema_match_ratios(csv_path: Path) -> dict[str, float]:
    """Matched-row ratio against every known schema's canonical mapping,
    keyed by dataset_schema string -- exposed separately from
    detect_dataset_schema() so callers needing the full breakdown (e.g. a
    diagnostic endpoint) don't have to recompute it."""
    col_names = read_csv_header_row(csv_path)
    return {schema: _match_ratio(path, col_names) for schema, path in SCHEMA_MAPPING_PATHS.items()}


def detect_dataset_schema(csv_path: Path) -> str:
    """Return the best-matching dataset_schema string, or 'unknown' if even
    the best match falls below UNKNOWN_THRESHOLD."""
    ratios = schema_match_ratios(csv_path)
    best_schema, best_ratio = max(ratios.items(), key=lambda kv: kv[1])
    return best_schema if best_ratio >= UNKNOWN_THRESHOLD else "unknown"
