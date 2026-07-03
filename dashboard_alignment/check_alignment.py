"""dashboard_alignment/check_alignment.py

Compares analysis engine output against Vietnam Power BI dashboard values.
Run from the project root: python dashboard_alignment/check_alignment.py
"""
import json
from pathlib import Path

import yaml

from data_loader.data_loader_api import load_survey_data

RUN_ID       = "2026_Q2"
RESULTS_PATH = Path(f"runs/{RUN_ID}/analysis_results.json")
MAP_PATH     = Path("dashboard_alignment/indicator_map.yaml")
TOLERANCE    = 0.005   # 0.5 pp — diff ≤ 0.005 → MATCH
INVESTIGATE  = 0.05    # 5 pp  — diff ≤ 0.05  → INVESTIGATE


def get_nested(d: dict, path: str):
    """Traverse a dot-separated path in a nested dict. Returns None on missing key."""
    for key in path.split("."):
        if isinstance(d, dict) and key in d:
            d = d[key]
        else:
            return None
    return d


def compute_first_time_access(ds) -> float:
    """Proportion of respondents whose q_prior_access indicates first-time insurance use."""
    col = "q_prior_access"
    if col not in ds.df.columns:
        return None
    return float((ds.df[col] == False).sum() / len(ds.df))   # noqa: E712


def compute_financial_worries_reduced(ds) -> float:
    """Proportion of insured-event respondents NOT using negative coping strategies.

    The dashboard 'Financial Worries Reduced' indicator uses the insured-event base
    (those who experienced an insured event in the past 12 months) as denominator.
    Among that base, flag_negative_coping == False means the respondent did NOT resort
    to distress-sale, debt, or other negative coping mechanisms.
    """
    col = "flag_negative_coping"
    ied = ds.insured_event_base
    if col not in ied.columns:
        return None
    n_not_coping = (ied[col] == False).sum()   # noqa: E712
    return float(n_not_coping / len(ied))


def main():
    results       = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    indicator_map = yaml.safe_load(MAP_PATH.read_text(encoding="utf-8"))

    # Load dataset only when a compute field requires it
    needs_dataset = any(
        ind.get("compute") is not None
        for ind in indicator_map["indicators"]
        if ind.get("status") == "COMPARE"
    )
    ds = load_survey_data(RUN_ID) if needs_dataset else None

    col_w = 48
    header = (
        f"\n{'Indicator':<{col_w}} {'Dashboard':>10} {'Ours':>10} {'Diff (pp)':>10}  Status"
    )
    sep = "─" * (col_w + 42)
    print(header)
    print(sep)

    mismatches   = []
    investigates = []
    missing      = []
    out_of_scope = []

    for ind in indicator_map["indicators"]:
        name         = ind["name"]
        dash         = ind["dashboard_value"]
        scale        = ind.get("scale_factor", 1.0)
        status_flag  = ind.get("status", "COMPARE")
        force_inv    = ind.get("force_investigate", False)

        if status_flag == "OUT_OF_SCOPE":
            out_of_scope.append(name)
            print(f"{name:<{col_w}} {dash:>10.4f} {'—':>10} {'—':>10}  OUT_OF_SCOPE")
            continue

        our_raw  = None
        json_path = ind.get("json_path")
        compute   = ind.get("compute")

        if compute == "share_of_respondents_where_q_prior_access_is_False" and ds is not None:
            our_raw = compute_first_time_access(ds)
        elif compute == "share_where_flag_negative_coping_is_False" and ds is not None:
            our_raw = compute_financial_worries_reduced(ds)
        elif json_path:
            our_raw = get_nested(results, json_path)

        if our_raw is None:
            missing.append(name)
            print(f"{name:<{col_w}} {dash:>10.4f} {'—':>10} {'—':>10}  MISSING")
            continue

        our_val  = float(our_raw) * scale
        diff     = abs(our_val - dash)
        diff_pp  = diff * 100  # for display

        if force_inv:
            verdict = "INVESTIGATE"
            investigates.append((name, dash, our_val, diff))
        elif diff <= TOLERANCE:
            verdict = "MATCH"
        elif diff <= INVESTIGATE:
            verdict = "INVESTIGATE"
            investigates.append((name, dash, our_val, diff))
        else:
            verdict = "MISMATCH"
            mismatches.append((name, dash, our_val, diff))

        print(f"{name:<{col_w}} {dash:>10.4f} {our_val:>10.4f} {diff_pp:>9.2f}pp  {verdict}")

    # Summary
    print(f"\n{sep}")
    print("SUMMARY")
    print(f"  Out of scope (crop-specific, not in engine):  {len(out_of_scope)}")
    print(f"  Missing (json_path not found in results):     {len(missing)}")
    print(f"  MATCH  (diff ≤ 0.5pp):                       "
          f"{sum(1 for ind in indicator_map['indicators'] if ind.get('status') == 'COMPARE' and ind.get('name') not in [m[0] for m in mismatches] and ind.get('name') not in [i[0] for i in investigates] and ind.get('name') not in missing)}")
    print(f"  INVESTIGATE (0.5pp < diff ≤ 5pp, or forced): {len(investigates)}")
    print(f"  MISMATCH (diff > 5pp):                        {len(mismatches)}")

    if mismatches:
        print("\nMISMATCHES requiring investigation:")
        for nm, dv, ov, df in mismatches:
            print(f"  {nm}")
            print(f"    dashboard={dv:.4f}  ours={ov:.4f}  diff={df*100:.2f}pp")

    if investigates:
        print("\nINVESTIGATE entries:")
        for nm, dv, ov, df in investigates:
            print(f"  {nm}")
            print(f"    dashboard={dv:.4f}  ours={ov:.4f}  diff={df*100:.2f}pp")

    if missing:
        print("\nMISSING — update json_path in indicator_map.yaml:")
        for nm in missing:
            print(f"  {nm}")

    schema = results.get("meta", {}).get("schema_version", "unknown")
    print(f"\nanalysis_results.json schema_version: {schema}")
    print()


if __name__ == "__main__":
    main()
