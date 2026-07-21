"""generation/assembler.py

Phase 4: Build the final .docx using python-docx. No Gemini calls here.
"""
import json
import logging
from datetime import datetime
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Inches, Pt, RGBColor

from utils import format_period_label

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent

# VisionFund brand orange (from the logo) — replaces python-docx's default
# blue heading theme colors (Title/Heading 1-4 come out of the box as shades
# of blue, e.g. #4F81BD, since nothing here set a color before).
VFI_ORANGE = RGBColor(0xF3, 0x66, 0x1F)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _set_default_font(doc, name: str, size: int):
    style = doc.styles["Normal"]
    font  = style.font
    font.name = name
    font.size = Pt(size)


def _apply_brand_heading_color(doc):
    for style_name in ("Title", "Heading 1", "Heading 2", "Heading 3", "Heading 4"):
        try:
            doc.styles[style_name].font.color.rgb = VFI_ORANGE
        except KeyError:
            pass


def _load_analysis_meta(run_id: str) -> dict:
    """Best-effort read of runs/{run_id}/analysis_results.json's meta block, for
    the cover page. Returns {} if the file is missing or unreadable rather than
    raising -- the cover page falls back to a plain title in that case."""
    path = ROOT / "runs" / run_id / "analysis_results.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("meta", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _format_profile(profile: dict) -> str:
    parts = []
    if profile.get("sex"):
        parts.append(profile["sex"])
    if profile.get("age"):
        parts.append(f"age {profile['age']}")
    if profile.get("branch") and profile.get("country"):
        parts.append(f"{profile['branch']}, {profile['country']}")
    elif profile.get("branch"):
        parts.append(profile["branch"])
    elif profile.get("country"):
        parts.append(profile["country"])
    flags = []
    if profile.get("is_claimant"):
        flags.append("claimant")
    if profile.get("is_caregiver"):
        flags.append("caregiver")
    if flags:
        parts.append(", ".join(flags))
    return " | ".join(parts) if parts else "anonymous"


def _add_heading(doc, text: str, level: int):
    doc.add_heading(text, level=level)


def _add_paragraph(doc, text: str, style: str = None):
    if not text:
        return
    if style:
        try:
            doc.add_paragraph(text, style=style)
        except KeyError:
            doc.add_paragraph(text)
    else:
        doc.add_paragraph(text)


def _add_insight_box(doc, insight_text: str, verbatims: list):
    _add_heading(doc, "Key Qualitative Insights", level=3)
    if insight_text:
        _add_paragraph(doc, insight_text)
    for v in verbatims[:3]:
        text    = v.get("text", "")
        profile = _format_profile(v.get("profile", {}))
        if not text:
            continue
        try:
            p = doc.add_paragraph(f'"{text}"', style="Quote")
        except KeyError:
            p = doc.add_paragraph(f'"{text}"')
            p.paragraph_format.left_indent = Inches(0.5)
        attr = doc.add_paragraph(f"— {profile}")
        attr.paragraph_format.left_indent = Inches(0.5)
        if attr.runs:
            attr.runs[0].italic = True


def _add_image_or_placeholder(doc, visual_info: dict):
    if visual_info.get("exists") and visual_info.get("path"):
        try:
            doc.add_picture(str(visual_info["path"]), width=Inches(5.5))
            p = doc.add_paragraph(visual_info.get("caption", ""), style="Caption")
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        except Exception:
            p = doc.add_paragraph(
                f'[VISUAL — could not insert: {visual_info["file"]} — {visual_info.get("caption", "")}]'
            )
            if p.runs:
                p.runs[0].italic = True
    else:
        p = doc.add_paragraph(
            f'[VISUAL PENDING: {visual_info["file"]} — {visual_info.get("caption", "")}]'
        )
        if p.runs:
            p.runs[0].italic = True


_PROTECTION_FLAG_LABELS = {
    "mis_selling": "Mis-selling",
    "premium_without_consent": "Premium deducted without consent",
    "coercion": "Coercion to purchase",
    "false_information": "False information",
    "unfair_claim_denial": "Unfair claim denial",
    "staff_misconduct": "Staff misconduct",
    "data_privacy": "Data privacy concern",
}

_SEVERITY_ORDER = ["high", "medium", "low"]


def _add_bold_paragraph(doc, text: str) -> None:
    p = doc.add_paragraph()
    run = p.add_run(text)
    run.bold = True


def _protection_flag_ref(row_id: str) -> str:
    """Convert an internal 'row_0011'-style ID into a reader-friendly client
    reference that's still traceable back to the same row for follow-up."""
    try:
        n = int(row_id.split("_")[1])
        return f"client ref. #{n}"
    except (IndexError, ValueError):
        return row_id


def _add_protection_signals(doc, protection_flags: list) -> None:
    """Render client-protection flags as grouped, readable sentences instead
    of raw [SEVERITY] tag lines -- keeps the per-case client reference for
    follow-up traceability without looking like a debug/audit dump."""
    _add_heading(doc, "Client Protection Signals", level=4)
    _add_paragraph(
        doc,
        "The following client-reported concerns were identified for follow-up "
        "by the client protection team."
    )

    by_severity: dict[str, list] = {}
    for flag in protection_flags:
        sev = (flag.get("severity") or "unspecified").lower()
        by_severity.setdefault(sev, []).append(flag)
    ordered_keys = [s for s in _SEVERITY_ORDER if s in by_severity]
    ordered_keys += [s for s in by_severity if s not in _SEVERITY_ORDER]

    for sev in ordered_keys:
        _add_bold_paragraph(doc, f"{sev.capitalize()} severity")
        for flag in by_severity[sev]:
            flag_type = flag.get("flag_type", "")
            label = _PROTECTION_FLAG_LABELS.get(flag_type, flag_type.replace("_", " ").capitalize())
            reason = (flag.get("reason") or "").strip()
            ref = _protection_flag_ref(flag.get("id", ""))
            _add_paragraph(doc, f"{label}: {reason} ({ref})", style="List Bullet")


def _add_generation_failure_notice(doc, error: str):
    p = doc.add_paragraph(
        f"[NARRATIVE GENERATION FAILED — Gemini call did not succeed after retries "
        f"({error}). This section requires manual write-up before publishing.]"
    )
    if p.runs:
        p.runs[0].italic = True
        p.runs[0].bold = True


def _add_table(doc, headers: list, rows: list) -> object:
    table = doc.add_table(rows=len(rows) + 1, cols=len(headers))
    try:
        table.style = "Table Grid"
    except KeyError:
        pass
    # Header row
    for i, h in enumerate(headers):
        cell = table.rows[0].cells[i]
        cell.text = h
        if cell.paragraphs and cell.paragraphs[0].runs:
            cell.paragraphs[0].runs[0].bold = True
    # Data rows
    for r_idx, row in enumerate(rows):
        for c_idx, val in enumerate(row):
            table.rows[r_idx + 1].cells[c_idx].text = str(val) if val is not None else ""
    return table


# ---------------------------------------------------------------------------
# Part 1
# ---------------------------------------------------------------------------

def build_part_1(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 1: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    for s_key, vis_idx in [("s1_1", 0), ("s1_2", 1)]:
        s_data = sections.get(s_key, {})
        _add_heading(doc, s_data.get("label", s_key), level=2)
        _add_paragraph(doc, texts.get(s_key, ""))
        if vis_idx < len(visuals):
            _add_image_or_placeholder(doc, visuals[vis_idx])

    s2b = sections.get("s1_2b", {})
    if s2b:
        _add_heading(doc, s2b.get("label", "Preferred Claims Channel"), level=2)
        _add_paragraph(doc, texts.get("s1_2b", ""))

    s3 = sections.get("s1_3", {})
    _add_heading(doc, s3.get("label", "s1_3"), level=2)
    _add_paragraph(doc, texts.get("s1_3", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 2
# ---------------------------------------------------------------------------

def build_part_2(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 2: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    # 2.1 — Claims Funnel
    s2_1 = sections.get("s2_1", {})
    _add_heading(doc, s2_1.get("label", "Claims Funnel"), level=2)
    _add_paragraph(doc, texts.get("s2_1", ""))

    ft = s2_1.get("funnel_table", {})
    if ft:
        metrics = s2_1.get("metrics", {})
        headers = ft.get("headers", ["Stage", "N", "Rate"])
        rows    = []
        for row_spec in ft.get("rows", []):
            n_val   = metrics.get(row_spec.get("n_key", ""), "")
            rate_val = metrics.get(row_spec.get("rate_key", ""), "")
            rows.append([row_spec.get("label", ""), n_val, rate_val])
        if rows:
            _add_table(doc, headers, rows)

    if len(visuals) > 0:
        _add_image_or_placeholder(doc, visuals[0])

    # 2.2 — No-claim reasons
    s2_2 = sections.get("s2_2", {})
    _add_heading(doc, s2_2.get("label", "Reasons for Not Claiming"), level=2)
    _add_paragraph(doc, texts.get("s2_2", ""))
    if len(visuals) > 1:
        _add_image_or_placeholder(doc, visuals[1])

    # 2.3 — Claim challenges
    s2_3 = sections.get("s2_3", {})
    _add_heading(doc, s2_3.get("label", "Claim Challenges"), level=2)
    _add_paragraph(doc, texts.get("s2_3", ""))
    if len(visuals) > 2:
        _add_image_or_placeholder(doc, visuals[2])

    prot_flags = s2_3.get("qualitative", {}).get("protection_flags", [])
    if prot_flags:
        _add_protection_signals(doc, prot_flags)

    # 2.4 — Payout outcomes
    s2_4 = sections.get("s2_4", {})
    _add_heading(doc, s2_4.get("label", "Payout Outcomes"), level=2)
    _add_paragraph(doc, texts.get("s2_4", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 3
# ---------------------------------------------------------------------------

def build_part_3(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 3: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    s3_0 = sections.get("s3_0", {})
    if s3_0:
        _add_heading(doc, s3_0.get("label", "Reaching Clients with No Prior Insurance Access"), level=2)
        _add_paragraph(doc, texts.get("s3_0", ""))

    s3_1 = sections.get("s3_1", {})
    _add_heading(doc, s3_1.get("label", "Financial Stress and Coping"), level=2)
    _add_paragraph(doc, texts.get("s3_1", ""))
    if visuals:
        _add_image_or_placeholder(doc, visuals[0])

    s3_2 = sections.get("s3_2", {})
    _add_heading(doc, s3_2.get("label", "Confidence in Payout"), level=2)
    _add_paragraph(doc, texts.get("s3_2", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 4
# ---------------------------------------------------------------------------

def build_part_4(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 4: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    s4_1 = sections.get("s4_1", {})
    _add_heading(doc, s4_1.get("label", "Net Promoter Score"), level=2)
    _add_paragraph(doc, texts.get("s4_1", ""))
    if visuals:
        _add_image_or_placeholder(doc, visuals[0])

    s4_2 = sections.get("s4_2", {})
    _add_heading(doc, s4_2.get("label", "Promoter and Detractor Themes"), level=2)
    _add_paragraph(doc, texts.get("s4_2", ""))
    if len(visuals) > 1:
        _add_image_or_placeholder(doc, visuals[1])

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 5
# ---------------------------------------------------------------------------

def build_part_5(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 5: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    s5_1 = sections.get("s5_1", {})
    _add_heading(doc, s5_1.get("label", "Child Wellbeing Drivers"), level=2)
    _add_paragraph(doc, texts.get("s5_1", ""))

    drivers_data  = s5_1.get("drivers_data", [])
    drivers_table = s5_1.get("drivers_table", {})
    if drivers_data:
        headers = drivers_table.get("headers", ["Driver", "ρ (Spearman)", "p-value", "N"])
        rows    = []
        for d in drivers_data:
            if d["suppressed"]:
                rows.append([d["label"], "SUPPRESSED", "SUPPRESSED", "SUPPRESSED"])
            else:
                rho_str = f"{d['rho']:+.3f}" if d["rho"] is not None else "?"
                p_str   = f"{d['p_value']:.4f}" if d["p_value"] is not None else "?"
                n_str   = str(d["n_valid"]) if d["n_valid"] is not None else "?"
                rows.append([d["label"], rho_str, p_str, n_str])
        _add_table(doc, headers, rows)
        scale_note = drivers_table.get("scale_note")
        if scale_note:
            _add_paragraph(doc, scale_note.strip())

    if visuals:
        _add_image_or_placeholder(doc, visuals[0])

    s5_2 = sections.get("s5_2", {})
    _add_heading(doc, s5_2.get("label", "Healthcare Access and Medical Cost"), level=2)
    _add_paragraph(doc, texts.get("s5_2", ""))
    if len(visuals) > 1:
        _add_image_or_placeholder(doc, visuals[1])

    scorecard = package.get("scorecard", [])
    if scorecard:
        s5_3 = sections.get("s5_3", {})
        _add_heading(doc, s5_3.get("label", "Caregivers vs Non-Caregivers"), level=2)
        headers = ["Metric", "Caregiver", "Non-Caregiver", "Sig.*"]
        rows, footnotes = [], []
        for row in scorecard:
            sig_mark = "*" if row["significant"] else ""
            label = row["label"]
            if row.get("population"):
                label += " †"
                footnotes.append(f"† {row['label']}: {row['population']}")
            rows.append([label, row["group_a_value"], row["group_b_value"], sig_mark])
        _add_table(doc, headers, rows)
        _add_paragraph(doc, "* p < 0.05 (chi-squared or Fisher's exact test)")
        for fn in footnotes:
            _add_paragraph(doc, fn)
        _add_paragraph(doc, texts.get("s5_3", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 6 — Claimant vs Non-Claimant
# ---------------------------------------------------------------------------

def build_part_6(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 6: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    scorecard = package.get("scorecard", [])
    if scorecard:
        headers = ["Metric", "Claimant", "Non-Claimant", "Sig.*"]
        rows, footnotes = [], []
        for row in scorecard:
            sig_mark = "*" if row["significant"] else ""
            label = row["label"]
            if row.get("population"):
                label += " †"
                footnotes.append(f"† {row['label']}: {row['population']}")
            rows.append([label, row["group_a_value"], row["group_b_value"], sig_mark])
        _add_table(doc, headers, rows)
        _add_paragraph(doc, "* p < 0.05 (chi-squared or Fisher's exact test)")
        for fn in footnotes:
            _add_paragraph(doc, fn)

    if visuals:
        _add_image_or_placeholder(doc, visuals[0])

    _add_heading(doc, "Findings", level=2)
    _add_paragraph(doc, texts.get("narrative", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Part 7 — Gender
# ---------------------------------------------------------------------------

def build_part_7(doc, package: dict, texts: dict):
    _add_heading(doc, f"Part 7: {package['title']}", level=1)
    sections = package.get("sections", {})
    visuals  = package.get("visuals", [])

    scorecard = package.get("scorecard", [])
    if scorecard:
        headers = ["Metric", "Female", "Male", "Sig.*"]
        rows, footnotes = [], []
        for row in scorecard:
            sig_mark = "*" if row["significant"] else ""
            label = row["label"]
            if row.get("population"):
                label += " †"
                footnotes.append(f"† {row['label']}: {row['population']}")
            rows.append([label, row["group_a_value"], row["group_b_value"], sig_mark])
        _add_table(doc, headers, rows)
        _add_paragraph(doc, "* p < 0.05 (chi-squared or Fisher's exact test)")
        for fn in footnotes:
            _add_paragraph(doc, fn)

    if visuals:
        _add_image_or_placeholder(doc, visuals[0])

    _add_heading(doc, "Findings", level=2)
    _add_paragraph(doc, texts.get("narrative", ""))

    _add_insight_box(doc, texts.get("insight", ""), sections.get("insight", {}).get("verbatims", []))


# ---------------------------------------------------------------------------
# Main assembly
# ---------------------------------------------------------------------------

def assemble(packages: list, written_texts: dict, run_id: str, output_path: Path):
    doc = Document()
    _set_default_font(doc, "Calibri", 11)
    _apply_brand_heading_color(doc)

    # Cover -- title is derived from run_id/meta rather than hardcoded to a
    # single country: the underlying survey spans many countries (only a small
    # crop-insurance subset is Vietnam-specific), so the report is always a
    # global-portfolio rollup regardless of which country config produced it.
    meta = _load_analysis_meta(run_id)
    period_label = format_period_label(run_id)
    n_total = meta.get("n_total")

    doc.add_heading("VisionFund International", level=0)
    doc.add_heading(f"Insurance Impact Report — Global Portfolio, {period_label}", level=1)
    if n_total:
        doc.add_paragraph(f"Covering {n_total:,} client responses across the VisionFund insurance portfolio.")
    doc.add_paragraph(f"Generated: {datetime.now().strftime('%d %B %Y')}")
    doc.add_page_break()

    builders = {
        "part_1": build_part_1,
        "part_2": build_part_2,
        "part_3": build_part_3,
        "part_4": build_part_4,
        "part_5": build_part_5,
        "part_6": build_part_6,
        "part_7": build_part_7,
    }

    for package in packages:
        part_key = package["part"]
        texts    = written_texts.get(part_key, {})
        builder  = builders.get(part_key)
        if builder:
            builder(doc, package, texts)
            if texts.get("_generation_failed"):
                log.warning(f"{part_key}: inserting manual-write-up placeholder (generation failed)")
                _add_generation_failure_notice(doc, texts.get("_error", "unknown error"))
            doc.add_page_break()
        else:
            log.warning(f"No builder for {part_key} — skipping")

    doc.save(str(output_path))
    log.info(f"Report saved: {output_path}")
