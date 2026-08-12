from dashboard_visuals.lookup import (
    MISSING_PLACEHOLDER_TEXT,
    find_dashboard_visual,
    find_dashboard_visuals,
    missing_dashboard_visuals,
)


def test_finds_a_png(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"fake png bytes")
    result = find_dashboard_visual("3.1", tmp_path)
    assert result.found is True
    assert result.path == tmp_path / "3.1.png"
    assert result.placeholder_text is None


def test_finds_a_jpg(tmp_path):
    (tmp_path / "gender_scorecard.jpg").write_bytes(b"fake jpg bytes")
    result = find_dashboard_visual("gender_scorecard", tmp_path)
    assert result.found is True
    assert result.path == tmp_path / "gender_scorecard.jpg"


def test_finds_a_jpeg(tmp_path):
    (tmp_path / "3-insight.jpeg").write_bytes(b"fake jpeg bytes")
    result = find_dashboard_visual("3-insight", tmp_path)
    assert result.found is True
    assert result.path == tmp_path / "3-insight.jpeg"


def test_png_wins_when_multiple_extensions_exist(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"png")
    (tmp_path / "3.1.jpg").write_bytes(b"jpg")
    result = find_dashboard_visual("3.1", tmp_path)
    assert result.path == tmp_path / "3.1.png"


def test_missing_file_returns_template_placeholder(tmp_path):
    result = find_dashboard_visual("3.2", tmp_path)
    assert result.found is False
    assert result.path is None
    assert result.placeholder_text == MISSING_PLACEHOLDER_TEXT


def test_does_not_match_a_different_subsection_id(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"png")
    result = find_dashboard_visual("3.10", tmp_path)  # must not fuzzy-match "3.1"
    assert result.found is False


def test_find_dashboard_visuals_batch_mixed_found_and_missing(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"png")
    results = find_dashboard_visuals(["3.1", "3.2", "3-insight"], tmp_path)
    assert results["3.1"].found is True
    assert results["3.2"].found is False
    assert results["3-insight"].found is False


def test_missing_dashboard_visuals_lists_only_the_gaps(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"png")
    results = find_dashboard_visuals(["3.1", "3.2", "3-insight"], tmp_path)
    assert missing_dashboard_visuals(results) == ["3.2", "3-insight"]


def test_missing_dashboard_visuals_empty_when_everything_found(tmp_path):
    (tmp_path / "3.1.png").write_bytes(b"png")
    (tmp_path / "3.2.png").write_bytes(b"png")
    results = find_dashboard_visuals(["3.1", "3.2"], tmp_path)
    assert missing_dashboard_visuals(results) == []
