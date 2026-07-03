"""
Tests for coverage_report.py.
Run: pytest tests/test_coverage_report.py -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from report_spec import ReportSpec

from coverage_report import generate_coverage_report

# ── Paths ─────────────────────────────────────────────────────────────────────
_SCHEMA_PATH = Path(__file__).parent.parent / "insurance-report-spec.schema.json"
_REAL_YAML   = Path(__file__).parent.parent / "insurance-report-spec.yaml"


# ── Fixture helpers ───────────────────────────────────────────────────────────

def _make_sub(
    subsection_id: str,
    fill_mode: str = "bespoke",
    word_cap: int | None = 80,
    outputs: list[str] | None = None,
    source_questions: list[dict] | None = None,
    metrics: list[dict] | None = None,
    visual: dict | None = None,
    qualitative: dict | None = None,
) -> dict:
    d: dict = {
        "subsection_id": subsection_id,
        "title": f"Sub {subsection_id}",
        "fill_mode": fill_mode,
        "word_cap": word_cap,
        "source_questions": source_questions or [],
        "outputs": outputs or ["analysis_prose"],
    }
    if metrics is not None:
        d["metrics"] = metrics
    if visual is not None:
        d["visual"] = visual
    if qualitative is not None:
        d["qualitative"] = qualitative
    return d


def _insight(part_id: int) -> dict:
    return _make_sub(f"{part_id}.insight", "bespoke", 120, ["insight_prose"])


def _make_part(part_id: int, extra_subs: list[dict] | None = None) -> dict:
    subs = list(extra_subs or [])
    if not any(s["subsection_id"] == f"{part_id}.insight" for s in subs):
        subs.append(_insight(part_id))
    return {"part_id": part_id, "title": f"Part {part_id}", "subsections": subs}


def _make_spec(parts: list[dict] | None = None) -> ReportSpec:
    if parts is None:
        parts = [_make_part(i) for i in range(1, 8)]
    raw = {
        "report_metadata": {
            "name": "Test Report",
            "template_version": "2.0",
            "priority_segments": ["female", "male"],
        },
        "parts": parts,
    }
    return ReportSpec.model_validate(raw)


# ── 1. Automation coverage counts ────────────────────────────────────────────

class TestAutomationCoverage:
    def _spec_with_mix(self) -> ReportSpec:
        """
        Part 1: 1 hybrid sub + 1 insight (bespoke) = 2 subs, 1 automatable
        Parts 2–7: insight only = 1 sub each, 0 automatable
        Total: 8 subs, 1 automatable (12%)
        """
        hybrid_sub = _make_sub(
            "1.1", "hybrid", 90, ["analysis_prose"],
            source_questions=[{"question_ref": "q_x"}],
            metrics=[{"method": "share", "variables": ["q_x"]}],
        )
        parts = [_make_part(1, [hybrid_sub])] + [_make_part(i) for i in range(2, 8)]
        return _make_spec(parts)

    def test_automatable_count_in_headline(self):
        spec = self._spec_with_mix()
        report = generate_coverage_report(spec)
        # 1 hybrid out of 8 total
        assert "Automatable (auto+hybrid): 1 of 8" in report

    def test_bespoke_insight_note_present(self):
        spec = self._spec_with_mix()
        report = generate_coverage_report(spec)
        # 7 insight blocks (one per part) should be mentioned
        assert "7 of 7 bespoke subsections are deliberate N.insight" in report

    def test_section_filter_returns_only_coverage(self):
        spec = self._spec_with_mix()
        section = generate_coverage_report(spec, section_filter="automation_coverage")
        assert "Automatable" in section
        assert "## 3." not in section  # per-part section should be absent

    def test_mixed_auto_hybrid_bespoke(self):
        """2 auto + 1 hybrid + 5 bespoke insight = 8 total, 3 automatable."""
        auto_sub = _make_sub(
            "1.1", "auto", 90, ["analysis_prose"],
            source_questions=[{"question_ref": "q_y"}],
            metrics=[{"method": "share", "variables": ["q_y"]}],
        )
        auto_sub2 = _make_sub(
            "2.1", "auto", 90, ["analysis_prose"],
            source_questions=[{"question_ref": "q_z"}],
            metrics=[{"method": "share", "variables": ["q_z"]}],
        )
        hybrid_sub = _make_sub(
            "3.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_w"}],
            metrics=[{"method": "share", "variables": ["q_w"]}],
        )
        parts = (
            [_make_part(1, [auto_sub])]
            + [_make_part(2, [auto_sub2])]
            + [_make_part(3, [hybrid_sub])]
            + [_make_part(i) for i in range(4, 8)]
        )
        spec = _make_spec(parts)
        report = generate_coverage_report(spec)
        assert "Automatable (auto+hybrid): 3 of 10" in report


# ── 2. Data demands de-duplication ───────────────────────────────────────────

class TestDataDemands:
    def test_shared_question_appears_once(self):
        """q_shared appears in two different subsections; should be listed once."""
        sub1 = _make_sub(
            "1.1", "bespoke", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_shared"}, {"question_ref": "q_a"}],
        )
        sub2 = _make_sub(
            "2.1", "bespoke", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_shared"}, {"question_ref": "q_b"}],
        )
        parts = [_make_part(1, [sub1])] + [_make_part(2, [sub2])] + [_make_part(i) for i in range(3, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="data_demands")
        # q_shared should appear exactly once
        assert report.count("q_shared") == 1

    def test_total_count_reflects_dedup(self):
        """3 unique questions across two subsections (1 shared)."""
        sub1 = _make_sub(
            "1.1", "bespoke", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_shared"}, {"question_ref": "q_a"}],
        )
        sub2 = _make_sub(
            "2.1", "bespoke", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_shared"}, {"question_ref": "q_b"}],
        )
        parts = [_make_part(1, [sub1])] + [_make_part(2, [sub2])] + [_make_part(i) for i in range(3, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="data_demands")
        assert "3 distinct survey questions" in report

    def test_checklist_header_present(self):
        spec = _make_spec()
        report = generate_coverage_report(spec, section_filter="data_demands")
        assert "data request checklist" in report.lower()


# ── 3. Derived variables detection ───────────────────────────────────────────

class TestDerivedVariables:
    def test_variable_missing_from_source_questions_detected(self):
        """q_derived_flag is in the metric but NOT in source_questions."""
        sub = _make_sub(
            "1.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_sex"}],
            metrics=[{"method": "gap_analysis", "variables": ["q_derived_flag"], "against": "q_sex"}],
        )
        parts = [_make_part(1, [sub])] + [_make_part(i) for i in range(2, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="derived_variables")
        assert "q_derived_flag" in report

    def test_against_variable_missing_detected(self):
        """The 'against' field ref is absent from source_questions."""
        sub = _make_sub(
            "1.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_outcome"}],
            metrics=[{"method": "gap_analysis", "variables": ["q_outcome"], "against": "q_derived_cut"}],
        )
        parts = [_make_part(1, [sub])] + [_make_part(i) for i in range(2, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="derived_variables")
        assert "q_derived_cut" in report

    def test_no_derived_when_all_declared(self):
        """All metric variables are in source_questions → clean message."""
        sub = _make_sub(
            "1.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_a"}, {"question_ref": "q_b"}],
            metrics=[{"method": "correlation", "variables": ["q_a"], "against": "q_b"}],
        )
        parts = [_make_part(1, [sub])] + [_make_part(i) for i in range(2, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="derived_variables")
        assert "No derived variables detected" in report

    def test_multiple_subsections_referencing_same_derived(self):
        """Same derived var in two subsections → both subsection ids listed."""
        sub1 = _make_sub(
            "1.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_x"}],
            metrics=[{"method": "share", "variables": ["q_derived_flag"]}],
        )
        sub2 = _make_sub(
            "2.1", "hybrid", 80, ["analysis_prose"],
            source_questions=[{"question_ref": "q_y"}],
            metrics=[{"method": "share", "variables": ["q_derived_flag"]}],
        )
        parts = [_make_part(1, [sub1])] + [_make_part(2, [sub2])] + [_make_part(i) for i in range(3, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="derived_variables")
        assert "1.1" in report
        assert "2.1" in report


# ── 4. Duplicate visual detection ────────────────────────────────────────────

class TestVisualsManifest:
    def _visual(self, name: str) -> dict:
        return {
            "powerbi_name": name,
            "source": "powerbi_screenshot",
            "visual_type": "bar_chart",
        }

    def test_duplicate_visual_flagged(self):
        """Two subsections sharing the same powerbi_name trigger the ⚠ warning."""
        sub1 = _make_sub("1.1", visual=self._visual("NPS Score Visual"))
        sub2 = _make_sub("2.1", visual=self._visual("NPS Score Visual"))
        parts = [_make_part(1, [sub1])] + [_make_part(2, [sub2])] + [_make_part(i) for i in range(3, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="visuals_manifest")
        assert "Duplicate visual referenced" in report
        assert "NPS Score Visual" in report
        assert "1.1" in report and "2.1" in report

    def test_unique_visuals_no_duplicate_warning(self):
        sub1 = _make_sub("1.1", visual=self._visual("Visual A"))
        sub2 = _make_sub("2.1", visual=self._visual("Visual B"))
        parts = [_make_part(1, [sub1])] + [_make_part(2, [sub2])] + [_make_part(i) for i in range(3, 8)]
        spec = _make_spec(parts)
        report = generate_coverage_report(spec, section_filter="visuals_manifest")
        assert "Duplicate visual" not in report

    def test_no_visuals_produces_clean_message(self):
        spec = _make_spec()
        report = generate_coverage_report(spec, section_filter="visuals_manifest")
        assert "No visuals declared" in report


# ── 5. Per-part filter ────────────────────────────────────────────────────────

class TestPartFilter:
    def test_part_filter_restricts_output(self):
        spec = _make_spec()
        report = generate_coverage_report(spec, part_filter=3)
        assert "Part 3" in report
        assert "Part 1" not in report

    def test_invalid_part_filter_message(self):
        spec = _make_spec()
        report = generate_coverage_report(spec, part_filter=9)
        assert "No part with id=9" in report


# ── 6. Integration test — real YAML ──────────────────────────────────────────

class TestRealSpecIntegration:
    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_generates_non_empty_report(self):
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        report = generate_coverage_report(result.spec, result.findings)
        assert len(report) > 100

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_headline_coverage_line_present(self):
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        report = generate_coverage_report(result.spec, result.findings)
        # Structure check — does not hard-code the exact percentage
        assert "Automatable (auto+hybrid):" in report

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_data_request_checklist_header_present(self):
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        report = generate_coverage_report(result.spec, result.findings)
        assert "data request checklist" in report.lower()

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_all_7_sections_present(self):
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        report = generate_coverage_report(result.spec, result.findings)
        for i in range(1, 8):
            assert f"## {i}." in report or (i == 1 and "#" in report)

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_duplicate_visual_flagged_in_real_spec(self):
        """The known 4.2/4.3 visual name collision should appear in the manifest."""
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        report = generate_coverage_report(
            result.spec, result.findings, section_filter="visuals_manifest"
        )
        # The real spec has a known duplicate visual name between 4.2 and 4.3
        assert "Duplicate visual referenced" in report

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_section_filter_data_demands_standalone(self):
        from report_spec import load_spec
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        section = generate_coverage_report(
            result.spec, section_filter="data_demands"
        )
        assert "distinct survey questions" in section
        # Should not contain per-part breakdown header
        assert "Per-Part Breakdown" not in section
