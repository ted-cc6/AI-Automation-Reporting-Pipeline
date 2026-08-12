"""Theme-tagging agent: clusters survey free text into themes with representative verbatims.

The one LLM component in the pipeline that does real judgment work. Grounding is enforced
structurally, not by post-hoc checking: the model only ever selects response IDs from a
numbered list we give it -- it never writes quote text or client profile fields itself, so
it cannot hallucinate either. See agent.py for how that's wired.
"""
