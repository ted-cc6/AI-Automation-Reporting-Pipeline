"""
Stage 4 -- triangulation.

Builds one "evidence pack" per report section: the relevant pre-computed
quant stats (already significance-tested and FDR-corrected in Stage 2) +
relevant qual themes/quotes (already coded in Stage 3) + explicit divergence
flags. Stage 5 (draft_writer) receives ONLY these packs -- never the raw
dataset -- so it cannot invent numbers.
"""
from __future__ import annotations

import json
from ast import literal_eval
from pathlib import Path

import pandas as pd

from gedsi_pipeline import config

ROUND = 1


def _round_floats(obj):
    if isinstance(obj, float):
        return round(obj, ROUND)
    if isinstance(obj, dict):
        return {k: _round_floats(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_round_floats(v) for v in obj]
    return obj


def _rows_for_indicators(table: pd.DataFrame, indicators: list[str]) -> list[dict]:
    if table.empty:
        return []
    sub = table[table["indicator"].isin(indicators)]
    return _round_floats(sub.to_dict("records"))


def _rows_for_multiselect(table: pd.DataFrame, group_names: list[str]) -> list[dict]:
    if table.empty:
        return []
    mask = table["indicator"].apply(lambda i: any(i.startswith(f"{g}__") for g in group_names))
    return _round_floats(table[mask].to_dict("records"))


def _theme_prevalence_by_sex(theme_csv_path, question_label: str) -> list[dict]:
    df = pd.read_csv(theme_csv_path)

    def parse(x):
        try:
            return literal_eval(x) if isinstance(x, str) else []
        except Exception:
            return []

    df["themes"] = df["themes"].apply(parse)
    exploded = df.explode("themes").dropna(subset=["themes"])
    rows = []
    for theme, grp in exploded.groupby("themes"):
        n_total = len(df)
        n_f = len(df[df["sex"] == "Female"])
        n_m = len(df[df["sex"] == "Male"])
        f_count = int((grp["sex"] == "Female").sum())
        m_count = int((grp["sex"] == "Male").sum())
        f_pct = 100 * f_count / n_f if n_f else None
        m_pct = 100 * m_count / n_m if n_m else None
        rows.append({
            "question": question_label,
            "theme": theme,
            "n_mentions": len(grp),
            "pct_of_all_responses": round(100 * len(grp) / n_total, 1) if n_total else None,
            "female_pct": round(f_pct, 1) if f_pct is not None else None,
            "male_pct": round(m_pct, 1) if m_pct is not None else None,
            "pt_diff_f_minus_m": round(f_pct - m_pct, 1) if (f_pct is not None and m_pct is not None) else None,
        })
    return sorted(rows, key=lambda r: -r["n_mentions"])


def _quotes_for(theme_bank: dict, codes: list[str], limit: int = 3) -> list[dict]:
    out = []
    for code in codes:
        for q in theme_bank.get(code, [])[:limit]:
            out.append({"theme": code, **q})
    return out


def _raw_supplementary_quotes(df: pd.DataFrame, col: str, limit: int = 5) -> list[dict]:
    sub = df[df[col].notna() & (df[col].str.strip() != "")]
    sample = sub.sample(n=min(limit, len(sub)), random_state=7) if len(sub) else sub
    return [{"sex": r.sex, "country": r.country, "quote": getattr(r, col)} for r in sample.itertuples()]


def build_evidence_packs(work_dir: Path | None = None) -> dict[str, dict]:
    work_dir = work_dir or config.WORK_DIR
    df = pd.read_parquet(work_dir / "response_frame.parquet")
    qt_dir = work_dir / "quant_tables"
    gender = pd.read_csv(qt_dir / "gender_comparisons.csv")
    disability = pd.read_csv(qt_dir / "disability_comparisons.csv")
    nps = pd.read_csv(qt_dir / "nps_by_group.csv")
    demo = pd.read_csv(qt_dir / "demographic_table.csv")

    quote_bank = json.loads((work_dir / "quote_bank.json").read_text(encoding="utf-8"))

    theme_paths = {
        "nps_detractor_reasons": work_dir / "theme_tables" / "nps_detractor_reasons.csv",
        "nps_passive_reasons": work_dir / "theme_tables" / "nps_passive_reasons.csv",
        "nps_promoter_reasons": work_dir / "theme_tables" / "nps_promoter_reasons.csv",
    }
    detractor_themes = _theme_prevalence_by_sex(theme_paths["nps_detractor_reasons"], "detractor (score 0-6)")
    passive_themes = _theme_prevalence_by_sex(theme_paths["nps_passive_reasons"], "passive (score 7-8)")
    promoter_themes = _theme_prevalence_by_sex(theme_paths["nps_promoter_reasons"], "promoter (score 9-10)")

    packs = {}

    packs["executive_summary"] = {
        "section": "Executive Summary & Demographics",
        "quant": {"demographic_table": _round_floats(demo.to_dict("records")),
                  "nps_overall": _round_floats(nps[nps["cut"] == "Overall"].to_dict("records"))},
        "qual": {}, "divergence_flags": [],
    }

    packs["access_understanding"] = {
        "section": "Access & Understanding of Insurance",
        "quant": {
            "gender": _rows_for_indicators(gender, ["understanding_coverage", "understanding_claims_process"])
                      + _rows_for_multiselect(gender, ["comms_channel_effectiveness"]),
            "disability": _rows_for_indicators(disability, ["understanding_coverage", "understanding_claims_process"]),
        },
        "qual": {"other_specify_quotes": _raw_supplementary_quotes(df, "comms_channel_other_specify")},
        "divergence_flags": [],
    }

    # Claims experience divergence: approval rate vs challenge rate
    claims_gender = _rows_for_indicators(gender, [
        "experienced_insured_event", "submitted_claim", "reason_no_claim",
        "claim_result", "payout_coverage_ratio", "experienced_claim_challenges",
    ]) + _rows_for_multiselect(gender, ["claim_challenges"])
    divergence = []
    approved_rows = [r for r in claims_gender if r["indicator"] == "claim_result" and "approved" in r["category"].lower()]
    challenge_rows = [r for r in claims_gender if r["indicator"] == "experienced_claim_challenges" and r["category"].lower() == "yes"]
    if approved_rows and challenge_rows:
        divergence.append({
            "note": "Compare claim approval rate against share reporting process challenges -- "
                    "a high approval rate alongside a non-trivial challenge rate indicates claims "
                    "are eventually paid but the client experience getting there is difficult.",
            "approved_rate": approved_rows[0], "challenge_rate": challenge_rows[0],
        })
    packs["claims_experience"] = {
        "section": "Claims Experience",
        "quant": {"gender": claims_gender, "disability": _rows_for_indicators(disability, [
            "experienced_insured_event", "submitted_claim", "claim_result", "experienced_claim_challenges",
        ]) + _rows_for_multiselect(disability, ["claim_challenges"])},
        "qual": {
            "reason_no_claim_quotes": _raw_supplementary_quotes(df, "reason_no_claim_other_specify"),
            "support_needed_quotes": _raw_supplementary_quotes(df, "claim_support_needed"),
        },
        "divergence_flags": divergence,
    }

    packs["additional_services"] = {
        "section": "Additional Services & Value-Added Benefits",
        "quant": {
            "gender": _rows_for_indicators(gender, ["claim_services_helped"]) + _rows_for_multiselect(gender, ["additional_services_used"]),
        },
        "qual": {"other_specify_quotes": _raw_supplementary_quotes(df, "other_vf_service_specify", limit=3)},
        "divergence_flags": [],
    }

    packs["wellbeing_resilience"] = {
        "section": "Wellbeing & Financial Resilience",
        "quant": {
            "gender": _rows_for_indicators(gender, ["financial_stress_reduction", "child_wellbeing_improved"])
                      + _rows_for_multiselect(gender, ["children_improvements", "coping_behaviors_after_event"]),
            "disability": _rows_for_indicators(disability, ["financial_stress_reduction", "child_wellbeing_improved"]),
        },
        "qual": {"coping_other_specify_quotes": _raw_supplementary_quotes(df, "coping_behavior_other_specify")},
        "divergence_flags": [],
    }

    # NPS / satisfaction: centerpiece pairing of quant NPS with qual driver themes
    nps_divergence = []
    top_detractor = detractor_themes[0] if detractor_themes else None
    top_promoter = promoter_themes[0] if promoter_themes else None
    if top_detractor and top_promoter:
        nps_divergence.append({
            "note": "The dominant reason for LOW scores and the dominant reason for HIGH scores both "
                    "relate to how well clients understand/experience the product -- pair these explicitly "
                    "rather than treating NPS as a single undifferentiated number.",
            "top_detractor_theme": top_detractor, "top_promoter_theme": top_promoter,
        })
    packs["satisfaction_nps"] = {
        "section": "Client Satisfaction & Net Promoter Score by Gender",
        "quant": {
            "nps_by_sex": _round_floats(nps[nps["cut"] == "Sex"].to_dict("records")),
            "nps_by_disability": _round_floats(nps[nps["cut"] == "Disability (HH)"].to_dict("records")),
            "gender": _rows_for_indicators(gender, ["worth_the_cost", "confidence_payout"]),
        },
        "qual": {
            "detractor_themes": detractor_themes, "passive_themes": passive_themes, "promoter_themes": promoter_themes,
            "detractor_quotes": _quotes_for(quote_bank.get("nps_detractor_reasons", {}), [t["theme"] for t in detractor_themes[:3]]),
            "passive_quotes": _quotes_for(quote_bank.get("nps_passive_reasons", {}), [t["theme"] for t in passive_themes[:3]]),
            "promoter_quotes": _quotes_for(quote_bank.get("nps_promoter_reasons", {}), [t["theme"] for t in promoter_themes[:3]]),
        },
        "divergence_flags": nps_divergence,
    }

    packs["financial_inclusion"] = {
        "section": "Financial Inclusion & First-Time Access",
        "quant": {"gender": _rows_for_indicators(gender, ["had_access_before_vfi", "ease_alternative_access"]),
                  "disability": _rows_for_indicators(disability, ["had_access_before_vfi", "ease_alternative_access"])},
        "qual": {}, "divergence_flags": [],
    }

    packs["disability_crosscut"] = {
        "section": "Disability & Vulnerability Cross-Cut",
        "quant": {"disability_all": _round_floats(disability.to_dict("records"))},
        "qual": {}, "divergence_flags": [],
    }

    packs["product_region_notes"] = {
        "section": "Product & Region Notes",
        "quant": {
            "demographic_table": _round_floats(demo.to_dict("records")),
            "nps_by_country": _round_floats(nps[nps["cut"] == "Country"].to_dict("records")),
            "nps_by_insurance_type": _round_floats(nps[nps["cut"] == "Insurance Type"].to_dict("records")),
            "product_specific": _rows_for_indicators(gender, [
                "renew_at_full_premium", "medical_care_easier", "oop_cost_change",
                "recovery_speed", "farming_approach_changed", "value_of_enhanced_benefits",
            ]) + _rows_for_multiselect(gender, ["credit_life_extra_benefits"]),
        },
        "qual": {}, "divergence_flags": [],
        "notes": ["Vietnam (Crop Insurance) and LACRO countries have small samples -- treat as directional, "
                  "not statistically robust, per the min-n gate in Stage 2."],
    }

    packs["external_evidence"] = {
        "section": "External Evidence & Context",
        "quant": {}, "qual": {}, "divergence_flags": [],
        "notes": ["No external benchmark or citation data was supplied with this dataset. Any external "
                  "framing must be generic and explicitly caveated as general context, not a verified citation."],
    }

    packs["benchmarking"] = {
        "section": "Benchmarking",
        "quant": {}, "qual": {}, "divergence_flags": [],
        "notes": ["No internal (cross-portfolio) or external (60 Decibels, regional/global) benchmark file "
                  "was supplied with this dataset. State this gap explicitly rather than inventing figures."],
    }

    packs["recommendations"] = {
        "section": "Recommendations / Actions",
        "quant": {"top_detractor_themes": detractor_themes[:5]},
        "qual": {"detractor_quotes": _quotes_for(quote_bank.get("nps_detractor_reasons", {}), [t["theme"] for t in detractor_themes[:5]], limit=1)},
        "divergence_flags": [],
    }

    return packs


def main(work_dir: Path | None = None):
    work_dir = work_dir or config.WORK_DIR
    packs = build_evidence_packs(work_dir)
    out_dir = work_dir / "evidence_packs"
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, pack in packs.items():
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(pack, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {path}")


if __name__ == "__main__":
    main()
