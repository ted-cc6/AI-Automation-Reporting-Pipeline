"""Resolves PowerBI dashboard-visual screenshots for each report subsection.

Deterministic file lookup -- no LLM, no agent, no framework, and (deliberately) no
third-party dependencies at all, just the standard library. Given a subsection_id (the same
id already used throughout the analysis stage's schemas, e.g. "3.1", "3-insight",
"gender_scorecard"), looks for a matching image in screenshots/ and reports whether it was
found. Called directly by whatever assembles the final report -- never invoked at an LLM's
discretion, the same "orchestrated invocation, not discretionary tool-calling" pattern used
for every other deterministic piece of this project.

Kept as its own top-level folder under agent/, not under agent/analysis/, because this isn't
analysis -- it's report construction. Today screenshots/ is populated by hand: export a
PowerBI page, save it under the matching subsection_id. The planned frontend upload feature
is meant to populate the exact same lookup (whatever storage ends up behind it), so nothing
in find_dashboard_visual() itself should need to change when that exists -- only where it
looks.
"""
