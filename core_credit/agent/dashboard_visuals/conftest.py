"""Makes `dashboard_visuals` importable as a top-level package for its own tests, regardless
of the directory pytest is invoked from -- same pattern as agent/analysis/conftest.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
