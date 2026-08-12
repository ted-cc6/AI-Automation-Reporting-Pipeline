"""One Opus 5 call that reads the finished report's full text and flags real issues worth a
human's attention before publishing -- tone/flow, awkward transitions between independently
generated subsections, anything that reads oddly stitched together. This is a genuine judgment
task, unlike the assembly and rendering steps around it, which are both deterministic.

Deliberately NOT checked here (enforced in code instead, not by the model):
- Brand mechanics (colours, fonts, table styling, page setup) -- the renderer emits fixed
  constants from brand.py; there's nothing for a model to "get right" or "get wrong" there.
- Numeric/statistical grounding -- every WrittenText was already grounding-checked by
  writer.grounding when it was first generated (ungrounded_percentages), and
  report_assembly.completeness already surfaces any that slipped through.

This model call only ever reads report text; it has no tools and cannot edit the document.
"""

from __future__ import annotations

from report_assembly.completeness import _walk

SYSTEM_PROMPT = """You are doing a final human-facing QA read of VisionFund's Core Credit \
Impact Report before it goes out, after every section was already independently written and \
statistically grounding-checked. You are NOT checking facts or numbers -- those are already \
verified. You are reading for what only a full read-through can catch:

- Awkward or repetitive transitions between subsections that were written independently and \
may not flow as one document.
- Tone-of-voice drift -- the report should read mission-driven, clear, warm but professional, \
action-oriented (per World Vision's brand voice), not clinical or inconsistent in register \
section to section.
- Any place the same statistic or finding is stated in a confusingly different way in two \
places.
- Genuinely awkward phrasing worth a human editor's attention.

Be concise and concrete: cite the specific subsection and quote the phrase you're flagging. If \
the report reads cleanly, say so plainly rather than inventing issues to fill space."""


def _full_report_text(report) -> str:
    lines = []
    for path, value in _walk(report):
        if value is not None:
            lines.append(f"[{path}]\n{value.text}")
    return "\n\n".join(lines)


def review_report(report, reasoning_effort: str = "high") -> str:
    """Returns a short QA note as plain text -- meant to be saved as a companion file
    alongside the .docx, never embedded in the branded deliverable itself.
    """
    from llm_client import build_chat_model, extract_text

    # max_tokens=2000 first attempt came back empty on the real ~3,400-word report -- adaptive
    # thinking's reasoning tokens share this same budget (see llm_client.py / theme_tag_batch's
    # own note on this), and reviewing that much text needs real reasoning room before any
    # response text gets written. 16000 matches the same fix already used for theme_tag_batch.
    llm = build_chat_model(reasoning_effort=reasoning_effort, max_tokens=16000)
    task = f"Full report text, in document order:\n\n{_full_report_text(report)}"
    response = llm.invoke([("system", SYSTEM_PROMPT), ("human", task)])
    return extract_text(response)
