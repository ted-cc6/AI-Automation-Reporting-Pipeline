"""generation/writer.py

Phase 3: Seven Gemini 2.5 Pro calls (one per part); house-voice system prompt.
"""
import json
import logging
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

from utils import word_count, truncate_to_limit

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent

HOUSE_VOICE = """
You are writing the VisionFund International Insurance Impact Report — Vietnam 2026 Q2.

AUDIENCE: Senior MFI leaders, impact investors, and programme managers.
Assume they understand financial inclusion concepts but not statistical methods.

VOICE RULES:
- Professional, empathetic, evidence-based
- Active voice. Past tense for findings ("revealed", "showed"), present for implications ("suggests", "indicates")
- No bullet points, no headers, no markdown in narrative text — flowing prose only
- Do not use academic jargon (no "statistically significant" — say "the difference is meaningful" or cite the p-value)
- Every statistic you cite MUST come from the data package. Never invent or round figures beyond what is provided.
- Suppressed values (marked "SUPPRESSED") must be noted as "data suppressed due to small sample size" — never estimate or interpolate
- When a note field is present, incorporate its guidance into the narrative

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
    "s1_1": 90, "s1_2": 90, "s1_3": 80,
    "s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100,
    "s3_1": 80, "s3_2": 70,
    "s4_1": 90, "s4_2": 90, "s4_3": 80,
    "s5_1": 90, "s5_2": 80,
    "narrative": 100,
    "insight": 120,
}

# Expected output keys per part
_OUTPUT_SCHEMAS = {
    "part_1": {"s1_1": 90, "s1_2": 90, "s1_3": 80, "insight": 120},
    "part_2": {"s2_1": 100, "s2_2": 70, "s2_3": 80, "s2_4": 100, "insight": 120},
    "part_3": {"s3_1": 80, "s3_2": 70, "insight": 120},
    "part_4": {"s4_1": 90, "s4_2": 90, "s4_3": 80, "insight": 120},
    "part_5": {"s5_1": 90, "s5_2": 80, "insight": 120},
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
    if profile.get("branch"):
        parts.append(profile["branch"])
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


def _build_sections_text(package: dict) -> str:
    """Format section data as readable text for the Gemini prompt."""
    lines = []
    for s_key, s_data in package.get("sections", {}).items():
        if s_key == "insight":
            wl = s_data.get("word_limit", 120)
            lines.append(f"\nSECTION insight (word_limit: {wl} words)")
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
        for m_key, m_val in s_data.get("metrics", {}).items():
            if m_key.endswith("_n"):
                base = m_key[:-2]
                lines.append(f"  {base}: {s_data['metrics'].get(base, '?')}  (n={m_val})")
            elif m_key + "_n" not in s_data.get("metrics", {}):
                lines.append(f"  {m_key}: {m_val}")

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

        # Drivers (Part 5)
        drivers_data = s_data.get("drivers_data", [])
        if drivers_data:
            lines.append("  DRIVERS (Spearman rho with child wellbeing):")
            for d in drivers_data:
                if d["suppressed"]:
                    lines.append(f"    {d['label']}: rho=SUPPRESSED")
                else:
                    rho = f"{d['rho']:+.3f}" if d["rho"] is not None else "?"
                    p   = f"{d['p_value']:.4f}" if d["p_value"] is not None else "?"
                    n   = d["n_valid"] or "?"
                    lines.append(f"    {d['label']}: rho={rho}, p={p}, n={n}")

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
    return "\n".join(lines)


def _build_part_prompt(package: dict, part_key: str) -> str:
    part_num = part_key.replace("part_", "")
    title    = package["title"]
    schema   = _OUTPUT_SCHEMAS.get(part_key, {})

    lines = [
        "REPORT: VisionFund International Insurance Impact Report — Vietnam 2026 Q2",
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

def write_part(package: dict, part_key: str, client, model: str) -> dict:
    user_message = _build_part_prompt(package, part_key)
    response = client.models.generate_content(
        model=model,
        contents=user_message,
        config=types.GenerateContentConfig(
            system_instruction=HOUSE_VOICE,
            response_mime_type="application/json",
            max_output_tokens=8192,
            temperature=0.3,
        ),
    )
    return json.loads(response.text)


def write_all_parts(packages: list, run_id: str, model: str,
                    max_retries: int = 2, retry_delay: int = 30) -> dict:
    """Write all report parts via Gemini.

    A part that fails every retry does NOT abort the run: it's recorded as
    failed (marked with a `_generation_failed` sentinel in its texts dict, so
    the assembler can render a manual-write-up placeholder instead of blank
    prose) and the remaining parts still get written. Callers can find out
    which parts need manual follow-up via the `_generation_failed` marker.
    """
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EnvironmentError(
            "GEMINI_API_KEY environment variable is not set. "
            "Set it before running: $env:GEMINI_API_KEY = 'your_key_here'"
        )

    client   = genai.Client(api_key=api_key)
    run_dir  = ROOT / "runs" / run_id
    all_texts: dict = {}
    failed_parts: list[str] = []

    for package in packages:
        part_key = package["part"]
        log.info(f"Writing {part_key} — {package['title']}...")

        raw_result = None
        last_error: Exception | None = None
        for attempt in range(max_retries + 1):
            try:
                raw_result = write_part(package, part_key, client, model)
                break
            except Exception as exc:
                last_error = exc
                if attempt < max_retries:
                    delay = retry_delay * (2 ** attempt)
                    log.warning(f"{part_key}: attempt {attempt + 1} failed: {exc}. Retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    log.error(f"{part_key}: Gemini call failed after {max_retries + 1} attempts: {exc}")

        if raw_result is None:
            failed_parts.append(part_key)
            all_texts[part_key] = {"_generation_failed": True, "_error": str(last_error)}
            continue

        # Save raw response
        raw_path = run_dir / f"writer_raw_{part_key}.json"
        raw_path.write_text(json.dumps(raw_result, ensure_ascii=False, indent=2), encoding="utf-8")

        enforced = enforce_word_limits(raw_result)
        all_texts[part_key] = enforced

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
