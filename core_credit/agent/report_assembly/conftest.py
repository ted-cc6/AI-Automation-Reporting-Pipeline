"""Makes `report_assembly` importable as a top-level package (same pattern as
dashboard_visuals/conftest.py), and also puts agent/analysis on the path -- report_assembly's
whole job is combining schemas and loader logic that live there, so its tests need both.
"""

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))  # so `import report_assembly` works
sys.path.insert(0, str(AGENT_ROOT / "analysis"))  # so `import schemas`, `import synthesis` work
