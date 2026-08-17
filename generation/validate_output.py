"""generation/validate_output.py

Post-generation validation pass (see the "Suggested validation pass" line of
the region-scoped-reports task spec): scans the LLM-written text for defect
patterns that the prompt instructs against but that an LLM can still slip
past -- internal identifiers leaking into prose, out-of-scope countries
appearing in a region-scoped report, comparative language on an indicator
the data explicitly marked non-comparable, and figures/quotes that don't
trace back to anything in the data package that was actually sent to the
model.

Advisory only: this never blocks generation or modifies output. Some finding
types (unstated_base, unverified_numeral) are heuristic and can have false
positives -- they are reported at severity "warn" for a human to judge, while
the precise, pattern-based checks (row_id, theme_key, out_of_scope_country,
comparative_verb, unverified_quote) are reported at severity "reject" since
they have no legitimate reason to ever fire.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from qualitative.llm_call import _PROTECTION_FLAG_TAXONOMY_BLOCK, _THEME_TAXONOMY_BLOCK

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RUNS_DIR = PROJECT_ROOT / "runs"


def load_in_scope_countries(run_id: str, runs_dir: "Path | None" = None) -> set:
    """The country set actually present in this run, read from
    analysis_results.json's parts.about_survey.by_country (computed
    directly from the survey data by analysis_engine/sections/
    about_survey.py) -- the authority the out-of-scope-country check tests
    report prose against, so it never goes stale relative to what this
    specific run's scope filter actually produced."""
    path = (runs_dir or RUNS_DIR) / run_id / "analysis_results.json"
    if not path.exists():
        return set()
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return set()
    by_country = ((analysis.get("parts") or {}).get("about_survey") or {}).get("by_country", [])
    return {row["country"] for row in by_country if row.get("country")}


# Matches analysis_engine/sections/about_survey.py's _PRODUCT_FLAGS labels.
_PRODUCT_LABELS = {"health": "Health", "crop": "Crop", "credit_life": "Credit Life"}


def load_product_mix(run_id: str, runs_dir: "Path | None" = None) -> dict:
    """{human label: n} for this run's actual product mix, read from
    analysis_results.json's parts.about_survey.product_mix.distribution --
    the authority the product-claim check tests report prose against, same
    pattern as load_in_scope_countries() above. Empty dict (not an error)
    if the product mix is unavailable for this schema (see about_survey.py's
    _PRODUCT_MIX_MIN_COVERAGE guard) -- the check simply has nothing to
    verify against in that case, not a reason to fail."""
    path = (runs_dir or RUNS_DIR) / run_id / "analysis_results.json"
    if not path.exists():
        return {}
    try:
        analysis = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    product_mix = ((analysis.get("parts") or {}).get("about_survey") or {}).get("product_mix") or {}
    distribution = product_mix.get("distribution") or []
    return {
        _PRODUCT_LABELS.get(row.get("product"), row.get("product")): row.get("n", 0)
        for row in distribution if row.get("product")
    }

_ROW_ID_PATTERN = re.compile(r"\brow_\d+\b", re.IGNORECASE)

_TAXONOMY_CODE_PATTERN = re.compile(r"^\s{0,4}([a-z][a-z_]*[a-z]):", re.MULTILINE)


def _extract_taxonomy_codes(block: str) -> set[str]:
    """Pull the internal snake_case codes (e.g. "staff_service",
    "mis_selling") out of a taxonomy block, so the theme-key check always
    matches whatever qualitative/llm_call.py's taxonomies actually define
    instead of a hand-copied list that can drift out of sync.

    Restricted to tokens that actually contain an underscore: the taxonomy
    blocks also have "key:" -shaped lines that aren't codes at all (the
    PROTECTION FLAG TAXONOMY block's SEVERITY RUBRIC has "high:", "medium:",
    "low:" sub-headings, and one real flag_type, "coercion", has no
    underscore) -- ordinary English words like "high" or "coercion" appear
    in legitimate prose constantly and would drown this check in false
    positives. "snake_case" in the spec this check implements means
    underscore-joined identifiers specifically.
    """
    return {code for code in _TAXONOMY_CODE_PATTERN.findall(block) if "_" in code}


_INTERNAL_KEYS = _extract_taxonomy_codes(_THEME_TAXONOMY_BLOCK) | _extract_taxonomy_codes(
    _PROTECTION_FLAG_TAXONOMY_BLOCK
)

# Verified against real production data for both dataset schemas (see
# analysis_engine/sections/about_survey.py's by_country output, run through
# runs/lacro_final_check and runs/africa_final_check) -- update this if
# VisionFund onboards a new country programme. This is the universe the
# out-of-scope-country check treats as "a real country name that could
# plausibly appear"; a run's own in-scope set (see about_survey.by_country,
# passed in by the caller) is always the true authority on what's actually
# allowed in THAT report.
ALL_KNOWN_COUNTRIES = {
    "Bolivia", "Ecuador", "Guatemala", "Honduras", "Mexico", "Dominican Republic",
    "Rwanda", "Ghana", "Zambia", "Uganda", "Tanzania", "Malawi", "Kenya", "Vietnam",
}

# Matches orchestrator.py's _build_trend_data() sig_note wording verbatim --
# a non-comparable indicator's row explicitly forbids the writer from using
# any of these words to describe it.
_COMPARATIVE_VERBS = [
    "rose", "fell", "improved", "declined", "increased", "decreased",
    "up", "down", "since last year",
]

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# Numerals that are almost never a cited statistic: bare 1-2 digit integers
# with no decimal point, no percent sign, and no thousands comma (e.g. "Part
# 4", "top 3", "a 5-point scale"), and 4-digit years. Excluding these keeps
# the unverified-numeral check useful instead of drowning in narrative noise.
_NUMERAL_PATTERN = re.compile(r"-?\d[\d,]*(?:\.\d+)?%?")
_YEAR_PATTERN = re.compile(r"^(19|20)\d{2}$")

_BASE_CUE_WORDS = (
    "of ", "of,", "of.", "of;", "among", "respondents", "clients", "n=", "n =",
    "base", "surveyed", "asked", "sample", "population",
)

_QUOTE_PATTERN = re.compile(r'"([^"]{15,})"')


def _fmt_num(value) -> str:
    return f"{value:.10g}"


def _numeric_candidates(value: float) -> set[str]:
    """Every string form a writer might plausibly render this number as,
    given format_value()'s conventions (plain, 1-decimal, whole-number, and
    percent forms when the raw value looks like a 0-1 proportion)."""
    out = {_fmt_num(value)}
    for nd in (0, 1, 2):
        out.add(f"{value:.{nd}f}")
        if 1000 <= abs(value):
            out.add(f"{value:,.{nd}f}")
    if -1.0 <= value <= 1.0:
        pct = value * 100
        for nd in (0, 1):
            out.add(f"{pct:.{nd}f}%")
    else:
        for nd in (0, 1):
            out.add(f"{value:.{nd}f}%")
    return out


def _flatten_numeric_candidates(obj) -> set[str]:
    """Every numeric leaf in a data package (dict/list of dicts, as returned
    by orchestrator.build_part_package()), expanded to every plausible
    rendered form via _numeric_candidates(). Booleans are excluded (Python's
    bool is an int subclass, and True/False are never a cited figure)."""
    found: set[str] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, (int, float)):
        found |= _numeric_candidates(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _flatten_numeric_candidates(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _flatten_numeric_candidates(v)
    return found


def _make_finding(severity: str, part_key: str, text_key: str, category: str, detail: str) -> dict:
    return {
        "severity": severity, "part": part_key, "text_key": text_key,
        "category": category, "detail": detail,
    }


def _check_row_ids(text: str, part_key: str, text_key: str) -> list[dict]:
    return [
        _make_finding("reject", part_key, text_key, "row_id_leak",
                      f'internal identifier "{m.group(0)}" appears in report prose')
        for m in _ROW_ID_PATTERN.finditer(text)
    ]


def _check_theme_keys(text: str, part_key: str, text_key: str) -> list[dict]:
    findings = []
    for key in _INTERNAL_KEYS:
        if re.search(rf"\b{re.escape(key)}\b", text):
            findings.append(_make_finding(
                "reject", part_key, text_key, "theme_key_leak",
                f'internal taxonomy code "{key}" appears in report prose instead of natural language',
            ))
    return findings


def _check_out_of_scope_countries(text: str, part_key: str, text_key: str, in_scope: set) -> list[dict]:
    findings = []
    for country in ALL_KNOWN_COUNTRIES - set(in_scope):
        if re.search(rf"\b{re.escape(country)}\b", text):
            findings.append(_make_finding(
                "reject", part_key, text_key, "out_of_scope_country",
                f'"{country}" is not in this report\'s scope ({sorted(in_scope)}) but appears in the text',
            ))
    return findings


def _check_product_claims(text: str, part_key: str, text_key: str, product_mix: dict) -> list[dict]:
    """Flags prose naming a product category (e.g. "Credit Life") that has
    zero respondents in this run's own product-mix table -- a real
    generated report characterized a verbatim as describing a credit-life
    death benefit ("widows having outstanding loan balances cleared") in a
    report whose product-mix table showed zero Credit Life respondents.
    No data field anywhere attaches product-type metadata to an individual
    verbatim (see qualitative/prepare_payload.py's record schema), so this
    is a genuinely interpretive judgment the model can get wrong -- "warn"
    tier, like the other heuristic checks in this module, for a human to
    confirm rather than a hard "reject": prose can legitimately discuss
    what a product generally offers without asserting this run's
    respondents hold it, which this check cannot distinguish from an
    actual overclaim."""
    if not product_mix:
        return []
    findings = []
    for label, n in product_mix.items():
        if n != 0:
            continue
        if re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE):
            findings.append(_make_finding(
                "warn", part_key, text_key, "product_claim_on_zero_mix",
                f'"{label}" is named here, but this run\'s product-mix table shows 0 '
                f"{label} respondents -- confirm this isn't overclaiming a product feature "
                "no respondent in this run actually holds before treating it as a false positive",
            ))
    return findings


def _check_comparative_verbs(text: str, part_key: str, text_key: str,
                              non_comparable_labels: list) -> list[dict]:
    if not non_comparable_labels:
        return []
    findings = []
    for sentence in _SENTENCE_SPLIT.split(text):
        lowered = sentence.lower()
        for label in non_comparable_labels:
            if label.lower() not in lowered:
                continue
            for verb in _COMPARATIVE_VERBS:
                if re.search(rf"\b{re.escape(verb)}\b", lowered):
                    findings.append(_make_finding(
                        "reject", part_key, text_key, "comparative_verb_on_non_comparable",
                        f'"{label}" is not comparable to the prior wave, but this sentence uses '
                        f'comparative language ("{verb}"): "{sentence.strip()}"',
                    ))
    return findings


def _check_unverified_quotes(text: str, part_key: str, text_key: str, quote_pool: list) -> list[dict]:
    findings = []
    pool_texts = [q.get("text", "") for q in quote_pool if q.get("text")]
    for m in _QUOTE_PATTERN.finditer(text):
        quoted = m.group(1).strip()
        if not any(quoted in pool_text or pool_text in quoted for pool_text in pool_texts):
            findings.append(_make_finding(
                "reject", part_key, text_key, "unverified_quote",
                f'quoted text does not match any verbatim in this section\'s quote pool: "{quoted[:120]}"',
            ))
    return findings


def _check_unverified_numerals(text: str, part_key: str, text_key: str,
                                numeric_candidates: set) -> list[dict]:
    findings = []
    for m in _NUMERAL_PATTERN.finditer(text):
        token = m.group(0)
        bare = token.rstrip("%").replace(",", "")
        if _YEAR_PATTERN.match(bare):
            continue
        if "." not in bare and "%" not in token and "," not in token and len(bare.lstrip("-")) <= 2:
            continue  # bare 1-2 digit integer, e.g. "Part 4", "top 3" -- not a cited statistic
        if token in numeric_candidates or bare in numeric_candidates:
            continue
        findings.append(_make_finding(
            "warn", part_key, text_key, "unverified_numeral",
            f'"{token}" does not match any figure in this part\'s data package',
        ))
    return findings


def _check_unstated_bases(text: str, part_key: str, text_key: str) -> list[dict]:
    findings = []
    for sentence in _SENTENCE_SPLIT.split(text):
        if "%" not in sentence:
            continue
        lowered = sentence.lower()
        if any(cue in lowered for cue in _BASE_CUE_WORDS):
            continue
        if re.search(r"\d[\d,]*\s+(?:of|out of)\s+\d", sentence):
            continue
        findings.append(_make_finding(
            "warn", part_key, text_key, "unstated_base",
            f"percentage with no nearby population/base language: \"{sentence.strip()}\"",
        ))
    return findings


# Mirrors generation/writer.py's _SENTIMENT_SPLIT_MIN_BASE_FOR_PCT -- kept as
# a separate constant rather than importing writer's (would create a
# writer<->validate_output import cycle, since writer already imports
# _COMPARATIVE_VERBS from this module) but must be kept equal to it, since
# this check's whole point is verifying writer.py's own instruction was
# followed.
_SENTIMENT_SPLIT_MIN_BASE_FOR_PCT = 10

_PCT_PATTERN = re.compile(r"\(\s*\d{1,3}%\s*\)")


def _check_tiny_sentiment_base_percentages(text: str, part_key: str, text_key: str,
                                            sentiment_total: "int | None") -> list[dict]:
    """Flags prose that states a "(NN%)" figure for a sentiment split whose
    real base was below the threshold writer.py instructs it to report as
    counts-only. Heuristic, not precise (can't prove which sentence in a
    multi-sentence insight block the split described), so this is a "warn"
    finding for a human to judge, the same severity class as the other
    heuristic checks in this module -- not a hard reject, since a percentage
    appearing here could legitimately belong to a different, larger figure
    quoted elsewhere in the same block."""
    if sentiment_total is None or sentiment_total >= _SENTIMENT_SPLIT_MIN_BASE_FOR_PCT:
        return []
    if not _PCT_PATTERN.search(text):
        return []
    return [_make_finding(
        "warn", part_key, text_key, "percentage_on_tiny_sentiment_base",
        f"sentiment split base is only {sentiment_total}, but this text states a percentage "
        "for it; writer.py instructs counts-only below the threshold -- confirm the percentage "
        "isn't describing that split before treating this as a false positive",
    )]


def _non_comparable_labels(package: dict) -> list:
    """Part 10 package's non-comparable indicator labels, read from the
    scorecard _build_trend_data() already built -- a row's "Prior Wave"
    column is the literal string "NOT COMPARABLE" exactly when
    part_10.py's _COMPARABLE table marked that indicator non-comparable."""
    if package.get("part") != "part_10":
        return []
    return [
        row["label"] for row in package.get("scorecard", [])
        if row.get("group_b_value") == "NOT COMPARABLE"
    ]


def validate_report(all_texts: dict, packages: list, in_scope_countries: set,
                    product_mix: "dict | None" = None) -> list[dict]:
    """Run every check against every generated text block.

    all_texts:          writer.write_all_parts()'s output, {part_key: {text_key: str}}
    packages:            orchestrator.orchestrate()'s output, the same package list
                          writer.py used to build each part's prompt (used here as the
                          ground truth for numerals, quote pools, and non-comparable
                          indicator labels)
    in_scope_countries:  the country set actually present in this run, e.g. from
                          analysis_results.json's parts.about_survey.by_country
    product_mix:         {label: n} for this run's actual product mix, e.g. from
                          load_product_mix() -- optional (defaults to None, which
                          simply skips the product-claim check) since not every
                          schema has a reliable product mix (see about_survey.py's
                          _PRODUCT_MIX_MIN_COVERAGE guard)
    """
    findings: list[dict] = []
    packages_by_part = {p["part"]: p for p in packages}

    for part_key, texts in all_texts.items():
        package = packages_by_part.get(part_key, {})
        if not isinstance(texts, dict) or texts.get("_generation_failed"):
            continue

        numeric_candidates = _flatten_numeric_candidates(package)
        non_comparable_labels = _non_comparable_labels(package)
        insight_summary = (package.get("sections") or {}).get("insight", {}).get("insight_summary") or {}
        insight_verbatims = (package.get("sections") or {}).get("insight", {}).get("verbatims", [])
        sentiment_split = insight_summary.get("sentiment_split")
        sentiment_total = (
            sum(v for v in sentiment_split.values() if isinstance(v, (int, float)))
            if sentiment_split else None
        )

        for text_key, text in texts.items():
            if not isinstance(text, str) or not text:
                continue
            findings += _check_row_ids(text, part_key, text_key)
            findings += _check_theme_keys(text, part_key, text_key)
            findings += _check_out_of_scope_countries(text, part_key, text_key, in_scope_countries)
            findings += _check_comparative_verbs(text, part_key, text_key, non_comparable_labels)
            findings += _check_unverified_numerals(text, part_key, text_key, numeric_candidates)
            findings += _check_unstated_bases(text, part_key, text_key)
            findings += _check_product_claims(text, part_key, text_key, product_mix or {})
            if text_key == "insight":
                findings += _check_unverified_quotes(text, part_key, text_key, insight_verbatims)
                findings += _check_tiny_sentiment_base_percentages(text, part_key, text_key, sentiment_total)

    return findings
