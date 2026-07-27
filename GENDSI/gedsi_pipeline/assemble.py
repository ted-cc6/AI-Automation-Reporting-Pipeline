"""
Stage 6 -- assemble.

Builds:
  outputs/GEDSI_Insurance_Report_<date>.docx        -- the report itself
  outputs/GEDSI_Insurance_Supporting_Workbook_<date>.xlsx -- underlying tables
  outputs/run_manifest_<date>.json                  -- auditability record
"""
from __future__ import annotations

import datetime as dt
import json
from ast import literal_eval
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt, RGBColor

from gedsi_pipeline import config
from gedsi_pipeline.ingest import _read_raw_rows

SECTION_ORDER = [
    "executive_summary",
    "access_understanding",
    "claims_experience",
    "additional_services",
    "wellbeing_resilience",
    "satisfaction_nps",
    "financial_inclusion",
    "disability_crosscut",
    "product_region_notes",
    "external_evidence",
    "benchmarking",
    "recommendations",
]


def _load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def _add_demo_table(doc: Document, demo_df: pd.DataFrame, cut_name: str):
    sub = demo_df[demo_df["cut"] == cut_name]
    if sub.empty:
        return
    table = doc.add_table(rows=1, cols=5)
    table.style = "Light Grid Accent 2"
    hdr = table.rows[0].cells
    for i, col in enumerate(["Segment", "Female n", "Male n", "Female %", "Pt diff (F-M)"]):
        hdr[i].text = col
    for _, row in sub.iterrows():
        cells = table.add_row().cells
        cells[0].text = str(row["value"])
        cells[1].text = str(int(row["Female_n"]))
        cells[2].text = str(int(row["Male_n"]))
        cells[3].text = f"{row['Female_pct_of_all_female']:.1f}%" if pd.notna(row["Female_pct_of_all_female"]) else "-"
        pd_val = row["pt_diff"]
        cells[4].text = f"{pd_val:+.1f}" if pd.notna(pd_val) else "-"
    doc.add_paragraph()


def _add_section(doc: Document, title: str, headline: str, paragraphs: list[str]):
    doc.add_heading(title, level=1)
    p = doc.add_paragraph()
    run = p.add_run(headline)
    run.bold = True
    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    for para_text in paragraphs:
        doc.add_paragraph(para_text)
    doc.add_paragraph()


def build_docx(drafts_dir, packs_dir, quant_dir, run_stats: dict) -> Document:
    doc = Document()

    ORANGE = RGBColor(0xED, 0x7D, 0x31)  # Word's default "Accent 2" orange
    for style_name in ("Title", "Heading 1", "Heading 2"):
        doc.styles[style_name].font.color.rgb = ORANGE

    title = doc.add_heading("VisionFund 2026 Insurance Survey", level=0)
    sub = doc.add_paragraph()
    sub_run = sub.add_run("GEDSI Analysis Report -- Gender Equality, Disability and Social Inclusion")
    sub_run.bold = True
    sub_run.font.size = Pt(14)
    meta = doc.add_paragraph()
    meta.add_run(
        f"Generated {dt.date.today().isoformat()} | Analysis assisted by Claude "
        f"({config.CLAUDE_MODEL}) under human review | n={run_stats['n_respondents']} "
        f"consenting respondents"
    ).italic = True
    doc.add_page_break()

    # Executive summary demographic table up front (PDF-specified front-of-report table)
    demo_df = pd.read_csv(quant_dir / "demographic_table.csv")
    exec_draft = _load_json(drafts_dir / "executive_summary.json")
    doc.add_heading("Executive Summary & Demographics", level=1)
    p = doc.add_paragraph()
    run = p.add_run(exec_draft["headline_insight"])
    run.bold = True
    run.font.highlight_color = WD_COLOR_INDEX.YELLOW
    for para in exec_draft["paragraphs"]:
        doc.add_paragraph(para)
    doc.add_heading("Survey Demographics by Insurance Type", level=2)
    _add_demo_table(doc, demo_df, "Insurance Type")
    doc.add_heading("Survey Demographics by Country", level=2)
    _add_demo_table(doc, demo_df, "Country")
    doc.add_paragraph()

    section_titles = {
        "access_understanding": "Access & Understanding of Insurance",
        "claims_experience": "Claims Experience",
        "additional_services": "Additional Services & Value-Added Benefits",
        "wellbeing_resilience": "Wellbeing & Financial Resilience",
        "satisfaction_nps": "Client Satisfaction & Net Promoter Score by Gender",
        "financial_inclusion": "Financial Inclusion & First-Time Access",
        "disability_crosscut": "Disability & Vulnerability Cross-Cut",
        "product_region_notes": "Product & Region Notes",
        "external_evidence": "External Evidence & Context",
        "benchmarking": "Benchmarking",
        "recommendations": "Recommendations / Actions",
    }
    for key in SECTION_ORDER:
        if key == "executive_summary":
            continue
        draft = _load_json(drafts_dir / f"{key}.json")
        _add_section(doc, section_titles[key], draft["headline_insight"], draft["paragraphs"])

    # Limitations & Methodology -- built directly from run facts, not LLM-authored
    doc.add_heading("Limitations & Methodology", level=1)
    limitations = [
        f"Analysis covers {run_stats['n_respondents']} consenting respondents out of "
        f"{run_stats['n_raw']} raw submissions ({run_stats['n_dropped_consent']} excluded for declining consent).",
        f"Quantitative comparisons use a minimum cell size of n={config.MIN_N}; comparisons below this "
        f"threshold are marked not-statistically-robust (n_ok=false) and treated as directional only.",
        f"All gender- and disability-comparison p-values in this report were corrected in a single "
        f"Benjamini-Hochberg false discovery rate pass (alpha={config.FDR_ALPHA}) to control for the "
        f"number of comparisons made; only findings surviving this correction are described as significant.",
        "Qualitative themes for the three Net Promoter Score driver questions were induced and coded by "
        f"Claude ({config.CLAUDE_MODEL}) under human review: a human reviewed and edited each theme "
        "codebook before it was applied to the full dataset. Smaller 'please specify' free-text fields "
        "are presented as raw illustrative quotes, not formally coded themes, due to low response counts.",
        "This survey instrument covers insurance clients only. GEDSI report elements specific to "
        "credit/savings products in VisionFund's broader reporting framework (loan goal tracking, "
        "savings group dynamics, household-head/group-leader sub-segments, Empowered Worldview module "
        "attribution) do not apply to this dataset and are omitted rather than approximated.",
        "No internal or external benchmark file (e.g. 60 Decibels, regional/global portfolio benchmarks) "
        "was supplied with this dataset. The Benchmarking section and per-indicator commentary state this "
        "gap explicitly rather than citing unverified figures.",
        "Vietnam (Crop Insurance) and LACRO-region respondents are a small share of the sample; "
        "country/region cuts for these groups are directional, not statistically robust.",
    ]
    for note in limitations:
        doc.add_paragraph(note, style="List Bullet")

    return doc


def build_workbook(quant_dir, work_dir) -> pd.io.excel._OpenpyxlWriter:
    from openpyxl import Workbook
    wb = Workbook()
    wb.remove(wb.active)

    def add_df_sheet(name, df):
        ws = wb.create_sheet(title=name[:31])
        ws.append(list(df.columns))
        for row in df.itertuples(index=False):
            ws.append(list(row))

    for csv_name in ["demographic_table", "gender_comparisons", "disability_comparisons", "nps_by_group"]:
        add_df_sheet(csv_name, pd.read_csv(quant_dir / f"{csv_name}.csv"))

    for q in ["nps_detractor_reasons", "nps_passive_reasons", "nps_promoter_reasons"]:
        path = work_dir / "theme_tables" / f"{q}.csv"
        if path.exists():
            add_df_sheet(f"theme_{q}", pd.read_csv(path))

    quote_bank_path = work_dir / "quote_bank.json"
    if quote_bank_path.exists():
        qb = _load_json(quote_bank_path)
        rows = []
        for question, themes in qb.items():
            for theme, quotes in themes.items():
                for q in quotes:
                    rows.append({"question": question, "theme": theme, **q})
        add_df_sheet("quote_bank", pd.DataFrame(rows))

    return wb


def main(csv_path=None, work_dir: Path | None = None, output_dir: Path | None = None):
    work_dir = work_dir or config.WORK_DIR
    output_dir = output_dir or config.OUTPUT_DIR
    quant_dir = work_dir / "quant_tables"
    packs_dir = work_dir / "evidence_packs"
    drafts_dir = work_dir / "drafts"
    output_dir.mkdir(parents=True, exist_ok=True)

    df = pd.read_parquet(work_dir / "response_frame.parquet")
    _header, raw_rows = _read_raw_rows(csv_path or config.RAW_CSV_PATH)  # csv.reader-based: handles embedded newlines in quoted fields
    n_raw = len(raw_rows)

    run_stats = {
        "n_respondents": len(df),
        "n_raw": n_raw,
        "n_dropped_consent": n_raw - len(df),
    }

    date_str = dt.date.today().isoformat()

    doc = build_docx(drafts_dir, packs_dir, quant_dir, run_stats)
    docx_path = output_dir / f"GEDSI_Insurance_Report_{date_str}.docx"
    doc.save(docx_path)
    print(f"Wrote {docx_path}")

    wb = build_workbook(quant_dir, work_dir)
    xlsx_path = output_dir / f"GEDSI_Insurance_Supporting_Workbook_{date_str}.xlsx"
    wb.save(xlsx_path)
    print(f"Wrote {xlsx_path}")

    cache_files = list(config.CACHE_DIR.glob("*.json"))
    manifest = {
        "generated_at": dt.datetime.now().isoformat(),
        "model": config.CLAUDE_MODEL,
        "min_n": config.MIN_N,
        "fdr_alpha": config.FDR_ALPHA,
        **run_stats,
        "n_cached_llm_responses": len(cache_files),
        "sections": SECTION_ORDER,
        "outputs": {"docx": str(docx_path), "xlsx": str(xlsx_path)},
    }
    manifest_path = output_dir / f"run_manifest_{date_str}.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {manifest_path}")

    return {"docx_path": docx_path, "xlsx_path": xlsx_path, "manifest_path": manifest_path}


if __name__ == "__main__":
    main()
