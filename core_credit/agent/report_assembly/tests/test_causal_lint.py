from report_assembly.causal_lint import format_hits, lint_report, main
from schemas.common import WrittenText


def _block(subsection_id, text):
    return {"subsection_id": subsection_id, "text": text, "word_count": len(text.split()), "within_cap": True}


def test_walks_nested_written_text_blocks_and_skips_non_narrative():
    report = {
        "run_id": "drives nothing -- not a narrative block",
        "agency": {
            "household_influence_improved_analysis": _block("6.2", "Receiving other services lifts household influence."),
            "insight_verbatims": [{"quote": "the loan drives my business", "country": "KEN"}],
        },
        "client_satisfaction": {"nps_analysis": _block("8.1", "The NPS of 69 is higher than the MFI Index's 58.")},
    }
    hits = lint_report(report)
    assert [(h.subsection_id, h.term, h.tier) for h in hits] == [("6.2", "lifts", "hard")]
    assert hits[0].path == "agency.household_influence_improved_analysis"


def test_accepts_a_pydantic_model():
    wt = WrittenText(subsection_id="executive-summary", text="Client satisfaction leads the story.", word_count=5, within_cap=True)
    assert [h.term for h in lint_report(wt)] == ["leads the story"]


def test_hard_only_drops_review_tier():
    report = {"x": _block("1.2", "Signaling a strong competitive moat.")}
    assert {h.tier for h in lint_report(report)} == {"hard", "review"}
    assert {h.tier for h in lint_report(report, include_review=False)} == {"hard"}


def test_format_and_cli_report_only(tmp_path, capsys):
    import json

    path = tmp_path / "report.json"
    path.write_text(json.dumps({"s": _block("3.1", "Our 45.8% outpaces the benchmark.")}), encoding="utf-8")
    assert main([str(path)]) == 0  # report-only: never fails
    out = capsys.readouterr().out
    assert "HARD: 1 hit(s) -- outpaces x1" in out
    assert "[outpaces] 3.1 (s)" in out
    assert format_hits([]) == "HARD: 0 hit(s)\nREVIEW: 0 hit(s)"
