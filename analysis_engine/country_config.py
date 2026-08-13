"""country_config.py — Country-specific configuration loader for the analysis engine."""
import logging
from dataclasses import dataclass, field
from pathlib import Path

import yaml

log = logging.getLogger("analysis_engine.country_config")

_CONFIGS_DIR = Path(__file__).parent.parent / "country_configs"
DEFAULT_COUNTRY = "default"


@dataclass
class SegmentOverride:
    available:   bool
    column:      str | None  = None
    label:       str | None  = None
    description: str | None  = None
    skip_reason: str | None  = None


@dataclass
class MetricNote:
    note:                str
    applies_to_segments: list[str] = field(default_factory=list)


@dataclass
class CountryConfig:
    country:           str
    label:             str
    report_context:    str                         = ""
    segment_overrides: dict[str, SegmentOverride]  = field(default_factory=dict)
    metric_notes:      dict[str, MetricNote]        = field(default_factory=dict)


def load_country_config(country: str) -> CountryConfig:
    """Load and parse a country YAML config, falling back to _default.yaml if not found.

    Config filenames are single lowercase tokens with underscores for spaces
    (e.g. "dominican_republic.yaml"), but callers pass the country through in
    whatever form it arrived in upstream -- the dashboard's country picker
    sends the raw CSV value lowercased but NOT slugified (e.g. "dominican
    republic", a literal space -- see dashboard/api/routes/csv_routes.py),
    and a CLI user might type "Dominican Republic". Every single-word country
    seen before 2026 made this distinction invisible; normalize here so a
    two-word country resolves to its dedicated config instead of silently
    falling back to default.yaml.
    """
    slug = country.strip().lower().replace(" ", "_")
    yaml_path = _CONFIGS_DIR / f"{slug}.yaml"

    if not yaml_path.exists():
        if country != DEFAULT_COUNTRY:
            log.warning(f"No config found for country '{country}' — falling back to default")
        yaml_path = _CONFIGS_DIR / f"{DEFAULT_COUNTRY}.yaml"

    if not yaml_path.exists():
        raise FileNotFoundError(
            f"Default country config not found: {yaml_path}. "
            "Ensure country_configs/_default.yaml exists."
        )

    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    log.info(f"Loaded country config: {yaml_path.name}")

    # Parse segment_overrides
    segment_overrides: dict[str, SegmentOverride] = {}
    for seg_name, raw in (data.get("segment_overrides") or {}).items():
        if not isinstance(raw, dict):
            continue
        valid_fields = SegmentOverride.__dataclass_fields__
        override = SegmentOverride(**{k: v for k, v in raw.items() if k in valid_fields})
        if override.available and not override.column:
            raise ValueError(
                f"Country config '{country}': segment_override '{seg_name}' has "
                "available=true but no column specified."
            )
        segment_overrides[seg_name] = override

    # Parse metric_notes
    metric_notes: dict[str, MetricNote] = {}
    for metric_name, raw in (data.get("metric_notes") or {}).items():
        if not isinstance(raw, dict):
            continue
        metric_notes[metric_name] = MetricNote(
            note=raw.get("note", ""),
            applies_to_segments=raw.get("applies_to_segments") or [],
        )

    return CountryConfig(
        country=data.get("country", country),
        label=data.get("label", country.title()),
        report_context=data.get("report_context", ""),
        segment_overrides=segment_overrides,
        metric_notes=metric_notes,
    )
