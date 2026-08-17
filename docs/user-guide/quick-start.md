# Quick Start: Generating a Report

This guide walks through generating a report in the VFI Report Dashboard (the
Hugging Face Space), from opening the page to downloading the finished
`.docx`. It covers all three report flows: Cupboard Week, Gender Study, and
Core Credit Impact Report.

## Before you start

* **You need your own LLM API key** (Gemini, Anthropic, or OpenAI depending
  on the report; see below). The dashboard does not provide one for you, and
  your key is only kept in your browser session. Nothing is stored on the
  server.
* **Your survey file must be a CSV delimited with semicolons**, exported
  directly from KoBoToolbox. If you upload a CSV delimited with commas, or a
  file that was opened and resaved in Excel, the upload will fail with a
  parse error. Export the file again from KoBoToolbox rather than trying to
  fix it by hand.
* **Only one report can run at a time** on the Space. If someone else's
  report is already running, starting a new one will fail until theirs
  finishes.

## 1. Choose a report family

The landing page shows two tiles:

* **Insurance Impact Reports**: Cupboard Week quarterly reports and the
  Gender Study report. Bring your own Gemini, Anthropic, or OpenAI key.
* **Core Credit Impact Report**: the global, multi country Core Credit
  portfolio report (9 theme sections, benchmarked against the MFI Index).
  Requires an Anthropic key.

Pick a tile. You can always click "All reports" in the header to go back and
switch.

## 2. Insurance Impact Reports

After picking the Insurance tile, use the **Report type** dropdown to choose
**Cupboard Week** or **Gender Study**. The setup screen changes depending on
which you pick.

### 2a. Cupboard Week

1. **Language model.** Choose Gemini, Anthropic Claude, or OpenAI, paste
   your API key, and click "Validate key." The key is used for dataset
   validation, qualitative tagging, and report writing, and stays in your
   browser session only.
2. **Card 1, Survey data.** Drag or click to upload the raw KoBoToolbox CSV
   export for the quarter. Once uploaded you will see the row and column
   count. If the file's schema cannot be detected automatically, you will
   be asked to confirm whether it is "Africa / Vietnam" or "LARCO" before
   continuing. Then click **Validate dataset**: see
   [Understanding "Validate dataset"](#understanding-validate-dataset)
   below before proceeding.
3. **Card 2, Report type and period.** Pick the report type, the country or
   region (or "All Countries (Global Portfolio)"), the year, and the
   quarter. A Run ID is generated automatically as
   `{country}_{year}_Q{quarter}`; you can override it if needed.
   * If this is a LACRO or Africa/Vietnam schema run, an optional **"Prior
     year's data for trend comparison"** field appears. See
     [Trend comparison](#trend-comparison-for-lacro-and-africavietnam-runs)
     below.
   * A checkbox lets you run **"Analysis only (skip report generation)."**
     Use this to clean and analyze the upload without spending any LLM
     calls, and without producing a `.docx`.
4. **Card 3, Report visuals.** Power BI API access is still pending, so
   upload chart screenshots manually (PNG) for each report part.
5. **Card 5, Generate the report.** Click **Generate quarterly report** (or
   **Run analysis only** in dry run mode). Four stages track live: Data
   loading, Analysis, Qualitative tagging, Report generation (with per part
   status for Parts 1 through 7). A live log streams below as it runs.
6. Once generation finishes, a **Results** panel appears with a **Download
   report (.docx)** link. Read any notes about failed sections before
   relying on the report as final.

### 2b. Gender Study

Mostly the same as Cupboard Week, with these differences:

* The LLM key is locked to **Anthropic Claude**: there is no provider
  choice.
* There are no country, quarter, or year fields, just an optional run
  label.
* After uploading the CSV, dataset validation runs against the project's
  reviewed Gender Study codebooks. There is no manual qualitative theming
  step; that section is informational only.
* There is no trend comparison, no dry run option, and no manual visual
  upload.
* The run panel shows 6 stages: Ingest and clean, Quantitative engine,
  Codebook check, Qualitative coding, Triangulation, and Draft writing and
  assembly.
* The Results panel offers **two downloads**: the `.docx` report and a
  supporting `.xlsx` workbook.

## 3. Core Credit Impact Report

1. **Language model.** Locked to Anthropic Claude; paste and validate your
   key.
2. **Card 1, Survey data.** Upload the raw quarterly Core Credit Impact
   Survey export, the full multi country portfolio in one file. There is
   **no separate validation step** here. Column cleaning and row level
   quality checks run automatically as the first stage of the pipeline.
3. **Card 2, Run label.** Optional, for example `2026Q3global`.
4. **Generate the report.** This runs the full pipeline end to end and
   typically takes **40 to 90 minutes or more** for the global portfolio.
   Progress is shown across 5 grouped stages: data prep, dashboard visuals,
   9 parallel theme sections, derived outputs, and render and QA.
5. Once finished, the Results panel notes any missing visuals or
   completeness issues, then offers a single **Download report (.docx)**
   link.

## Understanding "Validate dataset"

Cupboard Week and Gender Study both run a dataset validation step after
upload, before you can generate a report. Core Credit does not have this
step; its cleaning is automatic.

* If the file matches the expected column mapping, you will see: "Dataset
  structure matches the current column mapping, nothing needs review. You
  can continue."
* If not, you will see a list of recommendations covering renamed columns,
  new questions, or dropped columns, each with a confidence badge (green
  for high confidence, yellow for medium, red for low) and a plain
  language rationale. **You must approve or reject every recommendation**
  before you can continue. Read the rationale for each; approve it if the
  suggested match looks right, reject it otherwise, then click **Apply
  reconciliation**.
* The "Generate report" button stays disabled until reconciliation passes.
  If applying fails, fix your decisions above and apply again.

## Trend comparison for LACRO and Africa/Vietnam runs

For LACRO or Africa/Vietnam schema Cupboard Week runs, you can optionally
add a wave over wave trend comparison by uploading last year's **raw** CSV
export in the "Prior year's data for trend comparison" field on the setup
screen. No separate baseline run is needed. Leave it empty for a first wave
report with no trend comparison.

If the prior year file cannot be processed (wrong schema, bad file), the
main report still generates. It simply proceeds without the trend
comparison, and a note is logged explaining why.

## Data quality notes to check

The report generator automatically screens for suspicious response patterns,
for example a cluster of unusually fast interviews from one enumerator.
There is no onscreen warning for this during setup. Instead, check the
**Data Notes** section of your finished `.docx`. If a country was flagged:

* It is called out explicitly in Data Notes.
* It is excluded from headline and executive summary claims, but it still
  counts in pooled figures.
* Its records are excluded from the pool of candidate verbatim quotes.

## Troubleshooting

**"Could not parse CSV as semicolon delimited UTF-8."** Your file is not a
raw KoBoToolbox export. Export it again rather than editing the CSV by
hand.

**"Could not determine this upload's source survey schema."** The file did
not clearly match a known schema. Use the "It's Africa / Vietnam" or "It's
LARCO" confirmation buttons on the upload card.

**"Run '...' is already {status}. Only one run can be active at a time."**
Wait for the run already in progress (yours or someone else's) to finish
before starting a new one.

**The "Generate report" button stays disabled.** You still have unresolved
dataset validation recommendations. See
[Understanding "Validate dataset"](#understanding-validate-dataset).

**No trend comparison appears in the output despite uploading a prior year
file.** Check the log for a "Could not build a prior wave baseline"
message. The prior file most likely failed schema detection. The main
report still generated normally.
