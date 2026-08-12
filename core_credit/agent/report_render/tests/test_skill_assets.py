import pytest

from report_render import skill_assets


def test_get_logo_bytes_returns_a_real_png_for_every_variant():
    for variant in ("primary", "reverse", "mono"):
        data = skill_assets.get_logo_bytes(variant).read()
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(data) > 1000


def test_get_logo_bytes_rejects_an_unknown_variant():
    with pytest.raises(ValueError, match="Unknown logo variant"):
        skill_assets.get_logo_bytes("nonexistent")
