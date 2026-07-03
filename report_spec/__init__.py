"""
report_spec — load, validate, and iterate over a VisionFund Insurance Report spec.

Public API
----------
load_spec(yaml_path, schema_path=None, *, strict=True) -> LoadResult
ReportSpec, LoadResult, Finding, SpecValidationError
"""
from .errors import Finding, Severity, Category, SpecValidationError
from .loader import LoadResult, load_spec
from .models import ReportSpec

__all__ = [
    "load_spec",
    "LoadResult",
    "ReportSpec",
    "Finding",
    "Severity",
    "Category",
    "SpecValidationError",
]
