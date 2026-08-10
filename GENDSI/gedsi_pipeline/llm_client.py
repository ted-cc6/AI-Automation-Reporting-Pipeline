"""
Claude wrapper used by every LLM-calling stage (Stage 3 codebook induction,
Stage 3 coding, Stage 5 draft writing).

- generate_json() takes the API key explicitly, like llm_providers.call_llm()
  in the dashboard package -- no global client, no interactive prompt, so
  this module is safe to call from a web request handler serving a
  different user's key on every call. Nothing is ever written to disk, env,
  or logs.
- prompt_for_api_key() is a CLI-only convenience: getpass once at the start
  of an interactive run (RUNBOOK.md's usage), returning a plain string the
  caller then passes to every generate_json() call itself. Non-interactive
  callers (a web backend) already have the key from their own request and
  never call this.
- Every generate_json() call is content-addressed cached to cache/ so
  re-running a stage (e.g. after tweaking a prompt, or resuming after the
  codebook review pause) doesn't re-spend on unchanged calls. The cache is
  shared/global across runs, not per-run: the key already hashes the full
  prompt text (which embeds the actual data sample), so two different
  datasets can never collide on the same cache entry.
- Structured stages pass a JSON schema and get back parsed JSON (via
  output_config.format), not free text to scrape.
"""
from __future__ import annotations

import copy
import getpass
import hashlib
import json
import time

import anthropic

from gedsi_pipeline import config


def prompt_for_api_key() -> str:
    """CLI-only: getpass once at the start of an interactive run."""
    api_key = getpass.getpass("Claude API key (input hidden, not stored): ").strip()
    if not api_key:
        raise SystemExit("No API key entered; aborting.")
    return api_key


def _cache_key(model: str, prompt: str, schema_repr: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode())
    h.update(b"\0")
    h.update(schema_repr.encode())
    h.update(b"\0")
    h.update(prompt.encode())
    return h.hexdigest()


def _cache_path(key: str):
    return config.CACHE_DIR / f"{key}.json"


def _to_claude_json_schema(node):
    """Adapt a Gemini-style response_schema to Claude's structured-outputs
    dialect: every object needs additionalProperties: false, and array
    length constraints (unsupported) are folded into the description
    instead of dropped silently."""
    node = copy.deepcopy(node)

    def walk(n):
        if not isinstance(n, dict):
            return n
        if n.get("type") == "object":
            n.setdefault("additionalProperties", False)
            for v in n.get("properties", {}).values():
                walk(v)
        elif n.get("type") == "array":
            if "items" in n:
                walk(n["items"])
            notes = []
            if "minItems" in n:
                notes.append(f"minimum {n.pop('minItems')} items")
            if "maxItems" in n:
                notes.append(f"maximum {n.pop('maxItems')} items")
            if notes:
                n["description"] = (n.get("description", "") + " (" + ", ".join(notes) + ")").strip()
        return n

    return walk(node)


def generate_json(prompt: str, response_schema: dict, api_key: str, *, model: str = config.CLAUDE_MODEL,
                   effort: str = "medium", max_retries: int = 4) -> dict:
    """Call Claude with a JSON schema constraining the response; returns
    parsed JSON (dict/list). Cached on (model, schema, prompt) -- a cache hit
    never touches api_key or the network at all."""
    config.CACHE_DIR.mkdir(parents=True, exist_ok=True)
    schema_repr = json.dumps(response_schema, sort_keys=True)
    key = _cache_key(model, prompt, schema_repr)
    path = _cache_path(key)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))

    client = anthropic.Anthropic(api_key=api_key)
    claude_schema = _to_claude_json_schema(response_schema)
    last_err = None
    for attempt in range(max_retries):
        try:
            resp = client.messages.create(
                model=model,
                max_tokens=16000,
                output_config={
                    "effort": effort,
                    "format": {"type": "json_schema", "schema": claude_schema},
                },
                messages=[{"role": "user", "content": prompt}],
            )
            if resp.stop_reason == "refusal":
                raise RuntimeError(f"Claude declined the request: {resp.stop_details}")
            text = next(b.text for b in resp.content if b.type == "text")
            data = json.loads(text)
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            return data
        except Exception as e:  # noqa: BLE001 - retry on any transient API/parse error
            last_err = e
            time.sleep(min(2 ** attempt, 20))
    raise RuntimeError(f"Claude call failed after {max_retries} attempts: {last_err}")


def smoke_test():
    """One tiny live call to confirm the API key, model name, and cache all work."""
    schema = {
        "type": "object",
        "properties": {"greeting": {"type": "string"}},
        "required": ["greeting"],
    }
    api_key = prompt_for_api_key()
    result = generate_json(
        "Reply with a short one-sentence greeting confirming you are ready to help "
        "analyze a GEDSI insurance survey.",
        schema,
        api_key,
    )
    print("Smoke test response:", result)


if __name__ == "__main__":
    smoke_test()
