"""CC-098: draft codebooks for the four non-NPS theme passes, for human review.

Drafts from every CSV given, combined (pass both waves so a theme that only appears in 2026
still gets a code). Writes codebooks/<question>_draft.json and a 40-answer review sample per
question; approve with --approve, as for the NPS codebooks (draft_nps_codebooks.py).

Usage (from core_credit/agent/analysis):
    python -m qualitative_agent.draft_theme_codebooks <csv> [<csv> ...]
    python -m qualitative_agent.draft_theme_codebooks --approve [question ...]
"""

from __future__ import annotations

import sys

import pandas as pd

from driver.build_child_wellbeing import OTHER_IMPROVEMENTS_COL, OTHER_IMPROVEMENTS_TASK  # also loads .env
from driver.build_resilience import OTHER_COPING_COL, OTHER_COPING_TASK
from qualitative_agent.agent import PROTECTION_SIGNALS_TASK, QUALITY_OF_LIFE_DRIVERS_TASK
from qualitative_agent.codebook import CODEBOOK_DIR, approve_draft, draft_codebook
from qualitative_agent.data_prep import QUALITY_OF_LIFE_DRIVER_COLS, load_free_text_responses_multi
from section_configs.sections.client_protection import PROTECTION_SIGNAL_SOURCE_COLS

QUESTIONS = {
    "quality_of_life_drivers": (tuple(QUALITY_OF_LIFE_DRIVER_COLS), QUALITY_OF_LIFE_DRIVERS_TASK),
    "protection_signals": (tuple(PROTECTION_SIGNAL_SOURCE_COLS), PROTECTION_SIGNALS_TASK),
    "other_coping": ((OTHER_COPING_COL,), OTHER_COPING_TASK),
    "other_child_improvements": ((OTHER_IMPROVEMENTS_COL,), OTHER_IMPROVEMENTS_TASK),
}


def main(csv_paths: list) -> None:
    df = pd.concat([pd.read_csv(p, dtype=str, keep_default_na=False).replace("", pd.NA) for p in csv_paths], ignore_index=True)
    for question, (cols, task) in QUESTIONS.items():
        responses = load_free_text_responses_multi(df, cols)
        print(f"{question}: drafting from {len(responses)} answers...")
        codebook = draft_codebook(question, responses, task)
        print(f"{question}: {len(codebook['themes'])} codes")
        sample = pd.DataFrame(
            [{"question": r.source_field.rsplit("/", 1)[-1].replace("_resp_en", ""), "country": r.country, "answer": r.text} for r in responses]
        )
        sample.sample(n=min(40, len(sample)), random_state=98).to_csv(
            CODEBOOK_DIR / f"{question}_review_sample.csv", index=False, encoding="utf-8-sig"
        )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == "--approve":
        for q in sys.argv[2:] or list(QUESTIONS):
            a = approve_draft(q)
            print(f"{q}: approved, version {a['version']}, {len(a['themes'])} codes")
    else:
        main(sys.argv[1:])
