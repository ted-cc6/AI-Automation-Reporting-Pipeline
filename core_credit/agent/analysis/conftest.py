"""Makes `schemas`, `metrics_engine`, and `ppi_module` importable as top-level
packages for every test under agent/analysis/, regardless of the directory
pytest is invoked from.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
