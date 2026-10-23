"""Theme labels reach the writer's payload AND the rendered Executive Summary caption verbatim,
so they bypass both the prompt rules and the writer rewrite. Test6 proved it: the Resilience
label "... and realized preparedness" came straight back in the executive summary prose. Every
label must therefore pass the causal-language hard tier on its own."""
import ast
from pathlib import Path

from writer.causal_lint import lint_text

SOURCE = Path(__file__).resolve().parents[1] / "build_executive_summary.py"


def _theme_labels() -> list:
    labels = []
    for node in ast.walk(ast.parse(SOURCE.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name == "_mean_theme" and len(node.args) >= 2 and isinstance(node.args[1], ast.Constant):
            labels.append(node.args[1].value)
        for kw in node.keywords:
            if kw.arg == "metric_label" and isinstance(kw.value, ast.Constant):
                labels.append(kw.value.value)
    return labels


def test_labels_are_found():
    labels = _theme_labels()
    assert len(labels) >= 6
    assert any(label.startswith("Unweighted mean of savings increase") for label in labels)


def test_no_theme_label_carries_causal_or_overclaiming_wording():
    offenders = {label: [h.term for h in lint_text(label, include_review=False)] for label in _theme_labels()}
    assert {k: v for k, v in offenders.items() if v} == {}
