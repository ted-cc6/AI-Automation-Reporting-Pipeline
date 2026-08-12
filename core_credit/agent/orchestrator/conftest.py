"""Makes `orchestrator` importable as a top-level package, and puts agent/analysis on the
path too -- every node in this graph calls into code that lives there. Same pattern as
report_assembly/conftest.py and report_render/conftest.py.
"""

import sys
from pathlib import Path

AGENT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(AGENT_ROOT))  # so `import orchestrator` works
sys.path.insert(0, str(AGENT_ROOT / "analysis"))  # so `import schemas`, `import driver`, etc. work
