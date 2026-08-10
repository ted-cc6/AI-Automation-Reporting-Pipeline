"""
Unit tests for dashboard/api/routes/csv_routes.py's country-discovery
endpoint (Phase 2, revisited for Phase 6's frontend wiring). Covers the
value-normalization fix: value must be lowercased only, NOT slugified with
underscores, so it stays consistent with data_loader_screening.py's
case-insensitive (but space-preserving) country filter -- a multi-word
country name would otherwise silently fail to match.
Run: pytest tests/test_csv_routes.py -v
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from dashboard.api.config import UPLOADS_DIR
from dashboard.api.main import app

client = TestClient(app)


def _upload_csv(text: str) -> str:
    resp = client.post("/api/csv/upload", files={"file": ("test.csv", text.encode("utf-8"), "text/csv")})
    assert resp.status_code == 200
    return resp.json()["upload_id"]


def _cleanup(upload_id: str) -> None:
    for p in UPLOADS_DIR.glob(f"{upload_id}*"):
        p.unlink(missing_ok=True)


class TestListUploadCountries:
    def test_missing_upload_returns_404(self):
        resp = client.get("/api/csv/does-not-exist/countries")
        assert resp.status_code == 404

    def test_counts_and_sorting(self):
        csv_text = (
            "Device Info;start;end;Username;Region;Country\n"
            "d1;t1;t2;alice;East;Kenya\n"
            "d2;t1;t2;bob;East;Vietnam\n"
            "d3;t1;t2;carol;East;Vietnam\n"
            "d4;t1;t2;dan;East;Vietnam\n"
        )
        upload_id = _upload_csv(csv_text)
        try:
            resp = client.get(f"/api/csv/{upload_id}/countries")
            assert resp.status_code == 200
            data = resp.json()
            assert data == [
                {"value": "vietnam", "label": "Vietnam", "count": 3},
                {"value": "kenya", "label": "Kenya", "count": 1},
            ]
        finally:
            _cleanup(upload_id)

    def test_blank_country_values_excluded(self):
        csv_text = (
            "Device Info;start;end;Username;Region;Country\n"
            "d1;t1;t2;alice;East;Kenya\n"
            "d2;t1;t2;bob;East; \n"
            "d3;t1;t2;carol;East;\n"
        )
        upload_id = _upload_csv(csv_text)
        try:
            resp = client.get(f"/api/csv/{upload_id}/countries")
            data = resp.json()
            assert data == [{"value": "kenya", "label": "Kenya", "count": 1}]
        finally:
            _cleanup(upload_id)

    def test_multi_word_country_value_is_lowercased_not_slugified(self):
        # Regression test for the underscore-slugification bug: value must
        # stay space-separated (just lowercased) so it matches
        # data_loader_screening.py's find_unselected_country_rows(), which
        # only lowercases -- it does not swap underscores back to spaces.
        csv_text = (
            "Device Info;start;end;Username;Region;Country\n"
            "d1;t1;t2;alice;East;Papua New Guinea\n"
            "d2;t1;t2;bob;East;Papua New Guinea\n"
        )
        upload_id = _upload_csv(csv_text)
        try:
            resp = client.get(f"/api/csv/{upload_id}/countries")
            data = resp.json()
            assert data == [{"value": "papua new guinea", "label": "Papua New Guinea", "count": 2}]
            assert "_" not in data[0]["value"]
        finally:
            _cleanup(upload_id)

    def test_no_country_column_in_mapping_returns_empty_list(self, monkeypatch):
        import dashboard.api.routes.csv_routes as csv_routes
        import pandas as pd

        monkeypatch.setattr(
            csv_routes.data_loader_transformer,
            "load_mapping",
            lambda path: pd.DataFrame({"raw_index": [0], "raw_column_header": ["X"], "output_name": ["not_country"]}),
        )
        csv_text = "X\nfoo\n"
        upload_id = _upload_csv(csv_text)
        try:
            resp = client.get(f"/api/csv/{upload_id}/countries")
            assert resp.status_code == 200
            assert resp.json() == []
        finally:
            _cleanup(upload_id)
