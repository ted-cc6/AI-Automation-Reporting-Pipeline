Save each PowerBI dashboard screenshot in this folder, named after the subsection it
illustrates: `<subsection_id>.png` (`.jpg`/`.jpeg` also work).

Examples:
- `3.1.png` -- Business income change
- `3.2.png` -- Change in quality of life
- `3-insight.png` -- Insight for Business and Household Impact
- `gender-scorecard.png` -- the Gender section's scorecard table

`subsection_id` values come from each section's `SubsectionPrompt` (see
`agent/analysis/writer/section_prompts.py`) or the schema's own naming for sections that
don't go through the writer. Every compound id uses a hyphen, never an underscore --
`gender-scorecard`, `client-profile`, `executive-summary`, `1-insight`, etc. (an earlier
version of this file used `gender_scorecard.png` as its example, which would have silently
never matched -- find_dashboard_visual() looks up the exact subsection_id string, and every
SubsectionPrompt in the codebase is hyphenated).

The cross-cutting sections don't map 1:1 onto the numbered Parts:
- `client-profile` -- Client Profile & Methodology
- `executive-summary` -- Executive Summary
- `gender-scorecard` / `gender-insight` -- the Gender scorecard table / its Insight
- `client-voices` -- Client Voices (this one has no written Analysis text, just a curated
  verbatim bank, but the template still shows one PowerBI visual for it)

If a Part's subsections share one PowerBI page, save the same screenshot under each of that
Part's subsection_ids -- there's no reuse mechanism beyond that; every id looks up its own file.

Nothing needs to be registered anywhere else -- `dashboard_visuals.lookup.find_dashboard_visual`
checks this folder directly by filename.
