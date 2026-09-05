"""Renders the assembled CoreCreditImpactReport into a WVI-branded .docx, plus a companion QA
notes file. Three steps:

  1. build_report(): fully deterministic. No LLM. Assembles the 12 already-written sections.
  2. translate_report_verbatims(): one small structured-output call per non-English verbatim
     (detect language + translate) -- mechanical, not a judgment task, but genuinely needs the
     model since it's real translation, not something a lookup table can do.
  3. render_report(): fully deterministic. Lays everything into the template structure and
     applies wvi-docx.skill's brand rules.
  4. review_report(): one real LLM call (Sonnet 5) -- a genuine judgment task (does the finished
     document read well as one piece), kept strictly separate from the deliverable itself.

Usage: python build_docx.py [--skip-qa]
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from docx import Document

AGENT_ROOT = Path(__file__).resolve().parent.parent  # agent/
ANALYSIS_ROOT = AGENT_ROOT / "analysis"
PROJECT_ROOT = AGENT_ROOT.parent  # core_peoject

sys.path.insert(0, str(AGENT_ROOT))
sys.path.insert(0, str(ANALYSIS_ROOT))
load_dotenv(PROJECT_ROOT / ".env")

from report_assembly.build_report import build_report  # noqa: E402
from report_assembly.completeness import (  # noqa: E402
    completeness_report,
    raise_on_meta_text_leaks,
    raise_on_missing_caregiver_scope,
    raise_on_unknown_theme_references,
)
from report_assembly.translate_verbatims import translate_report_verbatims  # noqa: E402
from report_render.qa_review import review_report  # noqa: E402
from report_render.section_layout import render_report  # noqa: E402

OUTPUT_DIR = Path(__file__).resolve().parent / "output"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-qa", action="store_true", help="Skip the Sonnet 5 QA read (faster, no LLM cost).")
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    print("Assembling CoreCreditImpactReport from all 12 sections' real output...")
    report = build_report(run_id=timestamp)
    print(f"Assembled: {report.reporting_period}, {report.client_profile.n_respondents} respondents.")

    print("Checking for leaked meta-commentary (hard gate)...")
    raise_on_meta_text_leaks(report)  # raises MetaTextLeakError and stops the build if it finds one
    raise_on_unknown_theme_references(report)  # stops the build on a fabricated theme name
    raise_on_missing_caregiver_scope(report)  # stops the build if Child Wellbeing has no caregiver scope

    issues = completeness_report(report)
    if issues:
        print(f"\n{len(issues)} completeness issue(s) (over-cap / ungrounded / missing) -- see report_assembly output for detail.")

    print("\nTranslating non-English verbatims...")
    n_translated = translate_report_verbatims(report)
    print(f"Translated {n_translated} non-English verbatim(s).")

    print("\nRendering .docx (deterministic, no LLM)...")
    doc = Document()
    render_report(doc, report)

    OUTPUT_DIR.mkdir(exist_ok=True)
    docx_path = OUTPUT_DIR / f"Core_Credit_Impact_Report_{timestamp}.docx"
    doc.save(str(docx_path))
    print(f"Wrote {docx_path}")

    if args.skip_qa:
        print("\nSkipped Sonnet 5 QA read (--skip-qa).")
        return

    print("\nRunning Sonnet 5 QA read (one LLM call, reviews text only, cannot edit the document)...")
    qa_note = review_report(report)
    qa_path = OUTPUT_DIR / f"qa_notes_{timestamp}.md"
    qa_path.write_text(qa_note, encoding="utf-8")
    print(f"Wrote {qa_path}\n")
    print(qa_note)


if __name__ == "__main__":
    main()
