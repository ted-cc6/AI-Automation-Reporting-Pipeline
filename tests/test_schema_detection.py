"""
Unit tests for dashboard/api/schema_detection.py -- detecting which
source-survey schema (Africa/Vietnam vs LARCO) an uploaded CSV matches, by
diffing its header row against each schema's canonical column_mapping.csv.

Builds synthetic CSVs from each canonical mapping's own raw_column_header
values (checked into the repo) rather than depending on the real
proprietary export files, which live outside the repo and aren't available
in a general test environment.
Run: pytest tests/test_schema_detection.py -v
"""
from __future__ import annotations

import csv
import tempfile
from pathlib import Path

import pytest

from dashboard.api.schema_detection import (
    SCHEMA_MAPPING_PATHS,
    detect_dataset_schema,
    schema_match_ratios,
)
from data_loader.data_loader_transformer import load_mapping


def _headers_for(schema: str) -> list[str]:
    mapping = load_mapping(SCHEMA_MAPPING_PATHS[schema])
    return list(mapping["raw_column_header"])


def _write_csv(tmp_path: Path, headers: list[str]) -> Path:
    csv_path = tmp_path / "upload.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(headers)
        writer.writerow(["x"] * len(headers))
    return csv_path


class TestDetectDatasetSchema:
    def test_africa_headers_detect_as_africa_vietnam(self, tmp_path):
        csv_path = _write_csv(tmp_path, _headers_for("africa_vietnam"))
        assert detect_dataset_schema(csv_path) == "africa_vietnam"

    def test_larco_headers_detect_as_larco(self, tmp_path):
        csv_path = _write_csv(tmp_path, _headers_for("larco"))
        assert detect_dataset_schema(csv_path) == "larco"

    def test_africa_headers_score_low_against_larco_mapping(self, tmp_path):
        csv_path = _write_csv(tmp_path, _headers_for("africa_vietnam"))
        ratios = schema_match_ratios(csv_path)
        assert ratios["africa_vietnam"] > ratios["larco"]
        assert ratios["larco"] < 0.5

    def test_unrelated_headers_report_unknown(self, tmp_path):
        csv_path = _write_csv(tmp_path, ["Not", "A", "Real", "Survey", "Header", "Row"])
        assert detect_dataset_schema(csv_path) == "unknown"
