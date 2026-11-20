"""CC-089: write draft codebooks for the three NPS follow-up questions, for human review.

Run once per data base (Test6's 2025 wave for the first set). It open-codes each band, then
turns the themes into codebooks/<name>_draft.json. Review a draft and edit it, then approve it
(--approve below); from then on every run codes against the approved file.

Also writes codebooks/nps_detractor_review_sample.csv: 50 detractor answers in a fixed random
order, for checking the detractor codebook against real answers.

Usage (from core_credit/agent/analysis):
    python -m qualitative_agent.draft_nps_codebooks <analysis_ready.csv> [band ...]
    python -m qualitative_agent.draft_nps_codebooks --approve [band ...]
    band: promoter, passive, detractor (default: all three)
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

from driver.build_client_satisfaction import (  # also loads .env
    DETRACTOR_CODEBOOK,
    DETRACTOR_FOLLOWUP_COL,
    DETRACTOR_TASK,
    PASSIVE_CODEBOOK,
    PASSIVE_FOLLOWUP_COL,
    PASSIVE_TASK,
    PROMOTER_CODEBOOK,
    PROMOTER_FOLLOWUP_COL,
    PROMOTER_TASK,
)
from qualitative_agent.codebook import CODEBOOK_DIR, approve_draft, draft_codebook
from qualitative_agent.data_prep import load_free_text_responses

BANDS = {
    "promoter": (PROMOTER_CODEBOOK, PROMOTER_FOLLOWUP_COL, PROMOTER_TASK),
    "passive": (PASSIVE_CODEBOOK, PASSIVE_FOLLOWUP_COL, PASSIVE_TASK),
    "detractor": (DETRACTOR_CODEBOOK, DETRACTOR_FOLLOWUP_COL, DETRACTOR_TASK),
}


def main(csv_path: str, bands: list) -> None:
    df = pd.read_csv(csv_path, low_memory=False)
    for band in bands:
        name, col, task = BANDS[band]
        responses = load_free_text_responses(df, col)
        print(f"{band}: drafting from {len(responses)} answers...")
        codebook = draft_codebook(name, responses, task)
        print(f"{band}: {len(codebook['themes'])} codes -> {CODEBOOK_DIR / (name + '_draft.json')}")
        if band == "detractor":
            sample = pd.DataFrame([{"country": r.country, "answer": r.text, "your_codes": ""} for r in responses])
            sample = sample.sample(n=min(50, len(sample)), random_state=89)
            out = CODEBOOK_DIR / "nps_detractor_review_sample.csv"
            sample.to_csv(out, index=False, encoding="utf-8-sig")
            print(f"detractor: review sample -> {out}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--approve":
        for band in sys.argv[2:] or list(BANDS):
            approved = approve_draft(BANDS[band][0])
            print(f"{band}: approved, version {approved['version']}, {len(approved['themes'])} codes")
    else:
        main(sys.argv[1], sys.argv[2:] or list(BANDS))
