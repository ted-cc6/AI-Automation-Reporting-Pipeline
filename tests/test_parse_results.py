"""
Unit tests for qualitative/parse_results.py -- focused on the executive-summary
extension (Phase D): top_findings/top_actions are now required keys alongside
the pre-existing executive_summary, threaded straight into the saved
qualitative_results.json for generation/assembler.py's executive-summary
section to render.
Run: pytest tests/test_parse_results.py -v
"""
from __future__ import annotations

import pandas as pd
import pytest

from qualitative.parse_results import REQUIRED_TOP_KEYS, _lookup_profile, _validate


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


class TestLookupProfile:
    def _df(self):
        return pd.DataFrame({
            "client_id": ["CI-00042"],
            "q_sex": ["Female"],
            "q_client_age": [34],
            "branch": ["Branch A"],
            "country": ["Bolivia"],
            "flag_paid_claimant": [False],
            "flag_child_wellbeing_denominator": [True],
        }, index=[42])

    def test_profile_carries_client_id_for_traceable_appendix_refs(self):
        # generation/assembler.py's _protection_flag_ref() needs client_id
        # (plus branch) to render a reference the client protection team can
        # actually look up -- a row_id/row-index number means nothing to them
        # and doesn't survive a re-run of the pipeline.
        profile = _lookup_profile("row_0042", self._df())
        assert profile["client_id"] == "CI-00042"
        assert profile["branch"] == "Branch A"

    def test_missing_client_id_column_returns_none(self):
        df = self._df().drop(columns=["client_id"])
        profile = _lookup_profile("row_0042", df)
        assert profile["client_id"] is None

    def test_unresolvable_row_id_returns_empty_profile(self):
        profile = _lookup_profile("row_9999", self._df())
        assert profile == {}
