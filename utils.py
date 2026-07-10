"""utils.py — Shared utilities for the VisionFund report generation pipeline."""
import re


def format_period_label(run_id: str) -> str:
    """Extract a human-readable 'YYYY QN' label from a run_id like '2026_Q2',
    'default_2026_Q2', or 'Vietnam_2026_Q2'. Falls back to the raw run_id if
    no year/quarter pattern is found, so unusual run_ids never raise."""
    m = re.search(r"(\d{4})[_-]?Q([1-4])", run_id, re.IGNORECASE)
    if m:
        return f"{m.group(1)} Q{m.group(2)}"
    return run_id


def get_nested(d: dict, path: str, default=None):
    """Traverse a nested dict using a dot-separated path string."""
    keys = path.split(".")
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def format_value(v, fmt: str, suppressed: bool = False) -> str:
    """Convert raw numbers to display strings."""
    if suppressed or v is None:
        return "SUPPRESSED"
    if fmt == "pct":
        return f"{v * 100:.1f}%"
    if fmt == "pct1":
        return f"{v * 100:.1f}%"
    if fmt == "score":
        return f"{v * 100:.1f}"
    if fmt == "count":
        return str(int(round(v)))
    if fmt == "rho":
        return f"{v:+.3f}"
    if fmt == "nps":
        return f"{v:.1f}"
    return str(v)


def word_count(text: str) -> int:
    return len(text.split())


def truncate_to_limit(text: str, limit: int) -> str:
    """Truncate text to limit words at a sentence boundary."""
    if word_count(text) <= int(limit * 1.15):
        return text
    words = text.split()
    candidate = " ".join(words[:limit])
    match = re.search(r'[.?!][^.?!]*$', candidate)
    if match:
        return candidate[:match.start() + 1].strip()
    return candidate + "…"
