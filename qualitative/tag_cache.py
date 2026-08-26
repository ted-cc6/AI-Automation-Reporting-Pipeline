"""qualitative/tag_cache.py

Persistent cache for per-response LLM classifications (NPS theme tags,
protection flags), keyed by (respondent id, content hash). Regenerating a
report from the SAME underlying survey data should not re-roll the dice on
each individual response's classification every time -- three consecutive
runs on identical data were observed to disagree on protection-flag counts
(31 / 29 / 25), individual case severity/type (the same client reclassified
from "Unfair claim denial" to "Mis-selling" between runs), and even which
NPS theme had the most mentions overall (a close-running pair of themes
swapped which one led). A list the client protection team acts on should
not shrink or reclassify a case just because someone clicked Generate
again on the same data.

Scope, deliberately narrow: this cache covers PER-RECORD classification
outputs only (theme codes, protection flag type/severity/reason) -- the
kind of thing that should be a stable fact about a specific response once
decided. It does NOT cache anything that synthesizes ACROSS records
(executive summary prose, top_findings, theme_summary sentences, verbatim
selection, sub-theme clustering) -- those are comparative/curatorial
judgments that legitimately depend on seeing the whole response pool, and
are expected to read a little differently on a fresh regeneration. The
goal is "regeneration changes prose, not classifications," not "every
byte of output is identical forever."

Honest limitation: this cache is a JSON file on local disk. Hugging Face
Spaces' container filesystem is ephemeral (see
docs/maintenance/architecture-overview.md) -- this gives stability across
regenerations within the same container session (the common case: review
a report, ask for a redo shortly after), but resets on a redeploy or
Space restart. A fully redeploy-proof cache would need external
persistent storage, out of scope here.
"""
import hashlib
import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(__file__).resolve().parent / "cache" / "tag_cache.json"

# R-033 (docs/report_spec.md, session-10): a cache entry used to be trusted
# forever regardless of when it was written or what code wrote it -- a
# decision cached while a real bug was silently discarding or misattributing
# results (R-018, R-027, R-029) was indistinguishable from one cached after
# the fix, and get() had no way to tell them apart. Confirmed on real data:
# a stale entry written before R-027 was fixed suppressed a real protection
# flag every run afterward; a stale entry written before R-029 was fixed
# served one respondent's flag under a DIFFERENT record's own cache key.
#
# Bump this whenever logic that DECIDES what gets cached under "theme" or
# "flag" changes in a way that could change a past decision -- not for
# unrelated code changes elsewhere in the file. get() ignores (treats as a
# cache miss) any entry stamped with an older version than this, so a fix
# to that logic automatically invalidates exactly the entries it could have
# affected, the next time each one is looked up -- no manual cache surgery
# needed per fix.
#   1 -- initial version stamp (session-10). Every entry written before
#        this had no stamp at all and is unconditionally treated as a miss.
CACHE_LOGIC_VERSION = 1


def _cache_key(kind: str, record_id: str, text: str) -> str:
    """kind namespaces the key (e.g. "theme", "flag") -- the same
    (record_id, text) pair is cached for more than one purpose (a
    response's theme tags AND, independently, whether it carries a
    protection flag), and without a kind prefix the two would collide on
    an identical key and silently overwrite each other's cached value."""
    digest = hashlib.sha256((text or "").encode("utf-8")).hexdigest()[:16]
    return f"{kind}:{record_id}:{digest}"


def load(cache_path: "Path | None" = None) -> dict:
    """Returns {} (never raises) if the cache doesn't exist yet or is
    unreadable -- a cache miss just means "tag it fresh," never a hard
    failure.

    cache_path defaults to None rather than DEFAULT_CACHE_PATH directly:
    a default argument value is bound once at function-definition time, so
    a test monkeypatching the module-level DEFAULT_CACHE_PATH constant
    would silently have no effect on calls using the default. Resolving it
    inside the function body instead makes it a fresh lookup on every
    call, so monkeypatching tag_cache.DEFAULT_CACHE_PATH actually works."""
    cache_path = cache_path or DEFAULT_CACHE_PATH
    if not cache_path.exists():
        return {}
    try:
        return json.loads(cache_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        log.warning(f"Could not read qualitative tag cache at {cache_path}: {exc}; starting fresh")
        return {}


def save(cache: dict, cache_path: "Path | None" = None) -> None:
    cache_path = cache_path or DEFAULT_CACHE_PATH
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def get(cache: dict, kind: str, record_id: str, text: str):
    """Returns the cached value, or None if this exact (kind, id, text)
    combination hasn't been classified before -- OR if it was, but under
    an older CACHE_LOGIC_VERSION than the one this code was built against
    (R-033): a version mismatch is treated identically to "never cached,"
    a plain miss, so the caller re-classifies fresh and re-caches under
    the current version. An entry with no version stamp at all (written
    before this existed) is always a mismatch."""
    entry = cache.get(_cache_key(kind, record_id, text))
    if not isinstance(entry, dict) or "_cache_version" not in entry:
        return None
    if entry["_cache_version"] < CACHE_LOGIC_VERSION:
        return None
    return entry["value"]


def put(cache: dict, kind: str, record_id: str, text: str, value) -> None:
    """Content-hash-keyed: if the underlying response text for this id
    ever changes (a data correction, a re-export), the old cache entry is
    simply never looked up again rather than serving a stale result --
    the new (kind, id, text) combination is a fresh cache miss.

    Stamps CACHE_LOGIC_VERSION (R-033) alongside the value so a future
    get() can tell whether this decision was made under the caching
    logic current at read time."""
    cache[_cache_key(kind, record_id, text)] = {
        "_cache_version": CACHE_LOGIC_VERSION,
        "value": value,
    }
