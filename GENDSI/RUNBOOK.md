# GEDSI Insurance Survey Pipeline -- Runbook

Run every command from the project folder:
```
cd /d "D:\Vision Fund International\GENDSI"
```

## Option A: one command, one key entry (recommended)

```
python -m gedsi_pipeline.run_pipeline
```

Prompts for your Claude API key exactly once at the start, then runs all 6 stages
back-to-back in a single process, printing progress as it goes. Any NPS-driver question that
doesn't already have a human-approved codebook (`work/codebooks/<question>_approved.json`) gets
one auto-induced and auto-approved so the run completes unattended -- questions that already
have an approved codebook (like the ones we reviewed together) reuse it as-is, your prior review
is never overwritten. Ends with the final `.docx`/`.xlsx` paths in `outputs/`.

To get the original pause-for-review behavior back for a fresh codebook (e.g. if the underlying
survey data changes and you want to look at new themes before they're applied):
```
python -m gedsi_pipeline.run_pipeline --pause-for-codebook-review
```

## Option B: stage by stage (for walking through the pipeline out loud)

Steps marked **(API key)** will prompt for your Claude key -- paste it, hit Enter (nothing
displays, that's expected). Because the source CSV hasn't changed, most of these calls will
hit the local cache in `cache/` and return instantly without even prompting for the key --
that's the caching working correctly, not a bug.

| # | Stage | Command | Needs key? | What it does |
|---|-------|---------|:---:|---|
| 1 | Ingest & clean | `python -m gedsi_pipeline.ingest` | No | Parses the raw CSV, drops PII, normalizes sex/disability, writes `work/response_frame.parquet`. Prints sex/country/insurance-type counts as a sanity check. |
| 2 | Quantitative engine | `python -m gedsi_pipeline.quant_engine` | No | Computes gender/disability/NPS comparison tables with significance testing + FDR correction, writes `work/quant_tables/*.csv`. |
| 3 | Codebook induction | `python -m gedsi_pipeline.qual_engine` | (API key) | Samples responses, asks Claude to propose themes for the 3 NPS-driver questions, writes `work/codebooks/*_draft.json`, prints them to screen. |
| 4 | *(Human review gate)* | -- | -- | Already-approved codebooks exist at `work/codebooks/*_approved.json` from our last run. Skip to step 5 unless you want to demonstrate the review step itself (see below). |
| 5 | Full coding | `python -m gedsi_pipeline.qual_engine code` | (API key) | Codes every response against the approved codebooks, writes `work/theme_tables/*.csv` and `work/quote_bank.json`. |
| 6 | Triangulation | `python -m gedsi_pipeline.triangulate` | No | Builds one evidence pack per report section, `work/evidence_packs/*.json`. |
| 7 | Draft writing | `python -m gedsi_pipeline.draft_writer` | (API key) | Claude writes prose for all 12 sections, grounded only in each section's evidence pack, writes `work/drafts/*.json`. |
| 8 | Assemble | `python -m gedsi_pipeline.assemble` | No | Builds the final `.docx`, `.xlsx`, and `run_manifest.json` in `outputs/`, dated today. |

## To demo the human-in-the-loop review live (optional, step 4)

Instead of skipping straight to step 5, after step 3 you can show your manager the review gate:
1. Open one of `work/codebooks/*_draft.json` and point out the themes Claude proposed.
2. Show that `*_approved.json` is a separate, human-signed-off copy -- nothing gets coded
   against a codebook a person hasn't looked at first.
3. To "approve" a fresh draft yourself: copy it over the approved file, e.g.
   ```
   copy work\codebooks\nps_detractor_reasons_draft.json work\codebooks\nps_detractor_reasons_approved.json
   ```

## One command for everything (no review pause)

If you just want the full pipeline to run end-to-end without stopping to talk through each
stage, you can chain the non-interactive ones; you'll still be prompted for the API key at
steps 3, 5, 7 (once each, or not at all if cached):
```
python -m gedsi_pipeline.ingest && python -m gedsi_pipeline.quant_engine && python -m gedsi_pipeline.qual_engine && python -m gedsi_pipeline.qual_engine code && python -m gedsi_pipeline.triangulate && python -m gedsi_pipeline.draft_writer && python -m gedsi_pipeline.assemble
```

## Outputs

Look in `outputs/` for `GEDSI_Insurance_Report_<date>.docx`,
`GEDSI_Insurance_Supporting_Workbook_<date>.xlsx`, and `run_manifest_<date>.json`. Each run is
dated, so old runs aren't overwritten unless run twice on the same day.

## If something looks wrong

- **A step errors on a column/header mismatch** -- means the CSV structure changed; `config.py`'s
  `EXPECTED_HEADER_PREFIXES` will name exactly which column moved.
- **Claude call fails** -- check the error text (never share the key itself); usually an invalid
  key or a transient network issue (the client retries automatically up to 4 times).
- **Want a truly fresh run (ignore cache)** -- delete the relevant files under `cache/`, but this
  re-spends API budget and isn't needed just to demo the pipeline again.
