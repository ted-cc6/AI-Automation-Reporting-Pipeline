"""qualitative/parse_results.py

Phase 3: Validate Gemini output, count themes in Python, enrich verbatims
with profile from parquet, write qualitative_results.json.
"""
import json
import logging
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from qualitative.llm_call import _SEVERITY_RANK, humanize_theme_label
from qualitative.prepare_payload import load_config

log = logging.getLogger(__name__)


REQUIRED_TOP_KEYS = {
    "nps_tags", "claims_other_tagged", "not_worth_it_themes",
    "other_subthemes", "section_verbatims", "protection_flags",
    "executive_summary", "top_findings", "top_actions",
}

REQUIRED_SECTION_KEYS = {
    "part1", "part2", "part3", "part4", "part5", "part6", "part7"
}

SECTION_INSIGHT_FIELDS = {"theme_summary", "top_drivers", "sentiment_split"}

NPS_GROUPS = ("promoters", "passives", "detractors")


def _validate(raw: dict, provider: str = "LLM") -> None:
    missing = REQUIRED_TOP_KEYS - set(raw.keys())
    if missing:
        raise ValueError(f"{provider} response missing keys: {missing}")

    nps_tags = raw["nps_tags"]
    for grp in NPS_GROUPS:
        if grp not in nps_tags:
            raise ValueError(f"nps_tags missing group: {grp}")

    sv = raw["section_verbatims"]
    missing_sections = REQUIRED_SECTION_KEYS - set(sv.keys())
    if missing_sections:
        raise ValueError(f"section_verbatims missing sections: {missing_sections}")

    for section, ids in sv.items():
        if not isinstance(ids, list) or len(ids) == 0:
            raise ValueError(f"section_verbatims[{section}] is empty")


def _check_section_insights(section_insights: dict) -> None:
    """Soft-check section_insights: log warnings, never raise.

    Unlike section_verbatims, this is additive analytical content -- a
    missing or incomplete insight should not invalidate the whole
    qualitative run (that fragility is exactly what made the original
    single-gate _validate() risky).
    """
    if not section_insights:
        log.warning(
            "section_insights missing from Gemini response "
            "(older prompt version, or model omitted it)"
        )
        return

    missing_sections = REQUIRED_SECTION_KEYS - set(section_insights.keys())
    if missing_sections:
        log.warning(f"section_insights missing sections: {missing_sections}")

    for section, entry in section_insights.items():
        if not isinstance(entry, dict):
            log.warning(f"section_insights[{section}] is not an object")
            continue
        missing_fields = SECTION_INSIGHT_FIELDS - set(entry.keys())
        if missing_fields:
            log.warning(f"section_insights[{section}] missing fields: {missing_fields}")


def _count_themes(nps_tags: dict) -> dict:
    """Count theme frequency per NPS group from compact tag arrays.

    Counted, then relabeled: counting must happen on the raw taxonomy
    codes (so two spellings of the same idea don't fragment into separate
    counts), and only the final dict's keys are humanized -- see
    _humanize_top_drivers()'s docstring for why raw codes can't be allowed
    to reach a reader at all."""
    counts = {}
    for grp in NPS_GROUPS:
        counter = Counter()
        for entry in nps_tags.get(grp, []):
            if isinstance(entry, list) and len(entry) in (2, 3):
                themes = entry[1]
                if isinstance(themes, list):
                    counter.update(themes)
        counts[grp] = {humanize_theme_label(code): n for code, n in counter.most_common()}
    return counts


def _humanize_top_drivers(section_insights: dict) -> dict:
    """Relabel section_insights.*.top_drivers from raw taxonomy codes to
    human-readable text, deterministically -- the synthesis prompt already
    instructs the model not to write a raw code here (see llm_call.py's
    _build_synthesis_prompt()), but a real generated report shipped with
    "claims_process" sitting unlabeled in reader-facing prose despite that
    instruction, which is exactly the class of failure a prompt-only fix
    doesn't reliably prevent (see Part 10's no-prior-wave narrative
    hardening for the same lesson learned earlier). Non-destructive for
    freeform labels the model already wrote in plain words --
    humanize_theme_label() passes anything not in THEME_CODE_LABELS
    through unchanged."""
    out = {}
    for section, entry in (section_insights or {}).items():
        if not isinstance(entry, dict):
            out[section] = entry
            continue
        drivers = entry.get("top_drivers")
        if isinstance(drivers, list):
            entry = {**entry, "top_drivers": [humanize_theme_label(d) for d in drivers]}
        out[section] = entry
    return out


# ---------------------------------------------------------------------------
# R-006a Stage 1 (docs/report_spec.md): deterministic sentiment_split for
# report sections whose population is a flag already computed per-record,
# independent of any topic-matching judgment -- Part 5 (caregivers) and
# Part 6 (claimants). Computed here in Python, over every NPS record
# Task 1 actually tagged, instead of the synthesis call's own
# "best-judgment approximate counts... among the material you reviewed"
# estimate over a roughly 6-candidate shortlist.
#
# Part 7 (Gender) has its own function below (compute_part7_sentiment_
# splits()) -- it needs two groups (female, male), not one, since a single
# split over the whole respondent pool is the portfolio-wide split
# restated and tells a reader nothing about gender. Every
# sentiment_split, including this module's single-group sections, is
# returned in the SAME uniform nested (group -> split) shape (session-8,
# per instruction: no Part-7-only special case) -- see
# _wrap_single_group()'s docstring.
#
# Parts 1-4 are topic-defined (no per-record demographic flag exists for
# "relevant to this topic") -- see compute_stage2_sentiment_splits()
# below for their theme-mapped equivalent (R-006a Stage 2).
#
# Pinned definition (docs/report_spec.md's R-006a; state it once so it
# cannot drift between sections): source_pool_n is the section's ELIGIBLE
# population (e.g. every claimant in df, regardless of whether they left
# any text) -- the eligible population changes based on the section, but
# it does not depend on min_text_length at all. base_n is the subset of
# that population whose response ALSO passed min_text_length and was
# therefore actually tagged; positive + negative + neutral == base_n by
# construction.
# ---------------------------------------------------------------------------

_SENTIMENT_VALUES = ("positive", "negative", "neutral")

_STAGE1_SECTIONS = (
    ("part5", "caregivers"),
    ("part6", "claimants"),
)

# A real, three-way classification landing on an EXACT tie at this base_n
# or larger is vanishingly unlikely -- this is the specific signature a
# round-robin/placeholder generator produces (see the R-006a mechanism
# demo this guards against). Chosen well clear of small bases where a
# genuine tie is plausible by chance (e.g. base_n=3, 1/1/1).
_SUSPICIOUSLY_UNIFORM_MIN_BASE = 15


def _flatten_tagged_sentiment(nps_tags: dict) -> dict:
    """row_id -> sentiment, from every NPS group's tagged entries. A
    2-element entry (no sentiment -- see llm_call._apply_theme_tag_cache's
    docstring) is skipped: there is nothing to count it under."""
    out = {}
    for grp in NPS_GROUPS:
        for entry in nps_tags.get(grp, []):
            if isinstance(entry, list) and len(entry) == 3:
                row_id, _themes, sentiment = entry
                if sentiment in _SENTIMENT_VALUES:
                    out[row_id] = sentiment
    return out


def _stage1_segment_mask(section_key: str, df: pd.DataFrame) -> "pd.Series | None":
    """Boolean mask over df's full index defining a Stage-1 section's
    eligible population (independent of min_text_length -- see this
    module's Stage 1 header comment), or None if section_key isn't a
    Stage-1 section."""
    if section_key == "part5":
        col = "flag_child_wellbeing_denominator"
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].fillna(False).astype(bool)
    if section_key == "part6":
        # Canonical claimant definition (analysis_engine/segments.py,
        # matches Part 6's own scorecard and every other "claimant" figure
        # in this report): q_claim_submitted, NOT flag_paid_claimant --
        # see prepare_payload.py's _build_response_record() for the same
        # fix and its rationale (flag_paid_claimant is narrower: claim
        # approved AND paid, which silently excludes denied/pending
        # claimants). Logged as R-024.
        col = "q_claim_submitted"
        if col not in df.columns:
            return pd.Series(False, index=df.index)
        return df[col].fillna(False).astype(bool)
    return None


def _row_id_to_index(row_id: str) -> "int | None":
    try:
        return int(row_id.split("_")[1])
    except (IndexError, ValueError):
        return None


def _looks_synthetic(counts: dict, base_n: int) -> bool:
    """True if positive/negative/neutral are exactly tied at a base_n
    large enough that a real classification tying exactly is not a
    plausible coincidence -- see _SUSPICIOUSLY_UNIFORM_MIN_BASE."""
    return (
        base_n >= _SUSPICIOUSLY_UNIFORM_MIN_BASE
        and counts["positive"] == counts["negative"] == counts["neutral"]
    )


def _finalize_split(group_label: str, counts: dict, source_pool_n: int, selection_rule: str) -> dict:
    """Shared by every stage (1, 2, and Part 7): apply the synthetic-split
    guard (identical failure mode regardless of which stage or group
    produced it) and assemble ONE group's result dict. Raises ValueError;
    see _looks_synthetic(). group_label is used only in the error message
    (e.g. "part5" for a single-group section, "part7.female" for a group
    within a multi-group section) so a raised guard is traceable to its
    source."""
    base_n = sum(counts.values())
    if _looks_synthetic(counts, base_n):
        raise ValueError(
            f"{group_label}: sentiment split is exactly tied "
            f"({counts['positive']}/{counts['negative']}/{counts['neutral']}) "
            f"at base_n={base_n} -- this is the signature of a synthetic "
            "or placeholder split (e.g. a round-robin demo), not a real "
            "classification. Refusing to let it reach a rendered report."
        )
    return {
        **counts,
        "base_n": base_n,
        "source_pool_n": source_pool_n,
        "selection_rule": selection_rule,
    }


def _wrap_single_group(inner: dict) -> dict:
    """Uniform nested sentiment_split shape (session-8, per instruction):
    EVERY section's sentiment_split is keyed by group, never a bare
    flat dict -- a section with one group uses the single key "all". A
    section that needs splitting (Part 7 today; by country or claimant
    status in a hypothetical future one) uses its own group keys instead
    (see compute_part7_sentiment_splits()) with no further schema work,
    since every consumer already iterates groups rather than branching on
    section key."""
    return {"all": inner}


def compute_stage1_sentiment_splits(nps_tags: dict, df: pd.DataFrame) -> dict:
    """R-006a Stage 1: {section_key: {"positive": int, "negative": int,
    "neutral": int, "base_n": int, "source_pool_n": int,
    "selection_rule": str}} for exactly part5 and part6 (see this module's
    Stage 1 header comment for part7's pending status and the pinned
    base_n/source_pool_n definitions).

    Raises ValueError if a section's split is exactly tied across all
    three sentiment values at a base_n where that cannot plausibly be a
    real coincidence -- see _looks_synthetic(). This is a deliberate,
    hard guard: a synthetic/placeholder split (e.g. a round-robin demo)
    must never silently reach a rendered report.
    """
    tagged = _flatten_tagged_sentiment(nps_tags)
    min_text_length = load_config().get("min_text_length", 10)

    results = {}
    for section_key, population_label in _STAGE1_SECTIONS:
        mask = _stage1_segment_mask(section_key, df)
        source_pool_n = int(mask.sum())

        counts = {v: 0 for v in _SENTIMENT_VALUES}
        for row_id, sentiment in tagged.items():
            idx = _row_id_to_index(row_id)
            if idx is None or idx not in mask.index or not mask.loc[idx]:
                continue
            counts[sentiment] += 1

        selection_rule = (
            f"NPS follow-up responses from {population_label}, excluding "
            f"responses under {min_text_length} characters; "
            f"{sum(counts.values())} of {source_pool_n} {population_label} qualify."
        )

        results[section_key] = _wrap_single_group(
            _finalize_split(section_key, counts, source_pool_n, selection_rule)
        )
    return results


# ---------------------------------------------------------------------------
# R-006a Stage 2 (docs/report_spec.md): deterministic sentiment_split for
# Parts 1-4, whose population is defined by a theme-to-section mapping
# (qualitative/config.yaml's report_sections[*].theme_codes) rather than a
# demographic segment. A record belongs to a section if ANY of its 1-3
# tagged theme codes appear in that section's theme_codes list -- overlap
# across sections is expected (a response tagged both staff_service and
# claims_process reaches both Part 4 and Part 2), and a record whose
# themes match none of Parts 1-4 contributes to none of them. See
# config.yaml's own header comment for the mapping and its principle
# (primary section + co-tagging, not dual-mapping).
#
# source_pool_n here is NOT a demographic population (there is no
# independent "eligible to be about claims" population the way there is
# an "eligible to be a caregiver" one) -- it is every NPS record Task 1
# actually tagged with at least one theme (the pool that could possibly
# have matched ANY section), same for all four sections. base_n is the
# subset of that pool whose themes specifically matched THIS section.
# This is a real, intentional difference from Stage 1's source_pool_n
# (a fixed demographic count, computed independent of tagging) -- both
# still satisfy the same pinned contract (source_pool_n is what was
# eligible to count; base_n is what actually did).
#
# UNVERIFIED AGAINST REAL TAGS (session-7, 2026-08-2X): no GEMINI_API_KEY
# is configured and no qualitative_results.json exists for
# runs/lacro_final_check/, so this has been unit-tested against synthetic
# tag data only, never a real Task 1 output. The mapping itself (which
# theme codes belong to which section) is Lorenz-approved, but its
# PRACTICAL EFFECT -- how many real responses actually carry each theme,
# and therefore each section's real base_n -- is unknown until a live run
# happens. The first live run must print every Part 1-4 base_n for
# review before this mapping is treated as settled, not just approved in
# principle.
#
# Projected relative base sizes (informational, not yet verified): Part 1
# carries exactly ONE theme code (product_understanding) against Part 4's
# FIVE (product_value, staff_service, general_satisfaction,
# improvement_suggestion, complaint_grievance). Part 1's base_n is
# expected to be materially smaller than Part 4's for that structural
# reason alone -- a smaller Part 1 base is not evidence of a problem, it
# is the direct, predictable consequence of Part 1 having a narrower,
# more specific topic than Part 4's broad "general NPS driver" catch-all.
# ---------------------------------------------------------------------------

_STAGE2_SECTIONS = ("part1", "part2", "part3", "part4")

# Below this match rate (base_n / source_pool_n), a section's
# selection_rule gets an explicit "this is what the NPS prompt elicits,
# not a data restriction" clause -- see its use below. Chosen from the
# session-8 smoke test's real numbers (Part 2's ~3% match rate; Part 1's
# ~20% did not read as needing the caveat), not a precisely derived
# cutoff -- revisit if a future wave's distribution makes it fire (or
# fail to fire) somewhere that reads wrong.
_STAGE2_LOW_MATCH_RATE_THRESHOLD = 0.10


def _load_theme_section_map() -> dict:
    """{section_key: set(theme_codes)} for every report_sections entry
    that declares theme_codes (part1-4 today) -- see config.yaml's own
    header comment for the mapping and its principle."""
    config = load_config()
    out = {}
    for entry in config.get("report_sections", []):
        codes = entry.get("theme_codes")
        if codes:
            out[entry["key"]] = set(codes)
    return out


def compute_stage2_sentiment_splits(nps_tags: dict) -> dict:
    """R-006a Stage 2: {section_key: {"positive": int, "negative": int,
    "neutral": int, "base_n": int, "source_pool_n": int,
    "selection_rule": str}} for part1 through part4 (see this module's
    Stage 2 header comment for the mapping, its unverified status, and
    the pinned source_pool_n/base_n definitions for theme-matched
    sections specifically).

    Shares Stage 1's synthetic-split guard (_finalize_split) -- a
    placeholder split must never reach a rendered report regardless of
    which stage produced it.
    """
    theme_map = _load_theme_section_map()
    min_text_length = load_config().get("min_text_length", 10)

    # Every tagged NPS record (row_id -> (themes, sentiment)), regardless
    # of theme -- source_pool_n for every Stage-2 section, since nothing
    # about a section narrows WHICH records were eligible to be tagged,
    # only which of the tagged records matched its theme_codes.
    tagged_full = {}
    for grp in NPS_GROUPS:
        for entry in nps_tags.get(grp, []):
            if isinstance(entry, list) and len(entry) == 3:
                row_id, themes, sentiment = entry
                if sentiment in _SENTIMENT_VALUES and isinstance(themes, list):
                    tagged_full[row_id] = (themes, sentiment)
    source_pool_n = len(tagged_full)

    results = {}
    for section_key in _STAGE2_SECTIONS:
        section_codes = theme_map.get(section_key, set())
        counts = {v: 0 for v in _SENTIMENT_VALUES}
        for themes, sentiment in tagged_full.values():
            if section_codes.intersection(themes):
                counts[sentiment] += 1

        codes_str = ", ".join(sorted(section_codes)) if section_codes else "(none configured)"
        base_n_value = sum(counts.values())
        selection_rule = (
            f"NPS follow-up responses tagged with a theme mapped to this "
            f"section ({codes_str}), excluding responses under "
            f"{min_text_length} characters; {base_n_value} of "
            f"{source_pool_n} tagged responses qualify."
        )
        # A low match rate is a fact about what the NPS follow-up prompt
        # ("why did you give this score?") elicits -- most respondents
        # default to general sentiment, not this section's specific
        # topic -- not a sign the pipeline under-tagged or restricted the
        # data (R-025, docs/report_spec.md: found for Part 2, generalised
        # here since any Stage-2 section could land here on a future
        # wave). Stated explicitly so a small base is never misread as a
        # defect.
        match_rate = (base_n_value / source_pool_n) if source_pool_n else 0.0
        if match_rate < _STAGE2_LOW_MATCH_RATE_THRESHOLD:
            selection_rule += (
                " Most NPS follow-up responses describe general sentiment "
                "rather than this section's specific topic; a low base "
                "here reflects what the question elicits, not a data "
                "restriction."
            )

        results[section_key] = _wrap_single_group(
            _finalize_split(section_key, counts, source_pool_n, selection_rule)
        )
    return results


# ---------------------------------------------------------------------------
# R-006a Part 7 (docs/report_spec.md): Gender needs two splits, female and
# male, not the portfolio-wide restatement a single split would produce --
# comparing two groups is the entire point of a Gender section. Uses the
# SAME uniform nested shape every other section uses (session-8, per
# instruction: no Part-7-only special case) -- {"female": {...},
# "male": {...}} instead of {"all": {...}}. Population per group is a
# demographic count (like Stage 1's part5/part6), independent of tagging,
# NOT a Stage-2-style theme match -- Gender is a lens over the whole
# client base, not a topic.
# ---------------------------------------------------------------------------

_PART7_GROUPS = (
    ("female", "women"),
    ("male", "men"),
)


def compute_part7_sentiment_splits(nps_tags: dict, df: pd.DataFrame) -> dict:
    """{"part7": {"female": {...}, "male": {...}}} -- see this module's
    Part 7 header comment. Each group's base_n/source_pool_n/
    selection_rule follow the same pinned Stage-1 contract
    (source_pool_n = total women/men in df; base_n = subset who left a
    response of at least min_text_length and were tagged)."""
    tagged = _flatten_tagged_sentiment(nps_tags)
    min_text_length = load_config().get("min_text_length", 10)

    if "q_sex" not in df.columns:
        sex = pd.Series("", index=df.index)
    else:
        sex = df["q_sex"].fillna("")

    groups = {}
    for sex_value, population_label in _PART7_GROUPS:
        mask = sex == sex_value.capitalize()
        source_pool_n = int(mask.sum())

        counts = {v: 0 for v in _SENTIMENT_VALUES}
        for row_id, sentiment in tagged.items():
            idx = _row_id_to_index(row_id)
            if idx is None or idx not in mask.index or not mask.loc[idx]:
                continue
            counts[sentiment] += 1

        selection_rule = (
            f"NPS follow-up responses from {population_label}, excluding "
            f"responses under {min_text_length} characters; "
            f"{sum(counts.values())} of {source_pool_n} {population_label} qualify."
        )

        groups[sex_value] = _finalize_split(
            f"part7.{sex_value}", counts, source_pool_n, selection_rule
        )

    return {"part7": groups}


def _lookup_profile(row_id: str, df: pd.DataFrame) -> dict:
    """Return demographic profile for a row_id string like 'row_0042'."""
    try:
        idx = int(row_id.split("_")[1])
    except (IndexError, ValueError):
        return {}

    if idx not in df.index:
        return {}

    row = df.loc[idx]
    return {
        "client_id": str(row.get("client_id", "")) or None,
        "sex": str(row.get("q_sex", "")) or None,
        "age": (None if pd.isna(row.get("q_client_age"))
                else int(row["q_client_age"])),
        "branch": str(row.get("branch", "")) or None,
        "country": str(row.get("country", "")) or None,
        # Canonical claimant definition -- see prepare_payload.py's
        # _build_response_record() for the same fix and its rationale
        # (q_claim_submitted, not the narrower flag_paid_claimant).
        "is_claimant": (False if pd.isna(row.get("q_claim_submitted"))
                        else bool(row["q_claim_submitted"])),
        # Canonical caregiver definition (matches analysis_engine/segments.py's
        # "caregiver" segment): answered Yes OR No to child wellbeing (i.e. has
        # children to report on) -- NOT "Yes" only, which would wrongly exclude
        # caregivers whose child's wellbeing did not improve.
        "is_caregiver": bool(row.get("flag_child_wellbeing_denominator", False)),
    }


def _lookup_text(row_id: str, df: pd.DataFrame, text_cols: list) -> str:
    """Find the open-ended text for a row_id across all text columns."""
    try:
        idx = int(row_id.split("_")[1])
    except (IndexError, ValueError):
        return ""

    if idx not in df.index:
        return ""

    row = df.loc[idx]
    for col in text_cols:
        if col in df.columns:
            val = row.get(col)
            if not pd.isna(val) and str(val).strip():
                return str(val).strip()
    return ""


def _enrich_section_verbatims(
    section_verbatims: dict,
    df: pd.DataFrame,
    text_cols: list,
) -> dict:
    """Replace row_id lists with enriched verbatim objects including text + profile."""
    enriched = {}
    for section, ids in section_verbatims.items():
        enriched[section] = []
        for row_id in ids:
            text = _lookup_text(row_id, df, text_cols)
            profile = _lookup_profile(row_id, df)
            enriched[section].append({
                "id": row_id,
                "text": text,
                "profile": profile,
            })
    return enriched


def _enrich_protection_flags(flags: list, df: pd.DataFrame) -> list:
    """Add profile to each protection flag."""
    enriched = []
    for flag in flags:
        row_id = flag.get("id", "")
        enriched.append({
            **flag,
            "profile": _lookup_profile(row_id, df),
        })
    return enriched


def _normalise_reason(reason: "str | None") -> str:
    """Collapse whitespace and lowercase only -- no fuzzy or similarity
    matching, so this only ever collapses genuinely identical reason text."""
    return re.sub(r"\s+", " ", (reason or "").strip()).lower()


def _dedupe_protection_flags_by_client(flags: list) -> "tuple[list, int]":
    """Second dedup pass, run after _enrich_protection_flags attaches
    client_id.

    llm_call._dedupe_protection_flags already collapses flags sharing the
    same (row id, flag_type) -- but it runs before client_id exists, and
    its key is the survey row, not the client. A row id is 1:1 with a
    single dataframe row, so two DIFFERENT rows for the same client (a
    genuinely re-surveyed client, or an unresolved upstream duplicate --
    see data_loader_screening.py's client_id_reuse_warnings /
    uuid_duplicate_pairs) never collide on that key and both survive as
    separate entries even when they restate the identical concern. This
    pass catches that case at the client level instead.

    Key: (client_id, flag_type, normalised reason). A client raising two
    genuinely distinct concerns -- different flag_type, or the same
    flag_type worded differently -- is NOT collapsed: both entries are
    kept, and every surviving entry for a client left with more than one
    concern is marked same_client_multiple_concerns so the report can say
    so explicitly instead of rendering an unexplained repeat. On a
    collision, the higher-severity copy is kept (ties keep whichever was
    seen first), matching llm_call._dedupe_protection_flags's behaviour.

    Flags with no resolvable client_id (profile lookup failed) are passed
    through unchanged -- there is no client key to dedup on, and
    collapsing them onto a shared empty key would wrongly merge unrelated
    flags from different, merely-unidentified respondents.

    Returns (deduped_flags, n_unresolved): n_unresolved is how many input
    flags had no client_id and so skipped this pass untouched, made
    visible to the caller rather than silently absorbed -- if enrichment
    fails at scale, this dedup silently becomes a no-op, and that has to
    be visible, not inferred.
    """
    best: dict[tuple, dict] = {}
    order: list[tuple] = []
    unresolved: list[dict] = []
    for flag in flags:
        client_id = (flag.get("profile") or {}).get("client_id")
        if not client_id:
            unresolved.append(flag)
            continue
        key = (client_id, flag.get("flag_type"), _normalise_reason(flag.get("reason")))
        existing = best.get(key)
        if existing is None:
            best[key] = flag
            order.append(key)
            continue
        existing_rank = _SEVERITY_RANK.get((existing.get("severity") or "").lower(), 0)
        new_rank = _SEVERITY_RANK.get((flag.get("severity") or "").lower(), 0)
        if new_rank > existing_rank:
            best[key] = flag
    deduped = [best[key] for key in order]

    client_counts: dict[str, int] = {}
    for flag in deduped:
        cid = flag["profile"]["client_id"]
        client_counts[cid] = client_counts.get(cid, 0) + 1
    for flag in deduped:
        cid = flag["profile"]["client_id"]
        flag["same_client_multiple_concerns"] = client_counts[cid] > 1
    for flag in unresolved:
        flag["same_client_multiple_concerns"] = False

    return deduped + unresolved, len(unresolved)


def parse_and_save(
    raw_gemini: dict,
    df: pd.DataFrame,
    run_id: str,
    meta_extra: dict = None,
    provider: str = "LLM",
    model: str = "unknown",
) -> dict:
    """
    Validate, enrich, and assemble final qualitative_results.json.

    Args:
        raw_gemini:  Parsed dict from llm_call.call_gemini()
        df:          Full survey DataFrame (for profile lookups)
        run_id:      Run identifier (e.g. "2026_Q2")
        meta_extra:  Optional dict with token counts etc. from the API response
        provider:    Which provider actually produced raw_gemini (for accurate
                     error messages only -- "Gemini" was hardcoded here even
                     when Anthropic/OpenAI generated the response; see
                     llm_call.py's error messages, fixed for the same reason
                     in commit 3b47925 but missed in this sibling module).
        model:       Which model actually produced raw_gemini -- the output
                     meta.model field used to be hardcoded "gemini-2.5-pro"
                     regardless of provider, same bug class as the message
                     above.

    Returns:
        Final qualitative results dict (also written to disk)
    """
    _validate(raw_gemini, provider=provider)

    section_insights = raw_gemini.get("section_insights", {})
    _check_section_insights(section_insights)
    section_insights = _humanize_top_drivers(section_insights)

    # R-006a Stage 1 + Stage 2 + Part 7: override every section's
    # sentiment_split with its code-computed, uniformly-nested (group ->
    # split) version -- part5/part6 (segment-based, Stage 1), part1-4
    # (theme-mapped, Stage 2, unverified against real tags -- see
    # compute_stage2_sentiment_splits()'s module comment), and part7
    # (female/male, session-8). theme_summary/top_drivers are untouched
    # (still the model's own synthesis) for every section.
    nps_tags = raw_gemini.get("nps_tags", {})
    deterministic_splits = {
        **compute_stage1_sentiment_splits(nps_tags, df),
        **compute_stage2_sentiment_splits(nps_tags),
        **compute_part7_sentiment_splits(nps_tags, df),
    }
    for section_key, split in deterministic_splits.items():
        existing = section_insights.get(section_key)
        base = existing if isinstance(existing, dict) else {}
        section_insights = {**section_insights, section_key: {**base, "sentiment_split": split}}

    # All text columns (for verbatim text lookup)
    text_cols = [
        "q_nps_promoter_followup", "q_nps_passive_followup",
        "q_nps_detractor_followup", "q_no_claim_reason__other_text",
        "q_claim_challenges__other_text", "q_claim_challenges__support_text",
        "q_coping_mechanisms__other_text", "q_income_sources__other_text",
        "q_comm_channel_effective__other_text",
        "q_claim_channel_preferred__other_text",
        "q_vf_services_received__other_text",
        "q_child_improvements__other_text",
    ]

    theme_counts = _count_themes(raw_gemini["nps_tags"])

    enriched_verbatims = _enrich_section_verbatims(
        raw_gemini["section_verbatims"], df, text_cols
    )

    enriched_flags = _enrich_protection_flags(
        raw_gemini.get("protection_flags", []), df
    )
    enriched_flags, n_unresolved_client = _dedupe_protection_flags_by_client(enriched_flags)
    if n_unresolved_client:
        log.warning(
            f"{n_unresolved_client} protection flag(s) had no resolvable client_id "
            "and passed through client-level dedup (R-003) unchanged"
        )

    result = {
        "meta": {
            "schema_version": "1.1",
            "provider": provider,
            "model": model,
            "run_id": run_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            **(meta_extra or {}),
        },
        "theme_counts": theme_counts,
        "nps_tags_raw": raw_gemini["nps_tags"],
        "claims_other_tagged": raw_gemini.get("claims_other_tagged", {}),
        "not_worth_it_themes": raw_gemini.get("not_worth_it_themes", []),
        "other_subthemes": raw_gemini.get("other_subthemes", {}),
        "section_verbatims": enriched_verbatims,
        "section_insights": section_insights,
        "protection_flags": enriched_flags,
        "executive_summary": raw_gemini.get("executive_summary", ""),
        # Ranked-first lists, nominally 3 items each -- not strictly enforced
        # here (matches executive_summary's own lenient .get() pattern above);
        # generation/assembler.py's executive-summary renderer defensively
        # slices to the top 3 if the model ever returns more or fewer.
        "top_findings": raw_gemini.get("top_findings", []),
        "top_actions": raw_gemini.get("top_actions", []),
    }

    out_path = Path("runs") / run_id / "qualitative_results.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    log.info(f"qualitative_results.json written to {out_path}")

    return result
