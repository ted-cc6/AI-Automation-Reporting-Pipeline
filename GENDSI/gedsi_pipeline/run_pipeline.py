"""
Single entry point: prompts for the Claude API key exactly once, then runs
the full pipeline (Stages 0-6) end to end in one process.

    python -m gedsi_pipeline.run_pipeline
    python -m gedsi_pipeline.run_pipeline --pause-for-codebook-review

By default, any question that doesn't already have a human-approved codebook
(work/codebooks/<question>_approved.json) gets one auto-induced and
auto-approved so the whole run completes unattended. Questions that already
have an approved codebook (e.g. one you reviewed/edited previously) reuse it
as-is -- your prior review is never silently overwritten.

Pass --pause-for-codebook-review to restore the original behavior: the run
stops after inducing a fresh codebook so you can review/edit it before
coding proceeds.
"""
from __future__ import annotations

import shutil
import sys
import time

import pandas as pd

from gedsi_pipeline import assemble, config, draft_writer, ingest, llm_client, qual_engine, quant_engine, triangulate


def ensure_codebooks_approved(role_map, api_key: str, auto_approve: bool = True) -> None:
    df = pd.read_parquet(config.RESPONSE_FRAME_PATH)
    codebooks_dir = config.WORK_DIR / "codebooks"
    codebooks_dir.mkdir(parents=True, exist_ok=True)

    for question in role_map.qual_primary:
        approved_path = codebooks_dir / f"{question}_approved.json"
        if approved_path.exists():
            print(f"[codebook] Using existing approved codebook for {question} (not regenerated).")
            continue

        print(f"[codebook] No approved codebook for {question} yet -- inducing one now...")
        codebook = qual_engine.induce_codebook(df, question, api_key)
        qual_engine.save_draft_codebook(question, codebook)
        qual_engine.print_codebook(question, codebook)

        if auto_approve:
            draft_path = codebooks_dir / f"{question}_draft.json"
            shutil.copy(draft_path, approved_path)
            print(f"[codebook] Auto-approved {question} -- review {approved_path} later if you want to refine it.")
        else:
            print(f"\nPipeline paused for review.\nEdit {codebooks_dir / f'{question}_draft.json'}, "
                  f"save your edited version as {approved_path}, then rerun this command.")
            sys.exit(0)


def main() -> None:
    pause_for_review = "--pause-for-codebook-review" in sys.argv

    print("=" * 70)
    print("GEDSI Insurance Survey Pipeline -- full run")
    print("=" * 70)
    api_key = llm_client.prompt_for_api_key()  # prompt for the API key exactly once, up front
    start = time.time()
    role_map = config.DEFAULT_ROLE_MAP

    print("\n[1/6] Ingest & clean...")
    ingest.main(role_map=role_map)

    print("\n[2/6] Quantitative engine...")
    quant_engine.main(role_map=role_map)

    print("\n[3/6] Qualitative codebook induction / review gate...")
    ensure_codebooks_approved(role_map, api_key, auto_approve=not pause_for_review)

    print("\n[4/6] Qualitative coding (full dataset)...")
    for question in role_map.qual_primary:
        qual_engine.run_coding(question, api_key)

    print("\n[5/6] Triangulation...")
    triangulate.main()

    print("\n[6/6] Draft writing + assembly...")
    draft_writer.run_draft_writer(api_key)
    assemble.main()

    elapsed = time.time() - start
    print("\n" + "=" * 70)
    print(f"Pipeline complete in {elapsed / 60:.1f} minutes. See outputs/ for the final report.")
    print("=" * 70)


if __name__ == "__main__":
    main()
