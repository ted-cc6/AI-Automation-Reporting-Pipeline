"""Fixture pointing at the real External Benchmarks.xlsx, same approach as ppi_module's tests:
the real file is the strongest available fixture, and doubles as a drift check.
"""

from pathlib import Path

import pytest

# benchmark_module/tests -> benchmark_module -> analysis -> agent -> core_peoject (project root)
PROJECT_ROOT = Path(__file__).resolve().parents[4]
BENCHMARKS_PATH = str(PROJECT_ROOT / "External Benchmarks.xlsx")


@pytest.fixture(scope="session")
def benchmarks_path() -> str:
    assert Path(BENCHMARKS_PATH).exists(), f"missing fixture workbook: {BENCHMARKS_PATH}"
    return BENCHMARKS_PATH
