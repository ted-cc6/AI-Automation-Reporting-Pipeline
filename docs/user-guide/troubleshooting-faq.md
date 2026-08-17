# Troubleshooting and Frequently Asked Questions

This document covers questions and problems that go beyond the short
troubleshooting table in [quick-start.md](quick-start.md). Read that guide
first for the basic step by step flow; come here for anything that guide
does not answer.

## Getting started

### Do I need my own API key, and where do I get one?

Yes, for every report family you need your own key from the language
model provider the report requires: Gemini, Anthropic, or OpenAI for
Cupboard Week (your choice), or Anthropic only for Gender Study and Core
Credit. The dashboard does not supply a key for you. Obtaining an account
and a key with your chosen provider is outside the scope of this guide;
once you have one, paste it into the Language model card and click
Validate key before continuing.

### Is my API key or my uploaded data stored anywhere?

Your API key stays in your browser session only and is never written to
the server. Uploaded files and generated reports are stored temporarily
while your run is in progress, but the application's server storage does
not persist across restarts of the underlying service. Download your
finished report promptly once it is ready; do not rely on being able to
come back later and redownload it.

### Can two people generate reports at the same time?

No. Only one report can run at a time across the whole application. If
you try to start a run while another one, yours or someone else's, is
already in progress, you will see an error naming the run that is
currently active. Wait for it to finish, then try again.

## Upload and validation problems

### My upload was rejected with a parsing error. What went wrong?

The application expects a raw CSV export delimited with semicolons, in
UTF8 encoding, exactly as KoBoToolbox produces it. If your file has been
opened and resaved in Excel, converted to comma delimited format, or
edited by hand, the parser will usually fail. Export the file again
directly from KoBoToolbox rather than trying to repair an already edited
copy.

### The application could not tell what schema my file is. What do I do?

This happens when your file's columns do not closely enough match either
of the two known survey instruments (Africa/Vietnam or LARCO). Use the
confirmation buttons on the upload card to tell the application which one
it actually is. If neither seems right, your file may not be a supported
survey export at all; see [input-data-spec.md](input-data-spec.md) for
what each schema expects.

### Dataset validation found a long list of things to review. Is my data bad?

Not necessarily. This step exists because survey instruments occasionally
change slightly between waves, adding a question, renaming one, or
dropping one, and the application wants a person to confirm each change
rather than guessing silently. Read each recommendation's plain language
explanation and its confidence score. A high confidence recommendation is
usually safe to approve as is; a low confidence one deserves a closer
look, and you can reject it if it looks wrong. You must decide on every
recommendation before you can continue, but that does not mean something
is broken, only that the application wants your confirmation.

### Applying my reconciliation decisions failed. Now what?

This means the combination of decisions you approved would leave the
dataset in a state that fails a structural check, most often because a
required question ended up missing or mismatched. Read the specific error
list shown after the failed attempt, adjust the relevant decisions above
it, and apply again.

## During and after generation

### My run has been going for a long time. Is it stuck?

It depends on the report family. Core Credit typically takes forty to
ninety minutes or more for the full global portfolio; this is expected,
not a sign of a problem, and the run panel's log will keep updating as
each stage completes. Cupboard Week and Gender Study do not show a fixed
time estimate, but you should still see the stage indicators and the log
updating regularly. If the log has stopped updating entirely for an
extended period and the run has not reached a failed state, that is worth
reporting to whoever maintains the application.

### A section of my report is missing or says it needs to be written manually.

Occasionally a single report section can fail to generate, most often due
to a temporary issue with the language model provider. Rather than
failing the whole run, the affected section is replaced with a note
explaining that it needs manual attention, and the rest of the report
still generates normally. Check the Results panel's notes for exactly
which sections, if any, this applies to before treating your download as
completely final.

### Why does my finished respondent count not match what I expected from my raw file?

Every Cupboard Week and Gender Study upload passes through automatic
screening that removes test submissions, exact duplicate submissions,
respondents who did not consent, and respondents outside the study's
approved countries. See
[input-data-spec.md](input-data-spec.md) for the full explanation of what
gets removed and why. Your report's Data Notes section states exactly how
many rows were removed at each step. If you are comparing your count
against a number from a different system, such as an existing Power BI
dashboard, be aware that this application's screening logic and that
other system's own logic are maintained separately and are not guaranteed
to produce an identical count; a small residual difference between the
two is expected and not necessarily an error in either one.

### A country in my report is mentioned in a Data Notes warning. What does that mean for my results?

This means the automatic screening noticed an unusual pattern in that
country's interviews, most often a cluster of unusually fast interviews
concentrated among one enumerator. That country's data still counts in
every combined figure in the report, but it is left out of headline and
executive summary claims, and its responses are excluded from the pool of
quotes the report can draw from. This is a caution flag for that specific
country's data quality, not a statement that the rest of your report is
affected.

### I uploaded a prior year file for trend comparison, but Part 10 is missing or shows no comparison.

Check the run's log for a message about being unable to build a prior
wave baseline. This happens when the prior year file could not be
processed, usually because its schema could not be confidently detected.
When this happens, the main report still generates normally, simply
without the trend comparison section. Confirm the prior year file is a
raw, unedited export from the correct earlier wave and try again.

### I remember an older version of this application having a dropdown to pick a previous run for trend comparison. Where did it go?

That step was simplified. Trend comparison now only requires uploading
the prior year's raw CSV alongside your main file, in the same setup step;
the application builds the comparison automatically as part of generating
your report. There is no longer a separate step where you first run a
baseline analysis and then pick it from a list.

## Report family specific questions

### Can I generate a Gender Study report for a LACRO country?

Not currently. Gender Study only recognizes eight countries: Rwanda,
Ghana, Zambia, Malawi, Uganda, Tanzania, Kenya, and Vietnam. If your data
is from a LACRO country, use Cupboard Week instead.

### My Core Credit report says benchmark comparisons are unavailable for some metrics. Is my data wrong?

Probably not. Core Credit compares your figures against an external
reference dataset that is bundled with the application rather than
something you upload. If that reference file is missing or incomplete on
the deployment you are using, benchmark comparisons will come back
unavailable for the affected metrics, while every other part of your
report generates normally from your own data. This is worth reporting to
whoever maintains the application rather than treating it as a problem
with your survey export.

### Does Cupboard Week always include a Trend Comparison, Additional Services, Credit Life, or Crop section?

No. These four sections only appear when they are relevant: Trend
Comparison appears when you supplied a prior year file or your report is
scoped to LACRO; Additional Services appears only for a LACRO scoped
report; Credit Life and Crop Module sections appear only for a report
scoped to Africa. See
[report-family-reference.md](report-family-reference.md) for the full
list of parts and when each one applies.

## If none of this covers your issue

Check the run's live log for the specific error text, and compare it
against the table in [quick-start.md](quick-start.md)'s troubleshooting
section. If the error is not covered anywhere in this guide, note the
exact wording of the error message and bring it to whoever maintains the
application; exact error text is far more useful for diagnosing a problem
than a general description of what happened.
