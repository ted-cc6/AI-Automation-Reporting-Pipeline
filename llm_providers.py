"""dashboard/api/llm_providers.py

Single call-through for the three LLM providers the dashboard lets a user pick:
Gemini, Anthropic, and OpenAI. All three are used in "JSON-mode + prose-described
shape" style, matching how qualitative/llm_call.py and generation/writer.py
already prompt Gemini -- there is no formal structured-output schema object
anywhere in this project, so the abstraction doesn't need one either.

call_llm() always returns the raw JSON text (not a pre-parsed dict); existing
json.loads() call sites in qualitative/parse_results.py and generation/writer.py
are left untouched.
"""
import json
import logging
from typing import Literal

log = logging.getLogger(__name__)

Provider = Literal["gemini", "anthropic", "openai"]

DEFAULT_MODELS: dict[Provider, str] = {
    "gemini": "gemini-2.5-pro",
    "anthropic": "claude-opus-4-8",
    "openai": "gpt-5.1",
}

# Anthropic models that reject temperature/top_p/top_k outright (400) -- adaptive
# thinking replaced sampling-param tuning on these tiers. Checked proactively so
# the default model (claude-opus-4-8) doesn't pay for a failed request + retry
# on every single call.
_ANTHROPIC_NO_SAMPLING_PARAMS = frozenset({
    "claude-fable-5", "claude-mythos-5",
    "claude-opus-4-8", "claude-opus-4-7",
    "claude-sonnet-5",
})


def _call_gemini(api_key: str, system_prompt: str, user_content: str,
                  max_output_tokens: int, temperature: float | None, model: str) -> str:
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=user_content,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            max_output_tokens=max_output_tokens,
            temperature=temperature,
        ),
    )
    return response.text


def _call_anthropic(api_key: str, system_prompt: str, user_content: str,
                     max_output_tokens: int, temperature: float | None, model: str) -> str:
    from anthropic import Anthropic

    client = Anthropic(api_key=api_key)
    tool = {
        "name": "emit_json",
        "description": "Return the result as JSON matching the shape described in the prompt.",
        "input_schema": {"type": "object", "additionalProperties": True},
    }
    kwargs = dict(
        model=model,
        max_tokens=max_output_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_content}],
        tools=[tool],
        tool_choice={"type": "tool", "name": "emit_json"},
    )
    if temperature is not None and model not in _ANTHROPIC_NO_SAMPLING_PARAMS:
        kwargs["temperature"] = temperature

    try:
        response = client.messages.create(**kwargs)
    except Exception as exc:
        # Catch-all for any other/future tier that also rejects temperature --
        # the proactive skip above covers the known ones (incl. the default
        # claude-opus-4-8) without paying for a failed request first.
        if "temperature" in kwargs and "temperature" in str(exc).lower():
            log.warning(f"Model {model} rejected temperature param; retrying without it.")
            kwargs.pop("temperature")
            response = client.messages.create(**kwargs)
        else:
            raise

    for block in response.content:
        if block.type == "tool_use":
            return json.dumps(block.input, ensure_ascii=False)
    raise ValueError("Anthropic response did not contain a tool_use block with JSON output.")


def _call_openai(api_key: str, system_prompt: str, user_content: str,
                  max_output_tokens: int, temperature: float | None, model: str) -> str:
    from openai import OpenAI

    client = OpenAI(api_key=api_key)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=max_output_tokens,
        temperature=temperature,
    )
    return response.choices[0].message.content


_DISPATCH = {
    "gemini": _call_gemini,
    "anthropic": _call_anthropic,
    "openai": _call_openai,
}


def call_llm(
    provider: Provider,
    api_key: str,
    system_prompt: str,
    user_content: str,
    max_output_tokens: int,
    temperature: float | None,
    model: str | None = None,
) -> str:
    """One attempt; raises on failure. Callers keep their own retry/backoff loops."""
    if provider not in _DISPATCH:
        raise ValueError(f"Unknown provider: {provider!r}. Expected one of {list(_DISPATCH)}.")
    resolved_model = model or DEFAULT_MODELS[provider]
    return _DISPATCH[provider](api_key, system_prompt, user_content, max_output_tokens, temperature, resolved_model)


def validate_key(provider: Provider, api_key: str) -> tuple[bool, str]:
    """Cheap metadata-only call to confirm a key works -- no generation cost."""
    try:
        if provider == "gemini":
            from google import genai
            client = genai.Client(api_key=api_key)
            next(iter(client.models.list()), None)
        elif provider == "anthropic":
            from anthropic import Anthropic
            Anthropic(api_key=api_key).models.list()
        elif provider == "openai":
            from openai import OpenAI
            OpenAI(api_key=api_key).models.list()
        else:
            return False, f"Unknown provider: {provider!r}"
        return True, "Key is valid."
    except Exception as exc:
        return False, str(exc)
