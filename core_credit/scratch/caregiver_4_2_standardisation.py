"""STANDALONE, READ-ONLY. Not wired into the pipeline (CC-nnn diagnostic).

Question from the 4.2 review: is the caregiver vs non-caregiver gap driven by country
composition rather than caregiver status? Caregivers concentrate in certain countries; the
groups are lopsided (~4,851 vs ~967).

For each of the eight 4.2 outcomes this computes:
  - raw gap  = caregiver share - non-caregiver share (reproduces the current 4.2 table)
  - standardised gap = direct standardisation: the size-weighted mean of the WITHIN-country
    caregiver gaps, weights = the FULL analysis-ready sample's country distribution
    (renormalised over the countries where both groups have >=1 answer for that outcome)
  - composition effect = raw gap - standardised gap  (the part of the raw gap that is country mix)
  - per-country contributions to the composition effect (exact additive decomposition)
  - a robustness pass that drops countries with a non-caregiver cell below n=30

Caregiver status here is the PIPELINE's definition (metrics_engine.segments.caregiver_mask,
from IMPACT04). The dashboard spec's PROFILE04b/c/d>0 definition is reported alongside for
group-size comparison only; the raw gap is anchored on the pipeline definition so it
reproduces the shipped table.

Run:  python scratch/caregiver_4_2_standardisation.py
"""
from __future__ import annotations

import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

CC = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(CC / "agent" / "analysis"))

import numpy as np
import pandas as pd

from driver.build_child_wellbeing import (
    AGENCY_CONFIG,
    BUSINESS_HOUSEHOLD_IMPACT_CONFIG,
    CAREGIVER_TABLE_LABELS,
    CLIENT_PROTECTION_CONFIG,
    SAVINGS_COL,
    SAVINGS_TOP_2,
    _metric_config,
    _nps_promoter_mask,
    _non_caregiver_mask,
    _top_box_mask_for,
)
from metrics_engine.engine import gap_comparison, top_box_mask
from metrics_engine.segments import caregiver_mask, clean_blank_strings
from metrics_engine.segments import country as country_series

N30 = 30


def load_df() -> pd.DataFrame:
    csv = next((CC / "processed_data").glob("*_analysis_ready.csv"))
    return pd.read_csv(csv, dtype=str, keep_default_na=False)


def outcome_masks(df: pd.DataFrame) -> list[pd.Series]:
    """Exactly the eight masks driver.build_child_wellbeing._caregiver_vs_other builds."""
    return [
        _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "quality_of_life_change"),
        _top_box_mask_for(df, CLIENT_PROTECTION_CONFIG, "financial_worry_decreased"),
        _top_box_mask_for(df, AGENCY_CONFIG, "community_respect_improved"),
        _top_box_mask_for(df, BUSINESS_HOUSEHOLD_IMPACT_CONFIG, "business_income_change"),
        _top_box_mask_for(df, AGENCY_CONFIG, "loan_purpose_achieved_fully"),
        _top_box_mask_for(df, AGENCY_CONFIG, "household_influence_improved"),
        top_box_mask(clean_blank_strings(df[SAVINGS_COL]), SAVINGS_TOP_2),
        _nps_promoter_mask(df),
    ]


def _bool(s: pd.Series) -> pd.Series:
    return s.apply(lambda v: v is True)


def per_country_rates(mask: pd.Series, grp: pd.Series, ctry: pd.Series) -> dict:
    """country -> (n_answered, positive_rate) among rows where grp is True and mask is not None."""
    answered = grp & mask.notna()
    out = {}
    for c in sorted(ctry[answered].dropna().unique()):
        sel = answered & (ctry == c)
        n = int(sel.sum())
        if n == 0:
            continue
        rate = float(mask[sel].apply(lambda v: 1.0 if v is True else 0.0).mean())
        out[c] = (n, rate)
    return out


def analyse():
    df = load_df()
    ctry = country_series(df)
    valid_ctry = ctry.notna() & (ctry.astype(str).str.strip() != "")
    total = int(valid_ctry.sum())
    full_w = {c: int((ctry == c).sum()) / total for c in sorted(ctry[valid_ctry].unique())}

    care_status = caregiver_mask(df)          # True / False / None  (IMPACT04)
    care = _bool(care_status)
    noncare = _bool(_non_caregiver_mask(care_status))

    # ---------------- distribution report ----------------
    print("=" * 108)
    print("CAREGIVER STATUS BY COUNTRY (pipeline definition -- metrics_engine.segments.caregiver_mask, IMPACT04)")
    print("=" * 108)
    rows = []
    for c in sorted(full_w):
        nc_care = int((care & (ctry == c)).sum())
        nc_non = int((noncare & (ctry == c)).sum())
        rows.append((c, nc_care, nc_non))
    tot_care = sum(r[1] for r in rows)
    tot_non = sum(r[2] for r in rows)
    print(f"{'country':>8} | {'caregivers':>10} {'share%':>7} | {'non-careg':>10} {'share%':>7} | "
          f"{'full-sample%':>12} | flag")
    for c, nca, nno in rows:
        w_care = nca / tot_care
        w_non = nno / tot_non if tot_non else 0.0
        flag = "  <-- non-caregiver cell < 30" if nno < N30 else ""
        print(f"{c:>8} | {nca:>10} {w_care*100:>6.1f}% | {nno:>10} {w_non*100:>6.1f}% | "
              f"{full_w[c]*100:>11.1f}% |{flag}")
    print(f"{'TOTAL':>8} | {tot_care:>10} {'':>7} | {tot_non:>10} {'':>7} | "
          f"total rows w/ country = {total}")
    thin = [c for c, _, nno in rows if nno < N30]
    print(f"\nCountries with < {N30} non-caregivers: {thin or 'none'}  ({len(thin)} of {len(rows)})")

    # dashboard-spec definition (PROFILE04b/c/d > 0), group sizes only
    prof_cols = [c for c in df.columns if any(k in c for k in ("PROFILE04b", "PROFILE04c", "PROFILE04d"))]
    if prof_cols:
        def _num(col):
            return pd.to_numeric(df[col], errors="coerce").fillna(0)
        spec_care = sum(_num(c) for c in prof_cols) > 0
        print(f"\nDashboard-spec definition (PROFILE04b/c/d > 0), group sizes only -- columns {prof_cols}:")
        print(f"  caregivers = {int(spec_care.sum())}   non-caregivers = {int((~spec_care).sum())}   "
              f"(pipeline: {tot_care} / {tot_non})")
        agree = int((spec_care == care).sum())
        print(f"  agrees with the pipeline (IMPACT04) definition on {agree} of {len(df)} rows "
              f"({agree/len(df)*100:.1f}%)")
    else:
        print("\n(PROFILE04b/c/d columns not present in this export -- spec-definition comparison skipped)")

    # ---------------- per-outcome standardisation ----------------
    masks = outcome_masks(df)
    summary = []
    for label, mask in zip(CAREGIVER_TABLE_LABELS, masks):
        print("\n" + "=" * 108)
        print(f"OUTCOME: {label}")
        print("=" * 108)

        gc = gap_comparison(mask, care, "Caregiver", noncare, "Non-caregiver", run_significance=True)
        table_raw = gc.gap  # caregiver - non-caregiver, exactly as the 4.2 table
        print(f"  4.2 table:  caregiver {gc.group_a_share:.1%} (n={gc.group_a_n})   "
              f"non-caregiver {gc.group_b_share:.1%} (n={gc.group_b_n})   raw gap {table_raw:+.1%}"
              + (f"   sig p={gc.significance.p_value:.4f}" if gc.significance else ""))

        rc = per_country_rates(mask, care, ctry)
        rn = per_country_rates(mask, noncare, ctry)

        def standardise(cs: list[str]):
            wsum = sum(full_w[c] for c in cs)
            W = {c: full_w[c] / wsum for c in cs}
            ncare_sum = sum(rc[c][0] for c in cs)
            nnon_sum = sum(rn[c][0] for c in cs)
            a = {c: rc[c][0] / ncare_sum for c in cs}
            b = {c: rn[c][0] / nnon_sum for c in cs}
            raw_cs = sum(a[c] * rc[c][1] for c in cs) - sum(b[c] * rn[c][1] for c in cs)
            std = sum(W[c] * (rc[c][1] - rn[c][1]) for c in cs)
            contrib = {c: (a[c] - W[c]) * rc[c][1] - (b[c] - W[c]) * rn[c][1] for c in cs}
            return raw_cs, std, contrib, W, a, b

        cs_all = sorted(set(rc) & set(rn))
        cs_30 = [c for c in cs_all if rn[c][0] >= N30]
        raw_cs, std, contrib, W, a, b = standardise(cs_all)
        comp = raw_cs - std
        pct_comp = comp / table_raw * 100 if abs(table_raw) > 1e-9 else float("nan")

        print(f"  common support: {len(cs_all)} countries (both groups answer); "
              f"raw gap on that support {raw_cs:+.1%}  (table raw {table_raw:+.1%})")
        print(f"  STANDARDISED gap (full-sample country weights, direct standardisation): {std:+.1%}")
        print(f"  composition effect (raw - standardised): {comp:+.1%}   "
              f"= {pct_comp:+.0f}% of the raw gap")

        if cs_30 and set(cs_30) != set(cs_all):
            raw30, std30, _, _, _, _ = standardise(cs_30)
            dropped = sorted(set(cs_all) - set(cs_30))
            print(f"  robustness -- drop {len(dropped)} thin (<{N30} non-caregiver) countries "
                  f"{dropped}: standardised gap {std30:+.1%}  (raw on that support {raw30:+.1%})")
        else:
            print(f"  robustness -- no country has a non-caregiver cell below {N30} on the common support")

        top = sorted(contrib.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]
        print("  top countries contributing to the composition effect  "
              "(contrib_c sums to raw - standardised):")
        print(f"    {'ctry':>6} {'contrib':>9} | care rate  non rate  within-gap | "
              f"{'w_care':>7} {'w_non':>7} {'w_full':>7} | non-n")
        for c, v in top:
            print(f"    {c:>6} {v:+8.2%} | {rc[c][1]:8.1%}  {rn[c][1]:8.1%}  {rc[c][1]-rn[c][1]:+9.1%} | "
                  f"{a[c]*100:6.1f}% {b[c]*100:6.1f}% {W[c]*100:6.1f}% | {rn[c][0]}")

        survives = abs(std) >= 0.5 * abs(table_raw) and (np.sign(std) == np.sign(table_raw))
        sign_flip = np.sign(std) != np.sign(table_raw) and abs(std) > 0.005 and abs(table_raw) > 0.005
        summary.append(dict(label=label, table_raw=table_raw, std=std, comp=comp,
                            pct_comp=pct_comp, survives=survives, sign_flip=sign_flip,
                            thin=sorted(set(cs_all) - set(cs_30))))

    # ---------------- verdict ----------------
    print("\n\n" + "#" * 108)
    print("SUMMARY -- raw gap vs standardised gap, all eight outcomes")
    print("#" * 108)
    print(f"{'outcome':>32} | {'raw gap':>9} {'std gap':>9} {'comp eff':>9} {'comp %':>8} | "
          f"{'survives?':>10} {'sign flip?':>10}")
    for s in summary:
        print(f"{s['label']:>32} | {s['table_raw']:+8.1%} {s['std']:+8.1%} {s['comp']:+8.1%} "
              f"{s['pct_comp']:+7.0f}% | {str(s['survives']):>10} {str(s['sign_flip']):>10}")

    surv = [s['label'] for s in summary if s['survives']]
    flips = [s['label'] for s in summary if s['sign_flip']]
    biggest = sorted(summary, key=lambda s: abs(s['comp']), reverse=True)
    print(f"\nQ1  survives standardisation (std keeps sign AND >= 50% of raw): "
          f"{len(surv)} of 8 -> {surv}")
    print(f"Q2  changes most (|composition effect|):")
    for s in biggest[:4]:
        print(f"      {s['label']}: raw {s['table_raw']:+.1%} -> std {s['std']:+.1%}  "
              f"(composition {s['comp']:+.1%}, {s['pct_comp']:+.0f}% of raw)")
    print(f"Q3  sign reversal under standardisation: {flips or 'none'}")


if __name__ == "__main__":
    analyse()
