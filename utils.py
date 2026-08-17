"""utils.py — Shared utilities for the VisionFund report generation pipeline."""
import re

_PERIOD_PATTERN = re.compile(r"(\d{4})[_-]?Q([1-4])", re.IGNORECASE)


def format_period_label(run_id: str) -> str:
    """Extract a human-readable 'YYYY QN' label from a run_id like '2026_Q2',
    'default_2026_Q2', or 'Vietnam_2026_Q2'. Falls back to the raw run_id if
    no year/quarter pattern is found, so unusual run_ids never raise."""
    m = _PERIOD_PATTERN.search(run_id)
    if m:
        return f"{m.group(1)} Q{m.group(2)}"
    return run_id


def parse_period(run_id: str) -> "tuple[int | None, int | None]":
    """Same pattern as format_period_label(), but returns (year, quarter) as
    ints for callers that need to compare the entered period against
    something else (see data_quality_flags.derive_period_mismatch_flag()),
    rather than a display string. (None, None) if run_id has no
    recognizable year/quarter, same no-raise guarantee as
    format_period_label()."""
    m = _PERIOD_PATTERN.search(run_id)
    if not m:
        return None, None
    return int(m.group(1)), int(m.group(2))


def get_nested(d: dict, path: str, default=None):
    """Traverse a nested dict using a dot-separated path string."""
    keys = path.split(".")
    cur = d
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur if cur is not None else default


def format_value(v, fmt: str, suppressed: bool = False, not_applicable: bool = False) -> str:
    """Convert raw numbers to display strings.

    not_applicable is distinct from suppressed: suppressed means "asked, but
    too few answered to report reliably"; not_applicable means "nobody in
    this population was ever asked this question at all" (see
    analysis_engine/stats.py::_base_result()). A not_applicable metric is
    always suppressed too (0 valid responses), so this check must come
    first -- otherwise it would fall through to the generic "SUPPRESSED"
    string and lose the distinction entirely.
    """
    if not_applicable:
        return "NOT APPLICABLE"
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


def format_p_value(p: "float | None") -> str:
    """Format a p-value for display, flooring anything below 0.0001 to
    "<0.0001" instead of truncating it to "0.0000" -- a highly significant
    result (e.g. p=2.3e-38, seen in real Part 5 driver correlations) must
    never print as indistinguishable from p=0 by fixed-width truncation."""
    if p is None:
        return "?"
    if p < 0.0001:
        return "<0.0001"
    return f"{p:.4f}"


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
