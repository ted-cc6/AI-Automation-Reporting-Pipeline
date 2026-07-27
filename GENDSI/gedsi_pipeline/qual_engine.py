"""
Stage 3 -- qualitative engine (Claude).

Two halves, separated by a human-in-the-loop review gate:

1. induce_codebook(question) -- sample responses, ask Claude to propose a
   theme codebook, write it to work/codebooks/<question>_draft.json.
   PAUSE HERE: a human reviews/edits the draft before coding proceeds.

2. code_responses(question, codebook) -- once a codebook is approved
   (copy/edit the _draft.json into <question>_approved.json), batch-code
   every non-empty response against it, write work/theme_tables/<question>.csv
   and update work/quote_bank.json with illustrative verbatim quotes.
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from gedsi_pipeline import config, llm_client

BATCH_SIZE = 25
SAMPLE_PER_GENDER = 100  # cap per gender for codebook induction sample

CODEBOOK_SCHEMA = {
    "type": "object",
    "properties": {
        "themes": {
            "type": "array",
            "minItems": 4,
            "maxItems": 9,
            "items": {
                "type": "object",
                "properties": {
                    "code": {"type": "string", "description": "short snake_case identifier"},
                    "label": {"type": "string", "description": "human-readable theme name"},
                    "definition": {"type": "string", "description": "one-sentence definition of what qualifies for this theme"},
                    "example_quote": {"type": "string", "description": "one verbatim quote from the sample illustrating this theme"},
                },
                "required": ["code", "label", "definition", "example_quote"],
            },
        }
    },
    "required": ["themes"],
}

CODING_SCHEMA = {
    "type": "object",
    "properties": {
        "codings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "response_id": {"type": "string"},
                    "themes": {"type": "array", "items": {"type": "string"}},
                    "quote_worthy": {"type": "boolean", "description": "true if this response is a clear, well-phrased illustrative quote"},
                },
                "required": ["response_id", "themes", "quote_worthy"],
            },
        }
    },
    "required": ["codings"],
}

QUESTION_CONTEXT = {
    "nps_detractor_reasons": (
        "This is from an insurance client satisfaction survey (VisionFund, Health/Crop/Enhanced "
        "Credit Life insurance). The respondent gave a Net Promoter Score of 0-6 (a detractor) and "
        "was asked: 'What actions could VisionFund take to make you more likely to recommend the "
        "insurance product to a friend or family member?'"
    ),
    "nps_passive_reasons": (
        "This is from an insurance client satisfaction survey (VisionFund, Health/Crop/Enhanced "
        "Credit Life insurance). The respondent gave a Net Promoter Score of 7-8 (a passive) and "
        "was asked: 'What specifically about the VisionFund Insurance caused you to give it the "
        "score that you did?'"
    ),
    "nps_promoter_reasons": (
        "This is from an insurance client satisfaction survey (VisionFund, Health/Crop/Enhanced "
        "Credit Life insurance). The respondent gave a Net Promoter Score of 9-10 (a promoter) and "
        "was asked: 'What specifically about the VisionFund Insurance would cause you to recommend "
        "it to a friend or family member?'"
    ),
}


def _sample_for_induction(df: pd.DataFrame, question: str) -> pd.DataFrame:
    sub = df[df[question].notna() & (df[question].str.strip() != "")]
    parts = []
    for sex in ["Female", "Male"]:
        pool = sub[sub["sex"] == sex]
        n = min(SAMPLE_PER_GENDER, len(pool))
        if n:
            parts.append(pool.sample(n=n, random_state=42))
    return pd.concat(parts) if parts else sub.iloc[0:0]


def induce_codebook(df: pd.DataFrame, question: str, api_key: str) -> dict:
    sample = _sample_for_induction(df, question)
    quotes = "\n".join(f"- ({row.sex}) {getattr(row, question)}" for row in sample.itertuples())
    prompt = f"""{QUESTION_CONTEXT[question]}

Below is a sample of {len(sample)} responses (gender noted for context). Read them and induce a
THEME CODEBOOK: 4-9 mutually-as-distinct-as-possible themes that would let a researcher code every
response in the full dataset (thousands of similar responses) into one or more themes.

For each theme give: a short snake_case code, a human-readable label, a one-sentence definition
precise enough for consistent coding, and one verbatim example quote from the sample below.

Responses:
{quotes}
"""
    result = llm_client.generate_json(prompt, CODEBOOK_SCHEMA, api_key)
    return result


def save_draft_codebook(question: str, codebook: dict, work_dir: Path | None = None) -> None:
    out_dir = (work_dir or config.WORK_DIR) / "codebooks"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{question}_draft.json"
    path.write_text(json.dumps(codebook, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {path}")


def print_codebook(question: str, codebook: dict) -> None:
    print(f"\n=== Draft codebook: {question} ===")
    for t in codebook["themes"]:
        print(f"  [{t['code']}] {t['label']}")
        print(f"      def: {t['definition']}")
        print(f"      e.g. \"{t['example_quote'][:140]}\"")


def run_induction(api_key: str, questions: list[str] | None = None, role_map=None,
                   work_dir: Path | None = None) -> dict[str, dict]:
    work_dir = work_dir or config.WORK_DIR
    df = pd.read_parquet(work_dir / "response_frame.parquet")
    role_map = role_map or config.DEFAULT_ROLE_MAP
    questions = questions or list(role_map.qual_primary.keys())
    codebooks = {}
    for q in questions:
        codebook = induce_codebook(df, q, api_key)
        save_draft_codebook(q, codebook, work_dir)
        print_codebook(q, codebook)
        codebooks[q] = codebook
    return codebooks


# ---------------------------------------------------------------------------
# Stage 3b -- full coding against an APPROVED codebook (run after human review)
# ---------------------------------------------------------------------------

def _batched(seq, n):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def load_approved_codebook(question: str, work_dir: Path | None = None) -> dict:
    path = (work_dir or config.WORK_DIR) / "codebooks" / f"{question}_approved.json"
    if not path.exists():
        raise FileNotFoundError(
            f"No approved codebook at {path}. Review {question}_draft.json, save your edited "
            f"version as {question}_approved.json, then rerun coding."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def code_responses(df: pd.DataFrame, question: str, codebook: dict, api_key: str) -> pd.DataFrame:
    theme_desc = "\n".join(f"- {t['code']}: {t['label']} -- {t['definition']}" for t in codebook["themes"])
    sub = df[df[question].notna() & (df[question].str.strip() != "")]
    records = sub[["response_id", "sex", "disability", "country", "insurance_type", question]].to_dict("records")

    all_codings = []
    for batch in _batched(records, BATCH_SIZE):
        items = "\n".join(f"- response_id={r['response_id']}: {r[question]}" for r in batch)
        prompt = f"""{QUESTION_CONTEXT[question]}

Codebook (assign one or more codes per response; use ONLY these codes):
{theme_desc}

Code each of the following responses. For each, return its response_id, the list of theme codes
that apply (multi-label allowed), and whether it is "quote_worthy" (a clear, well-phrased response
that would work as an illustrative verbatim quote in a report).

Responses:
{items}
"""
        result = llm_client.generate_json(prompt, CODING_SCHEMA, api_key)
        all_codings.extend(result["codings"])

    codings_df = pd.DataFrame(all_codings)
    merged = sub[["response_id", "sex", "disability", "country", "insurance_type", question]].merge(
        codings_df, on="response_id", how="left"
    )
    return merged


def build_quote_bank(coded: pd.DataFrame, question: str, codebook: dict, top_n: int = 5) -> dict:
    bank = {}
    for t in codebook["themes"]:
        code = t["code"]
        has_theme = coded[coded["themes"].apply(lambda ths: isinstance(ths, list) and code in ths)]
        worthy = has_theme[has_theme["quote_worthy"] == True]  # noqa: E712
        picks = []
        seen_countries = set()
        for row in worthy.itertuples():
            if row.country not in seen_countries or len(picks) < top_n // 2:
                picks.append({
                    "response_id": row.response_id, "sex": row.sex, "country": row.country,
                    "quote": getattr(row, question),
                })
                seen_countries.add(row.country)
            if len(picks) >= top_n:
                break
        bank[code] = picks
    return {question: bank}


def run_coding(question: str, api_key: str, work_dir: Path | None = None) -> pd.DataFrame:
    work_dir = work_dir or config.WORK_DIR
    df = pd.read_parquet(work_dir / "response_frame.parquet")
    codebook = load_approved_codebook(question, work_dir)
    coded = code_responses(df, question, codebook, api_key)

    out_dir = work_dir / "theme_tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    coded.to_csv(out_dir / f"{question}.csv", index=False)
    print(f"Wrote {out_dir / f'{question}.csv'} ({len(coded)} coded responses)")

    quote_bank_path = work_dir / "quote_bank.json"
    existing = json.loads(quote_bank_path.read_text(encoding="utf-8")) if quote_bank_path.exists() else {}
    existing.update(build_quote_bank(coded, question, codebook))
    quote_bank_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Updated {quote_bank_path}")
    return coded


if __name__ == "__main__":
    import sys
    _api_key = llm_client.prompt_for_api_key()
    if len(sys.argv) > 1 and sys.argv[1] == "code":
        if len(sys.argv) > 2:
            run_coding(sys.argv[2], _api_key)
        else:
            for q in config.DEFAULT_ROLE_MAP.qual_primary:
                print(f"\n### Coding {q} ###")
                run_coding(q, _api_key)
    else:
        run_induction(_api_key)
