# Report Family Reference

This document describes what each report type actually covers, how the
finished document is structured, and how much of it is written
automatically versus left for a person to finish. It reflects what the
dashboard's Generate button actually produces today, not any earlier
planning document.

## Cupboard Week (Insurance Impact Report)

Cupboard Week produces a quarterly impact report from your uploaded
survey. Depending on your dataset's schema and the report scope you
select, the finished document contains between eight and twelve parts:

* **Part 1, Product Understanding and Awareness.** How well clients
  understand their coverage and the claims process.
* **Part 2, Claims Experience.** The claims funnel from an insured event
  through to a result, plus reasons claims were not filed and challenges
  clients faced.
* **Part 3, Financial Inclusion.** Financial stress, negative coping,
  access to alternatives, and confidence to pay.
* **Part 4, Client Voice.** Net Promoter Score and its correlation with
  child wellbeing outcomes.
* **Part 5, Child Wellbeing.** Drivers of child wellbeing outcomes across
  the survey's other indicators.
* **Part 6, Claimant vs Non Filer Outcomes.** A scorecard comparing
  clients who filed a claim against those who experienced an insured
  event but did not file.
* **Part 7, Gender Analysis.** A scorecard comparing female and male
  respondents.
* **Part 9, Additional Services.** Included only for reports scoped to
  LACRO; covers services beyond the core insurance product.
* **Part 10, Trend Comparison.** Included whenever a prior year's data
  was supplied for comparison, or automatically for a LACRO scoped
  report; shows how key indicators moved wave over wave. See
  [quick-start.md](quick-start.md) for how to supply the prior year data.
* **Part 11, Credit Life Module.** Included only for reports scoped to
  Africa, covering credit life clients specifically.
* **Part 12, Crop Module.** Included only for reports scoped to Africa,
  covering crop insurance clients specifically.

Not every report includes every part; which parts appear depends entirely
on your data's country mix and the report scope you choose. A
single country, non LACRO, non Africa scoped report will typically only
include Parts 1 through 7.

Every part in the finished document is fully computed and drafted by the
report writing engine; there is no part of a downloaded Cupboard Week
report that is left blank for you to write yourself. That said, always
read any notes about failed sections in the Results panel before treating
the report as final; a small number of parts can occasionally fail to
generate and are replaced with a placeholder noting that a person should
write that section manually.

## Gender Study

Gender Study produces a report built around gender and disability
disaggregated outcomes, using the same underlying survey instrument as
Cupboard Week's Africa/Vietnam upload but analyzed through a separate,
purpose built pipeline. It is currently only available for eight
countries: Rwanda, Ghana, Zambia, Malawi, Uganda, Tanzania, Kenya, and
Vietnam.

The finished document opens with a title page, an executive summary with
demographic breakdown tables by insurance type and by country, then eleven
named sections in a fixed order:

1. Access and Understanding of Insurance
2. Claims Experience
3. Additional Services and Value Added Benefits
4. Wellbeing and Financial Resilience
5. Client Satisfaction and Net Promoter Score by Gender
6. Financial Inclusion and First Time Access
7. Disability and Vulnerability Cross Cut
8. Product and Region Notes
9. External Evidence and Context
10. Benchmarking
11. Recommendations and Actions

The document closes with a Limitations and Methodology section. Unlike
the eleven main sections, this closing section and the Net Promoter Score
methodology note earlier in the document are written directly by the
application rather than drafted by the report writing engine, so their
wording stays consistent across every Gender Study report.

Gender Study is also the only report family that produces a second
downloadable file: a supporting Excel workbook containing the full
demographic table, gender and disability comparison tables, Net Promoter
Score breakdowns by group, the three theme tables behind the qualitative
findings, and the complete bank of quotes used throughout the report.

As with Cupboard Week, every section of a finished Gender Study report is
fully drafted automatically; there is no section left as a scaffold for a
person to complete.

## Core Credit Impact Report

Core Credit produces the global, multi country Core Credit portfolio
report, covering nine topic sections plus three summary sections built
from all nine, twelve sections in total:

* Client Profile and Methodology (an introductory section, not numbered
  as a Part)
* Part 1, Financial Access
* Part 2, Poverty Likelihood
* Part 3, Business and Household Impact
* Part 4, Child Wellbeing
* Part 5, Client Protection
* Part 6, Agency
* Part 7, Resilience
* Part 8, Client Satisfaction
* Executive Summary (built after the nine topic sections above)
* Part 9, Gender (a scorecard summarizing findings across the whole
  portfolio)
* Part 10, Client Voices (a curated set of standout positive and negative
  quotes from across the portfolio)

Core Credit's headline feature is that every quantitative figure in the
report is benchmarked against the sixty Decibels MFI Index, an external
reference dataset maintained outside this survey and bundled with the
reporting application itself. You do not need to upload or provide this
benchmark data; only your own survey export is needed. One caveat worth
knowing: this benchmark file is a project provided reference file rather
than something every deployment is guaranteed to have in place, so if a
report comes back noting that benchmark comparisons are unavailable for a
given metric, that is most likely a benchmark file issue on the
application side rather than a problem with your uploaded data.

Every section of a finished Core Credit report is fully computed and
drafted automatically, in the same way as Cupboard Week and Gender Study.
The one thing worth watching for is the completeness notes in the Results
panel once your report finishes; these call out any section that was left
short of its expected content or that could not be fully verified against
the underlying numbers, which is the closest thing Core Credit has to a
"needs a second look" signal.

## How much of a finished report is left for a person to do

Across all three report families, the document your Generate button
produces is meant to be complete on its own; none of the three pipelines
is designed to hand you a scaffold that still needs substantial writing.
The realistic amount of follow up work is: read whatever notes the
Results panel gives you about failed or incomplete sections, and treat
those specific sections, not the whole report, as needing a person's
attention.
