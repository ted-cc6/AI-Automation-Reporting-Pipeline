"""CC-089: codebook coding and its cache, with the LLM call stubbed out."""

import json

import pytest

from qualitative_agent import codebook as cb
from qualitative_agent.data_prep import FreeTextResponse

CODEBOOK = {
    "question": "nps_detractor",
    "version": 1,
    "themes": [
        {"code": "interest", "label": "Lower interest rates", "definition": "Asks for lower interest."},
        {"code": "staff", "label": "Better staff attitude", "definition": "Complains about staff conduct."},
    ],
}


def _r(cid, text, country="KEN"):
    return FreeTextResponse(
        client_id=cid, text=text, source_field="CLIENTSAT01b", gender="Female", age=40,
        branch="B1", country=country, loan_cycle=2,
    )


RESPONSES = [
    _r("1", "Please reduce the interest rate a lot"),
    _r("2", "The loan officer was rude to me at the branch", "RWA"),
    _r("3", "Interest is too high and staff are rude", "UGA"),
    _r("4", "no comment"),
]


def _fake_coder(answers):
    """Stub for code_batch: codes by keyword, and counts how often it is called."""
    calls = []

    def fake(responses, codebook, task, max_retries=1):
        calls.append(len(responses))
        out = {}
        for i, r in enumerate(responses):
            text = r.text.lower()
            codes = [c for c, word in answers if word in text]
            out[i] = codes or [cb.OTHER_CODE]
        return out

    return fake, calls


@pytest.fixture
def coder(monkeypatch):
    fake, calls = _fake_coder([("interest", "interest"), ("staff", "rude")])
    monkeypatch.setattr(cb, "code_batch", fake)
    return calls


def test_shares_and_order(tmp_path, coder):
    out = cb.tag_with_codebook("detractor_pain_points", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=tmp_path / "c.json")
    assert out.base_n == 4
    assert [(t.theme, t.frequency) for t in out.themes] == [("Better staff attitude", 2), ("Lower interest rates", 2)]
    assert out.themes[0].share_of_respondents == 0.5
    # "other" is never reported as a theme
    assert all(t.theme not in ("other", "Other") for t in out.themes)


def test_rerun_uses_cache_and_matches(tmp_path, coder):
    path = tmp_path / "c.json"
    first = cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    second = cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    assert coder == [4]  # second run made no LLM call
    assert first.model_dump() == second.model_dump()


def test_cache_holds_no_client_text(tmp_path, coder):
    path = tmp_path / "c.json"
    cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    raw = path.read_text(encoding="utf-8")
    assert "interest rate" not in raw and "rude" not in raw


def test_version_bump_recodes(tmp_path, coder):
    path = tmp_path / "c.json"
    cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    bumped = {**CODEBOOK, "version": 2}
    cb.tag_with_codebook("d", "nps_detractor", RESPONSES, bumped, "task", cache_path=path)
    assert coder == [4, 4]


def test_changed_answer_text_is_a_miss(tmp_path, coder):
    path = tmp_path / "c.json"
    cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    edited = RESPONSES[:3] + [_r("4", "staff were rude")]
    cb.tag_with_codebook("d", "nps_detractor", edited, CODEBOOK, "task", cache_path=path)
    assert coder == [4, 1]


def test_uncoded_answers_are_not_cached(tmp_path, monkeypatch):
    calls = []

    def skips_last(responses, codebook, task, max_retries=1):
        calls.append(len(responses))
        return {i: ["interest"] for i in range(len(responses) - 1)}

    monkeypatch.setattr(cb, "code_batch", skips_last)
    path = tmp_path / "c.json"
    out = cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    assert out.base_n == 4  # still in the base
    assert len(json.loads(path.read_text(encoding="utf-8"))) == 3
    cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=path)
    assert calls == [4, 1]  # only the uncoded answer is retried


def test_clean_codes_keeps_only_codebook_codes():
    valid = {"interest", "staff", cb.OTHER_CODE}
    assert cb._clean_codes(["interest", "made_up", "interest"], valid) == ["interest"]
    assert cb._clean_codes(["made_up"], valid) == [cb.OTHER_CODE]
    assert cb._clean_codes(["other", "staff"], valid) == ["staff"]


@pytest.mark.parametrize(
    "bad",
    [
        {"version": 1, "themes": []},
        {"version": "1", "themes": CODEBOOK["themes"]},
        {"version": 1, "themes": CODEBOOK["themes"] * 2},
        {"version": 1, "themes": [{"code": "other", "label": "x", "definition": "y"}]},
        {"version": 1, "themes": [{"code": "a", "label": "x"}]},
    ],
)
def test_validate_rejects_bad_codebooks(bad):
    with pytest.raises(ValueError):
        cb.validate_codebook(bad)


def test_falls_back_to_open_coding_without_approved_file(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(cb, "theme_tag_full_dataset", lambda label, responses, task: seen.append(label) or "open")
    assert cb.tag_responses("d", "nps_detractor", RESPONSES, "task", codebook_dir=tmp_path) == "open"
    assert seen == ["d"]


def test_uses_approved_file_when_present(tmp_path, coder):
    (tmp_path / "nps_detractor_approved.json").write_text(json.dumps(CODEBOOK), encoding="utf-8")
    out = cb.tag_responses("d", "nps_detractor", RESPONSES, "task", codebook_dir=tmp_path, cache_path=tmp_path / "c.json")
    assert {t.theme for t in out.themes} == {"Lower interest rates", "Better staff attitude"}


def test_malformed_approved_file_raises(tmp_path):
    (tmp_path / "nps_detractor_approved.json").write_text(json.dumps({"version": 1, "themes": []}), encoding="utf-8")
    with pytest.raises(ValueError):
        cb.load_approved_codebook("nps_detractor", tmp_path)


def test_verbatim_pick_is_order_independent(tmp_path, coder):
    a = cb.tag_with_codebook("d", "nps_detractor", RESPONSES, CODEBOOK, "task", cache_path=tmp_path / "a.json")
    b = cb.tag_with_codebook("d", "nps_detractor", list(reversed(RESPONSES)), CODEBOOK, "task", cache_path=tmp_path / "b.json")
    quotes = lambda s: [[v.quote for v in t.representative_verbatims] for t in s.themes]
    assert quotes(a) == quotes(b)


def _write_draft(tmp_path, themes):
    draft = {"question": "nps_detractor", "version": 1, "themes": themes}
    (tmp_path / "nps_detractor_draft.json").write_text(json.dumps(draft), encoding="utf-8")


def test_approve_strips_review_fields(tmp_path):
    themes = [{**t, "_review_examples": ["a client answer"], "_review_open_coding_share": 0.4} for t in CODEBOOK["themes"]]
    _write_draft(tmp_path, themes)
    approved = cb.approve_draft("nps_detractor", tmp_path)
    raw = (tmp_path / "nps_detractor_approved.json").read_text(encoding="utf-8")
    assert "a client answer" not in raw and "_review" not in raw
    assert approved["version"] == 1


def test_reapprove_bumps_version_only_on_change(tmp_path):
    _write_draft(tmp_path, CODEBOOK["themes"])
    cb.approve_draft("nps_detractor", tmp_path)
    assert cb.approve_draft("nps_detractor", tmp_path)["version"] == 1
    edited = [CODEBOOK["themes"][0], {**CODEBOOK["themes"][1], "definition": "Rude or dismissive staff."}]
    _write_draft(tmp_path, edited)
    assert cb.approve_draft("nps_detractor", tmp_path)["version"] == 2
