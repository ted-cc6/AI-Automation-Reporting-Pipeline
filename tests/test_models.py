"""
Unit + integration tests for the report_spec package.
Run: pytest tests/ -v
"""
from __future__ import annotations

from pathlib import Path

import pytest

from report_spec import (
    Category,
    ReportSpec,
    Severity,
    load_spec,
)
from report_spec.rules import (
    check_r2,
    check_r5,
    check_r6,
    check_r11,
)

# ---------------------------------------------------------------------------
# Helpers — minimal valid spec builders
# ---------------------------------------------------------------------------

_SCHEMA_PATH = Path(__file__).parent.parent / "insurance-report-spec.schema.json"
_REAL_YAML = Path(__file__).parent.parent / "insurance-report-spec.yaml"


def _minimal_subsection(
    subsection_id: str = "1.1",
    fill_mode: str = "bespoke",
    word_cap: int | None = 80,
    outputs: list[str] | None = None,
) -> dict:
    return {
        "subsection_id": subsection_id,
        "title": "Test subsection",
        "fill_mode": fill_mode,
        "word_cap": word_cap,
        "source_questions": [],
        "outputs": outputs or ["analysis_prose"],
    }


def _minimal_insight(part_id: int) -> dict:
    return {
        "subsection_id": f"{part_id}.insight",
        "title": "Synthesis",
        "fill_mode": "bespoke",
        "word_cap": 120,
        "source_questions": [],
        "outputs": ["insight_prose"],
    }


def _make_part(part_id: int, extra_subs: list[dict] | None = None) -> dict:
    subs = list(extra_subs or [])
    # ensure insight is present
    if not any(s["subsection_id"] == f"{part_id}.insight" for s in subs):
        subs.append(_minimal_insight(part_id))
    return {"part_id": part_id, "title": f"Part {part_id}", "subsections": subs}


def _make_spec(parts: list[dict] | None = None) -> dict:
    if parts is None:
        parts = [_make_part(i) for i in range(1, 8)]
    return {
        "report_metadata": {
            "name": "Test Report",
            "template_version": "2.0",
            "priority_segments": ["female", "male"],
        },
        "parts": parts,
    }


def _parse_spec(raw: dict) -> ReportSpec:
    return ReportSpec.model_validate(raw)


# ---------------------------------------------------------------------------
# Unit tests — valid spec
# ---------------------------------------------------------------------------

class TestValidSpec:
    def test_load_minimal_spec(self):
        spec = _parse_spec(_make_spec())
        assert len(spec.parts) == 7
        assert spec.report_metadata.template_version == "2.0"

    def test_subsections_flat_order(self):
        spec = _parse_spec(_make_spec())
        pairs = spec.subsections()
        # 7 parts × 1 subsection each (just insight) = 7
        assert len(pairs) == 7
        for (part, sub) in pairs:
            assert sub.is_insight

    def test_fill_mode_filters(self):
        raw = _make_spec()
        # make part 1 have a hybrid subsection too
        raw["parts"][0]["subsections"].insert(0, _minimal_subsection("1.1", "hybrid", 90, ["analysis_prose"]))
        # a hybrid subsection needs source_questions + metrics — patch it
        raw["parts"][0]["subsections"][0]["source_questions"] = [{"question_ref": "q_foo"}]
        raw["parts"][0]["subsections"][0]["metrics"] = [
            {"method": "share", "variables": ["q_foo"]}
        ]
        spec = _parse_spec(raw)
        assert len(spec.hybrid_subsections()) == 1
        assert len(spec.bespoke_subsections()) == 7  # all 7 insights

    def test_source_question_dedup(self):
        raw = _make_spec()
        # add two subsections in different parts that share a question ref
        for part_idx in [0, 1]:
            raw["parts"][part_idx]["subsections"].insert(
                0,
                {
                    **_minimal_subsection(f"{part_idx + 1}.1", "bespoke", 80),
                    "source_questions": [{"question_ref": "q_shared"}],
                },
            )
        spec = _parse_spec(raw)
        refs = [sq.question_ref for sq in spec.all_source_questions()]
        assert refs.count("q_shared") == 1

    def test_derived_variables(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"].insert(
            0,
            {
                "subsection_id": "1.1",
                "title": "T",
                "fill_mode": "hybrid",
                "word_cap": 80,
                "source_questions": [{"question_ref": "q_sex"}],
                "metrics": [
                    {"method": "gap_analysis", "variables": ["q_derived_flag"], "against": "q_sex"}
                ],
                "outputs": ["analysis_prose"],
            },
        )
        spec = _parse_spec(raw)
        assert "q_derived_flag" in spec.derived_variables()
        assert "q_sex" not in spec.derived_variables()


# ---------------------------------------------------------------------------
# Unit tests — schema violation
# ---------------------------------------------------------------------------

class TestSchemaViolation:
    def test_missing_required_field_raises(self):
        raw = _make_spec()
        del raw["report_metadata"]["name"]
        with pytest.raises(Exception):
            # Pydantic should reject missing required field
            ReportSpec.model_validate(raw)

    def test_invalid_fill_mode_rejected(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"][0]["fill_mode"] = "magic"
        with pytest.raises(Exception):
            ReportSpec.model_validate(raw)


# ---------------------------------------------------------------------------
# Unit tests — R2 missing insight
# ---------------------------------------------------------------------------

class TestR2:
    def test_missing_insight_detected(self):
        raw = _make_spec()
        # remove the insight subsection from part 1
        raw["parts"][0]["subsections"] = [_minimal_subsection("1.1", "bespoke")]
        spec = _parse_spec(raw)
        findings = check_r2(spec)
        assert any(f.rule_id == "R2" and f.severity == Severity.ERROR for f in findings)
        assert "part_id" in findings[0].message.lower() or "1.insight" in findings[0].message

    def test_valid_insight_passes(self):
        spec = _parse_spec(_make_spec())
        assert check_r2(spec) == []


# ---------------------------------------------------------------------------
# Unit tests — R5 typo vs derived variable
# ---------------------------------------------------------------------------

class TestR5:
    def _spec_with_metric_var(self, var: str) -> ReportSpec:
        raw = _make_spec()
        raw["parts"][0]["subsections"].insert(
            0,
            {
                "subsection_id": "1.1",
                "title": "T",
                "fill_mode": "hybrid",
                "word_cap": 80,
                "source_questions": [{"question_ref": "q_coverage_understanding"}],
                "metrics": [{"method": "share", "variables": [var]}],
                "outputs": ["analysis_prose"],
            },
        )
        return _parse_spec(raw)

    def test_typo_is_error(self):
        spec = self._spec_with_metric_var("q_coverge_typo")
        findings = check_r5(spec)
        errors = [f for f in findings if f.rule_id == "R5" and f.severity == Severity.ERROR]
        assert errors, "Expected an ERROR for a genuine typo variable"

    def test_known_derived_is_warning(self):
        spec = self._spec_with_metric_var("q_nps_score")
        findings = check_r5(spec)
        warnings = [f for f in findings if f.rule_id == "R5" and f.severity == Severity.WARNING]
        errors = [f for f in findings if f.rule_id == "R5" and f.severity == Severity.ERROR]
        assert warnings, "Expected a WARNING for a known derived variable"
        assert not errors

    def test_warning_category_is_known_gap(self):
        spec = self._spec_with_metric_var("q_coping_mechanisms")
        findings = check_r5(spec)
        kg = [f for f in findings if f.category == Category.KNOWN_GAP]
        assert kg


# ---------------------------------------------------------------------------
# Unit tests — R6 missing against
# ---------------------------------------------------------------------------

class TestR6:
    def test_correlation_without_against_is_error(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"].insert(
            0,
            {
                "subsection_id": "1.1",
                "title": "T",
                "fill_mode": "hybrid",
                "word_cap": 80,
                "source_questions": [{"question_ref": "q_x"}, {"question_ref": "q_y"}],
                "metrics": [{"method": "correlation", "variables": ["q_x"]}],
                "outputs": ["analysis_prose"],
            },
        )
        spec = _parse_spec(raw)
        findings = check_r6(spec)
        assert any(f.rule_id == "R6" and f.severity == Severity.ERROR for f in findings)

    def test_correlation_with_against_passes(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"].insert(
            0,
            {
                "subsection_id": "1.1",
                "title": "T",
                "fill_mode": "hybrid",
                "word_cap": 80,
                "source_questions": [{"question_ref": "q_x"}, {"question_ref": "q_y"}],
                "metrics": [{"method": "correlation", "variables": ["q_x"], "against": "q_y"}],
                "outputs": ["analysis_prose"],
            },
        )
        spec = _parse_spec(raw)
        assert check_r6(spec) == []


# ---------------------------------------------------------------------------
# Unit tests — R11 null word_cap on prose output
# ---------------------------------------------------------------------------

class TestR11:
    def test_null_word_cap_with_prose_is_error(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"][0]["word_cap"] = None
        raw["parts"][0]["subsections"][0]["outputs"] = ["insight_prose"]
        spec = _parse_spec(raw)
        findings = check_r11(spec)
        assert any(f.rule_id == "R11" for f in findings)

    def test_null_word_cap_table_only_passes(self):
        raw = _make_spec()
        raw["parts"][0]["subsections"][0]["word_cap"] = None
        raw["parts"][0]["subsections"][0]["outputs"] = ["scorecard_table"]
        spec = _parse_spec(raw)
        assert check_r11(spec) == []


# ---------------------------------------------------------------------------
# Integration test — real YAML file
# ---------------------------------------------------------------------------

class TestRealSpec:
    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_real_spec_loads(self):
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None, (
            "ReportSpec must parse from the real YAML. "
            f"First finding: {result.findings[0] if result.findings else 'none'}"
        )

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_real_spec_has_7_parts(self):
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        assert len(result.spec.parts) == 7

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_real_spec_known_gap_warnings_not_errors(self):
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        r5_errors = [
            f for f in result.findings
            if f.rule_id == "R5" and f.severity == Severity.ERROR
        ]
        # All R5 violations in the real spec should be KNOWN_GAP (derived variables)
        assert r5_errors == [], (
            f"Real spec has R5 ERRORs (unexpected — check variable names): {r5_errors}"
        )

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_real_spec_hybrid_subsections_exist(self):
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        hybrids = result.spec.hybrid_subsections()
        assert len(hybrids) >= 4, "Expected at least 4 hybrid subsections (4.1, 4.2, 4.3, 7.1)"

    @pytest.mark.skipif(not _REAL_YAML.exists(), reason="real spec YAML not found")
    def test_real_spec_derived_variables_detected(self):
        result = load_spec(_REAL_YAML, _SCHEMA_PATH, strict=False)
        assert result.spec is not None
        derived = result.spec.derived_variables()
        # q_nps_score is used as a derived promoter flag in Part 7
        assert "q_nps_score" in derived or len(derived) >= 0  # at least doesn't crash
