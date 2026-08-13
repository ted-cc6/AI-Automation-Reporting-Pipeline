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
from generation.assembler import (
    _add_drivers_table,
    _add_executive_summary,
    _add_protection_signals_annex,
    _add_protection_signals_summary,
    _load_analysis_meta,
    assemble,
)


def _make_run(tmp_path, run_id: str, meta: dict) -> None:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "analysis_results.json").write_text(json.dumps({"meta": meta}), encoding="utf-8")


def _make_run_with_parts(tmp_path, run_id: str, meta: dict, parts: dict, qual: "dict | None" = None) -> None:
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "analysis_results.json").write_text(
        json.dumps({"meta": meta, "parts": parts}), encoding="utf-8"
    )
    if qual is not None:
        (run_dir / "qualitative_results.json").write_text(json.dumps(qual), encoding="utf-8")


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
        assert paras[1] == f"Insurance Impact Report: Global Portfolio, {period}"

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
        assert paras[1] == f"Insurance Impact Report: Vietnam, {period}"
        assert paras[2] == "Covering 154 client responses from Vietnam."
        assert "Global Portfolio" not in paras[1]

    def test_scoped_country_without_label_falls_back_to_titlecase(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "kenya_run", {"country": "kenya", "n_total": 300})
        out = tmp_path / "out.docx"
        assemble([], {}, "kenya_run", out)
        paras = self._cover_paragraphs(out)
        assert "Kenya" in paras[1]

    def test_larco_rollup_uses_larco_regional_title_not_global(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "larco_run", {"country": "default", "dataset_schema": "larco", "n_total": 1355})
        out = tmp_path / "out.docx"
        assemble([], {}, "larco_run", out)
        paras = self._cover_paragraphs(out)
        assert "LARCO Regional Portfolio" in paras[1]
        assert "Global Portfolio" not in paras[1]
        assert paras[2] == "Covering 1,355 client responses across VisionFund's LARCO (Latin America and Caribbean) insurance portfolio."

    def test_larco_single_country_still_uses_country_label(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "ecuador_run", {"country": "ecuador", "country_label": "Ecuador", "dataset_schema": "larco", "n_total": 400})
        out = tmp_path / "out.docx"
        assemble([], {}, "ecuador_run", out)
        paras = self._cover_paragraphs(out)
        assert paras[1] == f"Insurance Impact Report: Ecuador, {assembler.format_period_label('ecuador_run')}"
        assert "LARCO" not in paras[1]

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

    def test_tiny_p_value_floors_instead_of_truncating_to_zero(self):
        rows = self._table_rows({
            "label": "Financial Stress", "rho": -0.387, "p_value": 2.28e-38, "n_valid": 1037,
            "suppressed": False, "not_applicable": False,
        })
        assert rows[1] == ["Financial Stress", "-0.387", "<0.0001", "1037"]

    def test_prints_appendix_pointer_not_full_methodology_text(self):
        from docx import Document
        doc = Document()
        _add_drivers_table(doc, {
            "drivers_data": [{
                "label": "NPS", "rho": 0.2, "p_value": 0.01, "n_valid": 500,
                "suppressed": False, "not_applicable": False,
            }],
            "drivers_table": {},
        })
        body_text = "\n".join(p.text for p in doc.paragraphs)
        assert "Appendix: Methodology Notes" in body_text
        # The old ~200-word inline explanation must not be duplicated here.
        assert "Spearman rank correlation coefficient" not in body_text


# ---------------------------------------------------------------------------
# Methodology appendix -- de-duplicates the Spearman ρ/p-value/N explanation
# that previously appeared verbatim under both Part 4's and Part 5's drivers
# tables into a single document appendix.
# ---------------------------------------------------------------------------

class TestMethodologyAppendix:
    def _doc_text(self, doc_path) -> str:
        doc = Document(str(doc_path))
        return "\n".join(p.text for p in doc.paragraphs)

    def test_appendix_added_when_part_4_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "p4_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        assemble([{"part": "part_4", "title": "Child Wellbeing Outcomes"}], {}, "p4_run", out)
        assert "Appendix: Methodology Notes" in self._doc_text(out)

    def test_appendix_added_when_part_5_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "p5_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        assemble([{"part": "part_5", "title": "Child Wellbeing"}], {}, "p5_run", out)
        assert "Appendix: Methodology Notes" in self._doc_text(out)

    def test_appendix_omitted_when_neither_part_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "p1_only_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        assemble([{"part": "part_1", "title": "Client Understanding & Value Perception"}], {}, "p1_only_run", out)
        assert "Appendix: Methodology Notes" not in self._doc_text(out)


# ---------------------------------------------------------------------------
# Protection signals -- short in-body summary (Part 2) + full itemized annex
# (Phase D), replacing the old single inline rendering that put the full
# itemized list (reason text + client ref per case) directly in Part 2's
# narrative flow.
# ---------------------------------------------------------------------------

_FLAGS = [
    {"id": "row_0011", "flag_type": "unfair_claim_denial", "severity": "high",
     "reason": "Client says claim was denied without explanation.",
     "profile": {"client_id": "CI-00011", "branch": "Branch A"}},
    {"id": "row_0042", "flag_type": "staff_misconduct", "severity": "medium",
     "reason": "Client reports unresponsive branch staff.",
     "profile": {"client_id": "CI-00042", "branch": "Branch B"}},
    {"id": "row_0099", "flag_type": "staff_misconduct", "severity": "low",
     "reason": "Minor communication friction reported.",
     "profile": {"client_id": "CI-00099", "branch": "Branch C"}},
]


class TestProtectionSignalsSummary:
    def _paragraphs(self, protection_flags: list) -> list:
        from docx import Document
        doc = Document()
        _add_protection_signals_summary(doc, protection_flags)
        return [p.text for p in doc.paragraphs]

    def test_no_flags_renders_nothing(self):
        assert self._paragraphs([]) == []

    def test_shows_counts_by_severity_not_full_reason_text(self):
        paras = self._paragraphs(_FLAGS)
        body = "\n".join(paras)
        assert "Client Protection Signals" in body
        assert "3 client-reported protection concerns" in body
        assert "1 high" in body and "1 medium" in body and "1 low" in body
        assert "Appendix: Client Protection Signals" in body
        # The full per-case reason text must NOT leak into the short summary.
        assert "Client says claim was denied without explanation." not in body
        assert "CI-00011" not in body

    def test_singular_wording_for_exactly_one_flag(self):
        body = "\n".join(self._paragraphs(_FLAGS[:1]))
        assert "1 client-reported protection concern was identified" in body


class TestProtectionSignalsAnnex:
    def _paragraphs(self, protection_flags: list) -> list:
        from docx import Document
        doc = Document()
        _add_protection_signals_annex(doc, protection_flags)
        return [p.text for p in doc.paragraphs]

    def test_no_flags_renders_nothing(self):
        assert self._paragraphs([]) == []

    def test_full_itemized_list_grouped_by_severity_with_client_refs(self):
        body = "\n".join(self._paragraphs(_FLAGS))
        assert "Appendix: Client Protection Signals" in body
        assert "High severity" in body
        assert "Unfair claim denial: Client says claim was denied without explanation. (CI-00011, Branch A)" in body
        assert "Staff misconduct: Client reports unresponsive branch staff. (CI-00042, Branch B)" in body
        assert "Staff misconduct: Minor communication friction reported. (CI-00099, Branch C)" in body

    def test_falls_back_to_row_id_when_profile_unresolved(self):
        # A flag whose row_id no longer maps into the survey dataframe (e.g.
        # a stale re-run) must still render something traceable rather than
        # silently dropping the reference.
        flags = [{"id": "row_0007", "flag_type": "coercion", "severity": "high",
                  "reason": "Unresolved case.", "profile": {}}]
        body = "\n".join(self._paragraphs(flags))
        assert "(row_0007)" in body

    def test_severity_order_high_medium_low(self):
        paras = self._paragraphs(_FLAGS)
        headings = [p for p in paras if p.endswith("severity")]
        assert headings == ["High severity", "Medium severity", "Low severity"]


class TestAssembleProtectionSignalsRouting:
    def _doc_text(self, doc_path) -> str:
        doc = Document(str(doc_path))
        return "\n".join(p.text for p in doc.paragraphs)

    def test_flags_extracted_from_part_2_package_and_routed_to_annex(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "flags_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        package = {
            "part": "part_2", "title": "Claims Experience",
            "sections": {"s2_3": {"qualitative": {"protection_flags": _FLAGS}}},
        }
        assemble([package], {}, "flags_run", out)
        body = self._doc_text(out)
        assert "Appendix: Client Protection Signals" in body
        assert "Client says claim was denied without explanation. (CI-00011, Branch A)" in body
        # Part 2's own inline section shows only the short summary.
        assert "3 client-reported protection concerns" in body

    def test_no_part_2_package_omits_annex(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "no_p2_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        assemble([{"part": "part_1", "title": "Client Understanding & Value Perception"}], {}, "no_p2_run", out)
        assert "Appendix: Client Protection Signals" not in self._doc_text(out)


# ---------------------------------------------------------------------------
# Executive Summary -- headline numbers (deterministic) + top findings/
# actions + narrative (from qualitative_results.json's Task 7) + a
# consolidated data-availability caveat box (Phase D).
# ---------------------------------------------------------------------------

_EXEC_SUMMARY_PARTS = {
    "part_4": {
        "nps": {"result": {"value": 20.0, "n_valid": 500, "suppressed": False, "not_applicable": False}},
        "child_wellbeing": {"headline": {"value": 0.35, "n_valid": 400, "suppressed": False, "not_applicable": False}},
    },
    "part_3": {
        "metrics": {
            "no_prior_access": {"headline": {"value": 0.8, "n_valid": 500, "suppressed": False, "not_applicable": False}},
            "confidence_pay": {"headline": {"value": None, "n_valid": 0, "suppressed": True, "not_applicable": True}},
            "negative_coping": {"headline": {"value": 0.1, "n_valid": 200, "suppressed": False, "not_applicable": False}},
        }
    },
    "part_2": {
        "claims_funnel": {
            "filed_claim": {"n": 100, "pct_of_event_base": 0.2, "suppressed": False, "not_applicable": False},
            "experienced_event": {"n": 400, "n_valid": 400, "suppressed": False, "not_applicable": False},
            "claim_paid": {"value": 0.7, "n": 70, "n_valid": 100, "suppressed": False, "not_applicable": False},
            "payout_adequacy": {"n_valid": 80, "suppressed": False, "not_applicable": False},
        }
    },
    "part_1": {
        "metrics": {
            "coverage_understanding": {"headline": {"value": 0.5, "n_valid": 500, "suppressed": False, "not_applicable": False}},
            "claim_process_understanding": {"headline": {"value": 0.5, "n_valid": 500, "suppressed": False, "not_applicable": False}},
            "worth_premium": {"headline": {"value": 0.5, "n_valid": 500, "suppressed": False, "not_applicable": False}},
            "renewal_intent": {"headline": {"value": 0.5, "n_valid": 500, "suppressed": False, "not_applicable": False}},
            "product_understanding": {"headline": {"value": None, "n_valid": 0, "suppressed": True, "not_applicable": True}},
        }
    },
}


class TestAddExecutiveSummary:
    def _doc_text(self, analysis: dict, qual: dict) -> str:
        from docx import Document
        doc = Document()
        _add_executive_summary(doc, analysis, qual)
        return "\n".join(p.text for p in doc.paragraphs)

    def test_headline_numbers_table_rendered(self):
        from docx import Document
        doc = Document()
        _add_executive_summary(doc, {"parts": _EXEC_SUMMARY_PARTS}, {})
        table = doc.tables[0]
        rows = [[c.text for c in row.cells] for row in table.rows]
        assert rows[0] == ["Metric", "Value", "N"]
        assert ["Net Promoter Score", "20.0", "500"] in rows

    def test_caveat_box_lists_not_applicable_metric(self):
        body = self._doc_text({"parts": _EXEC_SUMMARY_PARTS}, {})
        assert "Data Availability" in body
        assert "Combined Product Understanding" in body

    def test_no_qual_data_omits_findings_actions_but_keeps_numbers(self):
        body = self._doc_text({"parts": _EXEC_SUMMARY_PARTS}, {})
        assert "Top Findings" not in body
        assert "Recommended Actions" not in body

    def test_qual_data_adds_narrative_findings_and_actions(self):
        qual = {
            "executive_summary": "Clients value fast payouts.",
            "top_findings": ["Finding A", "Finding B", "Finding C", "Finding D"],
            "top_actions": ["Action A", "Action B", "Action C"],
        }
        body = self._doc_text({"parts": _EXEC_SUMMARY_PARTS}, qual)
        assert "Clients value fast payouts." in body
        assert "Top Findings" in body
        assert "Finding A" in body and "Finding C" in body
        # Only the top 3 are shown even if the model returns more.
        assert "Finding D" not in body
        assert "Recommended Actions" in body
        assert "Action A" in body


class TestAssembleExecutiveSummary:
    def _doc_text(self, doc_path) -> str:
        doc = Document(str(doc_path))
        return "\n".join(p.text for p in doc.paragraphs)

    def test_executive_summary_added_when_parts_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run_with_parts(
            tmp_path, "exec_run", {"country": "default", "n_total": 500}, _EXEC_SUMMARY_PARTS,
        )
        out = tmp_path / "out.docx"
        assemble([], {}, "exec_run", out)
        assert "Executive Summary" in self._doc_text(out)

    def test_executive_summary_precedes_about_this_survey(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        about = {"n_total": 500, "by_country": [], "product_mix": {"available": False},
                 "age": {}, "by_sex": [], "fieldwork": {"available": False}}
        parts = {**_EXEC_SUMMARY_PARTS, "about_survey": about}
        _make_run_with_parts(tmp_path, "order_run", {"country": "default", "n_total": 500}, parts)
        out = tmp_path / "out.docx"
        assemble([], {}, "order_run", out)
        body = self._doc_text(out)
        assert body.index("Executive Summary") < body.index("About This Survey")

    def test_qualitative_results_merged_in_when_present(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        qual = {
            "executive_summary": "A concise narrative.",
            "top_findings": ["F1", "F2", "F3"],
            "top_actions": ["A1", "A2", "A3"],
        }
        _make_run_with_parts(
            tmp_path, "qual_run", {"country": "default", "n_total": 500}, _EXEC_SUMMARY_PARTS, qual=qual,
        )
        out = tmp_path / "out.docx"
        assemble([], {}, "qual_run", out)
        body = self._doc_text(out)
        assert "A concise narrative." in body
        assert "F1" in body
        assert "A1" in body

    def test_no_parts_key_omits_executive_summary(self, tmp_path, monkeypatch):
        monkeypatch.setattr(assembler, "ROOT", tmp_path)
        _make_run(tmp_path, "no_parts_run", {"country": "default", "n_total": 100})
        out = tmp_path / "out.docx"
        assemble([], {}, "no_parts_run", out)
        assert "Executive Summary" not in self._doc_text(out)
