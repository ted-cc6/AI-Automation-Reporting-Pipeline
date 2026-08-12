"""Theme-tagging chain.

The model is only ever asked to classify: given a numbered list of responses, which theme
does each belong to, and which 2-3 IDs best represent it. It never writes quote text or
profile fields -- ThemeFinding/Verbatim objects are assembled afterward from our own
FreeTextResponse records, keyed by the IDs the model chose. An out-of-range ID is dropped
rather than guessed at. This is the same "don't let the LLM touch the facts" pattern used
throughout the pipeline, applied to free text instead of survey statistics.

Real Core Credit sections run to thousands of responses (quality-of-life drivers alone is
~5800 this quarter), far more than one structured-output call can reliably hold -- a batch of
just 60 responses already needed 16k tokens once thinking was accounted for, and asking a
single call to echo back thousands of response IDs per theme isn't a sound design at any
token budget. theme_tag_full_dataset splits the dataset into batches, theme-tags each batch
independently and in parallel (theme_tag_batch), then merges the batch-level themes into one
canonical list via a second, much smaller LLM call that only ever groups POOLED THEME
SUMMARIES by index -- it never re-touches raw response text either. Frequency counts and
representative-verbatim selection for the merged themes are both done in plain Python, using
only the already-grounded Verbatim objects the batch passes produced.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from pydantic import BaseModel, Field

from llm_client import build_chat_model, invoke_structured
from schemas.common import QualitativeSynthesis, ThemeFinding, Verbatim

from .data_prep import FreeTextResponse

SYSTEM_PROMPT = """You are a qualitative research analyst for VisionFund's Core Credit Impact \
Report. You theme-tag survey free-text responses into a small number of clear, recurring \
themes.

You never invent, translate, or paraphrase a client's words into your output -- you only \
classify which numbered response belongs to which theme, by response ID. The actual quote \
text and client profile will be attached separately from our own records, not from what you \
write, so your job is classification and selection only.

For each theme:
- Give a short, clear theme label in English, even when the underlying responses are in \
Spanish or another language.
- List every response ID that belongs to this theme, for an accurate frequency count -- a \
response may belong to more than one theme if it genuinely touches on more than one.
- Select the 2-3 of those IDs that best represent the theme.
- Only set severity ("high", "medium", or "low") if the theme reflects a client-protection \
concern (harassment, coercion, misselling, real hardship) -- leave it unset for ordinary \
thematic content.

Aim for a manageable number of clear themes (roughly 4-8 for a batch this size), not one \
theme per response. Merge near-duplicate themes rather than fragmenting them. Every response \
ID you use must be one of the IDs actually shown to you below -- never invent an ID."""

QUALITY_OF_LIFE_DRIVERS_TASK = """These responses answer three different follow-up questions \
about how a VisionFund loan affected the client's quality of life:
- IMPACT03a: "How has it improved?" (asked to clients who said life improved)
- IMPACT03b: "Why has it not changed?" (asked to clients who said no change)
- IMPACT03c: "How has it become worse?" (asked to clients who said life got worse)

The source question for each response is shown in parentheses before its text. Keep themes \
from these three questions conceptually distinct: what the loan drove (from IMPACT03a) should \
read as a different kind of theme than reasons for no change (IMPACT03b) or ways life got \
worse (IMPACT03c). A response from IMPACT03c should never be folded into a positive "what \
improved" theme, even if the wording sounds similar."""

PROTECTION_SIGNALS_TASK = """These responses answer two different follow-up questions:
- IMPACT03c: "How has your quality of life become worse?" (asked to clients who said life got \
worse because of the loan)
- CLIENTSAT01b: "What actions could VisionFund take to make you more likely to recommend?" \
(asked to clients who scored 0-6 on the recommendation question)

Unlike other theme-tagging passes over similar text, your ONLY job here is to identify \
client-protection signals: unfair treatment, harassment, coercion, pressure tactics, or \
misselling by a VisionFund representative, and complaints about the complaints/redress process \
itself (e.g. a complaint that was ignored or handled unfairly). Theme-tag ONLY responses that \
describe a genuine conduct or protection concern. Ordinary dissatisfaction with interest rates, \
loan terms, loan size, or processing speed is NOT a protection signal on its own and must not \
be grouped into a theme here, even though it will dominate the response volume in both source \
questions. If a response contains no protection-relevant content, it belongs in no theme at \
all -- do not force it into one to make the results look more complete.

Set severity on every theme you create (this is required here, not optional as it is for other \
theme-tagging tasks): high for coercion, harassment, or deliberate misselling; medium for \
pressure tactics or a protection process that failed a client; low for a milder conduct \
complaint. Expect fewer, smaller themes than a typical pass -- most of the response volume in \
both source questions is ordinary dissatisfaction, not a protection signal, and should simply \
not appear in your output."""

MERGE_SYSTEM_PROMPT = """You are consolidating theme-tagging results that were produced \
independently across several batches of the same underlying survey question. Several of the \
pooled summaries below describe the same underlying theme in slightly different words -- your \
job is to group them into a smaller set of canonical themes.

You only ever select pooled-item indices into groups; you do not rewrite or invent quote text. \
Keep themes conceptually distinct across batches the same way a single batch would: a theme \
about something improving should never merge with a theme about something not changing or \
getting worse, even if a merge would otherwise look tidy. Every pooled index must end up in \
exactly one group -- do not drop any."""


class _ThemeAssignment(BaseModel):
    theme: str = Field(description="Short, clear theme label in English")
    all_response_ids: list[int] = Field(
        description="Every response ID (from the numbered list given) belonging to this theme"
    )
    representative_response_ids: list[int] = Field(
        description="2-3 of the IDs above that best represent this theme"
    )
    severity: Optional[str] = Field(
        default=None, description="high/medium/low -- only for client-protection-relevant themes"
    )


class _ThemeTaggingOutput(BaseModel):
    # theme_count is a throwaway field, never read -- a single-field wrapper (just `themes:
    # list[...]`) reliably triggers a Sonnet-5 tool-calling bug at realistic batch sizes: the
    # model serializes its whole answer as a JSON string and hands it back AS that one
    # field's value instead of populating it, which then fails schema validation (worse, on
    # a large enough batch the double-encoded string itself gets cut off by max_tokens before
    # the closing brace, so it isn't even recoverable JSON). Reproduced live: 4/4 clean at a
    # two-field schema, 180 responses, vs. a repeated failure at one field. See
    # llm_client.py's docstring for the underlying mechanism.
    theme_count: int = Field(default=0, description="Number of distinct themes found")
    themes: list[_ThemeAssignment]


class _MergeGroup(BaseModel):
    canonical_label: str = Field(description="Final theme label for this merged group, in English")
    pooled_indices: list[int] = Field(
        description="Every pooled item index (from the numbered list given) that belongs to this canonical theme"
    )


class _MergeOutput(BaseModel):
    # group_count is a throwaway field, never read -- see _ThemeTaggingOutput's comment above:
    # a single-field wrapper schema is what triggers the Sonnet-5 double-encoding bug.
    group_count: int = Field(default=0, description="Number of merged groups")
    groups: list[_MergeGroup]


SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1}


def _format_responses(responses: list) -> str:
    lines = []
    for i, r in enumerate(responses):
        question = r.source_field.rsplit("/", 1)[-1].replace("_resp_en", "")
        lines.append(f"[{i}] ({question}) {r.text}")
    return "\n".join(lines)


def _to_verbatim(r: FreeTextResponse) -> Verbatim:
    return Verbatim(
        quote=r.text,
        gender=r.gender,
        age=r.age,
        branch=r.branch,
        country=r.country,
        loan_cycle=r.loan_cycle,
        segment_tags=list(r.segment_tags),
        source_field=r.source_field,
        client_id=r.client_id,
    )


def theme_tag_batch(
    section_label: str,
    responses: list,
    task_instructions: str,
    reasoning_effort: str = "high",
    max_tokens: int = 24000,
) -> QualitativeSynthesis:
    """Theme-tags one batch of responses (small enough for a single structured-output call).

    max_tokens defaults high (24000, raised from 16000) -- a batch of even a few dozen
    responses ran out of room at the library default of 4096 and returned an empty result;
    raised further after a production run hit the Sonnet-5 double-encoding bug (see
    llm_client.py's docstring) where the doubly-escaped string got cut off mid-JSON at
    16000. The schema-level fix (_ThemeTaggingOutput's throwaway second field) is what
    actually prevents the bug; this is just extra headroom in case it still slips through,
    and costs nothing unless actually used. use_thinking=False and invoke_structured() (not
    `.with_structured_output()`) are the other two layers of the same workaround.
    """
    n = len(responses)
    if n == 0:
        return QualitativeSynthesis(source_field=section_label, base_n=0, themes=[])

    llm = build_chat_model(reasoning_effort=reasoning_effort, max_tokens=max_tokens, use_thinking=False)
    task = f"{task_instructions}\n\nResponses:\n{_format_responses(responses)}"
    raw: _ThemeTaggingOutput = invoke_structured(
        llm, _ThemeTaggingOutput, [("system", SYSTEM_PROMPT), ("human", task)]
    )

    themes = []
    for assignment in raw.themes:
        valid_all_ids = [i for i in assignment.all_response_ids if 0 <= i < n]
        valid_rep_ids = [i for i in assignment.representative_response_ids if 0 <= i < n][:3]
        if not valid_all_ids:
            continue  # every ID the model gave was out of range -- drop rather than guess
        themes.append(
            ThemeFinding(
                theme=assignment.theme,
                frequency=len(valid_all_ids),
                share_of_respondents=len(valid_all_ids) / n,
                representative_verbatims=[_to_verbatim(responses[i]) for i in valid_rep_ids],
                severity=assignment.severity,
            )
        )
    themes.sort(key=lambda t: t.frequency, reverse=True)

    return QualitativeSynthesis(source_field=section_label, base_n=n, themes=themes)


def pick_diverse_verbatims(verbatims: list, k: int = 3) -> list:
    """Prefers spreading picks across different countries over taking the first k -- this is
    what makes the final report's verbatim bank not concentrate on whichever country happened
    to dominate a batch.
    """
    picked: list = []
    seen_countries: set = set()
    for v in verbatims:
        if len(picked) >= k:
            break
        if v.country not in seen_countries:
            picked.append(v)
            seen_countries.add(v.country)
    if len(picked) < k:
        for v in verbatims:
            if len(picked) >= k:
                break
            if v not in picked:
                picked.append(v)
    return picked


def _highest_severity(severities: list) -> Optional[str]:
    ranked = [s for s in severities if s in SEVERITY_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda s: SEVERITY_RANK[s])


def merge_batches(
    section_label: str,
    batch_results: list,
    total_n: int,
    reasoning_effort: str,
) -> QualitativeSynthesis:
    """The reduce half of the batch/merge map-reduce -- public so it can be called directly as
    a graph node (e.g. after a Send-based fan-out over theme_tag_batch), not just from
    theme_tag_full_dataset's own ThreadPoolExecutor path.
    """
    pooled: list = []  # list of ThemeFinding, one entry per (batch, theme)
    for synth in batch_results:
        pooled.extend(synth.themes)

    if not pooled:
        return QualitativeSynthesis(source_field=section_label, base_n=total_n, themes=[])

    summary_lines = []
    for i, theme in enumerate(pooled):
        examples = "; ".join(f'"{v.quote[:80]}"' for v in theme.representative_verbatims[:2])
        summary_lines.append(f'[{i}] "{theme.theme}" (n={theme.frequency}) examples: {examples}')

    llm = build_chat_model(reasoning_effort=reasoning_effort, max_tokens=24000, use_thinking=False)
    task = "Pooled theme summaries:\n" + "\n".join(summary_lines)
    raw: _MergeOutput = invoke_structured(llm, _MergeOutput, [("system", MERGE_SYSTEM_PROMPT), ("human", task)])

    themes = []
    for group in raw.groups:
        member_indices = [i for i in group.pooled_indices if 0 <= i < len(pooled)]
        if not member_indices:
            continue
        member_themes = [pooled[i] for i in member_indices]
        frequency = sum(t.frequency for t in member_themes)
        all_candidate_verbatims = [v for t in member_themes for v in t.representative_verbatims]
        themes.append(
            ThemeFinding(
                theme=group.canonical_label,
                frequency=frequency,
                share_of_respondents=(frequency / total_n if total_n else None),
                representative_verbatims=pick_diverse_verbatims(all_candidate_verbatims, k=3),
                severity=_highest_severity([t.severity for t in member_themes]),
            )
        )
    themes.sort(key=lambda t: t.frequency, reverse=True)

    return QualitativeSynthesis(source_field=section_label, base_n=total_n, themes=themes)


def theme_tag_full_dataset(
    section_label: str,
    responses: list,
    task_instructions: str,
    batch_size: int = 200,
    max_workers: int = 6,
    reasoning_effort: str = "high",
) -> QualitativeSynthesis:
    """Theme-tags the FULL `responses` list, however large, by batching + parallel batch calls
    + a merge pass -- see the module docstring for why a single call doesn't scale to this.
    """
    n = len(responses)
    if n == 0:
        return QualitativeSynthesis(source_field=section_label, base_n=0, themes=[])

    batches = [responses[i : i + batch_size] for i in range(0, n, batch_size)]
    batch_results: list = [None] * len(batches)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(theme_tag_batch, f"{section_label}[batch {i}]", batch, task_instructions, reasoning_effort): i
            for i, batch in enumerate(batches)
        }
        for future in as_completed(futures):
            batch_results[futures[future]] = future.result()

    return merge_batches(section_label, batch_results, n, reasoning_effort)
