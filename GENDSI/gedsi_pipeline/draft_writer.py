"""
Stage 5 -- draft writing (Claude).

One call per report section. Each call receives ONLY that section's evidence
pack (pre-computed, significance-tested quant stats + coded qual
themes/quotes from Stages 2-4) -- never the raw dataset -- so the model
cannot invent statistics, benchmarks, or citations. Output is structured:
a highlightable headline insight + house-style prose paragraphs.
"""
from __future__ import annotations

import json
from pathlib import Path

from gedsi_pipeline import config, llm_client

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {
        "headline_insight": {
            "type": "string",
            "description": "One or two sentence headline takeaway for this section, to be visually "
                            "highlighted in the report. Must be a factual claim directly supported by "
                            "the evidence pack, not a vague generality.",
        },
        "paragraphs": {
            "type": "array",
            "items": {"type": "string"},
            "description": "2-4 prose paragraphs (no bullet points) in the house style.",
        },
    },
    "required": ["headline_insight", "paragraphs"],
}

HOUSE_STYLE_PROMPT = """You are drafting one section of a VisionFund GEDSI (Gender Equality, Disability, \
and Social Inclusion) analysis report on the 2026 Insurance Survey, in VisionFund's house style.

Content rules:
- Written analysis first, in flowing prose, not bullet points.
- Weave together, in this order: the statistic, then a client voice (a verbatim quote), then a \
benchmark (only if supplied below; otherwise explicitly say benchmark data is not available for this \
indicator, and never invent one), then the implication for VisionFund's programming or product design.
- When quant and qual evidence appear to diverge (flagged explicitly below), name the divergence \
directly in the prose rather than glossing over it.
- Use ONLY the numbers, quotes, and notes given in the evidence pack below. Do not invent statistics, \
percentages, benchmarks, or external studies or citations not present in the pack. If you reference \
general external context (e.g. UN Women, World Bank framing), label it explicitly as general context, \
not a cited finding from this survey.
- Attribute quotes only by gender and country (e.g. "a female client in Rwanda said..."), never a name.
- Where a subgroup's sample size is marked n_ok=false or noted as small, treat the finding as \
directional or illustrative rather than statistically robust, and say so.

Formatting rules (strict, apply to every field you write):
- Do not use em dashes, en dashes, or arrow notation like "->" anywhere in the text. To set off a \
clause, use a comma, a period, or a separate sentence instead.
- Do not use a hyphen as punctuation to interrupt or join a clause. A hyphen is only acceptable inside \
an ordinary compound word, such as "first-time" or "small-scale".
- Do not use backslashes or LaTeX-style escapes anywhere, such as "\\%", "\\$", or "\\times". Write \
plain text instead, such as "12%", "$10", or "12 percentage points".
- Write in plain prose sentences and paragraphs only, with standard punctuation (periods, commas, \
parentheses, quotation marks).

SECTION: {section_name}

EVIDENCE PACK (JSON, this is your only source of facts for this section):
{evidence_json}

Write the section now.
"""


def draft_section(section_key: str, pack: dict, api_key: str) -> dict:
    prompt = HOUSE_STYLE_PROMPT.format(
        section_name=pack["section"],
        evidence_json=json.dumps(pack, ensure_ascii=False, indent=2),
    )
    return llm_client.generate_json(prompt, DRAFT_SCHEMA, api_key, effort="medium")


def run_draft_writer(api_key: str, work_dir: Path | None = None) -> dict[str, dict]:
    work_dir = work_dir or config.WORK_DIR
    packs_dir = work_dir / "evidence_packs"
    drafts_dir = work_dir / "drafts"
    drafts_dir.mkdir(parents=True, exist_ok=True)

    drafts = {}
    for pack_path in sorted(packs_dir.glob("*.json")):
        section_key = pack_path.stem
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        print(f"Drafting: {pack['section']} ...")
        draft = draft_section(section_key, pack, api_key)
        drafts[section_key] = draft
        out_path = drafts_dir / f"{section_key}.json"
        out_path.write_text(json.dumps(draft, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  headline: {draft['headline_insight'][:120]}")
    return drafts


if __name__ == "__main__":
    run_draft_writer(llm_client.prompt_for_api_key())
