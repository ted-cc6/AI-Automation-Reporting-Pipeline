"""
Central configuration for the GEDSI Insurance Survey pipeline.

Column roles (which raw CSV position means what) used to be dict literals
here, keyed by POSITION rather than name because the raw CSV export repeats
the header "If other, please specify:" for many different questions
(Kobo/ODK style export) -- names alone can't disambiguate them. That mapping
now lives in column_mapping.csv (one row per raw column) and is loaded via
mapping.load_role_map(), so a re-exported survey with moved/renamed/added
columns can be reconciled by editing a data file instead of this module. See
mapping.py for the loader and mapping.validate_role_map_against_csv() for
the "does the live CSV still match this mapping" check that replaces the old
validate_column_map().

This module keeps paths and statistical thresholds, plus DEFAULT_ROLE_MAP,
the mapping every stage falls back to when no role_map is passed explicitly
(the CLI/RUNBOOK usage path).
"""
from __future__ import annotations

from pathlib import Path

from gedsi_pipeline import mapping

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CSV_PATH = PROJECT_ROOT / (
    "Insurance_Survey_2026_-_LIVE_-_latest_version_-_English_en_-_2026-06-25-16-53-33.csv"
)
WORK_DIR = PROJECT_ROOT / "work"
CACHE_DIR = PROJECT_ROOT / "cache"
OUTPUT_DIR = PROJECT_ROOT / "outputs"
RESPONSE_FRAME_PATH = WORK_DIR / "response_frame.parquet"

COLUMN_MAPPING_PATH = Path(__file__).resolve().parent / "column_mapping.csv"
DEFAULT_ROLE_MAP = mapping.load_role_map(COLUMN_MAPPING_PATH)

# ---------------------------------------------------------------------------
# LLM
# ---------------------------------------------------------------------------
CLAUDE_MODEL = "claude-opus-5"

# ---------------------------------------------------------------------------
# Statistical thresholds
# ---------------------------------------------------------------------------
MIN_N = 30          # cells below this are suppressed in reporting (raw n still shown)
FDR_ALPHA = 0.05    # Benjamini-Hochberg false discovery rate

SUPPLEMENTARY_MIN_N = 15  # below this, keep as raw quotes only, don't run codebook induction
