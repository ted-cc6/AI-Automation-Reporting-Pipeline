from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .errors import Category, Finding, Severity, SpecValidationError
from .models import ReportSpec
from .rules import run_all_rules
from .schema_validation import validate_against_schema

_DEFAULT_SCHEMA = Path(__file__).parent.parent / "insurance-report-spec.schema.json"


@dataclass
class LoadResult:
    spec: ReportSpec | None
    findings: list[Finding] = field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return self.spec is not None and not any(
            f.severity == Severity.ERROR for f in self.findings
        )

    @property
    def errors(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.ERROR]

    @property
    def warnings(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == Severity.WARNING]


def load_spec(
    yaml_path: str | Path,
    schema_path: str | Path | None = None,
    *,
    strict: bool = True,
) -> LoadResult:
    """
    Load and validate a report spec YAML file.

    Parameters
    ----------
    yaml_path:
        Path to the spec YAML file.
    schema_path:
        Path to the JSON Schema file. Defaults to the schema bundled with this
        package (insurance-report-spec.schema.json in the project root).
    strict:
        If True (default), raise SpecValidationError when any ERROR-severity
        finding is present. Set False to get a LoadResult even for invalid specs.

    Returns
    -------
    LoadResult with spec (None if schema/Pydantic parsing failed), findings, is_valid.
    """
    yaml_path = Path(yaml_path)
    schema_path = Path(schema_path) if schema_path else _DEFAULT_SCHEMA

    # --- Step 1: parse YAML ---
    try:
        raw = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    except Exception as exc:
        finding = Finding(
            rule_id="PARSE",
            severity=Severity.ERROR,
            location=str(yaml_path),
            message=f"Failed to parse YAML: {exc}",
            category=Category.SCHEMA_VIOLATION,
        )
        result = LoadResult(spec=None, findings=[finding])
        if strict:
            raise SpecValidationError(result.errors) from exc
        return result

    # --- Step 2: JSON Schema validation ---
    schema_findings = validate_against_schema(raw, schema_path)

    if schema_findings:
        result = LoadResult(spec=None, findings=schema_findings)
        if strict:
            raise SpecValidationError(result.errors)
        return result

    # --- Step 3: Pydantic model construction ---
    try:
        spec = ReportSpec.model_validate(raw)
    except Exception as exc:
        finding = Finding(
            rule_id="MODEL",
            severity=Severity.ERROR,
            location="$",
            message=f"Pydantic model validation failed: {exc}",
            category=Category.SCHEMA_VIOLATION,
        )
        result = LoadResult(spec=None, findings=[finding])
        if strict:
            raise SpecValidationError(result.errors) from exc
        return result

    # --- Step 4: code-level rules ---
    rule_findings = run_all_rules(spec)
    result = LoadResult(spec=spec, findings=rule_findings)

    if strict and result.errors:
        raise SpecValidationError(result.errors)

    return result
