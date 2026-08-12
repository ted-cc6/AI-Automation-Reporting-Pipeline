"""Tool-less generation: turns already-computed structured data into report prose.

No tools are exposed to this chain -- it receives a MetricResult/NPSResult/
QualitativeSynthesis object as plain context and can only narrate the numbers already in
it, never compute its own. grounding.py is the safety net that checks that held.
"""
