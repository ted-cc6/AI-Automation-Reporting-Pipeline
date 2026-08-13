"""
Unit tests for analysis_engine/sections/part_11.py -- the Credit Life
Module (africa report_scope only). Focused on the two-base discipline:
awareness is measured against ALL credit-life clients, valuable_share
against only the aware subgroup -- these must never share a denominator.
Run: pytest tests/test_part_11.py -v
"""
from __future__ import annotations

import pandas as pd

from analysis_engine.sections.part_11 import calculate


class _FakeDataset:
    def __init__(self, df: pd.DataFrame):
        self.credit_life = df


def _df(n=10, additional_value=None):
    # q_credit_other_benefits is the multi-select PARENT column -- a Python
    # list of selected option labels per respondent (ranked_options() reads
    # this list column directly, not the individual boolean children).
    data = {
        "q_credit_other_benefits": [["Help with medical or hospital costs"] for _ in range(n)],
    }
    if additional_value is not None:
        data["q_credit_additional_value"] = additional_value
    return pd.DataFrame(data)


class TestCreditLifeModule:
    def test_awareness_and_valuable_share_use_different_bases(self):
        # n=40, kept >= LOW_N_THRESHOLD (30) so results aren't suppressed:
        # 8 unaware, 32 aware (of the 32 aware, 16 say valuable, 16 say
        # not) -- awareness base must be 40, valuable_share base must be
        # 32, and the two percentages must not share a denominator.
        additional_value = pd.Series(
            ["I am not aware of the additional benefits"] * 8
            + ["Very valuable"] * 10
            + ["Somewhat valuable"] * 6
            + ["Not valuable at all"] * 10
            + ["Neither valuable nor not valuable"] * 6
        )
        ds = _FakeDataset(_df(n=40, additional_value=additional_value))
        result = calculate(ds, {})

        av = result["additional_value"]
        assert av["n_base"] == 40
        assert av["awareness"]["n_valid"] == 40
        assert av["awareness"]["suppressed"] is False
        assert av["awareness"]["value"] == 32 / 40

        vs = av["valuable_share"]
        assert vs["n_base"] == 32  # only the aware subgroup
        assert vs["result"]["n_valid"] == 32
        assert vs["result"]["suppressed"] is False
        assert vs["result"]["value"] == 16 / 32  # 16 of 32 aware clients said valuable

    def test_somewhat_not_valuable_counts_as_aware_but_not_valuable(self):
        # "Somewhat not valuable" is a real observed value absent from
        # data_loader/value_coding_map.yaml's documented option list (a
        # separate pre-existing data-quality gap) -- it must still count as
        # an aware response (the client rated it), just not a valuable one.
        # n=32, kept >= LOW_N_THRESHOLD (30).
        additional_value = pd.Series(["Somewhat not valuable"] * 16 + ["Very valuable"] * 16)
        ds = _FakeDataset(_df(n=32, additional_value=additional_value))
        result = calculate(ds, {})

        av = result["additional_value"]
        assert av["awareness"]["value"] == 1.0  # both are aware responses
        assert av["valuable_share"]["result"]["value"] == 0.5  # only half is valuable

    def test_other_benefits_used_ranks_by_frequency(self):
        ds = _FakeDataset(_df(n=32))
        result = calculate(ds, {})
        ranked = result["other_benefits_used"]["headline"]["ranked"]
        assert ranked[0]["option"] == "Help with medical or hospital costs"
        assert ranked[0]["n"] == 32

    def test_missing_columns_degrade_to_not_applicable(self):
        ds = _FakeDataset(pd.DataFrame({"unrelated": [1, 2, 3]}))
        result = calculate(ds, {})
        assert result["other_benefits_used"]["headline"]["not_applicable"] is True
        assert result["additional_value"]["awareness"]["not_applicable"] is True
