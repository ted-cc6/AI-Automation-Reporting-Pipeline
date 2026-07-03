"""
coverage_report.py — Planning and stakeholder-communication tool for the
VisionFund Insurance Report spec. Answers "what does this spec commit us to
and how much is automatable?" without touching survey data or making network calls.

Usage
-----
    python coverage_report.py insurance-report-spec.yaml \\
        --schema insurance-report-spec.schema.json

    python coverage_report.py insurance-report-spec.yaml \\
        --schema insurance-report-spec.schema.json \\
        --markdown coverage.md --part 4

    python coverage_report.py insurance-report-spec.yaml \\
        --schema insurance-report-spec.schema.json \\
        --section data_demands
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

from report_spec import Finding, ReportSpec, Severity, load_spec
from report_spec.models import FillMode

# ── Rich (optional) ──────────────────────────────────────────────────────────
try:
    from rich.console import Console as _RichConsole
    from rich.markdown import Markdown as _RichMarkdown

    _RICH_CONSOLE = _RichConsole()
    HAS_RICH: bool = True
except ImportError:  # pragma: no cover
    HAS_RICH = False

# ── Section names (used for --section choices) ────────────────────────────────
SECTION_NAMES: list[str] = [
    "header",
    "automation_coverage",
    "per_part_breakdown",
    "data_demands",
    "derived_variables",
    "qualitative_footprint",
    "visuals_manifest",
]


# ── Low-level Markdown helpers ────────────────────────────────────────────────

def _h1(text: str) -> str:
    return f"# {text}"


def _h2(text: str) -> str:
    return f"## {text}"


def _h3(text: str) -> str:
    return f"### {text}"


def _md_table(headers: list[str], rows: list[list[str]]) -> str:
    """Render a Markdown-formatted table with auto-fitted column widths."""
    widths: list[int] = []
    for i, h in enumerate(headers):
        col_max = max((len(str(r[i])) for r in rows if i < len(r)), default=0)
        widths.append(max(len(h), col_max))

    header_line = "| " + " | ".join(h.ljust(widths[i]) for i, h in enumerate(headers)) + " |"
    sep_line    = "| " + " | ".join("-" * w for w in widths) + " |"
    data_lines  = [
        "| " + " | ".join(str(cell).ljust(widths[i]) for i, cell in enumerate(row)) + " |"
        for row in rows
    ]
    return "\n".join([header_line, sep_line] + data_lines)


def _pct(n: int, total: int) -> str:
    """Format n/total as a percentage string."""
    if total == 0:
        return "0%"
    return f"{n / total:.0%}"


# ── Section builders — pure functions returning Markdown strings ──────────────

def _build_header(spec: ReportSpec, findings: list[Finding] | None = None) -> str:
    """Section 1: report-level metadata and counts."""
    md = spec.report_metadata
    total_subs = len(spec.subsections())

    lines: list[str] = []

    if findings:
        errors = [f for f in findings if f.severity == Severity.ERROR]
        if errors:
            lines.append(
                f"> ⚠ Spec has {len(errors)} ERROR-level finding(s) — "
                "output may be incomplete. Run `inspect_spec.py` for details.\n"
            )

    lines.append(_h1(md.name))

    meta_parts = [f"Template version: **{md.template_version}**"]
    if md.reporting_period:
        meta_parts.append(f"Period: {md.reporting_period}")
    if md.regions:
        meta_parts.append(f"Regions: {', '.join(md.regions)}")
    lines.append(" | ".join(meta_parts))

    segs = ", ".join(s.value for s in md.priority_segments)
    lines.append(f"Priority segments: {segs}")
    lines.append(f"Total: **{len(spec.parts)} parts**, **{total_subs} subsections**")

    return "\n\n".join(lines)


def _build_automation_coverage(spec: ReportSpec) -> str:
    """Section 2: auto/hybrid/bespoke counts and headline automatable percentage."""
    auto_pairs    = spec.auto_subsections()
    hybrid_pairs  = spec.hybrid_subsections()
    bespoke_pairs = spec.bespoke_subsections()
    total         = len(spec.subsections())

    auto_n        = len(auto_pairs)
    hybrid_n      = len(hybrid_pairs)
    bespoke_n     = len(bespoke_pairs)
    automatable_n = auto_n + hybrid_n

    insight_in_bespoke = sum(1 for _, s in bespoke_pairs if s.is_insight)

    rows = [
        [
            "auto",
            str(auto_n),
            _pct(auto_n, total),
            "Pipeline computes everything; no human writing required",
        ],
        [
            "hybrid",
            str(hybrid_n),
            _pct(hybrid_n, total),
            "Pipeline computes inputs; human writes interpretation",
        ],
        [
            "bespoke",
            str(bespoke_n),
            _pct(bespoke_n, total),
            "Human writer only; pipeline renders scaffold",
        ],
    ]

    return "\n".join([
        _h2("2. Automation Coverage"),
        _md_table(["fill_mode", "count", "%", "meaning"], rows),
        "",
        f"**Automatable (auto+hybrid): {automatable_n} of {total} subsections "
        f"({_pct(automatable_n, total)})**",
        "",
        f"Note: {insight_in_bespoke} of {bespoke_n} bespoke subsections are "
        f"deliberate N.insight synthesis blocks — intentionally human-written "
        f"end-of-part synthesis, not automation gaps.",
    ])


def _build_per_part_breakdown(spec: ReportSpec, part_filter: int | None = None) -> str:
    """Section 3: per-part table of subsection attributes."""
    parts = spec.parts
    if part_filter is not None:
        parts = [p for p in parts if p.part_id == part_filter]
        if not parts:
            return f"No part with id={part_filter} found in this spec."

    blocks: list[str] = [_h2("3. Per-Part Breakdown")]

    for part in parts:
        rows: list[list[str]] = []
        automatable_in_part = 0

        for sub in part.subsections:
            if sub.metrics:
                unique_methods = list(dict.fromkeys(m.method.value for m in sub.metrics))
                methods_str = ", ".join(unique_methods)
            else:
                methods_str = "—"

            seg_str   = str(len(sub.disaggregation)) if sub.disaggregation else "—"
            visual_str = "Y" if sub.visual is not None else "N"
            qual_str   = "Y" if sub.qualitative is not None else "N"
            wc_str     = str(sub.word_cap) if sub.word_cap is not None else "—"

            rows.append([
                sub.subsection_id,
                sub.fill_mode.value,
                wc_str,
                methods_str,
                seg_str,
                visual_str,
                qual_str,
            ])

            if sub.fill_mode in (FillMode.auto, FillMode.hybrid):
                automatable_in_part += 1

        total_in_part = len(part.subsections)
        summary = (
            f"*{automatable_in_part}/{total_in_part} subsections automatable*"
        )

        blocks.append("\n".join([
            _h3(f"Part {part.part_id}: {part.title}"),
            _md_table(
                [
                    "subsection_id", "fill_mode", "word_cap",
                    "metric_methods", "#segs_cut", "visual?", "qual?",
                ],
                rows,
            ),
            summary,
        ]))

    return "\n\n".join(blocks)


def _build_data_demands(spec: ReportSpec) -> str:
    """Section 4: de-duplicated source question checklist (use as data request)."""
    questions = spec.all_source_questions()

    sorted_qs = sorted(
        questions,
        key=lambda q: (
            q.survey_section.value if q.survey_section else "\xff",
            q.question_ref,
        ),
    )

    sections_seen: set[str] = {
        q.survey_section.value for q in sorted_qs if q.survey_section
    }

    rows = [
        [
            q.question_ref,
            q.survey_section.value if q.survey_section else "—",
            q.response_type.value  if q.response_type  else "—",
        ]
        for q in sorted_qs
    ]

    table_str = (
        _md_table(["question_ref", "survey_section", "response_type"], rows)
        if rows else "_No source questions declared._"
    )

    return "\n".join([
        _h2("4. Data Demands (use this as the row-level data request checklist)"),
        f"Spec consumes **{len(questions)} distinct survey questions** "
        f"across **{len(sections_seen)} survey section(s)**.",
        "",
        table_str,
    ])


def _build_derived_variables(spec: ReportSpec) -> str:
    """Section 5: metric variables absent from source_questions (data-prep backlog)."""
    derived = spec.derived_variables()

    lines: list[str] = [_h2("5. Derived Variables (data-prep backlog)")]

    if not derived:
        # An empty result here may mean that composite/flag variables (negative coping
        # composite, NPS promoter flag) were declared as direct source questions rather
        # than omitted — worth a human glance to confirm computation intent is captured
        # in metric labels and subsection notes.
        lines.append(
            "No derived variables detected — all metric variables map to declared "
            "survey questions.\n\n"
            "_If composite or flag variables (e.g. negative coping composite, "
            "NPS promoter flag) were expected here, they may have been declared "
            "as source questions — confirm computation intent is captured in "
            "metric labels and subsection notes._"
        )
        return "\n".join(lines)

    # Build: ref → subsection_ids (preserving order of first encounter)
    ref_to_subs: dict[str, list[str]] = defaultdict(list)
    for _, sub in spec.subsections():
        if not sub.metrics:
            continue
        declared = sub.source_question_refs()
        for m in sub.metrics:
            for v in m.variables:
                if v not in declared and sub.subsection_id not in ref_to_subs[v]:
                    ref_to_subs[v].append(sub.subsection_id)
            if (
                m.against
                and m.against not in declared
                and sub.subsection_id not in ref_to_subs[m.against]
            ):
                ref_to_subs[m.against].append(sub.subsection_id)

    rows = [
        [ref, ", ".join(subs)]
        for ref, subs in sorted(ref_to_subs.items())
        if ref in derived
    ]
    lines.append(_md_table(["question_ref (derived)", "referenced_in_subsections"], rows))
    return "\n".join(lines)


def _build_qualitative_footprint(spec: ReportSpec) -> str:
    """Section 6: qualitative config and client-protection flag summary."""
    qual_pairs = [(p, s) for p, s in spec.subsections() if s.qualitative is not None]

    lines: list[str] = [_h2("6. Qualitative & Client-Protection Footprint")]

    if not qual_pairs:
        lines.append("_No subsections with a qualitative config._")
        return "\n".join(lines)

    rows: list[list[str]] = []
    protection_count = 0

    for _, sub in qual_pairs:
        q = sub.qualitative
        assert q is not None  # narrowing
        vcnt  = str(q.verbatim_count) if q.verbatim_count is not None else "—"
        cpf   = "**YES**" if q.client_protection_flag else "no"
        if q.client_protection_flag:
            protection_count += 1
        rows.append([
            sub.subsection_id,
            "Y" if q.verbatims_required else "N",
            vcnt,
            q.theme_method.value,
            cpf,
        ])

    lines.append(_md_table(
        ["subsection_id", "verbatims_req", "verbatim_count", "theme_method", "client_protection_flag"],
        rows,
    ))
    lines.append(
        f"\nSubsections raising `client_protection_flag`: **{protection_count}**"
    )
    return "\n".join(lines)


def _build_visuals_manifest(spec: ReportSpec) -> str:
    """Section 7: visual work-list with duplicate powerbi_name detection."""
    visual_pairs = [(p, s) for p, s in spec.subsections() if s.visual is not None]

    lines: list[str] = [_h2("7. Visuals Manifest (screenshot/export work-list)")]

    if not visual_pairs:
        lines.append("_No visuals declared._")
        return "\n".join(lines)

    # Detect duplicate powerbi_name references
    name_to_subs: dict[str, list[str]] = defaultdict(list)
    for _, sub in visual_pairs:
        assert sub.visual is not None
        name_to_subs[sub.visual.powerbi_name].append(sub.subsection_id)
    duplicates = {name: subs for name, subs in name_to_subs.items() if len(subs) > 1}

    rows: list[list[str]] = []
    for _, sub in visual_pairs:
        v = sub.visual
        assert v is not None
        dup_marker = " ⚠" if v.powerbi_name in duplicates else ""
        rows.append([
            sub.subsection_id,
            v.powerbi_name + dup_marker,
            v.source.value,
            v.visual_type or "—",
        ])

    lines.append(_md_table(
        ["subsection_id", "powerbi_name", "source", "visual_type"],
        rows,
    ))

    if duplicates:
        lines.append("")
        for name, subs in sorted(duplicates.items()):
            lines.append(
                f"⚠ **Duplicate visual referenced**: `{name}` appears in subsections: "
                f"{', '.join(subs)} — confirm this is intentional or correct the spec."
            )

    return "\n".join(lines)


# ── Top-level assembly ────────────────────────────────────────────────────────

def generate_coverage_report(
    spec: ReportSpec,
    findings: list[Finding] | None = None,
    *,
    part_filter: int | None = None,
    section_filter: str | None = None,
) -> str:
    """
    Build a human-readable coverage report for *spec*.

    This is the importable, testable entry point. Call it directly in tests
    without going through argparse.

    Parameters
    ----------
    spec:
        A validated (or partially valid) ReportSpec.
    findings:
        Findings from ``load_spec``; used to emit an error warning in the header.
    part_filter:
        If set, restrict the per-part breakdown to the given ``part_id``.
    section_filter:
        If set, return only the named section string (e.g. ``'data_demands'``).
        Must be one of :data:`SECTION_NAMES`.

    Returns
    -------
    str
        Full report (or single section) as a Markdown string.
    """
    # Build all sections unconditionally so section_filter is a simple dict lookup.
    sections: dict[str, str] = {
        "header":               _build_header(spec, findings),
        "automation_coverage":  _build_automation_coverage(spec),
        "per_part_breakdown":   _build_per_part_breakdown(spec, part_filter),
        "data_demands":         _build_data_demands(spec),
        "derived_variables":    _build_derived_variables(spec),
        "qualitative_footprint": _build_qualitative_footprint(spec),
        "visuals_manifest":     _build_visuals_manifest(spec),
    }

    if section_filter is not None:
        if section_filter not in sections:
            valid = ", ".join(sections)
            return f"Unknown section '{section_filter}'. Valid names: {valid}"
        return sections[section_filter]

    return "\n\n---\n\n".join(sections.values())


# ── Terminal display ──────────────────────────────────────────────────────────

def _display(text: str) -> None:
    """Print *text* to stdout, using Rich Markdown rendering if available."""
    if HAS_RICH:
        _RICH_CONSOLE.print(_RichMarkdown(text))
    else:
        try:
            print(text)
        except UnicodeEncodeError:
            # Windows consoles with non-UTF-8 code pages (e.g. GBK) can't encode
            # some Unicode characters. Fall back to 'replace' silently.
            enc = sys.stdout.encoding or "ascii"
            sys.stdout.buffer.write(
                text.encode(enc, errors="replace") + b"\n"
            )


# ── CLI ───────────────────────────────────────────────────────────────────────

def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="coverage_report",
        description=(
            "Generate a human-readable coverage report from a VisionFund Insurance "
            "Report spec YAML. Answers 'what does this spec commit us to?' without "
            "touching survey data."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "spec_path",
        metavar="SPEC_YAML",
        help="Path to the report spec YAML",
    )
    p.add_argument(
        "--schema",
        required=True,
        metavar="SCHEMA_JSON",
        help="Path to the JSON Schema (insurance-report-spec.schema.json)",
    )
    p.add_argument(
        "--markdown",
        metavar="OUTPUT_PATH",
        help="Also write the full report as Markdown to this file",
    )
    p.add_argument(
        "--part",
        type=int,
        metavar="N",
        help="Restrict per-part breakdown to part N (1–7)",
    )
    p.add_argument(
        "--section",
        metavar="NAME",
        choices=SECTION_NAMES,
        help="Print only one section. Choices: " + ", ".join(SECTION_NAMES),
    )
    return p


def main(argv: list[str] | None = None) -> None:
    """CLI entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    result = load_spec(args.spec_path, args.schema, strict=False)

    if result.spec is None:
        print(
            "ERROR: spec could not be loaded. Run inspect_spec.py for details.",
            file=sys.stderr,
        )
        sys.exit(1)

    report = generate_coverage_report(
        result.spec,
        findings=result.findings,
        part_filter=args.part,
        section_filter=args.section,
    )

    _display(report)

    if args.markdown:
        out_path = Path(args.markdown)
        out_path.write_text(report, encoding="utf-8")
        print(f"\nMarkdown written to: {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
