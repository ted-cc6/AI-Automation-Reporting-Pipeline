"""CC-099: theme-share changes between waves."""

import pandas as pd
import pytest

from schemas.common import QualitativeSynthesis, ThemeFinding
from yoy import themes as th
from yoy.table import build_yoy_section
from yoy.waves import COUNTRY_COL


def test_theme_change_tests_shares_and_skips_counts_only():
    c = th.theme_change("High interest", 100, 400, 60, 400)
    assert c["value_2025"] == 0.25 and c["value_2026"] == 0.15 and c["change_pts"] == pytest.approx(-10)
    assert c["significant"]
    counts = th.theme_change("Harassment", 7, 400, 3, 380, test=False)
    assert counts["count_2026"] == 3 and counts["p_value"] is None and not counts["significant"]


def test_a_theme_absent_in_both_waves_is_not_tested():
    assert th.theme_change("x", 0, 100, 0, 100)["p_value"] is None


def test_compute_uses_approved_codebooks_on_the_comparison_set(monkeypatch):
    books = {"nps_detractor": {"version": 1, "themes": [{"label": "High interest"}, {"label": "Rude staff"}]}}
    monkeypatch.setattr(th, "load_approved_codebook", lambda q: books.get(q))
    seen = []

    def fake_counts(source, df, codebook):
        seen.append((source.question, sorted(set(df[COUNTRY_COL]))))
        n = len(df)
        return ({"High interest": n // 2}, n)

    monkeypatch.setattr(th, "_counts", fake_counts)
    a = pd.DataFrame({COUNTRY_COL: ["KEN"] * 100 + ["IND"] * 50})
    b = pd.DataFrame({COUNTRY_COL: ["KEN"] * 80})
    out = th.compute_theme_deltas(a, b, ["KEN"])
    assert [q["question"] for q in out] == ["nps_detractor"]  # sources without a codebook are skipped
    assert seen == [("nps_detractor", ["KEN"]), ("nps_detractor", ["KEN"])]  # India dropped
    q = out[0]
    assert q["block"] == "8.2" and q["n_2025"] == 100 and q["n_2026"] == 80
    assert [t["label"] for t in q["themes"]] == ["High interest", "Rude staff"]
    assert q["themes"][1]["count_2025"] == 0


def _deltas_with_themes():
    from yoy.tests.test_table import DELTAS

    return {
        **DELTAS,
        "themes": [
            {"question": "nps_detractor", "group": "detractors' reasons", "block": "8.2", "counts_only": False, "n_2025": 400, "n_2026": 400,
             "themes": [th.theme_change("High interest", 100, 400, 60, 400), th.theme_change("Rude staff", 40, 400, 42, 400)]},
            {"question": "protection_signals", "group": "protection signals", "block": None, "counts_only": True, "n_2025": 700, "n_2026": 650,
             "themes": [th.theme_change("Coercive collection", 7, 700, 3, 650, test=False)]},
        ],
    }


def test_table_carries_significant_themes_and_protection_counts():
    from yoy.tests.test_table import MANIFEST

    s = build_yoy_section(_deltas_with_themes(), MANIFEST)
    assert [(r.label, r.group) for r in s.theme_rows] == [("High interest", "detractors' reasons")]
    p = s.protection_rows[0]
    assert p.is_count and p.value_2025 == 7 and p.value_2026 == 3 and p.change_pts == -4 and p.note == "of 700 and 650 answers"


def test_writer_gets_theme_facts_only_for_its_block(tmp_path, monkeypatch):
    import json

    from writer import yoy_facts

    path = tmp_path / "d.json"
    path.write_text(json.dumps(_deltas_with_themes()), encoding="utf-8")
    monkeypatch.setenv(yoy_facts.ENV, str(path))
    yoy_facts._load.cache_clear()
    text, accepted = yoy_facts.facts_for("8.2")
    assert 'theme "High interest" (detractors\' reasons): 15.0% of answers in 2026 compared with 25.0% in 2025' in text
    assert "themes among detractors' reasons: Rude staff" in text
    assert "Coercive collection" not in text  # protection counts never reach the writer
    assert {15.0, 25.0, 10.0} <= accepted
    assert "Coercive collection" not in yoy_facts.facts_for("5-insight")[0]
    yoy_facts._load.cache_clear()


def test_small_theme_sets_are_not_tested_and_named_in_the_note(monkeypatch):
    from yoy.tests.test_table import MANIFEST

    books = {"other_child_improvements": {"version": 1, "themes": [{"label": "Schooling"}]}}
    monkeypatch.setattr(th, "load_approved_codebook", lambda q: books.get(q))
    monkeypatch.setattr(th, "_counts", lambda source, df, codebook: ({"Schooling": len(df) // 2}, len(df)))
    a, b = pd.DataFrame({COUNTRY_COL: ["KEN"] * 51}), pd.DataFrame({COUNTRY_COL: ["KEN"] * 300})
    q = th.compute_theme_deltas(a, b, ["KEN"])[0]
    assert q["small_base"] and q["themes"][0]["p_value"] is None
    s = build_yoy_section({**_deltas_with_themes(), "themes": [q]}, MANIFEST)
    assert "other child improvements (51 and 300 answers)" in s.note and s.theme_rows == []
