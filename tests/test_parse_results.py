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

from qualitative.parse_results import (
    REQUIRED_TOP_KEYS,
    _count_themes,
    _humanize_top_drivers,
    _lookup_profile,
    _validate,
)


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


# ---------------------------------------------------------------------------
# Theme code humanization -- a real generated report shipped with the raw
# taxonomy code "claims_process" sitting unlabeled in reader-facing prose
# (the synthesis prompt allows it as a top_drivers value). Both theme_counts
# and top_drivers must never expose a raw snake_case code to a reader.
# ---------------------------------------------------------------------------

class TestCountThemes:
    def test_theme_counts_keys_are_human_readable_not_raw_codes(self):
        nps_tags = {
            "promoters": [["row_0001", ["product_value"]], ["row_0002", ["product_value"]]],
            "passives": [["row_0003", ["claims_process"]]],
            "detractors": [],
        }
        counts = _count_themes(nps_tags)
        assert counts["promoters"] == {"product value for money": 2}
        assert counts["passives"] == {"the claims process": 1}
        assert "product_value" not in counts["promoters"]
        assert "claims_process" not in counts["passives"]

    def test_counting_happens_before_relabeling_so_synonyms_dont_fragment(self):
        # Both entries are the same raw code; must still collapse into one
        # counted, humanized key -- not two separate near-duplicate keys.
        nps_tags = {
            "promoters": [["row_0001", ["staff_service"]], ["row_0002", ["staff_service"]]],
            "passives": [], "detractors": [],
        }
        counts = _count_themes(nps_tags)
        assert counts["promoters"] == {"staff service": 2}

    def test_empty_tags_produce_empty_counts(self):
        counts = _count_themes({"promoters": [], "passives": [], "detractors": []})
        assert counts == {"promoters": {}, "passives": {}, "detractors": {}}


class TestHumanizeTopDrivers:
    def test_raw_taxonomy_code_is_relabeled(self):
        section_insights = {
            "part2": {"theme_summary": "x", "top_drivers": ["claims_process", "documentation burden"],
                      "sentiment_split": {"positive": 1, "negative": 1, "neutral": 0}},
        }
        result = _humanize_top_drivers(section_insights)
        assert result["part2"]["top_drivers"] == ["the claims process", "documentation burden"]

    def test_freeform_label_passes_through_unchanged(self):
        section_insights = {
            "part4": {"theme_summary": "x", "top_drivers": ["slow payout", "lack of premium clarity"],
                      "sentiment_split": {"positive": 0, "negative": 1, "neutral": 0}},
        }
        result = _humanize_top_drivers(section_insights)
        assert result["part4"]["top_drivers"] == ["slow payout", "lack of premium clarity"]

    def test_missing_top_drivers_key_is_left_alone(self):
        section_insights = {"part1": {"theme_summary": "x"}}
        result = _humanize_top_drivers(section_insights)
        assert result["part1"] == {"theme_summary": "x"}

    def test_non_dict_entry_passes_through_unchanged(self):
        section_insights = {"part1": None}
        result = _humanize_top_drivers(section_insights)
        assert result["part1"] is None

    def test_empty_section_insights_returns_empty_dict(self):
        assert _humanize_top_drivers({}) == {}
        assert _humanize_top_drivers(None) == {}
