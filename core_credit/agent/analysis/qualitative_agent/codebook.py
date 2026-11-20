"""CC-089: theme-tag free text against a FIXED, human-approved codebook, with a per-response cache.

Why this exists: theme_tag_full_dataset (agent.py) is open coding -- every run invents its own
theme labels per batch and an LLM merge regroups them, and Sonnet 5 rejects `temperature`, so
nothing pins a run down. Test6 and local-cc066 disagreed on the lead detractor reason (interest
54.3% vs staff attitude 40.8%) on the same data. A year-over-year comparison needs both waves
coded against the same theme list, and a rerun on the same data needs to give the same numbers.

The flow (same method as GENDSI's insurance NPS codebooks):
  1. draft_codebook(): run the existing open coding once, then one LLM call turns the merged
     themes into codes with a one-line definition. Saved as codebooks/<question>_draft.json.
  2. A person reviews and edits the draft, then approve_draft() writes
     codebooks/<question>_approved.json without the review fields (which hold client answers).
  3. tag_with_codebook(): every response is coded into one or more approved codes, or "other".
     The model only picks from the list. Each response's codes are cached, keyed on question,
     codebook version, client id and a hash of the text, so a rerun on the same data makes no
     LLM call and gives identical shares. Bumping the codebook's "version" re-codes everything.
  4. Representative verbatims are chosen in code by a fixed rule, not by the model.

"other" is never reported as a theme: it holds answers no code fits (non-answers like "no
comments" included). Shares stay over every respondent with an answer (base_n), as before.
"""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from llm_client import build_chat_model, invoke_structured
from schemas.common import QualitativeSynthesis, ThemeFinding

from .agent import _response_key, _to_verbatim, pick_diverse_verbatims, theme_tag_full_dataset

log = logging.getLogger(__name__)

CODEBOOK_DIR = Path(__file__).resolve().parent / "codebooks"
DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "codebook_tags.json"
OTHER_CODE = "other"

# Representative quotes: prefer answers near this length (short enough to quote, long enough to
# say something), ties broken by a text hash so the pick never depends on row order or run.
_TARGET_QUOTE_LEN = 80


# ---------------------------------------------------------------------------------------------
# Codebook files
# ---------------------------------------------------------------------------------------------


def approved_path(question: str, codebook_dir: Optional[Path] = None) -> Path:
    return (codebook_dir or CODEBOOK_DIR) / f"{question}_approved.json"


def draft_path(question: str, codebook_dir: Optional[Path] = None) -> Path:
    return (codebook_dir or CODEBOOK_DIR) / f"{question}_draft.json"


def validate_codebook(codebook: dict) -> None:
    """Raises ValueError on a codebook that can't be coded against reliably."""
    themes = codebook.get("themes")
    if not isinstance(themes, list) or not themes:
        raise ValueError("codebook has no themes")
    if not isinstance(codebook.get("version"), int):
        raise ValueError("codebook needs an integer 'version'")
    codes = [t.get("code") for t in themes]
    if any(not c or not isinstance(c, str) for c in codes):
        raise ValueError("every theme needs a non-empty string 'code'")
    if len(set(codes)) != len(codes):
        raise ValueError(f"duplicate codes in codebook: {codes}")
    if OTHER_CODE in codes:
        raise ValueError(f"'{OTHER_CODE}' is reserved and added automatically")
    for t in themes:
        if not t.get("label") or not t.get("definition"):
            raise ValueError(f"theme {t.get('code')} needs a 'label' and a 'definition'")


def load_approved_codebook(question: str, codebook_dir: Optional[Path] = None) -> Optional[dict]:
    """The approved codebook, or None if nobody has approved one yet (callers fall back to open
    coding). An approved file that exists but is malformed raises rather than silently falling
    back, so a bad edit is caught on the next run."""
    path = approved_path(question, codebook_dir)
    if not path.exists():
        return None
    codebook = json.loads(path.read_text(encoding="utf-8"))
    validate_codebook(codebook)
    return codebook


def approve_draft(question: str, codebook_dir: Optional[Path] = None) -> dict:
    """Turns a reviewed draft into the approved file: validates it and drops every "_review"
    field (they hold client answers, and only the approved file is committed to git). If an
    approved file already exists with different themes, the version goes up by one so every
    answer is re-coded once under the new codebook."""
    draft = json.loads(draft_path(question, codebook_dir).read_text(encoding="utf-8"))
    themes = [{k: v for k, v in t.items() if not k.startswith("_review")} for t in draft["themes"]]
    approved = {"question": question, "version": int(draft.get("version", 1)), "themes": themes}
    previous = load_approved_codebook(question, codebook_dir)
    if previous is not None and previous["themes"] != themes:
        approved["version"] = max(approved["version"], previous["version"] + 1)
    elif previous is not None:
        approved["version"] = previous["version"]
    validate_codebook(approved)
    approved_path(question, codebook_dir).write_text(json.dumps(approved, ensure_ascii=False, indent=2), encoding="utf-8")
    return approved


# ---------------------------------------------------------------------------------------------
# Per-response cache
# ---------------------------------------------------------------------------------------------


def _text_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]


def cache_key(question: str, version: int, r) -> str:
    """No client text or raw client id in the key: question, codebook version, and hashes."""
    who = _text_hash(r.client_id) if r.client_id else "no_id"
    return f"{question}@v{version}:{r.source_field}:{who}:{_text_hash(r.text)}"


def load_cache(cache_path: Optional[Path] = None) -> dict:
    cache_path = cache_path or DEFAULT_CACHE_PATH
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(f"Could not read codebook tag cache at {cache_path}: {exc}; starting fresh")
        return {}


def save_cache(cache: dict, cache_path: Optional[Path] = None) -> None:
    cache_path = cache_path or DEFAULT_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")


# One lock for every read-modify-write of the cache file: the three NPS bands tag concurrently.
_CACHE_LOCK = threading.Lock()


# ---------------------------------------------------------------------------------------------
# Coding against the codebook
# ---------------------------------------------------------------------------------------------

CODING_SYSTEM_PROMPT = """You are a qualitative research analyst for VisionFund's Core Credit \
Impact Report. You code survey free-text responses against a FIXED codebook.

Rules:
- Use only the codes in the codebook below, or "other" when no code fits (including \
non-answers such as "no comment", "nothing", or unreadable text).
- A response may get more than one code if it genuinely raises more than one point.
- Code what the client actually said, in whatever language they wrote it. Do not infer \
reasons they did not give.
- Return every response ID you are shown, exactly once."""


class _CodedResponse(BaseModel):
    response_id: int = Field(description="The numbered response ID")
    codes: list[str] = Field(description="One or more codebook codes, or ['other']")


class _CodingOutput(BaseModel):
    # Throwaway second field: see llm_client.py on the single-field Sonnet 5 schema bug.
    coded_count: int = Field(default=0, description="Number of responses coded")
    responses: list[_CodedResponse]


def _format_codebook(codebook: dict) -> str:
    lines = ["Codebook:"]
    for t in codebook["themes"]:
        lines.append(f'- {t["code"]}: {t["label"]}. {t["definition"]}')
    lines.append(f"- {OTHER_CODE}: none of the above fits, or the answer gives no reason.")
    return "\n".join(lines)


def _format_batch(responses: list) -> str:
    return "\n".join(f"[{i}] {r.text}" for i, r in enumerate(responses))


def _clean_codes(codes: list, valid: set) -> list:
    """Keeps only codebook codes (order-stable, deduplicated). An answer whose every code was
    invalid becomes "other" rather than being dropped from the base."""
    kept = []
    for c in codes:
        c = (c or "").strip()
        if c in valid and c not in kept:
            kept.append(c)
    real = [c for c in kept if c != OTHER_CODE]
    return real or [OTHER_CODE]


def code_batch(responses: list, codebook: dict, task_instructions: str, max_retries: int = 1) -> dict:
    """Codes one batch. Returns {local index: [codes]} for every response the model returned;
    IDs it skipped are asked for again up to `max_retries` times. Anything still missing is
    left out, so the caller can count it as uncoded without caching a guess."""
    valid = {t["code"] for t in codebook["themes"]} | {OTHER_CODE}
    llm = build_chat_model(max_tokens=16000, use_thinking=False)
    pending = list(range(len(responses)))
    coded: dict = {}
    for _attempt in range(max_retries + 1):
        if not pending:
            break
        batch = [responses[i] for i in pending]
        task = f"{task_instructions}\n\n{_format_codebook(codebook)}\n\nResponses:\n{_format_batch(batch)}"
        raw: _CodingOutput = invoke_structured(
            llm, _CodingOutput, [("system", CODING_SYSTEM_PROMPT), ("human", task)]
        )
        for item in raw.responses:
            if 0 <= item.response_id < len(batch):
                original = pending[item.response_id]
                coded.setdefault(original, _clean_codes(item.codes, valid))
        pending = [i for i in pending if i not in coded]
    return coded


def _quote_sort_key(r) -> tuple:
    return (abs(len(r.text.strip()) - _TARGET_QUOTE_LEN), _text_hash(r.text))


def _synthesis_from_codes(section_label: str, responses: list, codes_by_index: dict, codebook: dict) -> QualitativeSynthesis:
    n = len(responses)
    themes = []
    for t in codebook["themes"]:
        members = [i for i in range(n) if t["code"] in codes_by_index.get(i, [])]
        if not members:
            continue
        ordered = sorted((responses[i] for i in members), key=_quote_sort_key)
        themes.append(
            ThemeFinding(
                theme=t["label"],
                frequency=len(members),
                share_of_respondents=len(members) / n,
                representative_verbatims=pick_diverse_verbatims([_to_verbatim(r) for r in ordered], k=3),
                response_keys=sorted(_response_key(responses[i], i) for i in members),
            )
        )
    # Ties broken by label so equal counts never swap order between runs.
    themes.sort(key=lambda th: (-th.frequency, th.theme))
    return QualitativeSynthesis(source_field=section_label, base_n=n, themes=themes)


def tag_with_codebook(
    section_label: str,
    question: str,
    responses: list,
    codebook: dict,
    task_instructions: str,
    batch_size: int = 100,
    max_workers: int = 6,
    cache_path: Optional[Path] = None,
) -> QualitativeSynthesis:
    """Codes every response against `codebook`, reusing cached codes where the same answer was
    already coded under the same codebook version. Only cache misses call the LLM."""
    validate_codebook(codebook)
    n = len(responses)
    if n == 0:
        return QualitativeSynthesis(source_field=section_label, base_n=0, themes=[])

    version = codebook["version"]
    with _CACHE_LOCK:
        cache = load_cache(cache_path)
    keys = [cache_key(question, version, r) for r in responses]

    codes_by_index: dict = {}
    misses: list = []
    for i, k in enumerate(keys):
        if k in cache:
            codes_by_index[i] = cache[k]
        else:
            misses.append(i)

    if misses:
        batches = [misses[j : j + batch_size] for j in range(0, len(misses), batch_size)]
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            futures = [
                (batch, pool.submit(code_batch, [responses[i] for i in batch], codebook, task_instructions))
                for batch in batches
            ]
            for batch, future in futures:
                for local, codes in future.result().items():
                    codes_by_index[batch[local]] = codes

        with _CACHE_LOCK:
            cache = load_cache(cache_path)  # re-read: another band may have saved meanwhile
            for i in misses:
                if i in codes_by_index:
                    cache[keys[i]] = codes_by_index[i]
            save_cache(cache, cache_path)

    uncoded = n - len(codes_by_index)
    print(
        f"{section_label}: {n} responses, {n - len(misses)} from cache, {len(misses)} coded now"
        + (f", {uncoded} left uncoded (not cached, will retry next run)" if uncoded else "")
    )
    return _synthesis_from_codes(section_label, responses, codes_by_index, codebook)


def tag_responses(section_label: str, question: str, responses: list, task_instructions: str, **kwargs) -> QualitativeSynthesis:
    """What section builders call: the approved codebook if there is one, else open coding."""
    codebook = load_approved_codebook(question, kwargs.pop("codebook_dir", None))
    if codebook is None:
        print(f"{section_label}: no approved codebook for '{question}', using open coding (not stable between runs)")
        return theme_tag_full_dataset(section_label, responses, task_instructions)
    return tag_with_codebook(section_label, question, responses, codebook, task_instructions, **kwargs)


# ---------------------------------------------------------------------------------------------
# Drafting a codebook (run once per question, then reviewed by a person)
# ---------------------------------------------------------------------------------------------

DRAFT_SYSTEM_PROMPT = """You turn the themes found in a set of survey answers into a codebook \
that another analyst will use to code every answer consistently.

For each theme give a short snake_case code, a plain English label, and a one-sentence \
definition that says what belongs in it and, where two themes are close, what does not. Merge \
themes that a coder could not tell apart. Do not create a theme for non-answers: those go to \
"other", which is added automatically. Keep the theme order you are given."""


class _DraftTheme(BaseModel):
    code: str = Field(description="Short snake_case code, e.g. high_interest_rates")
    label: str = Field(description="Plain English label")
    definition: str = Field(description="One sentence: what belongs here, and what does not")
    source_theme_indices: list[int] = Field(description="Indices of the found themes this code covers")


class _DraftOutput(BaseModel):
    theme_count: int = Field(default=0, description="Number of codes")
    themes: list[_DraftTheme]


def draft_codebook(question: str, responses: list, task_instructions: str, codebook_dir: Optional[Path] = None) -> dict:
    """Open-codes the responses once, then writes a draft codebook for review. The draft also
    carries, per code, the open-coding share and a few example answers, so the reviewer can see
    what each code would hold. Those review fields are ignored when coding."""
    found = theme_tag_full_dataset(f"{question}[draft]", responses, task_instructions)
    lines = []
    for i, t in enumerate(found.themes):
        examples = "; ".join(f'"{v.quote[:100]}"' for v in t.representative_verbatims[:3])
        lines.append(f'[{i}] "{t.theme}" (share {t.share_of_respondents or 0:.1%}) examples: {examples}')

    llm = build_chat_model(max_tokens=8000, use_thinking=False)
    task = f"{task_instructions}\n\nThemes found:\n" + "\n".join(lines)
    raw: _DraftOutput = invoke_structured(llm, _DraftOutput, [("system", DRAFT_SYSTEM_PROMPT), ("human", task)])

    themes = []
    for d in raw.themes:
        sources = [found.themes[i] for i in d.source_theme_indices if 0 <= i < len(found.themes)]
        themes.append(
            {
                "code": d.code,
                "label": d.label,
                "definition": d.definition,
                "_review_open_coding_share": round(sum(s.share_of_respondents or 0 for s in sources), 3),
                "_review_examples": [v.quote for s in sources for v in s.representative_verbatims][:4],
            }
        )
    codebook = {"question": question, "version": 1, "base_n": found.base_n, "themes": themes}

    path = draft_path(question, codebook_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2), encoding="utf-8")
    return codebook
