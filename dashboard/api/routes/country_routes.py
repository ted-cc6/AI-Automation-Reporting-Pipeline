"""dashboard/api/routes/country_routes.py"""
import yaml
from fastapi import APIRouter

from dashboard.api.config import COUNTRY_CONFIGS_DIR
from dashboard.api.models import CountryOption

router = APIRouter(prefix="/api/countries", tags=["countries"])


@router.get("", response_model=list[CountryOption])
async def list_countries() -> list[CountryOption]:
    """Dynamically lists country_configs/*.yaml stems so new countries show up
    with zero frontend changes."""
    options = []
    for path in sorted(COUNTRY_CONFIGS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        options.append(CountryOption(
            value=path.stem,
            label=data.get("label", path.stem.replace("_", " ").title()),
        ))
    return options
