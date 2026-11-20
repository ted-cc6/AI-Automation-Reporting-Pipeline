"""CC-094: compute year-over-year changes for a prepared wave pair.

Usage (from core_credit/agent/analysis):
    python -m yoy.run_deltas <path to <run>_wave_manifest.json>

Writes <run>_yoy_deltas.json next to the manifest and prints the significant portfolio changes.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

from yoy.deltas import compute_deltas
from yoy.themes import compute_theme_deltas


def _load(path: str) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str, keep_default_na=False).replace("", pd.NA)


def main(manifest_path: str) -> Path:
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    by_year = {w["year"]: w["analysis_ready_csv"] for w in manifest["waves"]}
    earlier, latest = manifest["comparison_wave"], manifest["report_wave"]
    df_a, df_b = _load(by_year[earlier]), _load(by_year[latest])
    result = compute_deltas(df_a, df_b, manifest["comparison_countries"])
    # CC-099: codes any answer not yet in the codebook cache (LLM), then compares theme shares
    result["themes"] = compute_theme_deltas(df_a, df_b, manifest["comparison_countries"])
    result.update(
        waves={"comparison": earlier, "report": latest},
        partial_countries=manifest["partial_countries"],
        provisional=manifest["provisional"],
        source_manifest=str(Path(manifest_path).resolve()),
    )
    out = Path(manifest_path).with_name(Path(manifest_path).name.replace("_wave_manifest.json", "_yoy_deltas.json"))
    out.write_text(json.dumps(result, indent=2, default=float), encoding="utf-8")

    print(f"Wrote {out}")
    for m in result["metrics"]:
        p = m["portfolio"]
        if p["significant"]:
            mix = " [country mix]" if p["mix_flag"] else ""
            print(f"  {m['label']}: {p['value_2025']:.1%} -> {p['value_2026']:.1%} ({p['change_pts']:+.1f} pts, p={p['p_value']:.3g}){mix}")
    review = result["swing_review"]
    print(f"  Swing screen: {len(review)} country figures moved more than {result['swing_screen_pts']:.0f} points (not narrated):")
    for r in review:
        unit = "" if r["metric_id"] == "nps_score" else " pts"
        print(f"    {r['country']} {r['label']}: {r['change_pts']:+.1f}{unit}")
    for q in result["themes"]:
        sig = [t for t in q["themes"] if t["significant"]]
        print(f"  Themes, {q['group']} (n {q['n_2025']} -> {q['n_2026']}): {len(sig)} significant" + ("" if not q["counts_only"] else " (counts only)"))
        for t in sig:
            print(f"    {t['label']}: {t['value_2025']:.1%} -> {t['value_2026']:.1%} ({t['change_pts']:+.1f} pts)")
    n = result["nps_score"]["portfolio"]
    print(f"  NPS: {n['value_2025']:.1f} -> {n['value_2026']:.1f} ({n['change_pts']:+.1f}, p={n['p_value']:.3g})")
    return out


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
