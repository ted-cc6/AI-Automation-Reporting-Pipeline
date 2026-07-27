"""
Stage 2 -- quantitative engine.

For every closed-ended indicator (single-response and multi-select), computes
n/% by group (sex, disability, country, insurance type), a two-proportion
z-test per category level, a min-n suppression gate, and a single
Benjamini-Hochberg FDR correction pass across every p-value produced in the
run (so volume of comparisons doesn't inflate false "significant" findings).

Also computes NPS (%Promoter - %Detractor) by group.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.proportion import proportions_ztest

from gedsi_pipeline import config
from gedsi_pipeline.mapping import RoleMap

# Indicators handled specially, not via the generic categorical loop.
NUMERIC_INDICATORS = {"nps_score"}


def _applicable_subset(df: pd.DataFrame, applies_to: str | None) -> pd.DataFrame:
    if applies_to is None:
        return df
    return df[df["insurance_type"] == applies_to]


def _binary_group_rows(df: pd.DataFrame, indicator: str, group_col: str,
                        g1: str, g2: str, applies_to: str | None) -> list[dict]:
    """One row per category level of `indicator`, comparing group g1 vs g2."""
    sub = _applicable_subset(df, applies_to)
    sub = sub[sub[group_col].isin([g1, g2])]
    sub = sub[sub[indicator].notna()]
    if sub.empty:
        return []

    n1_total = int((sub[group_col] == g1).sum())
    n2_total = int((sub[group_col] == g2).sum())
    rows = []
    for level in sorted(sub[indicator].dropna().unique()):
        s1 = sub[sub[group_col] == g1]
        s2 = sub[sub[group_col] == g2]
        c1 = int((s1[indicator] == level).sum())
        c2 = int((s2[indicator] == level).sum())
        n1, n2 = len(s1), len(s2)
        pct1 = 100 * c1 / n1 if n1 else None
        pct2 = 100 * c2 / n2 if n2 else None
        pt_diff = (pct1 - pct2) if (pct1 is not None and pct2 is not None) else None

        n_ok = n1 >= config.MIN_N and n2 >= config.MIN_N
        p_raw = None
        if n_ok and 0 < c1 + c2 < n1 + n2:  # avoid degenerate all-same/all-zero cases
            try:
                _, p_raw = proportions_ztest([c1, c2], [n1, n2])
            except Exception:
                p_raw = None

        rows.append({
            "indicator": indicator,
            "category": str(level),
            "applies_to": applies_to or "All",
            f"{g1}_n": n1, f"{g2}_n": n2,
            f"{g1}_count": c1, f"{g2}_count": c2,
            f"{g1}_pct": pct1, f"{g2}_pct": pct2,
            "pt_diff": pt_diff,
            "n_ok": n_ok,
            "p_raw": p_raw,
        })
    return rows


def _apply_fdr(rows: list[dict]) -> list[dict]:
    """One BH-FDR pass across every testable p-value in the batch."""
    idx_with_p = [i for i, r in enumerate(rows) if r.get("p_raw") is not None]
    if idx_with_p:
        pvals = [rows[i]["p_raw"] for i in idx_with_p]
        reject, p_adj, _, _ = multipletests(pvals, alpha=config.FDR_ALPHA, method="fdr_bh")
        for i, adj, sig in zip(idx_with_p, p_adj, reject):
            rows[i]["p_adj"] = adj
            rows[i]["significant"] = bool(sig)
    for r in rows:
        r.setdefault("p_adj", None)
        r.setdefault("significant", False)
    return rows


def gender_comparisons(df: pd.DataFrame, role_map: RoleMap | None = None) -> pd.DataFrame:
    role_map = role_map or config.DEFAULT_ROLE_MAP
    rows = []
    for indicator, (_idx, applies_to) in role_map.quant_indicators.items():
        if indicator in NUMERIC_INDICATORS:
            continue
        rows.extend(_binary_group_rows(df, indicator, "sex", "Female", "Male", applies_to))
    for group_name, (_parent, options) in role_map.multiselect_groups.items():
        for option_label in options:
            col = f"{group_name}__{option_label}"
            rows.extend(_binary_group_rows(df, col, "sex", "Female", "Male", None))
    rows = _apply_fdr(rows)
    return pd.DataFrame(rows)


def disability_comparisons(df: pd.DataFrame, role_map: RoleMap | None = None) -> pd.DataFrame:
    role_map = role_map or config.DEFAULT_ROLE_MAP
    d = df.copy()
    d = d[d["disability"].isin(["Yes", "No"])]  # exclude "Don't know" / null
    rows = []
    for indicator, (_idx, applies_to) in role_map.quant_indicators.items():
        if indicator in NUMERIC_INDICATORS:
            continue
        rows.extend(_binary_group_rows(d, indicator, "disability", "Yes", "No", applies_to))
    for group_name, (_parent, options) in role_map.multiselect_groups.items():
        for option_label in options:
            col = f"{group_name}__{option_label}"
            rows.extend(_binary_group_rows(d, col, "disability", "Yes", "No", None))
    rows = _apply_fdr(rows)
    df_out = pd.DataFrame(rows)
    if not df_out.empty:
        df_out = df_out.rename(columns={"Yes_n": "PWD_HH_n", "No_n": "Non_PWD_HH_n",
                                         "Yes_count": "PWD_HH_count", "No_count": "Non_PWD_HH_count",
                                         "Yes_pct": "PWD_HH_pct", "No_pct": "Non_PWD_HH_pct"})
    return df_out


def _nps_stats(sub: pd.DataFrame) -> dict:
    sub = sub[sub["nps_category"].notna()]
    n = len(sub)
    if n == 0:
        return {"n": 0, "promoter_pct": None, "passive_pct": None, "detractor_pct": None, "nps": None}
    promoter_pct = 100 * (sub["nps_category"] == "Promoter").sum() / n
    passive_pct = 100 * (sub["nps_category"] == "Passive").sum() / n
    detractor_pct = 100 * (sub["nps_category"] == "Detractor").sum() / n
    return {
        "n": n,
        "promoter_pct": promoter_pct,
        "passive_pct": passive_pct,
        "detractor_pct": detractor_pct,
        "nps": promoter_pct - detractor_pct,
    }


def nps_by_group(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    rows.append({"cut": "Overall", "group": "All", **_nps_stats(df)})
    for sex in df["sex"].dropna().unique():
        rows.append({"cut": "Sex", "group": sex, **_nps_stats(df[df["sex"] == sex])})
    for dis in ["Yes", "No"]:
        rows.append({"cut": "Disability (HH)", "group": dis, **_nps_stats(df[df["disability"] == dis])})
    for country in df["country"].dropna().unique():
        rows.append({"cut": "Country", "group": country, **_nps_stats(df[df["country"] == country])})
    for itype in df["insurance_type"].dropna().unique():
        rows.append({"cut": "Insurance Type", "group": itype, **_nps_stats(df[df["insurance_type"] == itype])})
    out = pd.DataFrame(rows)
    out["n_ok"] = out["n"] >= config.MIN_N
    return out


def demographic_table(df: pd.DataFrame) -> pd.DataFrame:
    """Front-of-report demographic table: n / % by sex, cut by insurance type & country."""
    rows = []
    total_f = int((df["sex"] == "Female").sum())
    total_m = int((df["sex"] == "Male").sum())
    for cut_name, col in [("Insurance Type", "insurance_type"), ("Country", "country")]:
        for val in df[col].dropna().unique():
            sub = df[df[col] == val]
            f_n = int((sub["sex"] == "Female").sum())
            m_n = int((sub["sex"] == "Male").sum())
            f_pct = 100 * f_n / total_f if total_f else None
            m_pct = 100 * m_n / total_m if total_m else None
            rows.append({
                "cut": cut_name, "value": val,
                "Female_n": f_n, "Male_n": m_n,
                "Female_pct_of_all_female": f_pct, "Male_pct_of_all_male": m_pct,
                "pt_diff": (f_pct - m_pct) if (f_pct is not None and m_pct is not None) else None,
            })
    return pd.DataFrame(rows)


def build_quant_tables(df: pd.DataFrame, role_map: RoleMap | None = None) -> dict[str, pd.DataFrame]:
    return {
        "demographic_table": demographic_table(df),
        "gender_comparisons": gender_comparisons(df, role_map),
        "disability_comparisons": disability_comparisons(df, role_map),
        "nps_by_group": nps_by_group(df),
    }


def main(role_map: RoleMap | None = None, work_dir: Path | None = None):
    work_dir = work_dir or config.WORK_DIR
    df = pd.read_parquet(work_dir / "response_frame.parquet")
    tables = build_quant_tables(df, role_map)
    out_dir = work_dir / "quant_tables"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        path = out_dir / f"{name}.csv"
        table.to_csv(path, index=False)
        print(f"Wrote {path} ({len(table)} rows)")

    # Spot checks against numbers already known from raw inspection
    demo = tables["demographic_table"]
    print("\n--- Spot check: demographic_table (Insurance Type cut) ---")
    print(demo[demo["cut"] == "Insurance Type"])

    nps = tables["nps_by_group"]
    print("\n--- Spot check: NPS by Sex ---")
    print(nps[nps["cut"] == "Sex"])

    gc = tables["gender_comparisons"]
    sig = gc[gc["significant"]]
    print(f"\n{len(gc)} gender-comparison rows computed; {len(sig)} significant after BH-FDR "
          f"(alpha={config.FDR_ALPHA}).")


if __name__ == "__main__":
    main()
