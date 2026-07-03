from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"


class Category(str, Enum):
    SCHEMA_VIOLATION = "SCHEMA_VIOLATION"
    STRUCTURAL = "STRUCTURAL"
    REFERENTIAL_INTEGRITY = "REFERENTIAL_INTEGRITY"
    CONDITIONAL_FIELD = "CONDITIONAL_FIELD"
    KNOWN_GAP = "KNOWN_GAP"


@dataclass(frozen=True)
class Finding:
    rule_id: str
    severity: Severity
    location: str
    message: str
    category: Category

    def __str__(self) -> str:
        return f"[{self.severity.value}] {self.rule_id} @ {self.location}: {self.message}"


class SpecValidationError(Exception):
    def __init__(self, findings: list[Finding]) -> None:
        self.findings = findings
        errors = [f for f in findings if f.severity == Severity.ERROR]
        super().__init__(
            f"Spec validation failed with {len(errors)} error(s). "
            f"First: {errors[0]}" if errors else "Spec validation failed."
        )
