"""dashboard/api/routes/country_routes.py"""
import yaml
from fastapi import APIRouter

from dashboard.api.config import COUNTRY_CONFIGS_DIR
from dashboard.api.models import CountryOption, ReportScopeOption
from report_scopes import REPORT_SCOPES

router = APIRouter(prefix="/api", tags=["countries"])


@router.get("/countries", response_model=list[CountryOption])
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


@router.get("/report-scopes", response_model=list[ReportScopeOption])
async def list_report_scopes() -> list[ReportScopeOption]:
    """report_scopes.py's REPORT_SCOPES, for the dashboard's report-scope
    picker (see CupboardWeekApp.tsx) -- lets a run be scoped to a named
    region group (e.g. LACRO) instead of a single country or the full
    portfolio, matching what run_pipeline.py's --report-scope flag already
    supports from the CLI."""
    return [
        ReportScopeOption(value=key, label=cfg["label"])
        for key, cfg in REPORT_SCOPES.items()
    ]
