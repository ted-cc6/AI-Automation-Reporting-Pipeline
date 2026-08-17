# Input Data Spec

This document describes what your uploaded survey CSV needs to look like
for each report family, and what the dashboard automatically checks,
removes, or flags before your data reaches the analysis stage. Read this
before uploading if your export is coming from somewhere other than a
direct KoBoToolbox download, or if your final respondent count comes out
lower than your raw row count and you want to understand why.

## General requirements for every report family

Every upload must be a raw CSV export delimited with semicolons, in UTF8
encoding. This is exactly what a direct KoBoToolbox export produces.
Opening the file in Excel and resaving it, or converting it to a comma
delimited file, will usually break the upload; export again from
KoBoToolbox instead of editing the file by hand.

## Cupboard Week: Africa/Vietnam schema

The dashboard checks your uploaded file's column headers against a known
set of expected columns for this schema, and computes what fraction of
them it can match automatically. If at least half of the expected columns
are matched, the file is accepted as this schema. If fewer than half
match, the upload is marked "unknown" and you will be asked to confirm
manually which schema it actually is.

The Africa/Vietnam schema expects columns covering these question areas.
You do not need to match column names exactly; this is a checklist for
sanity checking that your export includes the right content before
uploading:

* Consent (the opening consent question)
* Demographics: client age, education level, household size, sex,
  disability status, income sources
* Product understanding: understanding of coverage, understanding of the
  claims process, preferred communication and claim channels
* Claims experience: whether an insured event occurred in the last twelve
  months, whether a claim was filed, the reason if not filed, the claim
  result, whether the payout covered the cost, and claim challenges
* Coping mechanisms (a multi select question covering things like using
  savings, borrowing money, selling assets, reducing food spending, and
  taking children out of school)
* Bundled or value added services used, and whether they helped
* Financial stress reduction and what improved for children
* Net Promoter Score (0 to 10), plus a follow up free text question for
  detractors, passives, and promoters
* Whether the premium was worth it, renewal intent, and confidence the
  insurer will pay
* Prior insurance access and ease of finding an alternative
* Healthcare access change and out of pocket medical cost change (for
  health products)
* Crop insurance questions: weather shock recovery speed, change in
  farming approach (Vietnam only)
* Credit life questions: other included benefits and their perceived
  value (Africa only)

## Cupboard Week: LARCO schema

LARCO uses a shorter, Spanish language instrument. If your export was
collected under the older LARCO instrument rather than the unified 2026
schema, the dashboard checks it against a separate, shorter set of
expected columns:

* Consent and demographics (age, education, household size, sex)
* Claim type filed and claim experience rating
* Microfinance services also accessed
* Product understanding (a combined benefits, coverage, and process
  question)
* Financial stress impact and quality of life, in free text
* Child wellbeing impact and which areas improved
* Belief that a spouse or children are more financially secure
* Ease of finding an alternative and prior access
* Net Promoter Score, plus one combined free text follow up question

If you are uploading data collected under the 2026 unified survey for a
LACRO country, use the regular Africa/Vietnam upload path instead; the
LARCO schema described here only applies to older exports collected under
the previous instrument.

## Gender Study

Gender Study uses the same raw survey export as a Cupboard Week
Africa/Vietnam upload, the same underlying KoBoToolbox instrument, but it
is checked against a separate, purpose built column mapping used only by
the Gender Study pipeline. In practice this means: if you already have a
CSV that works for a Cupboard Week Africa/Vietnam report, the same file
will generally work for a Gender Study report too.

One important limitation: Gender Study currently only recognizes eight
countries: Rwanda, Ghana, Zambia, Malawi, Uganda, Tanzania, Kenya, and
Vietnam. It does not currently include the LACRO countries that were
folded into the Cupboard Week Africa/Vietnam schema for the 2026 wave. If
your data is from a LACRO country, a Gender Study report is not currently
available for it.

Gender Study also depends on three theme codebooks, one for each Net
Promoter Score follow up question (why detractors, passives, and
promoters answered as they did). These codebooks are reviewed by a person
ahead of time and kept as part of the application itself; they are never
regenerated from your specific upload. This is not something you need to
do anything about as a user, it is a setup detail worth knowing only if a
run fails with an error about a missing codebook, in which case the issue
is on the application side, not with your data.

## Core Credit Impact Report

Core Credit expects a raw quarterly KoBoToolbox or ODK style export
covering the full, multi country portfolio in one file. Unlike Cupboard
Week and Gender Study, there is no manual review step before generation
starts. Two automatic checks run as the very first stage of the pipeline
instead:

**Column cleaning.** The pipeline expects one column per question, using
the standard KoBoToolbox naming convention. It automatically drops an
entire savings related section (reported separately, out of scope for
this report), device and enumerator metadata columns, static
question and answer label columns, and any column that is completely
empty. It always keeps a small set of columns regardless of how empty
they are, since the rest of the pipeline depends on them directly: the
submission identifiers, the survey version (used to pick the correct
scoring reference), the client identifier, and the country question
(used to drive every country level breakdown and benchmark comparison).
If, after cleaning, very few columns remain, or no recognizable question
sections are detected at all, the pipeline stops and flags the file
rather than continuing. This usually means the file was not a genuine
KoBoToolbox export, or something went wrong with how it was delimited.

**Row checking.** Two checks run: exact duplicate rows (matching on every
column except system and audit fields) are automatically resolved by
keeping the first occurrence; and rows with a duplicate client identifier,
or containing an obvious test keyword such as "test," "demo," "training,"
"dummy," "sample," or "placeholder" in the client identifier, branch, or
submitted by fields, are flagged for a person to review rather than being
removed automatically. If more than one tenth of all rows are exact
duplicates, or more than one tenth contain a test keyword, the pipeline
stops rather than saving, since this usually means something is wrong
with the file itself rather than genuine data quality issues.

There is no fixed list of expected countries for Core Credit; any country
present in your export will be processed, with a small number of
documented exceptions handled by the reporting engine itself rather than
anything you need to prepare in your data (for example, one country is
excluded from this report by longstanding policy, and a few others use an
alternate scoring approach or are marked not available for the current
wave).

## Why your final respondent count may be lower than your raw row count

Every Cupboard Week and Gender Study upload passes through the same four
automatic screening checks, applied in this order, before analysis
begins. Understanding these checks explains most of the gap between your
raw export's row count and the respondent count that appears in your
finished report.

**Removed automatically:**

1. **Test and QA rows.** Any row whose client identifier, enumerator name,
   or branch contains the whole word "test," "demo," "training," "pilot,"
   or "qa" is treated as a known test submission and removed.
2. **Duplicate submissions.** Two rows are treated as the same interview
   submitted twice if every substantive answer matches exactly. Device
   identifiers, submission timestamps, enumerator usernames, and
   interview start and end times are not compared, since those can
   legitimately differ even for a genuine accidental resubmission. Of any
   matching group, the earliest submitted copy is kept and the rest are
   removed.
3. **Non consenting respondents.** Anyone who answered "no" to the
   opening consent question is removed.
4. **Out of scope country respondents.** Anyone whose country is not on
   the study's approved list for that schema is removed.

**Flagged for review, but never removed automatically:**

* A client identifier reused across two rows with genuinely different
  answers is logged as a warning for the field team to reconcile by
  hand; both rows are kept, since automatically dropping one risks
  deleting a real respondent's real answers.
* A shared device or session identifier across rows with differing
  content (Cupboard Week only) is flagged with a similarity score, since
  it may indicate a re edited or cloned form rather than a duplicate
  respondent.
* Countries where an unusually large share of interviews ran much faster
  than typical, especially if concentrated among one enumerator's
  interviews, are flagged as a data quality concern. See
  [quick-start.md](quick-start.md)'s section on data quality notes for
  what this means for your finished report.

If your final respondent count is noticeably lower than your raw row
count, the report's own Data Notes section will explain exactly how many
rows were removed and why.
