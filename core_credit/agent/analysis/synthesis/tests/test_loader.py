import pytest

from schemas.client_satisfaction import ClientSatisfactionSection
from synthesis.loader import canonical_output_path, load_section


def test_canonical_output_path_raises_clearly_for_unregistered_section():
    with pytest.raises(FileNotFoundError, match="No canonical real-run output registered"):
        canonical_output_path("not_a_real_section_id")


def test_canonical_output_path_resolves_a_real_file():
    path = canonical_output_path("client_satisfaction")
    assert path.exists()


def test_load_section_parses_back_into_the_right_schema():
    section = load_section("client_satisfaction")
    assert isinstance(section, ClientSatisfactionSection)
    assert section.nps.n > 0


def test_load_section_accepts_an_explicit_path_override(tmp_path):
    real_path = canonical_output_path("client_satisfaction")
    copy_path = tmp_path / "copy.json"
    copy_path.write_text(real_path.read_text(encoding="utf-8"), encoding="utf-8")

    section = load_section("client_satisfaction", path=copy_path)
    assert isinstance(section, ClientSatisfactionSection)
