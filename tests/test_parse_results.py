"""
Unit tests for qualitative/parse_results.py -- focused on the executive-summary
extension (Phase D): top_findings/top_actions are now required keys alongside
the pre-existing executive_summary, threaded straight into the saved
qualitative_results.json for generation/assembler.py's executive-summary
section to render.
Run: pytest tests/test_parse_results.py -v
"""
from __future__ import annotations

import pytest

from qualitative.parse_results import REQUIRED_TOP_KEYS, _validate


def _base_raw(**overrides) -> dict:
    base = {
        "nps_tags": {"promoters": [], "passives": [], "detractors": []},
        "claims_other_tagged": {},
        "not_worth_it_themes": [],
        "other_subthemes": {},
        "section_verbatims": {
            "part1": ["row_0001"], "part2": ["row_0001"], "part3": ["row_0001"],
            "part4": ["row_0001"], "part5": ["row_0001"], "part6": ["row_0001"],
            "part7": ["row_0001"],
        },
        "protection_flags": [],
        "executive_summary": "Some summary.",
        "top_findings": ["Finding 1", "Finding 2", "Finding 3"],
        "top_actions": ["Action 1", "Action 2", "Action 3"],
    }
    base.update(overrides)
    return base


class TestRequiredTopKeys:
    def test_top_findings_and_top_actions_are_required(self):
        assert "top_findings" in REQUIRED_TOP_KEYS
        assert "top_actions" in REQUIRED_TOP_KEYS


class TestValidate:
    def test_complete_payload_passes(self):
        _validate(_base_raw())  # must not raise

    def test_missing_top_findings_raises(self):
        raw = _base_raw()
        del raw["top_findings"]
        with pytest.raises(ValueError, match="top_findings"):
            _validate(raw)

    def test_missing_top_actions_raises(self):
        raw = _base_raw()
        del raw["top_actions"]
        with pytest.raises(ValueError, match="top_actions"):
            _validate(raw)
