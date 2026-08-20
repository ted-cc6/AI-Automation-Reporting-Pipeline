"""generation/orchestrator.py

Phase 2: Extract and package all data for each of 7 report parts.
"""
import json
import logging
from pathlib import Path

import yaml

from utils import get_nested, format_value, format_p_value

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent.parent
SPEC_PATH = ROOT / "generation" / "report_spec.yaml"

def _not_applicable_path(suppressed_path: str) -> str:
    """not_applicable lives as a sibling key next to suppressed in every
    result dict analysis_engine/stats.py's _base_result() produces (see
    Phase 3) -- derive its path by swapping the trailing key rather than
    requiring report_spec.yaml to declare a parallel *_not_applicable_path
    for every single metric/driver/scorecard entry. Returns "" (which
    get_nested() resolves to the given default) if suppressed_path doesn't
    end in ".suppressed" -- e.g. when a spec entry has no suppressed_path
    at all.
    """
    if suppressed_path.endswith(".suppressed"):
        return suppressed_path[: -len(".suppressed")] + ".not_applicable"
    return ""


def _resolve_population(population, report_scope: "str | None"):
    """A report_spec.yaml `population:` entry is usually a plain string
    (unconditional, shown for every scope) -- but several of them (worth_
    premium, renewal_intent) describe an Africa/Vietnam-specific product
    split ("Health & credit-life clients only; Vietnam's crop-insurance
    clients were not asked this question") that is simply FALSE for a
    LACRO-scoped report, whose clients are 100% Health product with no
    Vietnam or credit-life clients to exclude. A real generated LACRO
    report showed this exact wrong caveat throughout Parts 1/4/5/6/7 and
    the methodology appendix.

    A `population:` entry may instead be a dict keyed by report_scope (plus
    an optional "default" key for every scope not named explicitly), e.g.:
        population:
          default: "Health & credit-life clients only; ..."
          lacro: null
    Resolution order: this run's own report_scope key, else "default", else
    None (population omitted entirely -- e.g. LACRO's null above, since
    there is nothing to exclude and no caveat is needed at all).
    """
    if not isinstance(population, dict):
        return population
    if report_scope in population:
        return population[report_scope]
    return population.get("default")


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


# Coverage below this share of a metric's own declared population, on a
# metric that is NOT marked not_applicable, is far more likely a column-
# mapping bug (a question silently reading the wrong/empty/misrouted column
# for this dataset's schema) than genuine small-sample suppression --
# analysis_engine/stats.py's LOW_N_THRESHOLD (30 respondents) already handles
# ordinary small-segment suppression separately, and that's expected, not an
# error. Confirmed threshold choice: LARCO's insurance_type field, sourced
# from a claim-history question rather than product enrollment, fills at
# ~11% -- well above this 3% floor -- so this check catches something more
# broken than that near-miss, not every population-scoped edge case.
_LOW_COVERAGE_THRESHOLD = 0.03
_LOW_COVERAGE_MIN_POPULATION = 30


def _check_metric_coverage(analysis: dict, spec: dict) -> list:
    """Flag every report_spec.yaml metric whose answer coverage (n_valid /
    n_total, both siblings of `value` in every analysis_engine/stats.py
    _base_result()-shaped result) is suspiciously low relative to its own
    declared population, so a broken mapping is caught here -- loudly,
    before generation -- instead of the LLM quietly writing "data suppressed
    due to small sample size" prose about what is actually a pipeline bug.
    """
    problems = []
    for part_key, part_spec in spec.get("parts", {}).items():
        for s_key, s_spec in part_spec.get("sections", {}).items():
            for m_key, m_cfg in s_spec.get("metrics", {}).items():
                path = m_cfg.get("path", "")
                if not path.endswith(".value"):
                    continue
                base = path[: -len(".value")]
                not_app = bool(get_nested(analysis, base + ".not_applicable", default=False))
                if not_app:
                    continue
                n_valid = get_nested(analysis, base + ".n_valid")
                n_total = get_nested(analysis, base + ".n_total")
                if not isinstance(n_valid, int) or not isinstance(n_total, int) or n_total < _LOW_COVERAGE_MIN_POPULATION:
                    continue
                coverage = n_valid / n_total
                log.info(f"coverage: {part_key}.{s_key}.{m_key} = {n_valid}/{n_total} ({coverage:.1%})")
                if coverage < _LOW_COVERAGE_THRESHOLD:
                    problems.append(
                        f"{part_key}.{s_key}.{m_key}: only {n_valid}/{n_total} respondents "
                        f"({coverage:.1%}) answered, and it is not marked not_applicable — "
                        "check for a column-mapping issue before generating this report"
                    )
    return problems


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

    analysis_path = run_dir / "analysis_results.json"
    if analysis_path.exists():
        try:
            analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
            errors.extend(_check_metric_coverage(analysis, spec))
        except json.JSONDecodeError as exc:
            errors.append(f"{analysis_path} could not be parsed for coverage check: {exc}")

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
    report_scope = analysis.get("meta", {}).get("report_scope")

    for m_key, m_cfg in section_spec.get("metrics", {}).items():
        v    = get_nested(analysis, m_cfg["path"])
        sup_path = m_cfg.get("suppressed_path", "")
        sup  = bool(get_nested(analysis, sup_path, default=False))
        not_app = bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
        if not_app:
            # This question was never asked of this dataset's population at all (a
            # different survey schema, e.g. LARCO vs Africa/Vietnam, or a country-
            # exclusive question outside a single-country run's own country) --
            # omit it entirely rather than sending "NOT APPLICABLE" into the
            # prompt/table. A section with a schema-conditional counterpart metric
            # (e.g. Part 1's coverage_understanding vs product_understanding) relies
            # on exactly one of the pair surviving this drop per run.
            continue
        result[m_key] = format_value(v, m_cfg["fmt"], suppressed=sup, not_applicable=not_app)

        n_path = m_cfg.get("n_path")
        if n_path:
            n_val = get_nested(analysis, n_path)
            result[m_key + "_n"] = format_value(n_val, "count") if n_val is not None else "?"

        population = _resolve_population(m_cfg.get("population"), report_scope)
        if population:
            result[m_key + "_population"] = population

    # Driver rho/p/n for Part 4/5 sections. This flat "metrics" dict is a
    # SEPARATE representation of the same drivers _build_drivers_data() below
    # already renders correctly (that one omits not_applicable rows from the
    # table entirely) -- writer.py's "Metrics" prompt section iterates THIS
    # dict, not drivers_data, so a not_applicable driver must be skipped here
    # too or its label (e.g. "renewal_intent_rho: NOT APPLICABLE") still
    # reaches the model, redundant with the correctly-filtered DRIVERS
    # section right below it in the same prompt and a violation of "omit
    # silently, don't note that a module doesn't apply" for a region-scoped
    # report (e.g. LACRO, which never asks q_renewal_intent at all -- see
    # project_region_scoping memory). Confirmed real: this loop previously
    # had no continue, unlike the metrics loop above it in this same
    # function and _build_drivers_data() below, both of which already omit.
    for d_key, d_cfg in section_spec.get("drivers", {}).items():
        sup_path = d_cfg.get("suppressed_path", "")
        sup   = bool(get_nested(analysis, sup_path, default=False))
        not_app = bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
        if not_app:
            continue
        rho   = get_nested(analysis, d_cfg["rho_path"])
        p_val = get_nested(analysis, d_cfg["p_path"])
        n_val = get_nested(analysis, d_cfg["n_path"])
        # not_app already continue'd above, so a driver reaching here is
        # never not_applicable -- only "SUPPRESSED" (small sample) remains.
        result[d_key + "_rho"] = format_value(rho, "rho", suppressed=sup, not_applicable=False)
        result[d_key + "_p"]   = format_p_value(p_val) if (p_val is not None and not sup) else "SUPPRESSED"
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
    report_scope = analysis.get("meta", {}).get("report_scope")
    for d_key, d_cfg in drivers_spec.items():
        sup_path = d_cfg.get("suppressed_path", "")
        sup   = bool(get_nested(analysis, sup_path, default=False))
        not_app = bool(get_nested(analysis, _not_applicable_path(sup_path), default=False))
        if not_app:
            # This driver's column doesn't exist in this dataset's schema at all --
            # omit the row entirely rather than a dead "NOT APPLICABLE" table row
            # (see extract_metrics()'s identical drop for the same reasoning).
            continue
        rho   = get_nested(analysis, d_cfg["rho_path"])
        p_val = get_nested(analysis, d_cfg["p_path"])
        n_val = get_nested(analysis, d_cfg["n_path"])
        rows.append({
            "key":            d_key,
            "label":          _DRIVER_LABELS.get(d_key, d_key.replace("_", " ").title()),
            "rho":            rho,
            "p_value":        p_val,
            "n_valid":        n_val,
            "suppressed":     sup,
            "not_applicable": not_app,
            "population":     _resolve_population(d_cfg.get("population"), report_scope),
            "direction":      d_cfg.get("direction"),
        })
    # Sort by abs(rho) descending; suppressed rows go to bottom
    rows.sort(key=lambda r: (r["suppressed"], -abs(r["rho"]) if r["rho"] is not None else 0))
    return rows


# ---------------------------------------------------------------------------
# Scorecard builders (Parts 6 & 7)
# ---------------------------------------------------------------------------

def _build_scorecard_6(analysis: dict, scorecard_spec: list) -> list:
    rows = []
    report_scope = analysis.get("meta", {}).get("report_scope")
    for m in scorecard_spec:
        sup_a = bool(get_nested(analysis, m["claimant_sup"], default=False))
        sup_b = bool(get_nested(analysis, m["non_claimant_sup"], default=False))
        not_app_a = bool(get_nested(analysis, _not_applicable_path(m["claimant_sup"]), default=False))
        not_app_b = bool(get_nested(analysis, _not_applicable_path(m["non_claimant_sup"]), default=False))
        if not_app_a and not_app_b:
            # Neither group was ever asked this question -- drop the row rather
            # than a table line reading "NOT APPLICABLE" on both sides.
            continue
        val_a = format_value(get_nested(analysis, m["claimant_path"]), m["fmt"], suppressed=sup_a, not_applicable=not_app_a)
        val_b = format_value(get_nested(analysis, m["non_claimant_path"]), m["fmt"], suppressed=sup_b, not_applicable=not_app_b)
        p_val = get_nested(analysis, m["sig_path"])
        sig   = (p_val is not None and p_val < 0.05)
        rows.append({
            "label":         m["label"],
            "group_a_label": "Claimant",
            "group_a_value": val_a,
            # Not "Non-Claimant": this group is clients who experienced an
            # insured event but chose not to file (n = insured_event_base
            # minus claimants -- see part_6.py's calculate()), NOT the much
            # larger population who simply never had a claimable event.
            # "Non-Claimant" invited exactly that misreading in a real
            # generated report (its NPS 37.7 read as directly comparable to
            # the portfolio's own 48.3, which covers everyone).
            "group_b_label": "Non-Filer",
            "group_b_value": val_b,
            "sig_p":         p_val,
            "significant":   sig,
            "population":    _resolve_population(m.get("population"), report_scope),
            "sig_test_note": m.get("sig_test_note"),
        })
    return rows


def _build_scorecard_7(analysis: dict, scorecard_spec: list) -> list:
    rows = []
    report_scope = analysis.get("meta", {}).get("report_scope")
    for m in scorecard_spec:
        sup_a = bool(get_nested(analysis, m["female_sup"], default=False))
        sup_b = bool(get_nested(analysis, m["male_sup"], default=False))
        not_app_a = bool(get_nested(analysis, _not_applicable_path(m["female_sup"]), default=False))
        not_app_b = bool(get_nested(analysis, _not_applicable_path(m["male_sup"]), default=False))
        if not_app_a and not_app_b:
            continue
        val_a = format_value(get_nested(analysis, m["female_path"]), m["fmt"], suppressed=sup_a, not_applicable=not_app_a)
        val_b = format_value(get_nested(analysis, m["male_path"]), m["fmt"], suppressed=sup_b, not_applicable=not_app_b)
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
            "population":    _resolve_population(m.get("population"), report_scope),
            "sig_test_note": m.get("sig_test_note"),
        })
    return rows


def _build_trend_data(analysis: dict, trend_spec: list) -> "tuple[list, str]":
    """Part 10's wave-over-wave trend rows, shaped like
    _build_scorecard_6/7()'s output (label/group_a_*/group_b_*/sig_p/
    significant/population/sig_test_note) so writer.py's existing
    scorecard-table prompt builder and assembler.py's existing
    scorecard-table renderer can both be reused unmodified -- "group_a"/
    "group_b" become "Current Wave"/"Prior Wave" instead of two segments.
    (writer.py hardcodes those two literal group labels itself for Part 10's
    prompt text, R-012/not this session -- row["group_a_label"]/
    ["group_b_label"] below are unread by anything, kept only because every
    other scorecard-shaped row carries them.)

    Unlike every other part, part_10's current/prior/delta/significance are
    already fully pre-computed by analysis_engine/sections/part_10.py itself
    (it reads the prior run's own JSON at analysis time) -- this just
    formats what's already there, it doesn't re-derive anything.

    R-004/R-009 (session-4): comparability is a three-value status now
    ("clean"/"indicative"/"not_comparable", part_10.py's _COMPARABILITY
    table), carried on each row as `comparability` for assembler.py to
    render as its own Comparability column -- no more Sig. column, and this
    function no longer puts a real p-value into `sig_p`/`significant` for
    Part 10 at all (always None/False here). Parts 6/7 build their own rows
    through separate functions and are unaffected; writer.py's
    _build_scorecard_text() (shared by Parts 6, 7, and 10) reads sig_p
    generically and simply has nothing to quote for Part 10 rows now.

    R-005: for "clean" rows only, `group_a_value` (the table's current-wave
    figure) is the five-country comparable-subset value
    (current_common_scope), not the six-country full-scope one -- the
    number shown and the number the delta/significance test was computed
    from are now the same number, so no per-row footnote is needed to
    reconcile them (unlike the superseded version of this function, which
    had to explain the discrepancy every time). "indicative"/
    "not_comparable" rows keep `current_full_scope` for `group_a_value`
    (matching every other figure for that same indicator elsewhere in the
    report -- there is no test result to keep it consistent with instead).

    session-5 (LM3, per Lorenz): `group_b_value` for a non-"clean" row is
    now the real prior-wave figure whenever one exists, not the literal
    string "NOT COMPARABLE" -- suppressing a real number just because the
    comparison isn't rigorous defeated the point of a three-value
    Comparability column ("so we can SHOW both numbers and label the
    quality of the comparison, rather than suppressing one side"). No
    delta or significance test is computed for these rows either way (see
    part_10.py's _compare_indicator()) -- only what's DISPLAYED changed.
    validate_output.py's `_non_comparable_labels()` was updated in the same
    session to key off `comparability != "clean"` instead of the now-
    unreliable `group_b_value == "NOT COMPARABLE"` string match, so the
    comparative-language ban on these rows' generated narrative still
    applies.

    Returns (rows, scope_note) -- scope_note is the single, table-level
    sentence naming which row(s) are five-country and why Dominican
    Republic is excluded from them (R-005: stated once near the table, not
    repeated per row); "" if no clean row produced a comparison this run
    (no prior wave, or every clean indicator's own data was missing).
    """
    part_10 = get_nested(analysis, "parts.part_10", default=None) or {}
    current = part_10.get("current", {})
    comparison = part_10.get("comparison") or {}
    prior_available = bool(part_10.get("prior_available"))

    rows = []
    clean_labels_with_comparison = []
    for ind in trend_spec:
        key, label, fmt = ind["key"], ind["label"], ind["fmt"]
        cur = current.get(key, {})
        val_a = format_value(
            cur.get("value"), fmt,
            suppressed=bool(cur.get("suppressed", False)),
            not_applicable=bool(cur.get("not_applicable", False)),
        )

        val_b = "N/A (no prior wave)"
        comparability = None
        footnote = None
        if prior_available and key in comparison:
            comp = comparison[key]
            comparability = comp.get("comparability")
            reason = comp.get("comparability_reason")
            prior = comp.get("prior") or {}
            val_b = format_value(
                prior.get("value"), fmt,
                suppressed=bool(prior.get("suppressed", False)),
                not_applicable=bool(prior.get("not_applicable", False)),
            )

            if comparability != "clean":
                # session-5 (LM3, per Lorenz): both waves' real figures are
                # shown here -- val_a (computed above, from current_full)
                # and val_b (from prior, just above) -- whenever they
                # exist. The earlier version of this branch hardcoded
                # val_b to the literal string "NOT COMPARABLE", discarding
                # a real 2025 figure for access_to_alternatives/
                # child_wellbeing_improvement even though the instrument
                # change that makes them "indicative" doesn't mean the
                # number itself is missing -- that suppression defeated
                # the entire point of a three-value Comparability column:
                # "so we can SHOW both numbers and label the quality of
                # the comparison, rather than suppressing one side." No
                # delta or significance test is computed either way (see
                # part_10.py's _compare_indicator()) -- only whether a
                # real number is DISPLAYED changed, not what's tested.
                #
                # "Indicative" and "not_comparable" still read differently
                # to a reader even though neither attempts a delta (R-004:
                # the column already distinguishes them; the footnote
                # prose should too, not just repeat "not comparable" for
                # both).
                prefix = (
                    "Indicative only, not a rigorous comparison"
                    if comparability == "indicative" else
                    "Not comparable to the prior wave"
                )
                reason_clause = f": {reason}" if reason else " (instrument changed)"
                footnote = (
                    f"{prefix}{reason_clause}. Both figures are shown for reference, not as a "
                    "tested change -- do not use comparative language (rose, fell, improved, "
                    "declined, increased, decreased, up, down, since last year) to describe the "
                    "difference between them."
                )
                # product_understanding on the 2026 unified schema: the
                # CURRENT wave itself has no figure at all (not merely an
                # incompatible one) -- val_a already reads NOT APPLICABLE
                # (computed above from cur's own not_applicable flag), but
                # say so explicitly here too, since otherwise a reader
                # comparing this footnote against a row showing two real
                # numbers (access_to_alternatives, child_wellbeing) could
                # assume the same "reference only" framing implies a 2026
                # figure exists somewhere it just isn't showing.
                if bool(cur.get("not_applicable", False)):
                    footnote += (
                        " This wave's format has no figure for this indicator at all, in the "
                        "form it is defined from -- only the prior wave's own figure is available."
                    )
            else:
                # R-005: this row's own current-wave value is the five-
                # country comparable subset, the same base the delta was
                # computed on -- not the six-country current_full_scope
                # every other row (and every other figure in the report)
                # uses. See scope_note below for the one-time DR exclusion
                # statement this replaces per-row footnote text with.
                common = comp.get("current_common_scope") or {}
                val_a = format_value(
                    common.get("value"), fmt,
                    suppressed=bool(common.get("suppressed", False)),
                    not_applicable=bool(common.get("not_applicable", False)),
                )
                clean_labels_with_comparison.append(label)
                footnote = reason

                # Definition-match mismatch (see analysis_engine/sections/
                # part_10.py's _compare_indicator()) still needs flagging
                # prominently -- a changed question/scale/base between
                # waves is a real problem independent of significance.
                if comp.get("definition_match") is False:
                    mismatch = (
                        "DEFINITION MISMATCH: this indicator's underlying question, scale, "
                        "or population base differs between the current and prior wave -- "
                        "the comparison above may not be measuring the same thing both times."
                    )
                    footnote = f"{footnote} {mismatch}" if footnote else mismatch

        rows.append({
            "label":         label,
            "group_a_label": "Current Wave",
            "group_a_value": val_a,
            "group_b_label": "Prior Wave",
            "group_b_value": val_b,
            "sig_p":         None,
            "significant":   False,
            "population":    None,
            "sig_test_note": footnote,
            "comparability": comparability,
        })

    scope_note = ""
    if clean_labels_with_comparison:
        scope_note = (
            f"{' and '.join(clean_labels_with_comparison)} report the five countries surveyed "
            "in both waves; Dominican Republic is new in 2026 and excluded from those row(s), "
            "with no 2025 counterpart."
        )
    return rows, scope_note


def _build_scorecard_5(analysis: dict, scorecard_spec: list) -> list:
    """Part 5's caregiver vs non-caregiver comparison (financial stress & healthcare access)."""
    rows = []
    report_scope = analysis.get("meta", {}).get("report_scope")
    for m in scorecard_spec:
        sup_a = bool(get_nested(analysis, m["caregiver_sup"], default=False))
        sup_b = bool(get_nested(analysis, m["non_caregiver_sup"], default=False))
        not_app_a = bool(get_nested(analysis, _not_applicable_path(m["caregiver_sup"]), default=False))
        not_app_b = bool(get_nested(analysis, _not_applicable_path(m["non_caregiver_sup"]), default=False))
        if not_app_a and not_app_b:
            continue
        val_a = format_value(get_nested(analysis, m["caregiver_path"]), m["fmt"], suppressed=sup_a, not_applicable=not_app_a)
        val_b = format_value(get_nested(analysis, m["non_caregiver_path"]), m["fmt"], suppressed=sup_b, not_applicable=not_app_b)
        p_val = get_nested(analysis, m["sig_path"])
        sig   = (p_val is not None and p_val < 0.05)
        rows.append({
            "label":         m["label"],
            "group_a_label": "Caregiver",
            "group_a_value": val_a,
            "group_b_label": "Non-Caregiver",
            "group_b_value": val_b,
            "sig_p":         p_val,
            "significant":   sig,
            "population":    _resolve_population(m.get("population"), report_scope),
            "sig_test_note": m.get("sig_test_note"),
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
            # Extract verbatims + the section-scoped theme/driver/sentiment
            # summary from qual (see qualitative/llm_call.py Task 5B)
            verb_section = s_spec.get("verbatim_section", "")
            verbatims = []
            insight_summary = {}
            if qual and verb_section:
                verbatims = qual.get("section_verbatims", {}).get(verb_section, [])
                insight_summary = qual.get("section_insights", {}).get(verb_section, {})
            sections_out[s_key] = {
                "word_limit": s_spec.get("word_limit", 120),
                "verbatims":  verbatims,
                "insight_summary": insight_summary,
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

        # Drivers data (s5_1, s4_3)
        if "drivers" in s_spec:
            sec["drivers_data"] = _build_drivers_data(analysis, s_spec["drivers"])
            sec["drivers_table"] = s_spec.get("drivers_table", {})
            sec["drivers_outcome_label"] = s_spec.get("drivers_outcome_label", "child wellbeing")

        sections_out[s_key] = sec

    # Scorecard rows for Parts 5, 6 & 7
    scorecard = []
    groups: dict = {}
    trend_scope_note = ""
    if part_key == "part_5" and "scorecard_metrics" in spec_part:
        scorecard = _build_scorecard_5(analysis, spec_part["scorecard_metrics"])
        groups = get_nested(analysis, "parts.part_5.caregiver_comparison.groups", default={}) or {}
    elif part_key == "part_6" and "scorecard_metrics" in spec_part:
        scorecard = _build_scorecard_6(analysis, spec_part["scorecard_metrics"])
        groups = get_nested(analysis, "parts.part_6.groups", default={}) or {}
    elif part_key == "part_7" and "scorecard_metrics" in spec_part:
        scorecard = _build_scorecard_7(analysis, spec_part["scorecard_metrics"])
        groups = get_nested(analysis, "parts.part_7.groups", default={}) or {}
    elif part_key == "part_10" and "trend_indicators" in spec_part:
        # No groups() dict -- unlike Parts 5/6/7's segments, "current wave"
        # vs "prior wave" isn't a single fixed N (each indicator has its own
        # base/suppression), so a single per-table N in the header would be
        # misleading here; build_part_10() renders plain "Current Wave"/
        # "Prior Wave" column headers with no n= suffix.
        scorecard, trend_scope_note = _build_trend_data(analysis, spec_part["trend_indicators"])

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
        "groups":   groups,
        "visuals":  visuals,
        "trend_scope_note": trend_scope_note,
    }


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def default_parts_filter(spec: dict, analysis: dict) -> list:
    """Which report_spec.yaml part keys have real analysis data for this run.

    report_spec.yaml lists every part (including the conditionally-gated
    ones -- Parts 9-12), but a part only has real data when
    run_analysis.py's build_sections() actually computed it for this run
    (Part 9/10: report_scope=="lacro" or dataset_schema=="larco", Part 10
    additionally on --prior-run-id; Part 11/12: report_scope=="africa" --
    see run_analysis.py). Deriving the filter from analysis_results.json's
    own `parts` keys, instead of re-deriving those conditions a second time
    here (or hardcoding which part keys are "the conditional ones" -- a
    list that has to be remembered and updated every time a new
    conditionally-gated part is added, which this filter itself missed for
    Part 11/12 until caught against real LACRO-scope output), keeps every
    part in lockstep with build_sections() by construction. The always-on
    parts (about_survey, Parts 1-8) are unconditionally in `available` too,
    since build_sections() always includes them -- this one rule covers
    both cases uniformly.
    """
    available = set(analysis.get("parts", {}))
    return [k for k in spec["parts"] if k in available]


def orchestrate(run_id: str, parts_filter: list = None) -> list:
    spec = yaml.safe_load(SPEC_PATH.read_text(encoding="utf-8"))
    analysis, qual = load_data(run_id)

    # An explicit parts_filter (e.g. run_generation.py's --parts) always
    # bypasses default_parts_filter() and is used as-is.
    if parts_filter is None:
        parts_filter = default_parts_filter(spec, analysis)

    packages = []
    for part_key, part_spec in spec["parts"].items():
        if parts_filter and part_key not in parts_filter:
            continue
        pkg = build_part_package(part_key, analysis, qual, part_spec, run_id)
        packages.append(pkg)
    return packages
