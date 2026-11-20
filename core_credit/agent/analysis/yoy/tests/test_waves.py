"""CC-093: wave split, comparison country set, partial flags, manifest."""

import pandas as pd

from yoy import waves as w


def _df(rows):
    return pd.DataFrame(rows, columns=[w.SUBMISSION_TIME_COL, w.COUNTRY_COL, "answer"])


def test_split_by_submission_year_keeps_columns_and_drops_unreadable_times():
    df = _df([
        ["2025-07-10T09:00:00", "KEN", "a"],
        ["2025-12-30T23:59:00", "KEN", "b"],
        ["2026-08-01T00:00:00", "KEN", "c"],
        ["not a date", "KEN", "d"],
    ])
    out = w.split_waves(df)
    assert sorted(out) == [2025, 2026]
    assert out[2025]["answer"].tolist() == ["a", "b"] and out[2026]["answer"].tolist() == ["c"]
    assert list(out[2026].columns) == list(df.columns)


def test_timezone_suffixes_are_read():
    assert w.wave_of(pd.Series(["2026-11-18T17:47:44+03:00", "2025-07-01T00:00:00Z"])).tolist() == [2026, 2025]


def test_country_counts_ignore_blanks():
    df = _df([["2025-07-01", "KEN", ""], ["2025-07-01", " KEN ", ""], ["2025-07-01", "", ""], ["2025-07-01", None, ""]])
    assert w.country_counts(df) == {"KEN": 2}


COUNTS = {
    2025: {"IND": 285, "KEN": 271, "MLI": 276, "SEN": 268, "XXX": 140},
    2026: {"KEN": 269, "MLI": 193, "SEN": 206, "XXX": 300},
}


def test_comparison_set_needs_the_minimum_in_every_wave():
    assert w.comparison_countries(COUNTS) == ["KEN", "MLI", "SEN"]


def test_partial_when_latest_wave_is_more_than_20_percent_short():
    assert w.partial_countries(COUNTS[2025], COUNTS[2026]) == ["MLI", "SEN"]
    assert w.partial_countries({"A": 100}, {"A": 80}) == []  # exactly 20% short is not partial


def test_manifest_records_set_exclusions_and_provisional_state():
    m = w.build_manifest(COUNTS, {2025: "a.csv", 2026: "b.csv"}, "export.csv", "2026-11-18T17:47:44", rows_without_wave=2)
    assert m["report_wave"] == 2026 and m["comparison_wave"] == 2025
    assert m["comparison_countries"] == ["KEN", "MLI", "SEN"]
    assert m["excluded_countries"] == {"IND": "no rows in 2026", "XXX": "below 150 rows (2025: 140)"}
    assert m["partial_countries"] == ["MLI", "SEN"]
    assert [x["rows"] for x in m["waves"]] == [1240, 968]
    assert m["provisional"] is True and m["rows_without_wave"] == 2
