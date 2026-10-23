"""CC-085: deterministic scan of generated narrative for causal and overclaiming language.

The survey is cross-sectional and self-reported with no counterfactual, so the narrative can
describe what clients report but cannot claim what caused it, explain why subgroups differ,
promise what an action will achieve, or call VisionFund better than a benchmark. SYSTEM_PROMPT
has said so since CC-001 to CC-003, but until now nothing checked the writer's actual output --
CC001_BANNED_TERMS in chain.py only validates the prompts themselves.

Two tiers:
  - HARD_TERMS: phrases with no legitimate use in this report's narrative. CC-086 makes these
    enforcing (one rewrite, then a failed run).
  - REVIEW_TERMS: interpretive framings that are often fine ("signaling a need to review" is
    Henry's own approved wording) but that carried every residual overclaim in local-cc066
    ("pointing to gaps in access", "an easier alternative-lender landscape"). Reported for a
    human to read, never enforced.

Text inside double quotes is skipped -- a client's own words are a verbatim, not a claim the
report is making. Known false positives are allowlisted by context (ALLOWED_CONTEXTS), and a
hit preceded closely by a negation ("should not be read as evidence of") is not counted, except
for "as expected", where a negation is the violation itself ("doesn't run cleanly upward as
expected", Test5 3.1, HO27).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The handoff's CC-084 starting list, plus the R1-R8 additions from the same review round. Each
# additional term is a real string from Test5 or local-cc066, noted beside it. Since CC-083 this
# is also the ONE list chain.validate_subsection_prompts checks prompts against -- it absorbed
# chain.py's old CC001_BANNED_TERMS / CC003_BANNED_TERMS (marked "CC-001/003" below).
HARD_TERMS = (
    # R1 benchmark comparisons are descriptive
    "outpaces", "outpace", "outperform", "outperforms", "outperformed", "well ahead",
    "comfortably ahead", "beats", "wins",  # CC-003
    "ahead of the mfi index", "ahead of the benchmark",  # plain "ahead of" is review: cc066 4.1 "ahead of schooling"
    "far above the mfi index", "far above the benchmark",  # cc066 6.1; plain "far above" is review
    "leads the story",
    # R2 no causal claims from outcome data
    "drive", "drives", "drove", "driver", "drivers", "driven by",
    "driving",  # "whatever is driving Senegal and Mali's near-universal gains" (Test5 4 insight)
    "lifts", "translating into", "translates into", "confirming", "confirms",
    "mechanism", "dividend", "payoff", "evidence of", "a sign this", "genuinely",
    "converting",  # "women are converting loan capital into..." (Test5 Agency insight)
    "can be read as",  # "can be read as realized preparedness" (cc066 7.4)
    "realized preparedness", "realised preparedness",  # Resilience theme label -> Test6 executive summary
    "shaping", "shapes", "shaped",  # "pricing ... shaping whether clients lean toward recommending" (Step 6 regen, 8 insight)
    "shifting",  # "genuinely shifting decision-making power" (Test5 6.2, HO51)
    "shifts", "proves", "causes", "demonstrates", "leads to", "leading to", "lead to",  # CC-001
    # R3 subgroup differences are associations, never levers
    "lever",  # "a lever worth expanding" (Test5 3 insight, HO32)
    # R4 no expected patterns or causal sequences
    "as expected", "which frees",  # "loans first ease food security, which frees resources" (HO35)
    # R5 perceptions are not facts
    "moat",  # "a strong competitive moat" (Test5 1.2, HO17)
    "misselling", "mis-selling", "over-indebtedness",  # (Test5 5.2, HO42)
    # R6 poverty reach, not targeting
    "pro-poor targeting", "poverty targeting",  # (Test5 2.2 HO24, cc066 2.2)
    "targeting the poor", "targeting of the poor",  # the 2.2 prompt itself: "shows stronger targeting of the poor"
    # R8 recommendations are exploratory
    "should raise", "leverage", "would remove", "will improve",  # "will improve": CC-001
    "should keep prioritizing",  # "VisionFund should keep prioritizing women's loans" (Test5 6 insight)
)

REVIEW_TERMS = (
    "far above", "ahead of", "signaling", "signalling", "pointing to", "points to", "reflects", "reflecting",
    "targeting", "landscape", "weight", "scarce", "scarcity", "locked-in", "should",
)

# Phrases in which a HARD/REVIEW term is a plain noun, not a claim. Matched against the text
# around the hit; the hit is dropped if it falls inside one of these.
ALLOWED_CONTEXTS = (
    "complaints mechanism", "complaint mechanism", "coping mechanism", "coping mechanisms",
    "grievance mechanism", "reporting mechanism", "feedback mechanism",
)

_NEGATION_RE = re.compile(r"\b(not|never|no|nor|cannot)\b|n't\b", re.IGNORECASE)
_NEGATION_WINDOW_WORDS = 6
_NEGATION_EXEMPT = ("as expected",)

_QUOTED_SPAN_RE = re.compile(r'"[^"]*"|“[^”]*”')
# Not after "vs." -- the writer's own comparisons use it mid-sentence ("11.8% vs. 9.2%").
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])(?<!\bvs\.)\s+")


def _term_pattern(terms: tuple) -> re.Pattern:
    # Longest first so "driven by" wins over "drive" and "pro-poor targeting" over "targeting".
    ordered = sorted(terms, key=len, reverse=True)
    return re.compile(r"(?<![\w-])(" + "|".join(re.escape(t) for t in ordered) + r")(?![\w-])", re.IGNORECASE)


_HARD_RE = _term_pattern(HARD_TERMS)
_REVIEW_RE = _term_pattern(REVIEW_TERMS)


@dataclass(frozen=True)
class LintHit:
    term: str
    tier: str  # "hard" | "review"
    sentence: str


def _blank_quotes(text: str) -> str:
    """Replaces quoted spans with spaces of the same length, so offsets still line up."""
    return _QUOTED_SPAN_RE.sub(lambda m: " " * len(m.group(0)), text)


def _in_allowed_context(sentence: str, start: int, end: int) -> bool:
    lowered = sentence.lower()
    for phrase in ALLOWED_CONTEXTS:
        for m in re.finditer(re.escape(phrase), lowered):
            if m.start() <= start and end <= m.end():
                return True
    return False


def _is_negated(sentence: str, start: int, term: str) -> bool:
    if term.lower() in _NEGATION_EXEMPT:
        return False
    preceding = sentence[:start].split()[-_NEGATION_WINDOW_WORDS:]
    return bool(_NEGATION_RE.search(" ".join(preceding)))


def _matches(scan: str, pattern: re.Pattern) -> list[re.Match]:
    return [
        m for m in pattern.finditer(scan)
        if not _in_allowed_context(scan, m.start(), m.end()) and not _is_negated(scan, m.start(), m.group(1))
    ]


def lint_text(text: str, include_review: bool = True) -> list[LintHit]:
    """Every causal-language hit in `text`, one per term occurrence, in reading order. Empty
    list means the text is clean. Quoted client words are never scanned, and a review-tier
    term inside a hard-tier phrase ("targeting" in "pro-poor targeting") is not counted twice.
    """
    hits = []
    for sentence in _SENTENCE_SPLIT_RE.split(text or ""):
        scan = _blank_quotes(sentence)
        hard = _matches(scan, _HARD_RE)
        hits.extend(LintHit(term=m.group(1).lower(), tier="hard", sentence=sentence.strip()) for m in hard)
        if include_review:
            for m in _matches(scan, _REVIEW_RE):
                if any(h.start() <= m.start() and m.end() <= h.end() for h in hard):
                    continue
                hits.append(LintHit(term=m.group(1).lower(), tier="review", sentence=sentence.strip()))
    return hits
