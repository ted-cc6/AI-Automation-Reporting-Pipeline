"""
LangChain tools for Row Checker.

Two tools, both deterministic under the hood -- same principle as Column
Cleaner. scan_for_issues never modifies anything; save_clean_data writes the
analysis-ready CSV (exact duplicates removed) and a separate QA report JSON
(duplicate client ids + keyword matches, flagged only, never resolved).
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
from langchain_core.tools import tool

from checks import find_duplicate_client_ids, find_exact_duplicates, find_keyword_matches


class ScanResult:
    def __init__(self, df, exact_dup_mask, dup_first_uuid_map, dup_client_groups, keyword_hits):
        self.df = df
        self.exact_dup_mask = exact_dup_mask
        self.dup_first_uuid_map = dup_first_uuid_map  # {removed_uuid: kept_uuid}
        self.dup_client_groups = dup_client_groups
        self.keyword_hits = keyword_hits


def _scan_file(file_path: str, config: dict) -> ScanResult:
    df = pd.read_csv(file_path, dtype=str, encoding="utf-8-sig")

    ids = config["identity_columns"]
    uuid_col = ids["row_uuid"]
    client_col = ids["client_id"]

    exclude_cols = config.get("exclude_from_duplicate_check", [])
    exact_dup_mask, dup_first_uuid_map = find_exact_duplicates(df, exclude_cols, uuid_col)

    dup_client_groups = find_duplicate_client_ids(df, client_col, uuid_col)

    keyword_cols = config.get("keyword_check_columns", [])
    keywords = config.get("test_keywords", [])
    keyword_hits = find_keyword_matches(df, keyword_cols, keywords, uuid_col)

    return ScanResult(df, exact_dup_mask, dup_first_uuid_map, dup_client_groups, keyword_hits)


def build_tools(config: dict, project_root: Path):
    """Return [scan_for_issues, save_clean_data] bound to this config/root."""

    cache: dict[str, tuple] = {}

    def _get_scan(file_path: str) -> ScanResult:
        path = Path(file_path)
        mtime, size = path.stat().st_mtime, path.stat().st_size
        cached = cache.get(str(path))
        if cached and cached[0] == mtime and cached[1] == size:
            return cached[2]
        result = _scan_file(str(path), config)
        cache[str(path)] = (mtime, size, result)
        return result

    @tool
    def scan_for_issues(file_path: str) -> str:
        """Scan a Column-Cleaner-trimmed survey CSV for exact duplicate rows,
        duplicate Global unique client ids, and test-keyword matches in
        identity fields (Client ID, Branch, submitting user). Call this
        first, before save_clean_data."""
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: file not found: {file_path}"

        scan = _get_scan(str(path))
        total_rows = len(scan.df)
        n_exact_dup = int(scan.exact_dup_mask.sum())
        n_client_groups = len(scan.dup_client_groups)
        n_client_rows = sum(g["row_count"] for g in scan.dup_client_groups)
        n_keyword_hits = len(scan.keyword_hits)

        lines = [
            "=== ROW-LEVEL QA SCAN ===",
            f"File: {path}",
            f"Total rows: {total_rows}",
            "",
            f"Exact duplicate rows (auto-removed on save, keeping first occurrence): {n_exact_dup}",
            f"Duplicate Global unique client id groups (flagged for review, not resolved): "
            f"{n_client_groups} groups covering {n_client_rows} rows",
            f"Test-keyword matches (flagged for review, not resolved): {n_keyword_hits}",
            "",
        ]

        if total_rows and (
            n_exact_dup / total_rows > 0.10 or n_keyword_hits > 0.10 * total_rows
        ):
            lines.append(
                "*** ANOMALY WARNING: an unusually large share of rows are flagged. "
                "This is more likely a wrong file, a wrong column mapping, or a config "
                "problem than genuine data quality -- investigate and explain this to "
                "the user instead of calling save_clean_data. ***\n"
            )

        if scan.exact_dup_mask.any():
            lines.append("--- Sample exact duplicates (duplicate uuid -> kept original uuid) ---")
            for dup_uuid, orig_uuid in list(scan.dup_first_uuid_map.items())[:5]:
                lines.append(f"  {dup_uuid} -> {orig_uuid}")
            lines.append("")

        if scan.dup_client_groups:
            lines.append("--- Duplicate Global unique client id groups ---")
            for g in scan.dup_client_groups[:10]:
                lines.append(f"  client_id={g['client_id']} | rows={g['row_count']} | uuids={g['uuids']}")
            if len(scan.dup_client_groups) > 10:
                lines.append(
                    f"  ... and {len(scan.dup_client_groups) - 10} more groups "
                    "(full detail in the saved QA report)"
                )
            lines.append("")

        if scan.keyword_hits:
            lines.append("--- Test-keyword matches ---")
            for h in scan.keyword_hits[:10]:
                lines.append(
                    f"  uuid={h['uuid']} | column={h['column']} | "
                    f"value={h['value']!r} | matched={h['matched_keyword']!r}"
                )
            if len(scan.keyword_hits) > 10:
                lines.append(
                    f"  ... and {len(scan.keyword_hits) - 10} more (full detail in the saved QA report)"
                )

        lines.append("")
        lines.append(
            "Once you've reviewed this, call save_clean_data to write the "
            "analysis-ready CSV and the QA report."
        )
        return "\n".join(lines)

    @tool
    def save_clean_data(file_path: str, run_label: str = "") -> str:
        """Write the analysis-ready CSV (exact duplicate rows removed, every
        other row and column left exactly as in the input) plus a separate
        QA report JSON (duplicate client id groups and keyword-match hits,
        for human review -- never merged into the analysis-ready file).
        scan_for_issues must have been called on this file first. run_label
        is an optional short tag (e.g. "2026Q2") for the output filenames;
        defaults to the input file's name."""
        path = Path(file_path)
        if not path.exists():
            return f"ERROR: file not found: {file_path}"

        scan = _get_scan(str(path))
        clean_df = scan.df.loc[~scan.exact_dup_mask].reset_index(drop=True)

        output_dir = project_root / config.get("output_dir", "processed_data")
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", (run_label.strip() or path.stem))
        out_csv = output_dir / f"{stem}_{timestamp}_analysis_ready.csv"
        out_report = output_dir / f"{stem}_{timestamp}_qa_report.json"

        clean_df.to_csv(out_csv, index=False)

        report = {
            "source_file": str(path),
            "output_file": str(out_csv),
            "generated_at": datetime.now().isoformat(),
            "rows_in": len(scan.df),
            "rows_out": len(clean_df),
            "exact_duplicates_removed": [
                {"removed_uuid": dup_uuid, "kept_uuid": orig_uuid}
                for dup_uuid, orig_uuid in scan.dup_first_uuid_map.items()
            ],
            "duplicate_client_id_groups": scan.dup_client_groups,
            "test_keyword_matches": scan.keyword_hits,
        }
        out_report.write_text(json.dumps(report, indent=2), encoding="utf-8")

        return (
            f"Wrote analysis-ready CSV: {out_csv}\n"
            f"Wrote QA report: {out_report}\n"
            f"Rows: {len(scan.df)} -> {len(clean_df)} "
            f"({len(scan.dup_first_uuid_map)} exact duplicates removed)\n"
            f"Duplicate client id groups flagged for review: {len(scan.dup_client_groups)}\n"
            f"Test-keyword matches flagged for review: {len(scan.keyword_hits)}"
        )

    return [scan_for_issues, save_clean_data]
