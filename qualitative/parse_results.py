"""qualitative/parse_results.py

Phase 3: Validate Gemini output, count themes in Python, enrich verbatims
with profile from parquet, write qualitative_results.json.
"""
import json
import logging
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from qualitative.llm_call import humanize_theme_label

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
            if isinstance(entry, list) and len(entry) == 2:
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
        "is_claimant": (False if pd.isna(row.get("flag_paid_claimant"))
                        else bool(row["flag_paid_claimant"])),
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
