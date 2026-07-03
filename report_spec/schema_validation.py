from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import jsonschema.exceptions

from .errors import Category, Finding, Severity


def validate_against_schema(raw: dict, schema_path: Path) -> list[Finding]:
    """
    Validate *raw* (parsed YAML dict) against the JSON Schema at *schema_path*.
    Returns one Finding per violation; never raises.
    Draft 2020-12 requires jsonschema >= 4.18.
    """
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    validator_cls = jsonschema.validators.validator_for(schema)
    validator_cls.check_schema(schema)
    validator = validator_cls(schema)

    findings: list[Finding] = []
    for error in validator.iter_errors(raw):
        location = _json_path(error)
        findings.append(
            Finding(
                rule_id="SCHEMA",
                severity=Severity.ERROR,
                location=location,
                message=error.message,
                category=Category.SCHEMA_VIOLATION,
            )
        )
    return findings


def _json_path(error: jsonschema.exceptions.ValidationError) -> str:
    parts = list(error.absolute_path)
    if not parts:
        return "$"
    tokens: list[str] = ["$"]
    for p in parts:
        if isinstance(p, int):
            tokens.append(f"[{p}]")
        else:
            tokens.append(f".{p}")
    return "".join(tokens)
