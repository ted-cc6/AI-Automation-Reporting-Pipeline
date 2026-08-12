"""Makes `report_render` importable as a top-level package, and puts agent/analysis on the
path too -- this renderer's whole job is turning CoreCreditImpactReport (defined there) into a
.docx, so its tests need both. Same pattern as report_assembly/conftest.py.
"""

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))  # so `import report_render` works
sys.path.insert(0, str(AGENT_ROOT / "analysis"))  # so `import schemas`, `import synthesis` work
