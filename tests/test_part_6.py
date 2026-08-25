"""
Unit tests for analysis_engine/sections/part_6.py -- focused on the group
labels R-011 (session-10) settled on. _B's population (JSON key
"non_claimant", unchanged for path stability) is clients who experienced an
insured event but did not file, not the much larger population who simply
never had a claimable event at all -- q_claim_submitted is only ever asked
of clients who experienced an insured event, so a pandas boolean mask
(== False) can never match the rows that were never asked (NaN != False).
A real generated report labelled this group "Non-Claimant" and showed its
NPS as if directly comparable to the whole-portfolio NPS; "Non-Filer"
replaced that label but was itself opaque about what population it named.
Both are retired: the label now states the population directly ("Claimant
(filed)" / "Did not file"), backed by an explicit qualifier field the
scorecard header composes with the group's n (see generation/assembler.py's
_group_header()).
Run: pytest tests/test_part_6.py -v
"""
from __future__ import annotations

import pandas as pd

from analysis_engine.sections.part_6 import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame):
        self.df = df
        self.insured_event_base = df
        self.child_wellbeing_base = df


class TestPartSixGroupLabels:
    def _segment_masks(self, n_claimant: int, n_non_filer: int) -> dict:
        return {
            "claimant": pd.Series([True] * n_claimant + [False] * n_non_filer),
            "non_claimant": pd.Series([False] * n_claimant + [True] * n_non_filer),
        }

    def test_group_labels_state_the_population(self):
        df = pd.DataFrame(index=range(124))
        result = calculate(_FakeDataset(df), self._segment_masks(55, 69))
        assert result["groups"]["claimant"]["label"] == "Claimant"
        assert result["groups"]["claimant"]["qualifier"] == "filed"
        assert result["groups"]["non_claimant"]["label"] == "Did not file"
        assert "Non-Claimant" not in result["groups"]["non_claimant"]["label"]
        assert "Non-Filer" not in result["groups"]["non_claimant"]["label"]

    def test_group_counts_match_segment_masks(self):
        df = pd.DataFrame(index=range(124))
        result = calculate(_FakeDataset(df), self._segment_masks(55, 69))
        assert result["groups"]["claimant"]["n"] == 55
        assert result["groups"]["non_claimant"]["n"] == 69
