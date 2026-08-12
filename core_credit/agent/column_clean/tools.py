"""
LangChain tools for Column Cleaner.

Two tools, both deterministic under the hood -- no LLM calls happen inside
either one. The LLM's job is to read the compact report profile_survey_csv
returns and decide what (if anything) to override before calling
save_trimmed_csv.

build_tools(config, project_root) returns the two bound tool objects; the
factory pattern keeps config/project_root out of the tool schemas the LLM
sees (it should never need to pass those itself).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from rules import ColumnRecord, classify_column, detect_delimiter


class ReviewDecision(BaseModel):
    index: int = Field(
        description="Column index from the NEEDS REVIEW list in profile_survey_csv's output"
    )
    action: str = Field(description="'keep' or 'drop'")
    note: str = Field(default="", description="short reason for this decision")


class ProfileResult:
    def __init__(self, file_path: str, delimiter: str, total_rows: int, columns: list):
        self.file_path = file_path
        self.delimiter = delimiter
        self.total_rows = total_rows
        self.columns = columns
        self.sections = sorted({c.section for c in columns if c.section})


def _profile_file(file_path: str, config: dict) -> ProfileResult:
    with open(file_path, "r", encoding="utf-8-sig", errors="replace") as f:
        first_line = f.readline()
    delimiter = detect_delimiter(first_line)

    header = pd.read_csv(file_path, sep=delimiter, nrows=0, encoding="utf-8-sig").columns.tolist()
    chunk_size = config.get("chunk_size", 5000)
    cardinality_cap = config.get("cardinality_cap", 20)
    sample_n = config.get("sample_values_per_column", 3)

    null_counts = {c: 0 for c in header}
    uniq_sets: dict[str, set] = {c: set() for c in header}
    total_rows = 0

    for chunk in pd.read_csv(
        file_path, sep=delimiter, dtype=str, chunksize=chunk_size,
        low_memory=False, encoding="utf-8-sig",
    ):
        total_rows += len(chunk)
        for c in header:
            col = chunk[c]
            null_counts[c] += int(col.isna().sum())
            s = uniq_sets[c]
            if len(s) < cardinality_cap:
                for v in col.dropna().unique():
                    if len(s) >= cardinality_cap:
                        break
                    s.add(v)

    columns: List[ColumnRecord] = []
    for idx, c in enumerate(header):
        null_pct = 100.0 * null_counts[c] / total_rows if total_rows else 100.0
        uniq = uniq_sets[c]
        cardinality = len(uniq)
        capped = cardinality >= cardinality_cap
        samples = list(uniq)[:sample_n]
        action, reason, confidence = classify_column(c, null_pct, config)
        section = c.split("/", 1)[0] if "/" in c else None
        columns.append(
            ColumnRecord(
                index=idx, name=c, section=section, suffix=None,
                null_pct=round(null_pct, 1), cardinality=cardinality,
                cardinality_capped=capped, samples=samples,
                action=action, reason=reason, confidence=confidence,
            )
        )
    return ProfileResult(file_path=file_path, delimiter=delimiter, total_rows=total_rows, columns=columns)


def build_tools(config: dict, project_root: Path):
    """Return [profile_survey_csv, save_trimmed_csv] bound to this config/root."""

    cache: dict[str, tuple] = {}

    def _get_profile(file_path: str) -> ProfileResult:
        path = Path(file_path)
        mtime, size = path.stat().st_mtime, path.stat().st_size
        cached = cache.get(str(path))
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2]
        profile = _profile_file(str(path), config)
        cache[str(path)] = (mtime, size, profile)
        return profile

    @tool
    def profile_survey_csv(file_path: str) -> str:
        """Profile a survey CSV export and propose a keep/drop classification
        for every column using deterministic naming-convention rules
        (KoboToolbox/ODK export shape: Section/CODE_suffix per question).
        Call this first, before save_trimmed_csv, for any file you haven't
        already profiled in this conversation."""
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: file not found: {file_path}"

        profile = _get_profile(str(path))
        kept = [c for c in profile.columns if c.action == "keep"]
        dropped = [c for c in profile.columns if c.action == "drop"]
        review = [c for c in kept if c.confidence == "review"]

        lines = [
            "=== SURVEY FILE PROFILE ===",
            f"File: {profile.file_path}",
            f"Delimiter detected: {profile.delimiter!r}",
            f"Total rows: {profile.total_rows}",
            f"Total columns: {len(profile.columns)}",
            f"Sections found ({len(profile.sections)}): {', '.join(profile.sections) or '(none detected)'}",
            "",
            "=== RULE-BASED CLASSIFICATION (this is the outcome if you make no overrides) ===",
            f"KEEP: {len(kept)}   DROP: {len(dropped)}   "
            f"(of which {len(review)} KEEP columns are unrecognized-pattern and flagged for your review)",
            "",
        ]

        if len(kept) < max(5, 0.05 * len(profile.columns)) or not profile.sections:
            lines.append(
                "*** ANOMALY WARNING: very few columns were kept, or no sections were "
                "detected. This usually means delimiter detection failed or the file "
                "doesn't follow the expected naming convention. Investigate before "
                "proceeding -- do not call save_trimmed_csv on a profile like this "
                "without flagging it clearly to the user. ***\n"
            )

        if review:
            lines.append(
                f"=== {len(review)} COLUMNS NEEDING REVIEW "
                "(unrecognized naming pattern; currently defaulted to KEEP) ==="
            )
            lines.append("index | column name | section | null% | distinct values | samples")
            for c in review:
                card = f"{c.cardinality}+" if c.cardinality_capped else str(c.cardinality)
                samples = "; ".join(str(s) for s in c.samples)
                lines.append(f"{c.index} | {c.name} | {c.section or '-'} | {c.null_pct}% | {card} | {samples}")
            lines.append("")
            lines.append(
                "For any of these you want to DROP instead of the default KEEP, call "
                "save_trimmed_csv with a review_decisions entry "
                '{"index": ..., "action": "drop", "note": "..."}. Anything you don\'t '
                "mention stays kept -- that's the safe default."
            )
        else:
            lines.append("No columns needed review -- every column matched a known naming pattern.")

        lines.append("")
        lines.append("Once you're satisfied, call save_trimmed_csv to write the trimmed file.")
        return "\n".join(lines)

    @tool
    def save_trimmed_csv(
        file_path: str,
        review_decisions: Optional[List[ReviewDecision]] = None,
        run_label: str = "",
    ) -> str:
        """Write the trimmed CSV (kept columns only) plus a JSON audit
        manifest, applying any overrides from review_decisions to the rule
        engine's default classification. profile_survey_csv must have been
        called on this file earlier in the conversation. run_label is an
        optional short tag (e.g. "2026Q3") used in the output filenames;
        defaults to the input file's name."""
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: file not found: {file_path}"

        profile = _get_profile(str(path))
        by_index = {c.index: c for c in profile.columns}
        review_indices = {c.index for c in profile.columns if c.confidence == "review"}

        applied, ignored = [], []
        for dec in review_decisions or []:
            if dec.index not in review_indices:
                ignored.append({"index": dec.index, "why": "not a reviewable column"})
                continue
            action = dec.action.strip().lower()
            if action not in ("keep", "drop"):
                ignored.append({"index": dec.index, "why": f"invalid action {dec.action!r}"})
                continue
            record = by_index[dec.index]
            record.action = action
            record.reason = dec.note or f"agent override: {action}"
            record.confidence = "review-decided"
            applied.append({"index": dec.index, "name": record.name, "action": action, "note": dec.note})

        keep_columns = [c.name for c in profile.columns if c.action == "keep"]
        drop_columns = [c.name for c in profile.columns if c.action == "drop"]
        sections_in_output = sorted({c.split("/", 1)[0] for c in keep_columns if "/" in c})

        output_dir = project_root / config.get("output_dir", "processed_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", (run_label.strip() or path.stem))
        out_csv = output_dir / f"{stem}_{timestamp}_trimmed.csv"
        out_manifest = output_dir / f"{stem}_{timestamp}_manifest.json"

        chunk_size = config.get("chunk_size", 5000)
        first = True
        for chunk in pd.read_csv(
            str(path), sep=profile.delimiter, dtype=str, usecols=keep_columns,
            chunksize=chunk_size, low_memory=False, encoding="utf-8-sig",
        ):
            chunk = chunk[keep_columns]  # preserve original column order
            chunk.to_csv(out_csv, mode="w" if first else "a", header=first, index=False)
            first = False

        manifest = {
            "source_file": str(path),
            "output_file": str(out_csv),
            "generated_at": datetime.now().isoformat(),
            "delimiter_detected": profile.delimiter,
            "total_rows": profile.total_rows,
            "total_columns_original": len(profile.columns),
            "total_columns_kept": len(keep_columns),
            "total_columns_dropped": len(drop_columns),
            "excluded_sections": config.get("excluded_sections", []),
            "sections_in_output": sections_in_output,
            "review_overrides_applied": applied,
            "review_overrides_ignored": ignored,
            "kept_columns": keep_columns,
            "dropped_columns": drop_columns,
        }
        out_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        size_before = path.stat().st_size
        size_after = out_csv.stat().st_size
        pct = 100 * (1 - size_after / size_before) if size_before else 0.0

        return (
            f"Wrote trimmed CSV: {out_csv}\n"
            f"Wrote manifest: {out_manifest}\n"
            f"Rows: {profile.total_rows}\n"
            f"Columns: {len(profile.columns)} -> {len(keep_columns)} kept / {len(drop_columns)} dropped\n"
            f"File size: {size_before:,} bytes -> {size_after:,} bytes ({pct:.1f}% reduction)\n"
            f"Sections included in output (copy this list verbatim into your summary -- "
            f"it is the authoritative answer, not the 'Sections found' line from "
            f"profile_survey_csv, which lists sections in the raw file before trimming): "
            f"{', '.join(sections_in_output)}\n"
            f"Review overrides applied: {applied or 'none'}\n"
            f"Review overrides ignored: {ignored or 'none'}"
        )

    return [profile_survey_csv, save_trimmed_csv]
