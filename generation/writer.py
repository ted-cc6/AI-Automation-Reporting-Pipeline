"""generation/writer.py

Phase 3: Seven LLM calls (one per part); house-voice system prompt. Provider/
api_key are passed in explicitly by the caller (the dashboard backend threads
these through from the user's browser session; the CLI entrypoint in
run_generation.py falls back to GEMINI_API_KEY for standalone use).
"""
import json
import logging
import time
from pathlib import Path

from llm_providers import call_llm
from utils import word_count, truncate_to_limit, format_period_label

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent


def _report_title(run_id: str) -> str:
    return f"VisionFund International Insurance Impact Report — Global Portfolio, {format_period_label(run_id)}"


def _house_voice(report_title: str) -> str:
    return f"""
You are writing the {report_title}.

AUDIENCE: Senior MFI leaders, impact investors, and programme managers.
Assume they understand financial inclusion concepts but not statistical methods.

SCOPE: This report covers VisionFund's insurance client portfolio across MULTIPLE
countries in one combined analysis — it is not a single-country report. Some
metrics only apply to a subset of clients (for example, a product that is only
sold in one country, or a question that was only asked to certain product
types). Whenever a metric's data package states a "population" for it, use that
population description in your sentence (e.g. "among health and credit-life
clients" or "among Vietnam's crop-insurance clients") instead of implying the
figure describes all surveyed clients. Never present two metrics as a
before/after or "however" contrast unless they describe the same population —
check each metric's stated population before connecting it to another.

SCALE DIRECTION: Several survey questions are coded so that a LOWER number is
the more positive response (1=best, e.g. "Definitely would renew" = 1). When a
Part 5 driver correlation gives a "[direction: ...]" note, that note states
what the sign actually means in plain English for that specific driver — use
its stated real-world direction verbatim rather than assuming a negative rho
is automatically a negative finding. A negative correlation is frequently the
EXPECTED, POSITIVE result once the 1=best coding is accounted for (e.g.
stronger renewal intent aligning with better child wellbeing produces a
negative rho, not a positive one) — never describe such a result as
counterintuitive or concerning without first checking its direction note.

VOICE RULES:
- Professional, empathetic, evidence-based
- Active voice. Past tense for findings ("revealed", "showed"), present for implications ("suggests", "indicates")
- No bullet points, no headers, no markdown in narrative text — flowing prose only
- Do not use academic jargon (no "statistically significant" — say "the difference is meaningful" or cite the p-value)
- Every statistic you cite MUST come from the data package. Never invent or round figures beyond what is provided.
- Suppressed values (marked "SUPPRESSED") must be noted as "data suppressed due to small sample size" — never estimate or interpolate
- When a note field is present, incorporate its guidance into the narrative
- For insight blocks: SECTION SUMMARY (theme summary, top drivers, sentiment split) describes the
  pattern across all responses judged relevant to that section — use it for the section's overall
  characterization. Use the quoted VERBATIM(s) to illustrate that pattern with a specific client
  voice, not as evidence of the pattern itself — never imply that 1-3 quotes represent the full
  client base's sentiment when a SENTIMENT SPLIT is available and shows a different balance.

WORD LIMITS (strictly enforced):
- If a section specifies word_limit: 90, write AT MOST 90 words. Aim for 85-90.
- insight blocks: 120 words maximum. Aim for 110-120.
- narrative blocks (Parts 6, 7): 100 words maximum.
- Precision matters more than hitting the limit exactly. A tight 80-word paragraph is better than a padded 90-word one.

OUTPUT FORMAT:
Return ONLY valid JSON with the exact keys listed in the user message.
No markdown code fences, no explanation text outside the JSON.
"""

# Word limits per text block key
WORD_LIMITS = {
    "s1_1": 90, "s1_2": 90, "s1_2b": 70, "s1_3": 80,
    "s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100,
    "s3_0": 70, "s3_1": 80, "s3_2": 70,
    "s4_1": 90, "s4_2": 90, "s4_3": 90,
    "s5_1": 90, "s5_2": 80, "s5_3": 80,
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


def _fmt_insight_summary(summary: dict | None) -> str:
    """Format the section-scoped theme/driver/sentiment summary (qualitative
    Task 5B) that grounds an insight block in the aggregate response pool,
    not just the 1-3 quoted verbatims below it."""
    if not summary:
        return "  SECTION SUMMARY: (not available)"
    lines = []
    if summary.get("theme_summary"):
        lines.append(f"  THEME SUMMARY: {summary['theme_summary']}")
    if summary.get("top_drivers"):
        lines.append(f"  TOP DRIVERS: {', '.join(summary['top_drivers'])}")
    split = summary.get("sentiment_split")
    if split:
        split_str = ", ".join(f"{k}={v}" for k, v in split.items())
        lines.append(f"  SENTIMENT SPLIT (approx., across all responses judged relevant to this section): {split_str}")
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
        lines.append(f"\nSECTION {s_key} — {label} (word_limit: {wl} words)")

        # Metrics
        metrics = s_data.get("metrics", {})
        for m_key, m_val in metrics.items():
            if m_key.endswith("_n") or m_key.endswith("_population"):
                continue
            line = f"  {m_key}: {m_val}"
            n_val = metrics.get(m_key + "_n")
            if n_val is not None:
                line += f"  (n={n_val})"
            pop_val = metrics.get(m_key + "_population")
            if pop_val:
                line += f"  [population: {pop_val}]"
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
                if d["suppressed"]:
                    lines.append(f"    {d['label']}: rho=SUPPRESSED")
                else:
                    rho = f"{d['rho']:+.3f}" if d["rho"] is not None else "?"
                    p   = f"{d['p_value']:.4f}" if d["p_value"] is not None else "?"
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
        p_note   = f"(p={row['sig_p']:.4f})" if row["sig_p"] is not None else ""
        lines.append(
            f"  {row['label']:<40} {row['group_a_value']:<18} {row['group_b_value']:<18} {sig_mark} {p_note}"
        )
        if row.get("population"):
            lines.append(f"    [population: {row['population']}]")
        if row.get("sig_test_note"):
            lines.append(f"    [note: {row['sig_test_note']}]")
    return "\n".join(lines)


def _build_part_prompt(package: dict, part_key: str, report_title: str) -> str:
    part_num = part_key.replace("part_", "")
    title    = package["title"]
    schema   = _OUTPUT_SCHEMAS.get(part_key, {})

    lines = [
        f"REPORT: {report_title}",
        f"PART {part_num}: {title}",
        "",
    ]

    if part_key in ("part_6", "part_7"):
        # Scorecard parts
        group_a = "Claimant" if part_key == "part_6" else "Female"
        group_b = "Non-Claimant" if part_key == "part_6" else "Male"
        lines.append("SCORECARD TABLE:")
        lines.append(_build_scorecard_text(package.get("scorecard", []), group_a, group_b))
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
              report_title: str) -> dict:
    user_message = _build_part_prompt(package, part_key, report_title)
    result_text = call_llm(
        provider=provider,
        api_key=api_key,
        system_prompt=_house_voice(report_title),
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
    report_title = _report_title(run_id)
    all_texts: dict = {}
    failed_parts: list[str] = []

    for package in packages:
        part_key = package["part"]
        log.info(f"Writing {part_key} — {package['title']}...")

        raw_result = None
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_result = write_part(package, part_key, provider, api_key, model, report_title)
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)
                    log.warning(f"{part_key}: attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    log.error(f"{part_key}: {provider} call failed after {max_retries + 1} attempts: {exc}")

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
