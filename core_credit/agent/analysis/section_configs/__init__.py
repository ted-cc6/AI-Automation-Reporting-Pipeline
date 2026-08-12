"""Config-driven section building: the data that turns "one hardcoded Part 3 script" into
"one generic graph, N section configs" (see agent/analysis/graph/, which consumes these).

Each section's config lives in its own file under sections/, mirroring how schemas/ has one
file per section. registry.py collects them into one lookup.

Not every section fits this abstraction cleanly, and forcing a bad fit was worse than leaving
a gap explicit -- see registry.py's docstring for exactly which sections are and aren't
covered here, and why.
"""
