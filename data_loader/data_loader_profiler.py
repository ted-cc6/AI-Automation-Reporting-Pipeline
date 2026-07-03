"""
data_loader_profiler.py — VisionFund Insurance Survey Data Loader
Step 1 of 4: Profile the raw CSV and produce profile_report.md.

Usage:
    python data_loader/data_loader_profiler.py --csv path/to/export.csv --output-dir runs/2026_Q3
"""

import sys
import argparse
import warnings
from pathlib import Path

import pandas as pd

# ---------------------------------------------------------------------------
# Paths (static reference files live alongside this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MAPPING = SCRIPT_DIR / "column_mapping.csv"

WARN_VERY_LOW = 50.0
WARN_LOW = 80.0
SKIP_CATEGORIES = {"drop_scaffold", "drop_system"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_survey(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(
        csv_path,
        delimiter=";",
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def load_mapping(mapping_path: Path) -> pd.DataFrame:
    mapping = pd.read_csv(mapping_path, dtype=str, keep_default_na=False)
    mapping["raw_index"] = mapping["raw_index"].astype(int)
    return mapping


def fill_rate(series: pd.Series) -> float:
    total = len(series)
    if total == 0:
        return 0.0
    filled = series.apply(lambda v: v is not None and str(v).strip() != "").sum()
    return round(filled / total * 100, 2)


def top_n_values(series: pd.Series, n: int = 5) -> list[tuple]:
    non_empty = series[series.apply(lambda v: str(v).strip() != "")]
    counts = non_empty.value_counts(dropna=True).head(n)
    return [(str(val), int(cnt)) for val, cnt in counts.items()]


def warn_level(fr: float) -> str:
    if fr < WARN_VERY_LOW:
        return "WARN_VERY_LOW_FILL"
    if fr < WARN_LOW:
        return "WARN_LOW_FILL"
    return ""


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(csv_path: Path, mapping_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "profile_report.md"

    print(f"Loading survey CSV: {csv_path}")
    df = load_survey(csv_path)
    actual_cols = list(df.columns)
    n_rows = len(df)
    print(f"  Rows: {n_rows}  |  Columns detected: {len(actual_cols)}")

    print(f"Loading column mapping: {mapping_path}")
    mapping = load_mapping(mapping_path)

    results = []
    skipped_scaffold = []
    header_mismatches = []

    for _, row in mapping.iterrows():
        idx = int(row["raw_index"])
        category = row.get("category", "").strip()
        question_ref = row.get("question_ref", "").strip()
        parent_ref = row.get("parent_ref", "").strip()
        mapped_header = row.get("raw_column_header", "").strip()

        if category in SKIP_CATEGORIES:
            skipped_scaffold.append((idx, category, mapped_header[:60]))
            continue

        if idx >= len(actual_cols):
            warnings.warn(f"Index {idx} out of range (CSV has {len(actual_cols)} columns). Skipping.")
            continue

        actual_header = actual_cols[idx]

        mapped_norm = " ".join(mapped_header.replace("...", "").split())
        actual_norm = " ".join(actual_header.split())
        if not (actual_norm.startswith(mapped_norm[:40]) or mapped_norm[:40] in actual_norm):
            header_mismatches.append((idx, mapped_header[:60], actual_header[:60]))

        series = df.iloc[:, idx]
        fr = fill_rate(series)
        dc = series.apply(lambda v: str(v).strip()).replace("", pd.NA).dropna().nunique()
        top5 = top_n_values(series)
        wl = warn_level(fr)

        results.append({
            "raw_index": idx,
            "question_ref": question_ref,
            "parent_ref": parent_ref,
            "category": category,
            "mapped_header": mapped_header,
            "actual_header": actual_header,
            "fill_rate": fr,
            "distinct_count": dc,
            "top5": top5,
            "warning": wl,
        })

    # Build report
    lines = []
    lines.append("# Profile Report — VisionFund Insurance Survey\n")
    lines.append(f"**Source CSV:** `{csv_path.name}`  ")
    lines.append(f"**Rows:** {n_rows}  |  **Columns mapped:** {len(mapping)}  |  **Columns profiled:** {len(results)}\n")

    warnings_list = [r for r in results if r["warning"]]
    lines.append("---\n")
    lines.append("## Warnings\n")
    if warnings_list:
        lines.append("| raw_index | question_ref | category | fill_rate | warning |")
        lines.append("|-----------|-------------|----------|-----------|---------|")
        for r in warnings_list:
            lines.append(
                f"| {r['raw_index']} | {r['question_ref'] or '—'} | {r['category']} "
                f"| {r['fill_rate']:.1f}% | **{r['warning']}** |"
            )
    else:
        lines.append("_No fill-rate warnings._")

    if header_mismatches:
        lines.append("\n### Header Mismatches\n")
        lines.append("| raw_index | mapped_header (truncated) | actual_csv_header (truncated) |")
        lines.append("|-----------|--------------------------|-------------------------------|")
        for idx, mh, ah in header_mismatches:
            lines.append(f"| {idx} | {mh} | {ah} |")

    lines.append("\n---\n")
    lines.append("## Summary Table\n")
    lines.append("| raw_index | question_ref | category | fill_rate | distinct_count | warning |")
    lines.append("|-----------|-------------|----------|-----------|----------------|---------|")
    for r in results:
        qr = r["question_ref"] or "—"
        wl = r["warning"] or ""
        lines.append(
            f"| {r['raw_index']} | {qr} | {r['category']} "
            f"| {r['fill_rate']:.1f}% | {r['distinct_count']} | {wl} |"
        )

    lines.append("\n---\n")
    lines.append("## Per-Column Detail\n")
    for r in results:
        qr = r["question_ref"] or f"col_{r['raw_index']}"
        lines.append(f"### [{r['raw_index']}] {qr}  —  `{r['category']}`")
        if r["parent_ref"]:
            lines.append(f"**parent_ref:** `{r['parent_ref']}`  ")
        lines.append(f"**Header:** {r['actual_header'][:120]}  ")
        lines.append(f"**Fill rate:** {r['fill_rate']:.1f}%  |  **Distinct values:** {r['distinct_count']}")
        if r["warning"]:
            lines.append(f"**Warning:** `{r['warning']}`")
        if r["top5"]:
            lines.append("\n**Top 5 values:**\n")
            lines.append("| Value | Count |")
            lines.append("|-------|-------|")
            for val, cnt in r["top5"]:
                safe_val = val.replace("|", "\\|").replace("\n", " ").replace("\r", "")
                if len(safe_val) > 100:
                    safe_val = safe_val[:97] + "..."
                lines.append(f"| {safe_val} | {cnt} |")
        else:
            lines.append("_No non-empty values._")
        lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Profile report written: {report_path}")
    print(
        f"Done. {len(results)} columns profiled, "
        f"{len(warnings_list)} fill-rate warnings, "
        f"{len(header_mismatches)} header mismatches."
    )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionFund Survey Profiler")
    parser.add_argument("--csv", type=Path, required=True, help="Path to the KoBoToolbox CSV export")
    parser.add_argument("--mapping", type=Path, default=DEFAULT_MAPPING, help="Path to column_mapping.csv")
    parser.add_argument("--output-dir", type=Path, required=True, help="Directory to write profile_report.md")
    args = parser.parse_args()

    for p, label in [(args.csv, "Survey CSV"), (args.mapping, "Column mapping")]:
        if not p.exists():
            print(f"ERROR: {label} not found: {p}", file=sys.stderr)
            sys.exit(1)

    main(args.csv, args.mapping, args.output_dir)
