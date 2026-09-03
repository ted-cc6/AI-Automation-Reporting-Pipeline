"""Fixtures pointing at the real reference workbooks and survey export.

These tests deliberately use the production PPI_scorecards.xlsx /
PPI_lookups.xlsx / analysis-ready CSV rather than small synthetic copies --
they're the strongest fixtures available (two of the results, Ecuador and
Rwanda, are independently cross-checked by two humans in the project's
email thread), and they double as a drift check: if a future refresh of
those workbooks changes shape, these tests catch it.
"""

from pathlib import Path

import pandas as pd
import pytest

# ppi_module/tests -> ppi_module -> analysis -> agent -> core_credit (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[4]
SCORECARD_PATH = str(PROJECT_ROOT / "PPI_scorecards.xlsx")
LOOKUP_PATH = str(PROJECT_ROOT / "PPI_lookups.xlsx")


def _find_latest_analysis_ready_csv() -> str:
    # Not a hardcoded filename -- processed_data/ gets a fresh timestamped file every real
    # pipeline run (and nothing but a real run, since processed_data/ is pure output, never
    # hand-edited), so pinning one exact name breaks the moment someone reruns the pipeline or
    # clears the folder. Confirmed the hard way: a hardcoded name here broke every PPI test the
    # first time processed_data/ was cleared and regenerated with a new timestamp.
    candidates = sorted(PROJECT_ROOT.glob("processed_data/*_analysis_ready.csv"))
    assert candidates, f"no *_analysis_ready.csv found under {PROJECT_ROOT / 'processed_data'}"
    return str(candidates[-1])


@pytest.fixture(scope="session")
def scorecard_path() -> str:
    assert Path(SCORECARD_PATH).exists(), f"missing fixture workbook: {SCORECARD_PATH}"
    return SCORECARD_PATH


@pytest.fixture(scope="session")
def lookup_path() -> str:
    assert Path(LOOKUP_PATH).exists(), f"missing fixture workbook: {LOOKUP_PATH}"
    return LOOKUP_PATH


@pytest.fixture(scope="session")
def analysis_ready_df() -> pd.DataFrame:
    return pd.read_csv(_find_latest_analysis_ready_csv(), dtype=str, keep_default_na=False)
