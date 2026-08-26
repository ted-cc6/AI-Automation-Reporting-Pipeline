"""generation/writer.py

Phase 3: Seven LLM calls (one per part); house-voice system prompt. Provider/
api_key are passed in explicitly by the caller (the dashboard backend threads
these through from the user's browser session; the CLI entrypoint in
run_generation.py falls back to GEMINI_API_KEY for standalone use).
"""
import json
import logging
import re
import time
from pathlib import Path

from analysis_engine.country_config import DEFAULT_COUNTRY
from analysis_engine.sections.part_6 import LABEL_CLAIMANT, LABEL_NON_FILER, QUALIFIER_CLAIMANT
from generation.validate_output import _COMPARATIVE_VERBS
from llm_providers import call_llm
from report_scopes import LACRO_SHORT_LABEL
from utils import word_count, truncate_to_limit, format_period_label, format_p_value

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent


def _load_analysis_meta(run_id: str) -> dict:
    """Best-effort read of runs/{run_id}/analysis_results.json's meta block --
    mirrors generation/assembler.py's helper of the same name. Returns {} if
    the file is missing or unreadable rather than raising, so title/voice
    fall back to the global-portfolio wording in that case."""
    path = ROOT / "runs" / run_id / "analysis_results.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("meta", {})
    except (json.JSONDecodeError, OSError):
        return {}


def _is_single_country(meta: dict) -> bool:
    """True when this run was scoped to one country by data_loader_screening.py's
    country filter -- i.e. meta["country"] is anything other than the
    DEFAULT_COUNTRY sentinel ("default"), which means no filter was applied."""
    country = meta.get("country")
    return bool(country) and country != DEFAULT_COUNTRY


def _is_larco_rollup(meta: dict) -> bool:
    """True when this run combines every LARCO country into one analysis --
    dataset_schema == "larco" (see run_analysis.py's meta block) with no
    single-country filter applied. Distinct from the true Africa+Vietnam
    global portfolio, which uses dataset_schema == "africa_vietnam" (the
    default when the key is absent, e.g. for analysis_results.json files
    written before dataset_schema was added to meta)."""
    return meta.get("dataset_schema") == "larco" and not _is_single_country(meta)


def _lacro_scoped(meta: dict) -> bool:
    """True whenever this run represents a full LACRO regional rollup --
    either the legacy dataset_schema=="larco" export (see _is_larco_rollup,
    a 2025-wave LARCO-instrument CSV, its own dataset_schema) or the newer
    report_scope=="lacro" region filter over the 2026+ unified schema (see
    report_scopes.py). Both map to identical "LACRO Regional Portfolio"
    title/subtitle wording -- the underlying mechanism differs (a distinct
    source CSV/schema vs a Region-column filter on the shared one), but the
    report itself should read identically either way. Without this check,
    a report_scope=="lacro" run fell through to the "Global Portfolio"
    branch below, since only dataset_schema was ever considered -- caught
    from a real generated report titling itself "Global Portfolio" and
    saying so throughout its prose despite being correctly filtered to
    LACRO clients only underneath."""
    return _is_larco_rollup(meta) or meta.get("report_scope") == "lacro"


def _report_title(run_id: str, meta: "dict | None" = None) -> str:
    period = format_period_label(run_id)
    meta = meta or {}
    if _is_single_country(meta):
        label = meta.get("country_label") or meta["country"].title()
        return f"VisionFund International Insurance Impact Report: {label}, {period}"
    if _lacro_scoped(meta):
        # LACRO_SHORT_LABEL (report_scopes.py) is the one place this acronym
        # is spelled -- previously hardcoded here as "LARCO" (this
        # codebase's internal file/variable naming convention, see
        # report_scopes.py's module docstring), which leaked the internal
        # spelling into every reader-facing occurrence of the region name:
        # this title, the cover subtitle (generation/assembler.py), and
        # from there into the writing LLM's own prose throughout the
        # report, since _house_voice_text() opens with "You are writing
        # the {report_title}."
        return f"VisionFund International Insurance Impact Report: {LACRO_SHORT_LABEL} Regional Portfolio, {period}"
    report_scope = meta.get("report_scope")
    if report_scope:
        label = meta.get("report_scope_label") or report_scope
        return f"VisionFund International Insurance Impact Report: {label} Portfolio, {period}"
    return f"VisionFund International Insurance Impact Report: Global Portfolio, {period}"


# ---------------------------------------------------------------------------
# Single-country SCOPE paragraph variant
#
# The multi-country body text below is left completely untouched --
# _house_voice() always returns it verbatim when single_country=False (the
# default), so the global report's house-voice prompt has zero risk of
# drifting from what it is today. For a single-country run, the "it is not a
# single-country report" framing and the cross-country example are no longer
# true or useful (there's no larger multi-country pool in the payload to
# distinguish a subset from), so this swaps in a simplified SCOPE paragraph
# via an exact substring replace -- same technique as
# qualitative/llm_call.py's single-country prompt variant.
# ---------------------------------------------------------------------------

_MULTI_COUNTRY_SCOPE_PARAGRAPH = (
    "SCOPE: This report covers VisionFund's insurance client portfolio across MULTIPLE\n"
    "countries in one combined analysis, not a single-country report. Some\n"
    "metrics only apply to a subset of clients (for example, a product that is only\n"
    "sold in one country, or a question that was only asked to certain product\n"
    "types). Whenever a metric's data package states a \"population\" for it, use that\n"
    "population description in your sentence (e.g. \"among health and credit-life\n"
    "clients\" or \"among Vietnam's crop-insurance clients\") instead of implying the\n"
    "figure describes all surveyed clients. Never present two metrics as a\n"
    "before/after or \"however\" contrast unless they describe the same population;\n"
    "check each metric's stated population before connecting it to another. Any\n"
    "recommendation or forward-looking suggestion you write must name only countries\n"
    "covered by this report; never recommend an action for a country this report does\n"
    "not cover, even one VisionFund operates in elsewhere."
)

_SINGLE_COUNTRY_SCOPE_PARAGRAPH = (
    "SCOPE: This report covers VisionFund's insurance client portfolio in a single\n"
    "country programme. Some metrics only apply to a subset of clients within that\n"
    "country (for example, a product that only some clients hold, or a question that\n"
    "was only asked to certain product types). Whenever a metric's data package\n"
    "states a \"population\" for it, use that population description in your sentence\n"
    "(e.g. \"among health and credit-life clients\") instead of implying the figure\n"
    "describes all surveyed clients. Never present two metrics as a before/after or\n"
    "\"however\" contrast unless they describe the same population; check each\n"
    "metric's stated population before connecting it to another. Any recommendation\n"
    "or forward-looking suggestion you write must be about this one country only;\n"
    "never recommend an action for any other country."
)


def _house_voice(report_title: str, single_country: bool = False) -> str:
    prompt = _house_voice_text(report_title)
    if single_country:
        prompt = prompt.replace(_MULTI_COUNTRY_SCOPE_PARAGRAPH, _SINGLE_COUNTRY_SCOPE_PARAGRAPH)
    return prompt


def _house_voice_text(report_title: str) -> str:
    return f"""
You are writing the {report_title}.

AUDIENCE: Senior MFI leaders, impact investors, and programme managers.
Assume they understand financial inclusion concepts but not statistical methods.

SCOPE: This report covers VisionFund's insurance client portfolio across MULTIPLE
countries in one combined analysis, not a single-country report. Some
metrics only apply to a subset of clients (for example, a product that is only
sold in one country, or a question that was only asked to certain product
types). Whenever a metric's data package states a "population" for it, use that
population description in your sentence (e.g. "among health and credit-life
clients" or "among Vietnam's crop-insurance clients") instead of implying the
figure describes all surveyed clients. Never present two metrics as a
before/after or "however" contrast unless they describe the same population;
check each metric's stated population before connecting it to another. Any
recommendation or forward-looking suggestion you write must name only countries
covered by this report; never recommend an action for a country this report does
not cover, even one VisionFund operates in elsewhere.

SCALE DIRECTION: Several survey questions are coded so that a LOWER number is
the more positive response (1=best, e.g. "Definitely would renew" = 1). When a
Part 5 factor correlation gives a "[direction: ...]" note, that note states
what the sign actually means in plain English for that specific factor; use
its stated direction verbatim rather than assuming a negative rho is
automatically a negative finding. A negative correlation is frequently the
EXPECTED, POSITIVE association once the 1=best coding is accounted for (e.g.
stronger renewal intent occurring alongside better child wellbeing produces a
negative rho, not a positive one). Never describe such a result as
counterintuitive or concerning without first checking its direction note.

VOICE RULES:
- Professional, empathetic, evidence-based
- Active voice. Past tense for findings ("revealed", "showed"), present for implications ("suggests", "indicates")
- Describe correlations and group differences as associations only, never as one thing
  driving, causing, or determining another -- this is cross-sectional survey data, and the
  study design does not support causal inference. Do not use, outside a quoted client
  verbatim: drive, drives, drove, driver, cause, causes, caused, leads to, determines,
  improves, reduces, strengthens, underpins, eases, translates into, lever, or impact as a
  verb. Required substitutions: "X drives Y" becomes "X is associated with Y"; "X improves Y"
  becomes "higher X is associated with higher Y"; "the strongest driver" becomes "the factor
  most strongly associated"; describe a group difference as what was observed, e.g.
  "claimants reported higher child wellbeing than those who did not file", never as what one
  group's status did to produce the other's outcome, e.g. never "claiming improved child
  wellbeing". Keep this plain, not hedged: "Claimants reported higher child wellbeing" is
  correct and clear as written; do not soften it into "there may possibly be some
  association." The report title, "Insurance Impact Report," is the programme's name, not a
  causal claim, and needs no rewording.
- Never use an em dash (—) or en dash (–) anywhere in your writing. Use a comma, colon,
  semicolon, parentheses, or a new sentence instead.
- No bullet points, no headers, no markdown in narrative text; flowing prose only
- Do not use academic jargon (no "statistically significant"; say "the difference is meaningful" or cite the p-value)
- Every statistic you cite MUST come from the data package. Never invent or round figures beyond what is provided.
- Suppressed values (marked "SUPPRESSED") must be noted as "data suppressed due to small sample size"; never estimate or interpolate
- Values marked "NOT APPLICABLE" are a different situation from "SUPPRESSED": this
  question was never asked of this report's population at all (e.g. a product-specific
  question that doesn't apply here), not a small sample. Phrase these as "not asked of
  [population]" or similar; never as "data suppressed," "small sample size," or "missing
  data"
- When a note field is present, incorporate its guidance into the narrative
- For insight blocks: SECTION SUMMARY (theme summary, top drivers, sentiment split) describes the
  pattern across all responses judged relevant to that section; use it for the section's overall
  characterization. Use the quoted VERBATIM(s) to illustrate that pattern with a specific client
  voice, not as evidence of the pattern itself; never imply that 1-3 quotes represent the full
  client base's sentiment when a SENTIMENT SPLIT is available and shows a different balance.
- Whenever you describe a SENTIMENT SPLIT in prose, state EVERY category as "n (pct%)" together
  (e.g. "18 positive (60%), 9 negative (30%), 3 neutral (10%)"); never a bare count and never a
  bare percentage on its own. Compute each percentage yourself as that category's count divided by
  the SENTIMENT SPLIT line's own total (do not use any percentage from elsewhere in the data
  package). The percentages across all categories you mention must sum to approximately 100%
  (allow ±1% for rounding only). If they do not, you have made an arithmetic error; recompute
  directly from the given counts before writing the sentence.
  EXCEPTION: if a SENTIMENT SPLIT line itself says its base is "too small to state as
  percentages," follow that line's own instruction instead: state the plain counts only (e.g.
  "2 positive, 1 negative"), with no percentage at all, for that section.
- If a quoted VERBATIM is not already in English (e.g. a Spanish response from a LACRO client),
  give a brief English gloss of its meaning FIRST, then the original-language text in parentheses
  immediately after, for example "the process was very slow" ("el proceso fue muy lento"), every
  time you quote it, not just the first time. Never quote non-English text without an English gloss,
  and never silently translate without showing the original.
- Do not characterize a quoted verbatim as evidence of a specific insurance product feature (a
  credit-life death benefit, crop insurance payout, or similar) unless that product is confirmed
  present in this report's own product mix. A verbatim describing something that sounds like a
  loan being cleared, a payout on a family member's death, or similar does not by itself establish
  which product paid it; if you are not certain from the data package which product is involved,
  describe the benefit generically (e.g. "a benefit paid on a family member's death") rather than
  naming a specific product category, and never generalize a single respondent's account into a
  portfolio-wide pattern (e.g. "many clients experienced X") on the strength of one quote alone.

WORD LIMITS (strictly enforced):
- If a section specifies word_limit: 90, write AT MOST 90 words. Aim for 85-90.
- insight blocks: 120 words maximum. Aim for 110-120.
- narrative blocks (Parts 6, 7): 100 words maximum.
- Precision matters more than hitting the limit exactly. A tight 80-word paragraph is better than a padded 90-word one.

OUTPUT FORMAT:
Return ONLY valid JSON with the exact keys listed in the user message.
No markdown code fences, no explanation text outside the JSON.
"""


# Fail loudly at import time (not silently at prompt-build time) if the
# house-voice text ever changes without updating the SCOPE paragraph
# constants above -- a silent no-op .replace() would leave the
# single-country prompt quietly carrying stale multi-country wording.
assert _MULTI_COUNTRY_SCOPE_PARAGRAPH in _house_voice_text("__ASSERT_PLACEHOLDER__"), \
    "house_voice SCOPE paragraph changed -- update _MULTI_COUNTRY_SCOPE_PARAGRAPH to match"


# Word limits per text block key
WORD_LIMITS = {
    "s1_1": 90, "s1_2": 90, "s1_2b": 70, "s1_3": 80,
    "s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100,
    "s3_0": 70, "s3_1": 80, "s3_2": 70,
    "s4_1": 90, "s4_2": 90, "s4_3": 90,
    "s5_1": 90, "s5_2": 80, "s5_3": 80,
    "s9_1": 90, "s9_2": 70,
    "narrative": 100,
    "insight": 120,
}

# Expected output keys per part
_OUTPUT_SCHEMAS = {
    "part_1": {"s1_1": 90, "s1_2": 90, "s1_2b": 70, "s1_3": 80, "insight": 120},
    "part_2": {"s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100, "insight": 120},
    "part_3": {"s3_0": 70, "s3_1": 80, "s3_2": 70, "insight": 120},
    "part_4": {"s4_1": 90, "s4_2": 90, "s4_3": 90, "insight": 120},
    "part_5": {"s5_1": 90, "s5_2": 80, "s5_3": 80, "insight": 120},
    "part_6": {"narrative": 100, "insight": 120},
    "part_7": {"narrative": 100, "insight": 120},
    # LARCO only (see run_analysis.py's build_sections())
    "part_9": {"s9_1": 90, "s9_2": 70, "insight": 120},
    "part_10": {"narrative": 130, "insight": 120},
}


# ---------------------------------------------------------------------------
# Prompt building helpers
# ---------------------------------------------------------------------------

def _fmt_profile(profile: dict) -> str:
    parts = []
    if profile.get("sex"):
        parts.append(profile["sex"])
    if profile.get("age"):
        parts.append(f"age {profile['age']}")
    if profile.get("branch") and profile.get("country"):
        parts.append(f"{profile['branch']}, {profile['country']}")
    elif profile.get("branch"):
        parts.append(profile["branch"])
    elif profile.get("country"):
        parts.append(profile["country"])
    flags = []
    if profile.get("is_claimant"):
        flags.append("claimant")
    if profile.get("is_caregiver"):
        flags.append("caregiver")
    if flags:
        parts.append(", ".join(flags))
    return " | ".join(parts) if parts else "anonymous"


def _fmt_distribution(items: list, label: str = "main", top_n: int = 5) -> str:
    if not items:
        return ""
    lines = [f"  {label.upper()} DISTRIBUTION (top {min(top_n, len(items))}):"]
    for item in items[:top_n]:
        if isinstance(item, dict):
            option = item.get("option") or item.get("label") or item.get("value") or str(item)
            n   = item.get("n", "")
            pct = item.get("pct", "")
            if pct is not None and pct != "":
                try:
                    pct_str = f"{float(pct)*100:.1f}%" if float(pct) <= 1 else f"{float(pct):.1f}%"
                except (TypeError, ValueError):
                    pct_str = str(pct)
            else:
                pct_str = ""
            n_str = f" (n={n})" if n != "" else ""
            pct_out = f", {pct_str}" if pct_str else ""
            lines.append(f"    - {option}{n_str}{pct_out}")
        else:
            lines.append(f"    - {item}")
    return "\n".join(lines)


def _fmt_qual_value(key: str, value) -> str:
    if value is None:
        return f"  {key}: (not available)"
    if isinstance(value, dict):
        # Theme counts: {theme: count}
        top5 = sorted(value.items(), key=lambda x: x[1], reverse=True)[:5]
        top5_str = ", ".join(f"{k} ({v})" for k, v in top5)
        return f"  {key}: {top5_str}"
    if isinstance(value, list):
        if not value:
            return f"  {key}: (none)"
        # protection_flags or not_worth_it_themes or subthemes
        lines = [f"  {key} ({len(value)} items):"]
        for item in value[:5]:
            if isinstance(item, dict):
                # Summarize key fields
                summary_parts = []
                for k in ("label", "flag_type", "type", "severity", "summary", "reason", "count"):
                    if k in item:
                        summary_parts.append(f"{k}={item[k]}")
                lines.append(f"    - {'; '.join(summary_parts[:4])}")
            else:
                lines.append(f"    - {item}")
        return "\n".join(lines)
    return f"  {key}: {value}"


# Below this many total coded responses, a percentage reads as a finding
# ("100%!") when it's really just 3 out of 3. Deliberately much lower than
# analysis_engine/stats.py's LOW_N_THRESHOLD=30, which suppresses whole
# quantitative metrics outright -- qualitative sections legitimately run
# small (a handful of coded verbatims per part is normal), so the fix here
# is to report counts only below this floor, not to suppress the section.
_SENTIMENT_SPLIT_MIN_BASE_FOR_PCT = 10


def _fmt_sentiment_group(group_label: str, group_data: dict) -> str:
    """One group's SENTIMENT SPLIT line -- shared by the single-group and
    multi-group render paths in _fmt_insight_summary() below. group_data
    is R-006a's deterministic split shape: positive/negative/neutral/
    base_n/source_pool_n/selection_rule (docs/report_spec.md's
    SentimentSplit)."""
    positive = group_data.get("positive", 0)
    negative = group_data.get("negative", 0)
    neutral = group_data.get("neutral", 0)
    base_n = group_data.get("base_n", positive + negative + neutral)
    selection_rule = group_data.get("selection_rule", "")
    counts_str = f"positive={positive}, negative={negative}, neutral={neutral}"

    if base_n < _SENTIMENT_SPLIT_MIN_BASE_FOR_PCT:
        return (
            f"  {group_label} (n={base_n}, too small to state as percentages): {counts_str} "
            "-- report these as plain counts only (e.g. \"2 positive, 1 negative\"); do NOT "
            "compute or state a percentage for this group, the base is too small for one to "
            f"be meaningful. Base: {selection_rule}"
        )
    return f"  {group_label} (n={base_n}): {counts_str}. Base: {selection_rule}"


def _fmt_insight_summary(summary: dict | None) -> str:
    """Format the section-scoped theme/driver/sentiment summary (qualitative
    Task 5B, overridden for most sections by R-006a's deterministic
    sentiment_split -- docs/report_spec.md) that grounds an insight block
    in the aggregate response pool, not just the 1-3 quoted verbatims
    below it.

    sentiment_split is always {group_label: {positive, negative, neutral,
    base_n, source_pool_n, selection_rule}} (session-8, per instruction:
    ONE shape everywhere, a single-group section nested under the key
    "all" -- no Part-7-only special case). This function always iterates
    groups and never branches on which section it's formatting. A section
    with more than one group (Part 7: female, male) gets an explicit
    instruction to compare the groups in prose -- reporting two isolated
    splits side by side would defeat the entire reason the section has
    more than one group in the first place (Part 7 exists to contrast
    women and men, not to restate the portfolio-wide split twice).
    """
    if not summary:
        return "  SECTION SUMMARY: (not available)"
    lines = []
    if summary.get("theme_summary"):
        lines.append(f"  THEME SUMMARY: {summary['theme_summary']}")
    if summary.get("top_drivers"):
        lines.append(f"  TOP DRIVERS: {', '.join(summary['top_drivers'])}")

    split = summary.get("sentiment_split")
    if split:
        group_lines = [_fmt_sentiment_group(label.upper(), data) for label, data in split.items()]
        if len(split) > 1:
            lines.append(
                "  SENTIMENT SPLIT BY GROUP (compare these groups explicitly in your prose, e.g. "
                "\"women were more likely to report X than men\"; do NOT report each group's "
                "figures as a separate, isolated statement -- the comparison IS the finding):"
            )
        else:
            lines.append("  SENTIMENT SPLIT:")
        lines.extend(group_lines)

    return "\n".join(lines) if lines else "  SECTION SUMMARY: (not available)"


def _build_sections_text(package: dict) -> str:
    """Format section data as readable text for the Gemini prompt."""
    lines = []
    for s_key, s_data in package.get("sections", {}).items():
        if s_key == "insight":
            wl = s_data.get("word_limit", 120)
            lines.append(f"\nSECTION insight (word_limit: {wl} words)")
            lines.append(_fmt_insight_summary(s_data.get("insight_summary")))
            verbatims = s_data.get("verbatims", [])
            if verbatims:
                for i, v in enumerate(verbatims, 1):
                    text = v.get("text", "")
                    profile = _fmt_profile(v.get("profile", {}))
                    lines.append(f'  VERBATIM {i}: "{text}" [{profile}]')
            else:
                lines.append("  VERBATIMS: (qualitative data not yet available)")
            continue

        wl    = s_data.get("word_limit", 80)
        label = s_data.get("label", s_key)
        lines.append(f"\nSECTION {s_key}: {label} (word_limit: {wl} words)")

        # Metrics
        metrics = s_data.get("metrics", {})
        for m_key, m_val in metrics.items():
            if m_key.endswith("_n") or m_key.endswith("_population") or m_key.endswith("_components"):
                continue
            line = f"  {m_key}: {m_val}"
            n_val = metrics.get(m_key + "_n")
            if n_val is not None:
                line += f"  (n={n_val})"
            pop_val = metrics.get(m_key + "_population")
            if pop_val:
                line += f"  [population: {pop_val}]"
            comp_val = metrics.get(m_key + "_components")
            if comp_val:
                line += f"  [components: {comp_val}]"
            lines.append(line)

        # Distributions
        for dist_label, dist_items in s_data.get("distributions", {}).items():
            txt = _fmt_distribution(dist_items, label=dist_label)
            if txt:
                lines.append(txt)

        # Qualitative
        for q_key, q_val in s_data.get("qualitative", {}).items():
            if q_key == "verbatims":
                continue
            lines.append(_fmt_qual_value(q_key, q_val))

        # Drivers (Part 4 satisfaction / Part 5 child wellbeing)
        drivers_data = s_data.get("drivers_data", [])
        if drivers_data:
            outcome_label = s_data.get("drivers_outcome_label", "child wellbeing")
            lines.append(f"  DRIVERS (Spearman rho with {outcome_label}):")
            for d in drivers_data:
                if d.get("not_applicable"):
                    lines.append(f"    {d['label']}: rho=NOT APPLICABLE")
                elif d["suppressed"]:
                    lines.append(f"    {d['label']}: rho=SUPPRESSED")
                else:
                    rho = f"{d['rho']:+.3f}" if d["rho"] is not None else "?"
                    p   = format_p_value(d["p_value"])
                    n   = d["n_valid"] or "?"
                    lines.append(f"    {d['label']}: rho={rho}, p={p}, n={n}")
                if d.get("population"):
                    lines.append(f"      [population: {d['population']}]")
                if d.get("direction"):
                    lines.append(f"      [direction: {d['direction']}]")

        # Note
        note = s_data.get("note", "")
        if note:
            lines.append(f"  NOTE: {note.strip()}")

    return "\n".join(lines)


def _build_scorecard_text(scorecard: list, group_a: str, group_b: str) -> str:
    if not scorecard:
        return "  (no scorecard data)"
    lines = [f"  {'Metric':<40} {group_a:<18} {group_b:<18} Sig?"]
    lines.append("  " + "-" * 80)
    for row in scorecard:
        sig_mark = "*" if row["significant"] else ""
        p_note   = f"(p={format_p_value(row['sig_p'])})" if row["sig_p"] is not None else ""
        lines.append(
            f"  {row['label']:<40} {row['group_a_value']:<18} {row['group_b_value']:<18} {sig_mark} {p_note}"
        )
        if row.get("population"):
            lines.append(f"    [population: {row['population']}]")
        if row.get("sig_test_note"):
            lines.append(f"    [note: {row['sig_test_note']}]")
    return "\n".join(lines)


def _part10_trend_available(package: dict) -> bool:
    """True when at least one Part 10 indicator has a real prior-wave value --
    i.e. there is something to actually compare, not just an empty trend
    table. Shared by _build_part_prompt() (tells the model whether a trend
    exists at all) and _part10_narrative_violations() below (decides whether
    the stricter no-prior-wave rules apply to the returned narrative)."""
    return bool(package.get("scorecard")) and any(
        row["group_b_value"] != "N/A (no prior wave)" for row in package.get("scorecard", [])
    )


# Phrases report_spec.yaml's part_10 prompt note explicitly forbids when no
# prior wave is available -- reverse-engineered from a real generated report
# that called the current wave a "founding baseline for VisionFund's global
# insurance portfolio" and claimed product understanding "was not asked of
# this population" despite Part 1 reporting it at length. The prompt already
# instructs against both; this is the code-level guard so a report doesn't
# ship with either fabrication if the model doesn't comply, per
# docs/maintenance/known-issues-log.md's "fail loudly, not confidently
# wrong" requirement for this section specifically.
_PART10_BANNED_PATTERNS = [
    re.compile(r"founding (?:baseline|wave)", re.IGNORECASE),
    re.compile(r"not asked of (?:this|the) population", re.IGNORECASE),
]

_PART10_NO_PRIOR_WAVE_FALLBACK = (
    "This is the first wave on record for this dataset. No prior wave is "
    "available yet, so no wave-over-wave trend can be described for these "
    "indicators."
)


def _part10_narrative_violations(narrative) -> list[str]:
    """Checked only when _part10_trend_available() is False, i.e. the trend
    table is genuinely empty. Returns a human-readable violation per banned
    phrase or comparative verb found, or [] if the narrative is clean. An
    empty/non-string narrative is not this function's concern (that's a
    missing-key problem the existing JSON-schema handling already catches)."""
    if not isinstance(narrative, str) or not narrative:
        return []
    violations = []
    for pattern in _PART10_BANNED_PATTERNS:
        m = pattern.search(narrative)
        if m:
            violations.append(f'uses banned phrasing "{m.group(0)}"')
    lowered = narrative.lower()
    for verb in _COMPARATIVE_VERBS:
        if re.search(rf"\b{re.escape(verb)}\b", lowered):
            violations.append(f'uses comparative language ("{verb}") despite no prior wave being available')
            break
    return violations


def _build_part_prompt(package: dict, part_key: str, report_title: str, extra_instruction: str = "") -> str:
    part_num = part_key.replace("part_", "")
    title    = package["title"]
    schema   = _OUTPUT_SCHEMAS.get(part_key, {})

    lines = [
        f"REPORT: {report_title}",
        f"PART {part_num}: {title}",
        "",
    ]

    if part_key in ("part_6", "part_7", "part_10"):
        # Scorecard-shaped parts -- Part 10's "scorecard" is a wave-over-wave
        # trend table (Current Wave vs Prior Wave), built by
        # orchestrator.py's _build_trend_data() into the exact same row
        # shape Parts 6/7's segment scorecards use, so it reuses this same
        # prompt formatting unmodified.
        if part_key == "part_6":
            # R-011 (session-10): pass the same terminology the rendered
            # table uses, not a hardcoded "Non-Claimant" -- that label was
            # already tried and retracted (see part_6.py's module
            # docstring) because it implies the much larger population
            # who never had a claimable event, not this narrower group.
            group_a, group_b = f"{LABEL_CLAIMANT} ({QUALIFIER_CLAIMANT})", LABEL_NON_FILER
        elif part_key == "part_7":
            group_a, group_b = "Female", "Male"
        else:
            group_a, group_b = "Current Wave", "Prior Wave"
        table_label = "TREND TABLE" if part_key == "part_10" else "SCORECARD TABLE"
        lines.append(f"{table_label}:")
        lines.append(_build_scorecard_text(package.get("scorecard", []), group_a, group_b))
        if part_key == "part_10":
            lines.append(f"\nTREND AVAILABLE: {_part10_trend_available(package)}")
        lines.append("")

        # Narrative section note
        narr = package.get("sections", {}).get("narrative", {})
        if narr.get("note"):
            lines.append(f"NARRATIVE NOTE: {narr['note'].strip()}")

        # Insight verbatims
        insight = package.get("sections", {}).get("insight", {})
        lines.append(f"\nSECTION insight (word_limit: {insight.get('word_limit', 120)} words)")
        lines.append(_fmt_insight_summary(insight.get("insight_summary")))
        verbatims = insight.get("verbatims", [])
        if verbatims:
            for i, v in enumerate(verbatims, 1):
                text    = v.get("text", "")
                profile = _fmt_profile(v.get("profile", {}))
                lines.append(f'  VERBATIM {i}: "{text}" [{profile}]')
        else:
            lines.append("  VERBATIMS: (qualitative data not yet available)")

    else:
        lines.append(_build_sections_text(package))
        # Part 5's caregiver vs non-caregiver comparison (the only non-6/7 part
        # with a scorecard) -- appended after the generic sections text so the
        # LLM sees both the drivers/healthcare content and this table.
        if package.get("scorecard"):
            lines.append("\nSCORECARD TABLE (Caregiver vs Non-Caregiver):")
            lines.append(_build_scorecard_text(package["scorecard"], "Caregiver", "Non-Caregiver"))

    # Required output schema
    lines.append("\n\nREQUIRED OUTPUT JSON:")
    schema_lines = ["{"]
    for k, wl in schema.items():
        schema_lines.append(f'  "{k}": "...",  // ≤{wl} words')
    schema_lines.append("}")
    lines.append("\n".join(schema_lines))

    if extra_instruction:
        lines.append(f"\n\n{extra_instruction}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Word-limit enforcement
# ---------------------------------------------------------------------------

def enforce_word_limits(texts: dict) -> dict:
    enforced = {}
    for key, text in texts.items():
        if not isinstance(text, str):
            enforced[key] = text
            continue
        limit = WORD_LIMITS.get(key)
        if limit and word_count(text) > int(limit * 1.15):
            original = word_count(text)
            text = truncate_to_limit(text, limit)
            log.warning(f"{key}: truncated {original} → {word_count(text)} words")
        enforced[key] = text
    return enforced


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def write_part(package: dict, part_key: str, provider: str, api_key: str, model: str | None,
              report_title: str, single_country: bool = False, extra_instruction: str = "") -> dict:
    user_message = _build_part_prompt(package, part_key, report_title, extra_instruction=extra_instruction)
    result_text = call_llm(
        provider=provider,
        api_key=api_key,
        system_prompt=_house_voice(report_title, single_country=single_country),
        user_content=user_message,
        max_output_tokens=8192,
        temperature=0.3,
        model=model,
    )
    return json.loads(result_text)


def write_all_parts(packages: list, run_id: str, model: str | None,
                    max_retries: int = 2, retry_delay: int = 30,
                    provider: str = "gemini", api_key: str | None = None,
                    progress_cb=None) -> dict:
    """Write all report parts via the chosen LLM provider.

    A part that fails every retry does NOT abort the run: it's recorded as
    failed (marked with a `_generation_failed` sentinel in its texts dict, so
    the assembler can render a manual-write-up placeholder instead of blank
    prose) and the remaining parts still get written. Callers can find out
    which parts need manual follow-up via the `_generation_failed` marker.

    progress_cb(part_key: str, status: dict), if given, is invoked once per
    part immediately after it either succeeds or exhausts its retries -- this
    is the hook the dashboard uses to stream per-part progress over SSE.
    """
    if api_key is None:
        if provider == "gemini":
            import os
            api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "No API key provided for provider "
                f"{provider!r}. Pass api_key=..., or for Gemini set "
                "$env:GEMINI_API_KEY = 'your_key_here'"
            )

    run_dir  = ROOT / "runs" / run_id
    meta = _load_analysis_meta(run_id)
    report_title = _report_title(run_id, meta)
    single_country = _is_single_country(meta)
    all_texts: dict = {}
    failed_parts: list[str] = []

    for package in packages:
        part_key = package["part"]
        log.info(f"Writing {part_key} — {package['title']}...")

        raw_result = None
        last_error: Exception | None = None
        extra_instruction = ""
        for attempt in range(max_retries + 1):
            try:
                raw_result = write_part(package, part_key, provider, api_key, model, report_title,
                                        single_country=single_country, extra_instruction=extra_instruction)
            except Exception as exc:
                raw_result = None
                last_error = exc
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)
                    log.warning(f"{part_key}: attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    log.error(f"{part_key}: {provider} call failed after {max_retries + 1} attempts: {exc}")
                continue

            # Part 10 with a genuinely empty trend table: a prompt instruction
            # alone isn't enough (see docs/maintenance/known-issues-log.md) --
            # verify the model actually complied, retry once with the specific
            # violation named, and if it still doesn't comply, guarantee
            # correctness by substituting a fixed sentence rather than
            # shipping whatever the model wrote.
            if part_key == "part_10" and not _part10_trend_available(package):
                violations = _part10_narrative_violations(raw_result.get("narrative"))
                if violations:
                    last_error = RuntimeError(
                        "part_10 narrative violated no-prior-wave rules: " + "; ".join(violations)
                    )
                    if attempt < max_retries:
                        extra_instruction = (
                            'CORRECTION REQUIRED: your previous "narrative" answer '
                            + " and ".join(violations)
                            + ". There is genuinely no prior wave to compare against for this "
                              'dataset. Rewrite "narrative" to state that plainly, in one '
                              "neutral sentence, using none of the phrasing named above."
                        )
                        log.warning(
                            f"part_10: narrative violated no-prior-wave rules (attempt {attempt + 1}): "
                            f"{violations}. Retrying with a corrective instruction..."
                        )
                        continue
                    else:
                        log.error(
                            f"part_10: narrative still violated no-prior-wave rules after "
                            f"{max_retries + 1} attempts: {violations}. Substituting the fixed "
                            "fallback sentence rather than shipping a fabricated narrative."
                        )
                        raw_result["narrative"] = _PART10_NO_PRIOR_WAVE_FALLBACK

            break

        if raw_result is None:
            failed_parts.append(part_key)
            all_texts[part_key] = {"_generation_failed": True, "_error": str(last_error)}
            if progress_cb:
                progress_cb(part_key, {"status": "failed", "error": str(last_error)})
            continue

        # Save raw response
        raw_path = run_dir / f"writer_raw_{part_key}.json"
        raw_path.write_text(json.dumps(raw_result, ensure_ascii=False, indent=2), encoding="utf-8")

        enforced = enforce_word_limits(raw_result)
        all_texts[part_key] = enforced
        if progress_cb:
            progress_cb(part_key, {"status": "succeeded"})

    # Save final collection
    out_path = run_dir / "written_texts.json"
    out_path.write_text(json.dumps(all_texts, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info(f"Written texts saved to {out_path}")

    if failed_parts:
        log.error(
            f"Generation failed for {len(failed_parts)} part(s): {failed_parts} — "
            "these sections need manual write-up before publishing."
        )

    return all_texts
