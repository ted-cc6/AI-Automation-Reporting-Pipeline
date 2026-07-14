"""dashboard/api/config.py -- shared paths for the dashboard backend."""
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.parent
RUNS_DIR = PROJECT_ROOT / "runs"
COUNTRY_CONFIGS_DIR = PROJECT_ROOT / "country_configs"
UPLOADS_DIR = Path(__file__).parent / "uploads"

UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
