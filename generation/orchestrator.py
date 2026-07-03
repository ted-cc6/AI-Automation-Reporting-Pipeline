"""generation/orchestrator.py

Phase 2: Extract and package all data for each of 7 report parts.
"""
import json
import logging
from pathlib import Path

import yaml

from utils import get_nested, format_value

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
SPEC_PATH = ROOT / "generation" / "report_spec.yaml"

_DRIVER_LABELS = {
    "financial_stress":             "Financial Stress (High)",
    "coverage_understanding":       "Coverage Understanding",
    "claim_process_understanding":  "Claim Process Understanding",
    "worth_premium":                "Worth Premium",
    "renewal_intent":               "Renewal Intent",
    "confidence_pay":               "Confidence in Payout",
    "nps_score":                    "Net Promoter Score",
    "economic_strain_relief_proxy": "Economic Strain Relief",
}


# ---------------------------------------------------------------------------
# Preflight
# ---------------------------------------------------------------------------

def preflight_check(run_id: str) -> dict:
    errors, warnings = [], []
    run_dir = ROOT / "runs" / run_id

    for fname in ("analysis_results.json", "qualitative_results.json"):
        if not (run_dir / fname).exists():
            if fname == "analysis_results.json":
                errors.append(f"{run_dir / fname} missing")
            else:
                warnings.append(f"{run_dir / fname} not found — qualitative data will be empty")

    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    for part_key, part_spec in spec.get("parts", {}).items():
        for v in part_spec.get("visuals", []):
            vpath = run_dir / "visuals" / v["file"]
            if not vpath.exists():
                warnings.append(f"Visual missing: visuals/{v['file']}")

    ok = len(errors) == 0
    for e in errors:
        log.error(e)
    for w in warnings:
        log.warning(w)
    return {"ok": ok, "errors": errors, "warnings": warnings}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_data(run_id: str) -> tuple:
    run_dir = ROOT / "runs" / run_id

    with open(run_dir / "analysis_results.json", encoding="utf-8") as f:
        analysis = json.load(f)

    sv = analysis.get("meta", {}).get("schema_version", "")
    if sv != "1.5":
        raise ValueError(f"Expected schema_version 1.5, got '{sv}'")

    qual_path = run_dir / "qualitative_results.json"
    if qual_path.exists():
        with open(qual_path, encoding="utf-8") as f:
            qual = json.load(f)
    else:
        qual = {}

    return analysis, qual


# ---------------------------------------------------------------------------
# Per-section extractors
# ---------------------------------------------------------------------------

def extract_metrics(analysis: dict, section_spec: dict) -> dict:
    """Build a flat dict of formatted metric strings for one section."""
    result = {}

    for m_key, m_cfg in section_spec.get("metrics", {}).items():
        v    = get_nested(analysis, m_cfg["path"])
        sup  = bool(get_nested(analysis, m_cfg.get("suppressed_path", ""), default=False))
        result[m_key] = format_value(v, m_cfg["fmt"], suppressed=sup)

        n_path = m_cfg.get("n_path")
        if n_path:
            n_val = get_nested(analysis, n_path)
            result[m_key + "_n"] = format_value(n_val, "count") if n_val is not None else "?"

    # Driver rho/p/n for Part 5 sections
    for d_key, d_cfg in section_spec.get("drivers", {}).items():
        sup   = bool(get_nested(analysis, d_cfg.get("suppressed_path", ""), default=False))
        rho   = get_nested(analysis, d_cfg["rho_path"])
        p_val = get_nested(analysis, d_cfg["p_path"])
        n_val = get_nested(analysis, d_cfg["n_path"])
        result[d_key + "_rho"] = format_value(rho, "rho", suppressed=sup)
        result[d_key + "_p"]   = f"{p_val:.4f}" if (p_val is not None and not sup) else "SUPPRESSED"
        result[d_key + "_n"]   = format_value(n_val, "count") if (n_val is not None and not sup) else "SUPPRESSED"

    return result


def extract_qualitative(qual: dict, section_spec: dict) -> dict:
    """Extract qualitative data slices for a section."""
    if not qual:
        return {}

    out = {}
    for q_key in section_spec.get("qualitative_keys", []):
        out[q_key] = get_nested(qual, q_key, default=None)

    verb_section = section_spec.get("verbatim_section")
    if verb_section:
        sv = qual.get("section_verbatims", {})
        out["verbatims"] = sv.get(verb_section, [])

    return out


def extract_distribution(analysis: dict, path: str) -> list:
    """Extract a distribution list from analysis by dotted path."""
    result = get_nested(analysis, path)
    if isinstance(result, list):
        return result
    return []


def check_visual(run_id: str, filename: str):
    p = ROOT / "runs" / run_id / "visuals" / filename
    return p if p.exists() else None


# ---------------------------------------------------------------------------
# Drivers data builder (Part 5)
# ---------------------------------------------------------------------------

def _build_drivers_data(analysis: dict, drivers_spec: dict) -> list:
    """Pre-compute the sorted drivers table rows for the assembler."""
    rows = []
    for d_key, d_cfg in drivers_spec.items():
        sup   = bool(get_nested(analysis, d_cfg.get("suppressed_path", ""), default=False))
        rho   = get_nested(analysis, d_cfg["rho_path"])
        p_val = get_nested(analysis, d_cfg["p_path"])
        n_val = get_nested(analysis, d_cfg["n_path"])
        rows.append({
            "key":        d_key,
            "label":      _DRIVER_LABELS.get(d_key, d_key.replace("_", " ").title()),
            "rho":        rho,
            "p_value":    p_val,
            "n_valid":    n_val,
            "suppressed": sup,
        })
    # Sort by abs(rho) descending; suppressed rows go to bottom
    rows.sort(key=lambda r: (r["suppressed"], -abs(r["rho"]) if r["rho"] is not None else 0))
    return rows


# ---------------------------------------------------------------------------
# Scorecard builders (Parts 6 & 7)
# ---------------------------------------------------------------------------

def _build_scorecard_6(analysis: dict, scorecard_spec: list) -> list:
    rows = []
    for m in scorecard_spec:
        sup_a = bool(get_nested(analysis, m["claimant_sup"], default=False))
        sup_b = bool(get_nested(analysis, m["non_claimant_sup"], default=False))
        val_a = format_value(get_nested(analysis, m["claimant_path"]), m["fmt"], suppressed=sup_a)
        val_b = format_value(get_nested(analysis, m["non_claimant_path"]), m["fmt"], suppressed=sup_b)
        p_val = get_nested(analysis, m["sig_path"])
        sig   = (p_val is not None and p_val < 0.05)
        rows.append({
            "label":         m["label"],
            "group_a_label": "Claimant",
            "group_a_value": val_a,
            "group_b_label": "Non-Claimant",
            "group_b_value": val_b,
            "sig_p":         p_val,
            "significant":   sig,
        })
    return rows


def _build_scorecard_7(analysis: dict, scorecard_spec: list) -> list:
    rows = []
    for m in scorecard_spec:
        sup_a = bool(get_nested(analysis, m["female_sup"], default=False))
        sup_b = bool(get_nested(analysis, m["male_sup"], default=False))
        val_a = format_value(get_nested(analysis, m["female_path"]), m["fmt"], suppressed=sup_a)
        val_b = format_value(get_nested(analysis, m["male_path"]), m["fmt"], suppressed=sup_b)
        p_val = get_nested(analysis, m["sig_path"])
        sig   = (p_val is not None and p_val < 0.05)
        rows.append({
            "label":         m["label"],
            "group_a_label": "Female",
            "group_a_value": val_a,
            "group_b_label": "Male",
            "group_b_value": val_b,
            "sig_p":         p_val,
            "significant":   sig,
        })
    return rows


# ---------------------------------------------------------------------------
# Package builder
# ---------------------------------------------------------------------------

def build_part_package(part_key: str, analysis: dict, qual: dict,
                       spec_part: dict, run_id: str) -> dict:
    sections_out = {}

    for s_key, s_spec in spec_part.get("sections", {}).items():
        if s_key == "insight":
            # Extract verbatims from qual
            verb_section = s_spec.get("verbatim_section", "")
            verbatims = []
            if qual and verb_section:
                verbatims = qual.get("section_verbatims", {}).get(verb_section, [])
            sections_out[s_key] = {
                "word_limit": s_spec.get("word_limit", 120),
                "verbatims":  verbatims,
            }
            continue

        sec = {
            "label":      s_spec.get("label", s_key),
            "word_limit": s_spec.get("word_limit", 80),
            "metrics":    extract_metrics(analysis, s_spec),
            "note":       s_spec.get("note", ""),
            "qualitative": extract_qualitative(qual, s_spec),
        }

        # Distributions
        dist_path = s_spec.get("distribution_path")
        if dist_path:
            sec["distributions"] = {"main": extract_distribution(analysis, dist_path)}
        else:
            sec["distributions"] = {}

        # Extra distributions (s2_4)
        for dist_key, dist_path_extra in s_spec.get("extra_distributions", {}).items():
            sec["distributions"][dist_key] = extract_distribution(analysis, dist_path_extra)

        # Funnel table spec (s2_1) — pass through for assembler
        if "funnel_table" in s_spec:
            sec["funnel_table"] = s_spec["funnel_table"]

        # Drivers data (s5_1)
        if "drivers" in s_spec:
            sec["drivers_data"] = _build_drivers_data(analysis, s_spec["drivers"])
            sec["drivers_table"] = s_spec.get("drivers_table", {})

        sections_out[s_key] = sec

    # Scorecard rows for Parts 6 & 7
    scorecard = []
    if part_key == "part_6" and "scorecard_metrics" in spec_part:
        scorecard = _build_scorecard_6(analysis, spec_part["scorecard_metrics"])
    elif part_key == "part_7" and "scorecard_metrics" in spec_part:
        scorecard = _build_scorecard_7(analysis, spec_part["scorecard_metrics"])

    # Visuals
    visuals = []
    for v in spec_part.get("visuals", []):
        vpath = check_visual(run_id, v["file"])
        visuals.append({
            "file":    v["file"],
            "caption": v.get("caption", ""),
            "path":    str(vpath) if vpath else None,
            "exists":  vpath is not None,
        })

    return {
        "part":     part_key,
        "title":    spec_part["title"],
        "sections": sections_out,
        "scorecard": scorecard,
        "visuals":  visuals,
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def orchestrate(run_id: str, parts_filter: list = None) -> list:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    analysis, qual = load_data(run_id)
    packages = []
    for part_key, part_spec in spec["parts"].items():
        if parts_filter and part_key not in parts_filter:
            continue
        pkg = build_part_package(part_key, analysis, qual, part_spec, run_id)
        packages.append(pkg)
    return packages
