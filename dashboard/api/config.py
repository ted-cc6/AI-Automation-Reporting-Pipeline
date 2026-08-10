"""dashboard/api/config.py -- shared paths for the dashboard backend."""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"
COUNTRY_CONFIGS_DIR = PROJECT_ROOT / "country_configs"
UPLOADS_DIR = Path(__file__).parent / "uploads"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

# GENDSI (the Gender Study pipeline) lives in its own sibling project folder
# with its own package namespace (gedsi_pipeline), not installed alongside
# this package -- add it to sys.path so `from gedsi_pipeline import ...`
# resolves the same way in dev and in the eventual single-container deploy
# (Phase 6 decides how GENDSI physically ships in the Docker image; this
# path just needs GENDSI/ to exist as a sibling of this PROJECT_ROOT).
GENDSI_ROOT = PROJECT_ROOT / "GENDSI"
if GENDSI_ROOT.is_dir() and str(GENDSI_ROOT) not in sys.path:
    sys.path.insert(0, str(GENDSI_ROOT))
