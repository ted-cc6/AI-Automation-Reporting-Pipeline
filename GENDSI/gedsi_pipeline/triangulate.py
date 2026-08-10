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

# insurance_type (Health Insurance / Enhanced Credit Life / Crop Insurance) is
# a portfolio/segment classification -- which single product a client's
# record is filed under -- not a response to a question about choice. The
# survey never asks whether a client selected their insurance product,
# whether it came bundled with a specific loan type, or whether eligibility
# rules assigned it, so nothing in this dataset supports describing gender
# differences across this field as differences in "uptake," "adoption," or
# an implied marketing/enrollment gap. Attached to every evidence pack that
# carries the Insurance Type cut of demographic_table.
UNDERSTANDING_BY_PRODUCT_NOTE = (
    "The understanding_by_product figures compare Female vs Male coverage understanding separately "
    "within each insurance product, computed only from clients who currently hold a policy. This "
    "dataset has no clients who considered a product and declined it, so it cannot show that poor "
    "understanding causes lower enrollment ('uptake') in a product, or the reverse; it can only show "
    "whether understanding and product differ together among people who already hold a policy. State "
    "any link as an open question or a shared-root-cause hypothesis, never as a causal claim in either "
    "direction."
)

CLAIMS_UNDERSTANDING_NOTE = (
    "The claim_rate_by_understanding figures compare claim-submission rates, among clients who "
    "experienced an insured event, between those reporting poor/very poor understanding of their "
    "coverage and those reporting good/very good understanding, computed separately by sex. "
    "Understanding and claim behavior are both self-reported at the same point in time, so this is a "
    "strong statistical association, not proof of causation: it is plausible that not understanding "
    "one's coverage discourages filing a claim, but it is also possible that the claim experience "
    "itself (or its absence) shapes how a client later describes their own understanding, or that a "
    "third factor (e.g. literacy, branch-level service quality) drives both. Describe this as a "
    "strong, statistically significant association that may help explain the gender gap in claim "
    "submission, not as a confirmed cause of it."
)

CLIENT_BASE_COMPOSITION_NOTE = (
    "client_base_composition gives each sex's share of the entire client base, alongside the estimated "
    "number of detractors that share represents in absolute terms. Rate and volume can diverge: a group "
    "can have a LOWER detractor rate (less likely, per client, to be a detractor) while still accounting "
    "for MORE detractors in absolute terms, simply because it makes up a larger share of the overall "
    "client base. Keep these two ideas distinct in your prose -- do not use one to imply the other -- and "
    "if a group is the large majority of the client base, a finding specific to that group affects the "
    "large majority of clients overall, not a small subgroup."
)

STRESS_VS_PEACE_OF_MIND_NOTE = (
    "financial_stress_reduction asks about a broad, general change in day-to-day financial stress, "
    "which is influenced by many factors beyond a single insurance product (income, debt, other "
    "economic pressures). This is a different construct from the 'sense of financial security / peace "
    "of mind' theme reported elsewhere in this report as the leading reason NPS promoters give for "
    "their high score: that is a specific, anticipatory reassurance about being covered, not a claim "
    "that overall financial stress went down. stress_reduction_by_nps_category shows these are related "
    "but not interchangeable: Promoters report 'No effect' on financial stress less often than "
    "Detractors (44.0% vs 59.6%), but a plurality of Promoters (44.0%) still report 'No effect.' Do not "
    "treat a 'No effect' finding as contradicting or disproving the peace-of-mind finding, and do not "
    "treat the peace-of-mind finding as evidence that most clients' measured financial stress declined; "
    "report each on its own terms and note the relationship is directional, not a majority reversal."
)

CREDIT_LIFE_BENEFITS_NOTE = (
    "The credit_life_extra_benefits question ('Besides protection in case of death or disability, which "
    "other insurance benefits are included with your Credit insurance?') asks what benefits a client "
    "believes are CURRENTLY included in their existing policy -- it is a comprehension/awareness measure "
    "of reported or believed coverage, not a question about what benefits clients want added. Never "
    "describe these figures using the words 'expect,' 'expectation,' or 'want'; describe them as what "
    "clients report or believe is included in their coverage. This question was asked of all respondents "
    "regardless of their primary insurance_type, not only Enhanced Credit Life holders (only 285 of 2091 "
    "respondents hold Enhanced Credit Life as their primary product), so do not describe this as an "
    "Enhanced-Credit-Life-holder-specific finding. Finally, every one of these benefit options is a "
    "minority response within both sexes (all under 16%); describe any gender gap as a gap in a minority "
    "response, not as a majority view or a widespread expectation."
)

INSURANCE_TYPE_NOTE = (
    "The insurance_type field (Health Insurance / Enhanced Credit Life / Crop Insurance) records "
    "which single product each client's record is filed under -- it is a portfolio/segment "
    "classification, not a response to a question about choice. The survey does not capture whether "
    "this reflects the client's own selection, the loan product they hold, eligibility rules, or "
    "regional product availability. Describe differences across this field as differences in "
    "composition or distribution (e.g. \"Health Insurance is held disproportionately by male "
    "clients\"), not as differences in uptake, adoption, or an implied marketing or enrollment gap, "
    "unless a qualitative quote elsewhere in this pack directly supports a specific mechanism."
)


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
    return [
        {"sex": r.sex, "country": r.country, "disability": r.disability, "quote": getattr(r, col)}
        for r in sample.itertuples()
    ]


def build_evidence_packs(work_dir: Path | None = None) -> dict[str, dict]:
    work_dir = work_dir or config.WORK_DIR
    df = pd.read_parquet(work_dir / "response_frame.parquet")
    qt_dir = work_dir / "quant_tables"
    gender = pd.read_csv(qt_dir / "gender_comparisons.csv")
    disability = pd.read_csv(qt_dir / "disability_comparisons.csv")
    nps = pd.read_csv(qt_dir / "nps_by_group.csv")
    demo = pd.read_csv(qt_dir / "demographic_table.csv")
    understanding_by_product = pd.read_csv(qt_dir / "understanding_by_product.csv")
    claims_by_understanding = pd.read_csv(qt_dir / "claims_by_understanding.csv")
    stress_by_nps = pd.read_csv(qt_dir / "stress_reduction_by_nps_category.csv")

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
        "qual": {"top_detractor_theme": detractor_themes[0] if detractor_themes else None},
        "divergence_flags": [],
        "notes": [
            INSURANCE_TYPE_NOTE,
            "Qualitative theme analysis of NPS detractor, passive, and promoter reasons has already "
            "been conducted for this survey (see top_detractor_theme above, and the full breakdown in "
            "the Client Satisfaction & NPS and Recommendations sections of this same report). Do not "
            "recommend that qualitative research into detractor pain points be conducted in the future "
            "as though it were an open gap; if you reference the detractor rate, cite the top theme "
            "already identified instead.",
        ],
    }

    understanding_by_product_rows = [
        r for r in _rows_for_indicators(understanding_by_product, ["understanding_coverage"])
        if r["category"] in ("Poor", "Very poor")
    ]
    packs["access_understanding"] = {
        "section": "Access & Understanding of Insurance",
        "quant": {
            "gender": _rows_for_indicators(gender, ["understanding_coverage", "understanding_claims_process"])
                      + _rows_for_multiselect(gender, ["comms_channel_effectiveness", "credit_life_extra_benefits"]),
            "disability": _rows_for_indicators(disability, ["understanding_coverage", "understanding_claims_process"]),
            "understanding_by_product": understanding_by_product_rows,
        },
        "qual": {"other_specify_quotes": _raw_supplementary_quotes(df, "comms_channel_other_specify")},
        "divergence_flags": [],
        "notes": [
            UNDERSTANDING_BY_PRODUCT_NOTE,
            CREDIT_LIFE_BENEFITS_NOTE,
            "A figure (bar chart) breaking down understanding_by_product by sex is inserted into this "
            "section automatically after your text -- do not describe it, refer to a 'figure below,' or "
            "attempt to reproduce it in words; just write the analysis as usual and it will appear "
            "immediately after your paragraphs.",
        ],
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
    claim_rate_by_understanding = _round_floats(
        claims_by_understanding[claims_by_understanding["category"] == "Yes"].to_dict("records")
    )
    if claim_rate_by_understanding:
        divergence.append({
            "note": "Compare claim-submission rate between clients with poor/very poor coverage "
                    "understanding and clients with good/very good understanding, within each sex -- "
                    "see the accompanying note on why this is an association, not a confirmed cause, "
                    "of the gender gap in claim submission reported above.",
            "claim_rate_by_understanding": claim_rate_by_understanding,
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
        "notes": [CLAIMS_UNDERSTANDING_NOTE],
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
            "stress_reduction_by_nps_category": _round_floats(stress_by_nps.to_dict("records")),
        },
        "qual": {"coping_other_specify_quotes": _raw_supplementary_quotes(df, "coping_behavior_other_specify")},
        "divergence_flags": [],
        "notes": [STRESS_VS_PEACE_OF_MIND_NOTE],
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
    sex_n_rows = nps[nps["cut"] == "Sex"][["group", "n", "detractor_pct"]].to_dict("records")
    total_client_n = sum(r["n"] for r in sex_n_rows)
    client_base_composition = [
        {
            "sex": r["group"],
            "n": r["n"],
            "pct_of_all_clients": round(100 * r["n"] / total_client_n, 1) if total_client_n else None,
            "n_detractors_est": round(r["n"] * r["detractor_pct"] / 100),
            "pct_of_all_clients_that_are_this_sexs_detractors": (
                round(100 * (r["n"] * r["detractor_pct"] / 100) / total_client_n, 1) if total_client_n else None
            ),
        }
        for r in sex_n_rows
    ]
    packs["satisfaction_nps"] = {
        "section": "Client Satisfaction & Net Promoter Score by Gender",
        "quant": {
            "nps_by_sex": _round_floats(nps[nps["cut"] == "Sex"].to_dict("records")),
            "nps_by_disability": _round_floats(nps[nps["cut"] == "Disability (HH)"].to_dict("records")),
            "gender": _rows_for_indicators(gender, ["worth_the_cost", "confidence_payout"]),
            "client_base_composition": client_base_composition,
        },
        "qual": {
            "detractor_themes": detractor_themes, "passive_themes": passive_themes, "promoter_themes": promoter_themes,
            "detractor_quotes": _quotes_for(quote_bank.get("nps_detractor_reasons", {}), [t["theme"] for t in detractor_themes[:3]]),
            "passive_quotes": _quotes_for(quote_bank.get("nps_passive_reasons", {}), [t["theme"] for t in passive_themes[:3]]),
            "promoter_quotes": _quotes_for(quote_bank.get("nps_promoter_reasons", {}), [t["theme"] for t in promoter_themes[:3]]),
        },
        "divergence_flags": nps_divergence,
        "notes": [CLIENT_BASE_COMPOSITION_NOTE, STRESS_VS_PEACE_OF_MIND_NOTE],
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
            ]),
        },
        "qual": {}, "divergence_flags": [],
        "notes": [
            "Vietnam (Crop Insurance) and LACRO countries have small samples -- treat as directional, "
            "not statistically robust, per the min-n gate in Stage 2.",
            INSURANCE_TYPE_NOTE,
            "The credit_life_extra_benefits comprehension finding (whether clients believe extra "
            "benefits are included in their credit-linked coverage) is covered in the Access & "
            "Understanding of Insurance section, not here -- do not duplicate it in this section.",
        ],
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
        "quant": {
            "top_detractor_themes": detractor_themes[:5],
            "comms_channel_effectiveness": _rows_for_multiselect(gender, ["comms_channel_effectiveness"]),
            "understanding_gap_by_product": understanding_by_product_rows,
        },
        "qual": {"detractor_quotes": _quotes_for(quote_bank.get("nps_detractor_reasons", {}), [t["theme"] for t in detractor_themes[:5]], limit=1)},
        "divergence_flags": [],
        "notes": [
            "comms_channel_effectiveness and understanding_gap_by_product are given together because "
            "they may be connectable: if a specific product/sex combination has a significant understanding "
            "gap (see understanding_gap_by_product, n_ok=true and significant=true rows), check whether the "
            "preferred communication channel for that gap's affected group differs from what the "
            "population-wide comms_channel_effectiveness figures show. If it does not differ (the affected "
            "group prefers the same channel as everyone else), that points to a delivery/reach problem with "
            "the already-preferred channel for that group, not a wrong-channel problem; only make this "
            "connection if the numbers given here actually support it.",
        ],
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
