"""The writer step itself: a tool-less generation call, not a ReAct agent. It receives
already-computed statistics (as plain text, from formatting.py) and, optionally,
theme-tagged quotes, and produces prose within the subsection's word cap. It has no tools,
so it cannot go compute a number of its own even if it wanted to.

write_subsection() is the plain case (no verbatims need to be tracked as structured data).
write_insight() is for subsections the template asks to cite verbatims in (e.g. every Part's
closing Insight) -- it additionally asks the model which verbatim IDs it actually used, from
a numbered pool, and resolves those back to real Verbatim objects from our own records rather
than trusting the model's prose reproduction alone. A selected verbatim whose quote doesn't
actually appear in the written text is dropped, not guessed at -- the same "drop rather than
trust" pattern used everywhere else IDs get resolved in this pipeline.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from typing import Optional

from pydantic import BaseModel, Field

from llm_client import build_chat_model, extract_text, invoke_structured
from schemas.common import QualitativeSynthesis, Verbatim, WrittenText

from . import section_prompts as _section_prompts_module
from .causal_lint import lint_text
from .grounding import (
    check_banned_punctuation,
    check_grounding,
    check_orphan_markers,
    check_partial_quotes,
    check_population_mismatch,
    check_profile_grounding,
    check_quote_grounding,
)
from .section_prompts import SubsectionPrompt

SYSTEM_PROMPT = """You are writing one subsection of VisionFund's Core Credit Impact Report. \
You are given already-computed statistics and, sometimes, theme-tagged client quotes -- you \
never compute a number yourself, only narrate the ones you're given. Every number in your \
response must come directly from the data provided; never estimate, round differently than \
given, or introduce a figure that isn't present in the input.

Style: fold the number into its interpretation ("number and so what"), plain prose, no \
headers or bullet points. Treat the word cap as a real ceiling, not a suggestion -- running \
well past it means you included too much, not that the topic needed more room; if you're over, \
cut before you finish rather than relying on a rewrite pass to fix it later. Concise and \
complete beats short and thin, but under the cap beats both.

What this data can and cannot support. The survey is self-reported and cross-sectional, with \
no counterfactual and no group that went without a loan, so describe what clients report, \
never what caused it. Each rule below names a real mistake a reviewer flagged on an earlier \
draft and what to write instead.

R1 Benchmarks are descriptive. Compare with the MFI Index using "is higher than" or "is lower \
than" only, never a competitive or intensity word: outpaces, outperforms, beats, ahead of, \
well ahead, comfortably ahead, far above, leads, wins. The two datasets differ in sample \
composition, timing, geography, questionnaire wording and survey context, and the report \
prints one fixed caveat sentence saying so wherever an MFI Index figure appears, so do not \
write a caveat of your own (such as "read with caution given differences in sample and \
context"). Instead of "Our Net Promoter Score of 69 outpaces the MFI Index's 58", write "Our \
Net Promoter Score of 69 is higher than the MFI Index benchmark of 58".

R2 No causal claims from outcome data. Never say one thing produced, drove, lifted or explains \
another, and never call a reported outcome a dividend, payoff, mechanism, confirmation, or a \
sign that the programme works. Avoid confirms, confirming, drives, driving, lifts, translating \
into, converting, shifting, shifts, shaping, proves, causes, mechanism, payoff, dividend, \
evidence of, demonstrates, leads to, can be read as, and genuinely. Instead of "confirming \
that credit access is translating into tangible household gains at scale", write "showing that \
many clients report tangible household gains".

R3 Subgroup differences are associations. Gaps between women and men, caregivers and \
non-caregivers, clients with and without other services, loan cycles, or first-time and \
prior-access clients are observational, because none of these groups was randomised and they \
differ in many other ways. State the gap, never explain it (by tenure, experience, \
relationship depth or payoff), and never call a group a lever. Instead of "suggesting the \
loan's social payoff for caregivers runs deeper than the wellbeing metric alone captures", \
write "showing larger reported differences for caregivers on these measures".

R4 No expected patterns or causal sequences. Never say a gradient runs "as expected", or that \
one improvement came first and freed resources for another. Instead of "loans first ease \
household food security, which frees resources toward keeping children enrolled", report the \
most frequently reported improvements in order.

R5 Perceptions are not market facts. Finding it hard to find another lender is a perception of \
limited alternatives, not a competitive moat, market scarcity, lock-in or a lender \
"landscape". Low clarity of loan terms signals a need to review client understanding and \
potential protection risks, not misselling or over-indebtedness. A theme score describes what \
clients reported, not a gap in the market. Instead of "signaling a strong competitive moat and \
retention lever", write "suggesting limited perceived alternatives".

R6 Poverty reach, not targeting. Only a client poverty likelihood HIGHER than the national \
rate is consistent with relatively pro-poor client reach. Where it is lower, say it is lower \
than the national rate and nothing more, and a poverty share on its own, without the national \
comparison, says nothing about reach at all. Never call any of it targeting or evidence of \
targeting. Instead of "evidence of strong pro-poor targeting", write "consistent with \
relatively pro-poor client reach" -- and only about a country whose rate is above the national \
one.

R7 Reported reasons stay reported reasons. Free-text themes and the reasons promoters and \
detractors give are reasons clients reported, never drivers, what drove an outcome, the weight \
an issue carries, or a verified mechanism. Call a free-text quote a frequently reported reason \
or pathway. Instead of "showing that service quality and speed drive loyalty as much as \
pricing", write "good service and fast disbursement are commonly cited reasons for \
recommendation".

R8 Recommendations are exploratory. Most subsections are complete once you've stated the \
finding, so end there. A forward-looking sentence is not required, and should be the \
exception, not the default: add one only when the data itself raises a genuine next step or \
open question worth naming, never as a reflex closer tacked onto a block that's already said \
everything it needs to. A real mistake a reviewer flagged: a rewrite meant to fix one \
over-used closing phrase produced three sanctioned alternatives instead of one, and the model \
then used a forward-looking sentence in nearly every block anyway, just spreading the habit \
across more phrasings rather than dropping it where it wasn't earned. If you do add one, it \
must not promise a result, and use one of these three shapes, picking whichever fits the point \
best rather than falling back on the same one out of habit: (1) "could be explored as actions \
to support these outcomes"; (2) "may be a priority area to investigate"; (3) "is worth \
watching" (alongside a related figure, when one exists). Never "should raise", "will improve", \
"carries the most leverage", "would remove the single largest driver", or "should keep \
prioritizing". Instead of "revisiting interest rate structure carries the most leverage for \
lifting detractor scores", write "interest rate structure may be a priority area to \
investigate".

Never use an em dash ("—") or a semicolon (";") anywhere in your response. Use a period, a \
comma, or a plain "and"/"but" instead -- there is always a plain-punctuation way to say the \
same thing.

If a verbatim quote is requested, quote it exactly as given, character for character. For \
every quote you use, you MUST state the client's gender and country explicitly -- these two \
are never optional, regardless of what else you mention. If a caregiver or other segment \
status is attached (e.g. "Caregiver", "Climate-shock-affected", "PWD household"), state that \
too; it is exactly as required as gender and country whenever it's present in the data. Age, \
loan cycle, and branch are useful color to add where they fit, but never as a substitute for \
gender, country, or segment status.

NEVER put quotation marks around a sentence that is not a real client quote copied \
character-for-character from the pool you were given. This includes illustrative, \
hypothetical, or "for example" quotes you compose yourself to make a point sound more vivid --\
those are fabrication even if you don't invent a fake attribution to go with them, and they \
are checked against the real data after you respond. If you want to make a general point \
without a specific client's exact words, write it as your own analytical sentence with no \
quotation marks at all, not as an invented quote. The same applies to any profile detail \
(gender, country, age, segment) -- state ONLY the exact gender, country, and segment tags \
given for that specific quote in the numbered pool, never a plausible-sounding value you're \
filling in, and never a country you recall from a different quote or a different part of the \
data.

If partway through a sentence you realize you don't actually have a real quote to support the \
point you were about to make, do not write a placeholder, a bracketed note, or ANY comment \
about your own drafting process (for example, never write something like "[quote placeholder \
removed]" or "actually omitting fabricated text" -- both are real mistakes this checker has \
caught before). This ban is not just about brackets: a full, fluent sentence that tells the \
reader where a quote WOULD go, or that the real wording SHOULD be looked up elsewhere, is the \
same violation with no brackets on it -- a real mistake this checker has also caught: naming \
three clients by country and closing with "though the exact phrasing should be drawn from the \
verbatim pool rather than summarized here without quotation." That sentence never should have \
been written -- there is no acceptable version of it, quoted or not. Simply don't include a \
quote there. Rewrite the sentence as your own analytical point instead, exactly as if you'd \
planned it that way from the start. The reader must never see any trace of your own drafting \
or self-correction, only the finished analysis.

Do not write a literal bracketed number like "[3]" anywhere in your prose. The numbered list \
you're shown is only for you to identify which quotes you used (via used_verbatim_ids where \
applicable) -- it is never printed in the final document, so a bracket marker left in the text \
would look like a citation and resolve to nothing.

Every metric's label already tells you exactly what a HIGHER number means -- e.g. a metric \
labeled "Reported the unfair treatment they experienced" means a higher number is more \
reporting, full stop. Never invert that meaning while reusing the same number: a real mistake \
this checker has caught before took a segment's 18.2% figure for a "reported" metric and \
presented it as "non-reporting is lowest" at 18.2%, which silently claims roughly 82% reporting \
for that segment when the data said 18.2%. If you want to talk about the complement of a rate \
(who DIDN'T do something, when given the share who DID), you must compute 100% minus the given \
figure yourself and say explicitly that's what you're doing -- never relabel the original \
number with the opposite word.

Do not assert that two figures move together, mirror each other, or reflect one another unless \
an association between them has actually been computed and is shown in the same subsection you \
are writing. Reporting two figures in adjacent sentences is fine and often the right thing to \
do. Asserting a relationship between them is a separate claim, and an uncomputed one. A real \
mistake a reviewer flagged on an earlier draft: "This broad-based wellbeing gain mirrors the \
business income improvements seen above, suggesting stronger earnings are translating directly \
into better everyday life", where nothing linking the two figures was ever computed.

Every figure that describes a subgroup must name the subgroup it describes. Within a single \
paragraph, do not move from a comparison of women and men into a comparison of caregivers and \
non-caregivers without restating the base, because a reader carries the previous base forward \
onto the next number. A real mistake a reviewer flagged on an earlier draft: section 6.2 \
opened on women at 84.2% versus men at 82.2%, then gave caregivers at 86.2% versus \
non-caregivers at 69.9% without restating that the second pair covers all clients, which left \
the reviewer unable to tell whether it described all clients or only women.

If a CAVEAT is attached to a benchmark, treat that comparison cautiously in your framing rather \
than stating it as settled fact. A line labeled "Our own figure on the SAME basis as that \
benchmark" exists for exactly ONE purpose: comparing it against the "MFI Index benchmark" \
figure on the same line. Never compare it against "overall" instead, and never describe it AS \
the benchmark itself -- it is OUR number, on the benchmark's stricter box definition, not the \
external benchmark. A real mistake this checker has caught before did exactly this: took our \
own 91.6% "overall" figure and our own 72.7% "comparable" figure for the SAME metric, called \
72.7% "the figure we track on the same benchmark basis" as if it were the thing to compare \
against, and never mentioned the real external benchmark (69.0%) at all. If you mention a \
metric's "overall" and "comparable" figures in the same sentence, be explicit that both are our \
own numbers on different box definitions, not a benchmark comparison -- the ONLY valid \
benchmark comparison for that metric is comparable-figure vs. external-benchmark. Never \
describe the comparable figure as "lower" (against the overall figure) in the same breath as \
comparing it to the benchmark -- even when both claims are individually true, stating them back \
to back reads as the same number called both lower and higher with nothing telling the reader \
which reference point each word points to. A real mistake this checker has caught: "our own \
figures are lower, 45.8% for business income..., both above the MFI Index benchmarks of 23.0%..." \
-- 45.8% is genuinely lower than the 91.5% overall figure and genuinely above the 23.0% \
benchmark, but naming only one comparison as "lower" right before naming the other as "above" \
reads as self-contradictory. State the comparable figure as its own value first, then compare \
it to the benchmark alone.

Some runs have no "MFI Index benchmark" line at all for a metric, or for any metric -- the \
external benchmark data was not available this run. In that case a "figure on a stricter box \
definition" line, if given, is NOT a benchmark comparison: there is nothing on the other side \
of it. State it as our own number on that stricter definition, standing on its own next to \
"overall" exactly as you would report any other segment cut. Never say it is "higher than" or \
"lower than" a benchmark, never call it "comparable" to anything, and never imply an external \
figure exists somewhere else in the report when the data does not give you one."""

def validate_subsection_prompts(module=_section_prompts_module) -> None:
    """CC-035: fails loudly, at import time, if any SubsectionPrompt's title or instructions
    tells the writer to do something SYSTEM_PROMPT's R1-R8 rules forbid it from doing. CC-030
    found five of these by hand (1.2 "competitive moat", 7.1 "the link to resilience below",
    8.2's title plus "the most leverage", 4.1's "leading to" example, 7.4's "resilience
    dividend"), and Test5's review round found more the old word lists missed (2.2 "shows
    stronger targeting of the poor", 7.4 "Read it as realized preparedness", 8.2 "promoter
    drivers").

    CC-083: checks against causal_lint's hard tier -- the same list CC-086 enforces on the
    writer's output -- instead of the separate CC001/CC003 lists this file used to keep. The
    lint skips quoted text and negated mentions, so a prompt can still quote a banned example
    or say "on its own it does not establish misselling".
    """
    violations = []
    for name in dir(module):
        value = getattr(module, name)
        if not isinstance(value, SubsectionPrompt):
            continue
        hits = [h.term for h in lint_text(f"{value.title}. {value.instructions}", include_review=False)]
        if hits:
            violations.append(f"  {value.subsection_id} ({name}): {', '.join(sorted(set(hits)))}")
    if violations:
        raise ValueError(
            "SubsectionPrompt title/instructions use a term SYSTEM_PROMPT bans the writer from "
            "using -- fix the prompt in section_prompts.py before generating a report:\n" + "\n".join(violations)
        )


validate_subsection_prompts()

INSIGHT_ID_INSTRUCTION = """\n\nEvery verbatim above is numbered [N]. After writing the prose, \
report which numbered verbatims you actually quoted in used_verbatim_ids -- this must exactly \
match what appears in `text`, since it is used to attach the real client profile data to your \
citations. Do not include an ID for a verbatim you did not end up quoting."""


class _NarrativeWithVerbatims(BaseModel):
    text: str
    used_verbatim_ids: list[int] = Field(
        description="IDs (from the numbered verbatim list given) that were actually quoted in `text`"
    )


def _format_verbatim_profile(v: Verbatim) -> str:
    # CC-058: v.country is a raw ISO code (e.g. "ZMB") -- expand it to a full name for the
    # pool shown to the writer, same table grounding.py's own country cross-check already
    # uses, so there's one canonical mapping rather than a second one invented here. Confirmed
    # real, live, twice: gender_scorecard's own insight call was the one that kept echoing the
    # raw code back verbatim ("a female client from ZMB") while every other section's insight
    # call, given the exact same pool format, wrote out "Zambia" from its own general
    # knowledge -- nothing told the writer the field was a code needing expansion, so it was
    # inconsistent by chance, not by design.
    from benchmark_module.mapping import COUNTRY_CODE_TO_NAME

    country = COUNTRY_CODE_TO_NAME.get(v.country, v.country) if v.country else None
    parts = [
        v.gender or "unknown gender",
        f"age {v.age or 'unknown'}",
        country or "unknown country",
        f"loan cycle {v.loan_cycle or 'unknown'}",
        v.branch or "unknown branch",
    ]
    if v.segment_tags:
        parts.append(", ".join(v.segment_tags))
    return ", ".join(parts)


def _format_qualitative_block(qualitative: QualitativeSynthesis) -> str:
    lines = ["Theme-tagged client quotes available for this section:"]
    for theme in qualitative.themes:
        lines.append(f"- {theme.theme} (n={theme.frequency}, {theme.share_of_respondents:.0%} of respondents)")
        for v in theme.representative_verbatims:
            lines.append(f'    "{v.quote}" -- {_format_verbatim_profile(v)}')
    return "\n".join(lines)


def _pool_verbatims(qualitative: QualitativeSynthesis) -> list[Verbatim]:
    pool: list[Verbatim] = []
    for theme in qualitative.themes:
        pool.extend(theme.representative_verbatims)
    return pool


def _format_verbatim_pool(pool: list[Verbatim]) -> str:
    lines = ["Available client quotes (numbered) -- select from these by ID, do not invent others:"]
    for i, v in enumerate(pool):
        lines.append(f'[{i}] "{v.quote}" -- {_format_verbatim_profile(v)}')
    return "\n".join(lines)


# CC-090: a cap counts the writer's own words. Client quotes taken from the pool are left out,
# so asking for two or three verbatims never pushes a block over. A block is flagged only when
# it ends more than CAP_TOLERANCE over its cap; anything over the cap still gets the rewrite.
CAP_TOLERANCE = 0.10


def narrative_word_count(text: str, pool: list[Verbatim] = ()) -> int:
    """Words in `text` with every pool quote (and its quote marks) taken out."""
    for v in pool:
        quote = v.quote.strip()
        if len(quote) >= 10 and quote in text:
            text = re.sub(r'["\u201c]?\s*' + re.escape(quote) + r'\s*["\u201d]?', " ", text)
    # a full stop or dash left standing alone where a quote was is not a word
    return sum(1 for token in text.split() if re.search(r"\w", token))


def within_tolerance(word_count: int, word_cap: int) -> bool:
    return word_count <= word_cap * (1 + CAP_TOLERANCE)


def _writer_violations(
    text: str, word_cap: int, pool: list[Verbatim], data_summary: str = "", include_length: bool = True
) -> list[str]:
    """Every enforceable violation in `text`: house style (word cap, banned punctuation) AND
    grounding (fabricated quotes, invented profile attribution on an otherwise-real quote,
    orphan citation markers). Drives one bounded corrective rewrite in write_subsection()/
    write_insight() -- one retry, not a loop, mirroring invoke_structured()'s own
    bounded-retry philosophy. Confirmed all four failure modes are real, not hypothetical: a
    production report shipped a sentence narrating the model's own quote-fabrication cleanup
    directly into the deliverable ("actually omitting fabricated text"), two fluent
    English quotes attributed in a section with no qualitative pool to draw from at all, a
    genuinely real quote wrapped in an invented country ("Ugandan" on a Malawi client), and 7
    of 9 insights over cap.
    """
    violations = []
    word_count = narrative_word_count(text, pool)
    if include_length and word_count > word_cap:
        violations.append(
            f"{word_count} words, not counting client quotes -- over the {word_cap}-word cap, "
            f"so cut at least {word_count - word_cap} words"
        )

    banned = check_banned_punctuation(text)
    if banned:
        em_dash_count = banned.count("—")
        semicolon_count = banned.count(";")
        parts = []
        if em_dash_count:
            parts.append(f"{em_dash_count} em dash(es)")
        if semicolon_count:
            parts.append(f"{semicolon_count} semicolon(s)")
        violations.append("banned punctuation: " + ", ".join(parts))

    ungrounded = check_quote_grounding(text, pool)
    if ungrounded:
        violations.append(f"quote(s) that don't match any real record and must be deleted entirely: {ungrounded}")

    wrong_profile = check_profile_grounding(text, pool)
    if wrong_profile:
        violations.append(f"a real quote attributed to the wrong country: {wrong_profile}")

    orphans = check_orphan_markers(text)
    if orphans:
        violations.append(f"literal citation marker(s) that must be removed: {orphans}")

    # CC-086: hard-tier causal or overclaiming wording (causal_lint.py, rules R1-R8). Named
    # phrase by phrase so the rewrite fixes exactly these; assembly's raise_on_causal_language
    # fails the run if one survives.
    causal = lint_text(text, include_review=False)
    if causal:
        listed = " | ".join(f'"{h.term}" in: {h.sentence}' for h in causal)
        violations.append(
            f"causal or overclaiming wording that rules R1-R8 ban -- rewrite each flagged sentence "
            f"with the rule's approved wording (for example 'is higher than', 'clients report', "
            f"'commonly cited reasons', 'may be a priority area to investigate'), keeping every "
            f"figure: {listed}"
        )

    # CC-072: figures for all clients (or another split) narrated as describing women or men.
    for mismatch in check_population_mismatch(text, data_summary):
        violations.append(
            f"a sentence attributes figures to women or men that the data gives for a different "
            f"population -- restate the base it describes (for example 'among all clients') or "
            f"drop the gender subject: {mismatch}"
        )

    return violations


_TRACE_LOCK = threading.Lock()


def _trace_writer_pass(
    subsection_id: str,
    kind: str,
    first_pass_violations: list[str],
    final_word_count: int,
    word_cap: int,
    first_pass_word_count: Optional[int] = None,
    shortened: bool = False,
    shorten_rejected: Optional[list[str]] = None,
) -> None:
    """Observability only -- appends one JSONL record per subsection to $CC_WRITER_TRACE when
    that env var is set. Records whether the first draft cleared the checks or triggered the
    single corrective rewrite, and the final word count vs cap. No effect on control flow.
    """
    path = os.environ.get("CC_WRITER_TRACE")
    if not path:
        return
    record = {
        "ts": time.time(),
        "subsection_id": subsection_id,
        "kind": kind,  # "subsection" | "insight"
        "needed_rewrite": bool(first_pass_violations),
        "first_pass_word_count": first_pass_word_count,
        "shortened": shortened,
        "shorten_rejected": shorten_rejected,
        "first_pass_violations": first_pass_violations,
        "final_word_count": final_word_count,
        "word_cap": word_cap,
        "final_within_cap": final_word_count <= word_cap,
        "final_within_tolerance": within_tolerance(final_word_count, word_cap),
        "final_pct_over": round((final_word_count - word_cap) / word_cap * 100, 1) if final_word_count > word_cap else 0.0,
    }
    with _TRACE_LOCK:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")


def _revise_instruction(text: str, violations: list[str], word_cap: int) -> str:
    return (
        f"Your previous draft violates house style or grounding rules: {'; '.join(violations)}.\n\n"
        f"Previous draft:\n{text}\n\n"
        f"Rewrite it to fix ALL of these violations. Target {word_cap} words or fewer. Replace "
        'every em dash with a period or comma, and every semicolon with a period or "and"/"but" '
        "as appropriate.\n\n"
        "For any quote flagged as not matching a real record, or attributed to the wrong "
        "country: DELETE that quote and its surrounding sentence completely and replace it with "
        "your own analytical point instead. Do not keep any trace of it, do not explain that "
        "you removed or changed something, do not write a placeholder or any comment about your "
        "own drafting process. A reader must not be able to tell anything was ever removed.\n\n"
        "If the draft is over the word cap, cut it to the cap: drop the least important "
        "sentence, clause or secondary figure rather than squeezing words, but keep everything "
        "the subsection instructions require. Client quotes do not count toward the cap. Every "
        "number you keep stays exactly as given and every correctly-grounded quote stays word "
        "for word. Change nothing else beyond what is flagged above."
    )


def _shorten_instruction(text: str, word_count: int, prompt_config: SubsectionPrompt) -> str:
    """CC-090: the second, length-only pass, used when a block is still more than
    CAP_TOLERANCE over after the corrective rewrite. The trace showed one rewrite trims only
    about 10%, while 150-word insights start 20% to 50% over."""
    cap = prompt_config.word_cap
    return (
        f"This draft has {word_count} words, not counting client quotes. The ceiling is {cap}. "
        f"Rewrite it at {cap} words or fewer, so cut at least {word_count - cap} words. Drop the "
        "least important sentence, clause or secondary figure; do not just trim words. Keep "
        "everything the subsection instructions below require, keep every number you keep "
        "exactly as given, and keep any client quote word for word. Change nothing else.\n\n"
        f"Subsection instructions:\n{prompt_config.instructions}\n\n"
        f"Draft:\n{text}"
    )


def _task_preamble(prompt_config: SubsectionPrompt, data_summary: str) -> str:
    return (
        f"Subsection: {prompt_config.title}\n"
        f"Word cap: {prompt_config.word_cap} words\n\n"
        f"{prompt_config.instructions}\n\n"
        f"Computed statistics:\n{data_summary}"
    )


def _shorten_rejection(candidate: str, previous_word_count: int, word_cap: int, pool: list[Verbatim], data_summary: str) -> list[str]:
    """Why a shortened draft can't replace the previous one; empty means accept. It must be
    actually shorter and break no rule other than length. A shorten pass that invents a quote
    or adds causal wording is thrown away, and the longer, clean draft is kept."""
    if not candidate.strip():
        return ["empty"]
    n = narrative_word_count(candidate, pool)
    if n >= previous_word_count:
        return [f"not shorter ({n} words)"]
    return _writer_violations(candidate, word_cap, pool, data_summary, include_length=False)


def write_subsection(
    prompt_config: SubsectionPrompt,
    data_summary: str,
    qualitative: Optional[QualitativeSynthesis] = None,
    acceptable_percentages: Optional[set] = None,
    reasoning_effort: str = "high",
) -> WrittenText:
    """Plain subsection write: no structured verbatim tracking. Use write_insight() instead
    for subsections the template asks to cite client quotes in.
    """
    llm = build_chat_model(reasoning_effort=reasoning_effort)

    task = _task_preamble(prompt_config, data_summary)
    if qualitative and qualitative.themes:
        task += f"\n\n{_format_qualitative_block(qualitative)}"

    response = llm.invoke([("system", SYSTEM_PROMPT), ("human", task)])
    text = extract_text(response)
    pool = _pool_verbatims(qualitative) if qualitative else []

    first_pass_word_count = narrative_word_count(text, pool)
    first_pass_violations = _writer_violations(text, prompt_config.word_cap, pool, data_summary)
    if first_pass_violations:
        revise_task = _revise_instruction(text, first_pass_violations, prompt_config.word_cap)
        response = llm.invoke([("system", SYSTEM_PROMPT), ("human", revise_task)])
        text = extract_text(response)

    word_count = narrative_word_count(text, pool)
    shortened, shorten_rejected = False, None
    if not within_tolerance(word_count, prompt_config.word_cap):
        response = llm.invoke([("system", SYSTEM_PROMPT), ("human", _shorten_instruction(text, word_count, prompt_config))])
        candidate = extract_text(response)
        shorten_rejected = _shorten_rejection(candidate, word_count, prompt_config.word_cap, pool, data_summary)
        if not shorten_rejected:
            text, shortened = candidate, True
            word_count = narrative_word_count(text, pool)
    _trace_writer_pass(
        prompt_config.subsection_id, "subsection", first_pass_violations, word_count, prompt_config.word_cap,
        first_pass_word_count, shortened, shorten_rejected,
    )

    return WrittenText(
        subsection_id=prompt_config.subsection_id,
        text=text,
        word_count=word_count,
        within_cap=within_tolerance(word_count, prompt_config.word_cap),
        ungrounded_percentages=check_grounding(text, acceptable_percentages or set()),
        ungrounded_quotes=check_quote_grounding(text, pool),
        partial_quotes=check_partial_quotes(text, pool),
        orphan_markers=check_orphan_markers(text),
        banned_punctuation=check_banned_punctuation(text),
        misattributed_quotes=check_profile_grounding(text, pool),
    )


def write_insight(
    prompt_config: SubsectionPrompt,
    data_summary: str,
    qualitative: QualitativeSynthesis,
    acceptable_percentages: Optional[set] = None,
    reasoning_effort: str = "high",
) -> tuple[WrittenText, list[Verbatim]]:
    """Like write_subsection, but for subsections that must cite verbatims (e.g. every Part's
    Insight). Also returns the real Verbatim objects actually quoted, resolved from our own
    pool by ID -- never from the model's own reproduction of them -- and drops any selected ID
    whose quote text doesn't actually turn up in the written prose.
    """
    pool = _pool_verbatims(qualitative)
    if not pool:
        written = write_subsection(prompt_config, data_summary, qualitative=qualitative, acceptable_percentages=acceptable_percentages, reasoning_effort=reasoning_effort)
        return written, []

    llm = build_chat_model(reasoning_effort=reasoning_effort, use_thinking=False)
    task = _task_preamble(prompt_config, data_summary) + "\n\n" + _format_verbatim_pool(pool) + INSIGHT_ID_INSTRUCTION

    raw: _NarrativeWithVerbatims = invoke_structured(
        llm, _NarrativeWithVerbatims, [("system", SYSTEM_PROMPT), ("human", task)]
    )
    text = raw.text.strip()

    first_pass_word_count = narrative_word_count(text, pool)
    first_pass_violations = _writer_violations(text, prompt_config.word_cap, pool, data_summary)
    if first_pass_violations:
        revise_task = (
            _revise_instruction(text, first_pass_violations, prompt_config.word_cap)
            + "\n\n"
            + _format_verbatim_pool(pool)
            + INSIGHT_ID_INSTRUCTION
        )
        raw = invoke_structured(llm, _NarrativeWithVerbatims, [("system", SYSTEM_PROMPT), ("human", revise_task)])
        text = raw.text.strip()

    word_count = narrative_word_count(text, pool)
    shortened, shorten_rejected = False, None
    if not within_tolerance(word_count, prompt_config.word_cap):
        shorten_task = (
            _shorten_instruction(text, word_count, prompt_config) + "\n\n" + _format_verbatim_pool(pool) + INSIGHT_ID_INSTRUCTION
        )
        candidate = invoke_structured(llm, _NarrativeWithVerbatims, [("system", SYSTEM_PROMPT), ("human", shorten_task)])
        shorten_rejected = _shorten_rejection(candidate.text.strip(), word_count, prompt_config.word_cap, pool, data_summary)
        if not shorten_rejected:
            raw, text, shortened = candidate, candidate.text.strip(), True
            word_count = narrative_word_count(text, pool)
    _trace_writer_pass(
        prompt_config.subsection_id, "insight", first_pass_violations, word_count, prompt_config.word_cap,
        first_pass_word_count, shortened, shorten_rejected,
    )

    used_verbatims = []
    for i in raw.used_verbatim_ids:
        if 0 <= i < len(pool) and pool[i].quote in text:
            used_verbatims.append(pool[i])

    written = WrittenText(
        subsection_id=prompt_config.subsection_id,
        text=text,
        word_count=word_count,
        within_cap=within_tolerance(word_count, prompt_config.word_cap),
        ungrounded_percentages=check_grounding(text, acceptable_percentages or set()),
        ungrounded_quotes=check_quote_grounding(text, pool),
        partial_quotes=check_partial_quotes(text, pool),
        orphan_markers=check_orphan_markers(text),
        banned_punctuation=check_banned_punctuation(text),
        misattributed_quotes=check_profile_grounding(text, pool),
    )
    return written, used_verbatims
