"""
Unit tests for generation/assembler.py's scope-aware cover page (Phase 5).
The core guarantee under test: an unscoped (global-portfolio) run must
produce a byte-identical cover heading/subtitle to what assembler.py always
produced, so adding single-country support can't change the global report.
Run: pytest tests/test_assembler.py -v
"""
from __future__ import annotations

import json

import pytest
from docx import Document

import generation.assembler as assembler
from generation.assembler import _add_drivers_table, _load_analysis_meta, assemble


def _make_run(tmp_path, run_id: str, meta: dict) -> None:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "analysis_results.json").write_text(json.dumps({"meta": meta}), encoding="utf-8")


# ---------------------------------------------------------------------------
# _load_analysis_meta
# ---------------------------------------------------------------------------

class TestLoadAnalysisMeta:
    def test_missing_run_dir_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        assert _load_analysis_meta("no_such_run") == {}

    def test_valid_file_returns_meta_block(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "good_run", {"country": "vietnam", "n_total": 154})
        assert _load_analysis_meta("good_run") == {"country": "vietnam", "n_total": 154}


# ---------------------------------------------------------------------------
# assemble() cover page
# ---------------------------------------------------------------------------

class TestAssembleCoverPage:
    def _cover_paragraphs(self, doc_path) -> list[str]:
        doc = Document(str(doc_path))
        return [p.text for p in doc.paragraphs[:4]]

    def test_no_meta_matches_original_hardcoded_global_cover(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "no_meta_run", {})
        out = tmp_path / "out.docx"
        assemble([], {}, "no_meta_run", out)
        period = assembler.format_period_label("no_meta_run")
        paras = self._cover_paragraphs(out)
        assert paras[0] == "VisionFund International"
        assert paras[1] == f"Insurance Impact Report — Global Portfolio, {period}"

    def test_default_country_matches_original_hardcoded_global_cover(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "default_run", {"country": "default", "country_label": "Default", "n_total": 2111})
        out = tmp_path / "out.docx"
        assemble([], {}, "default_run", out)
        paras = self._cover_paragraphs(out)
        assert "Global Portfolio" in paras[1]
        assert paras[2] == "Covering 2,111 client responses across the VisionFund insurance portfolio."

    def test_scoped_country_uses_country_label_in_title_and_subtitle(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "vietnam_run", {"country": "vietnam", "country_label": "Vietnam", "n_total": 154})
        out = tmp_path / "out.docx"
        assemble([], {}, "vietnam_run", out)
        paras = self._cover_paragraphs(out)
        period = assembler.format_period_label("vietnam_run")
        assert paras[1] == f"Insurance Impact Report — Vietnam, {period}"
        assert paras[2] == "Covering 154 client responses from Vietnam."
        assert "Global Portfolio" not in paras[1]

    def test_scoped_country_without_label_falls_back_to_titlecase(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "kenya_run", {"country": "kenya", "n_total": 300})
        out = tmp_path / "out.docx"
        assemble([], {}, "kenya_run", out)
        paras = self._cover_paragraphs(out)
        assert "Kenya" in paras[1]

    def test_missing_n_total_omits_subtitle_paragraph_in_both_scopes(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "no_n_total_run", {"country": "default"})
        out = tmp_path / "out.docx"
        assemble([], {}, "no_n_total_run", out)
        paras = self._cover_paragraphs(out)
        # Next paragraph after the heading should jump straight to "Generated:"
        assert paras[2].startswith("Generated:")


# ---------------------------------------------------------------------------
# _add_drivers_table -- the drivers-table not_applicable marker (the gap
# picked up after Phase 5: a population-exclusive driver's table row must
# show "NOT APPLICABLE", not "SUPPRESSED", for a human reader too).
# ---------------------------------------------------------------------------

class TestAddDriversTable:
    def _table_rows(self, driver_row: dict) -> list:
        from docx import Document
        doc = Document()
        _add_drivers_table(doc, {"drivers_data": [driver_row], "drivers_table": {}})
        table = doc.tables[-1]
        return [[cell.text for cell in row.cells] for row in table.rows]

    def test_not_applicable_driver_renders_marker_row(self):
        rows = self._table_rows({
            "label": "Renewal Intent", "rho": None, "p_value": None, "n_valid": None,
            "suppressed": True, "not_applicable": True,
        })
        assert rows[1] == ["Renewal Intent", "NOT APPLICABLE", "NOT APPLICABLE", "NOT APPLICABLE"]

    def test_ordinary_suppressed_driver_still_shows_suppressed(self):
        rows = self._table_rows({
            "label": "Coverage Understanding", "rho": None, "p_value": None, "n_valid": None,
            "suppressed": True, "not_applicable": False,
        })
        assert rows[1] == ["Coverage Understanding", "SUPPRESSED", "SUPPRESSED", "SUPPRESSED"]

    def test_normal_driver_row_unaffected(self):
        rows = self._table_rows({
            "label": "Confidence in Payout", "rho": 0.312, "p_value": 0.001, "n_valid": 1200,
            "suppressed": False, "not_applicable": False,
        })
        assert rows[1] == ["Confidence in Payout", "+0.312", "0.0010", "1200"]
