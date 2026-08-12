"""Shared Claude Sonnet 5 client factory for every LLM-calling component under agent/analysis/.

Switched from Opus 5 to Sonnet 5 (2026-08-07) to cut per-run cost. Centralizes the
model-specific quirks found while setting this up:

- `temperature` is rejected outright for this model (400 error) -- never pass it.
- Extended thinking is only configurable via the "adaptive thinking" +
  `reasoning_effort` API -- the older `{"type": "enabled", "budget_tokens": N}`
  form is not supported.
- Structured output via forced tool calling has a real Sonnet-5-specific failure mode,
  reproduced live and confirmed data-size-dependent, NOT thinking-dependent (an earlier
  version of this note blamed adaptive thinking off a too-small test; that diagnosis was
  wrong -- disabling thinking alone does not fix it): for a single-field wrapper schema
  (e.g. `class Output(BaseModel): themes: list[...]`), once the batch is large enough, the
  model sometimes serializes the ENTIRE answer object as a JSON string and hands it back as
  the value of that one field -- e.g. `{"themes": '{"themes": [...]}'}` -- instead of
  populating the field directly. `.with_structured_output()` then fails pydantic validation
  ("Input should be a valid list", got a str).
  This is stochastic, not a fixed trigger condition -- there is no known way to make it
  exactly zero, only to push the rate down and catch the rest:
  1. Schema mitigation: give every structured-output schema at least two fields (e.g. a
     throwaway `theme_count: int`, never read). Lowers the rate a lot but does NOT zero it
     out -- confirmed live: a one-field wrapper failed repeatedly at 180 responses; the
     two-field version was 4/4 clean in one trial run, then still failed 2/5 in a later,
     larger trial run. `_ThemeTaggingOutput`/`_MergeOutput` in qualitative_agent/agent.py
     both carry such a field for this reason -- keep it, and give any new single-field
     structured-output schema the same treatment.
  2. Unwrap-before-validate: if the top-level args still come back double-encoded,
     `invoke_structured()` detects a string value that JSON-decodes to a dict matching the
     schema's own field names and substitutes it before validating.
  3. Bounded retry: unwrap can't help when the doubly-escaped string itself gets cut off by
     max_tokens before its closing brace (that happened in production once, and looks like
     invalid/unparseable JSON, not recoverable data). `invoke_structured()` retries the
     WHOLE call (a fresh generation, not just re-parsing) up to `max_retries` times before
     raising -- only calls that actually hit the bug pay for a retry.
  Always use `invoke_structured()` instead of `.with_structured_output(...).invoke(...)` at
  every structured-output call site -- it's the only code path with all three layers.
- LangSmith tracing is automatic via the LANGSMITH_* env vars in .env -- nothing
  code-side to wire up here, just make sure load_dotenv() has already run in
  whatever script imports this (each run_validation.py does that itself).
"""

from __future__ import annotations

import json
from typing import Literal, TypeVar

from langchain_anthropic import ChatAnthropic
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

ReasoningEffort = Literal["max", "xhigh", "high", "medium", "low"]

MODEL = "claude-sonnet-5"

SchemaT = TypeVar("SchemaT", bound=BaseModel)


def build_chat_model(
    reasoning_effort: ReasoningEffort = "high", max_tokens: int = 4096, use_thinking: bool = True
) -> ChatAnthropic:
    """A ChatAnthropic client configured for Sonnet 5.

    `use_thinking` defaults to True for plain-generation call sites. Pass
    `use_thinking=False` at any call site that chains `.with_structured_output(...)`
    off the returned model -- see the module docstring for why.
    """
    if not use_thinking:
        return ChatAnthropic(model=MODEL, max_tokens=max_tokens)
    return ChatAnthropic(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive", "display": "summarized"},
        reasoning_effort=reasoning_effort,
    )


def extract_text(response) -> str:
    """With adaptive thinking on, `.content` comes back as a list of blocks (thinking +
    text) instead of a plain string. Pulls out and concatenates just the text block(s).
    """
    content = response.content
    if isinstance(content, str):
        return content.strip()
    parts = [block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"]
    return "".join(parts).strip()


def invoke_structured(llm: ChatAnthropic, schema: type[SchemaT], messages, max_retries: int = 2) -> SchemaT:
    """Structured-output call via forced tool calling, with a workaround for the Sonnet-5
    double-encoding quirk described in the module docstring.

    Binds `schema` as the one forced tool (mirroring what `.with_structured_output()` does
    internally). Before validating, repairs each top-level argument independently: if a
    field's value is a JSON string that decodes to a dict CONTAINING that same field name --
    e.g. `args["themes"] == '{"themes": [...]}'` -- the model has nested the field one level
    too deep (sometimes wrapping just that field, sometimes re-stuffing the whole answer
    into it), so pull out `parsed[field_name]` as the real value. This is deliberately
    per-field, not a whole-args swap: an earlier version required the parsed dict's keys to
    exactly match every field in the schema, which silently failed to fire on multi-field
    schemas where only ONE field got corrupted this way (confirmed live -- see below).

    This bug is stochastic per-generation, not a fixed trigger condition. At a realistic
    batch size (180 responses), the per-field unwrap above resolved it 6/6 -- including the
    exact seeds that had failed 4/6 under the earlier (buggy) whole-args version. `max_tokens`
    headroom and `max_retries` remain as defense-in-depth for the case that motivated adding
    retry in the first place: the doubly-escaped string getting cut off by max_tokens before
    its closing brace, which is invalid JSON and not recoverable by any unwrap logic.
    """
    bound = llm.bind_tools([schema], tool_choice=schema.__name__)
    last_error: Exception = OutputParserException(f"Model did not call the {schema.__name__} tool.")

    for _attempt in range(max_retries + 1):
        response = bound.invoke(messages)
        if not response.tool_calls:
            continue

        args = dict(response.tool_calls[0]["args"])
        for key, value in list(args.items()):
            if not isinstance(value, str):
                continue
            try:
                parsed = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and key in parsed:
                args[key] = parsed[key]

        try:
            return schema(**args)
        except ValidationError as e:
            last_error = e
            continue

    raise last_error
