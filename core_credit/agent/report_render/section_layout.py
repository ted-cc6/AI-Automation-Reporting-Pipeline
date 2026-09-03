"""Maps CoreCreditImpactReport's already-computed, already-written fields onto the report
template's own fixed structure -- section titles, subsection order, and which subsections get
a table are all taken directly from Core_Credit_Impact_Report_Template_v2.0.pdf, not invented
here. Every WrittenText's `.text` is inserted verbatim; nothing in this file writes new prose.

Per the template's own stated design ("Tables are used only where a comparison genuinely needs
a grid"), most subsections are prose-only (dashboard visual + Analysis text). Only two places
get a generated table, because the template itself shows one: Child Wellbeing's 4.2
caregiver-vs-other table, and the Gender scorecard. Two subsections have no Analysis prose at
all and are rendered straight from their structured data instead: Business & Household
Impact's 3.3 ("What drove the improvement", theme-tagged only) and Client Voices (a pure
verbatim bank, no narrative field in its schema).
"""

from __future__ import annotations

from typing import Optional

from dashboard_visuals.lookup import find_dashboard_visual
from schemas.common import QualitativeSynthesis, Verbatim, WrittenText

from . import docx_helpers as h

# Every subsection_id the template shows a PowerBI visual for -- the one authoritative list,
# used both by _visual() below (which asserts every id it's called with is a member, so a
# typo'd or newly-added call fails a test rather than silently looking up the wrong screenshot)
# and by the orchestrator's resolve_dashboard_visuals node, which needs to know the full set
# up front rather than discovering it one render_report() call at a time.
ALL_SUBSECTION_IDS = (
    "client-profile", "executive-summary",
    "1.1", "1.2",
    "2.1", "2.2",
    "3.1", "3.2",
    "4.1", "4.2",
    "5.1", "5.2", "5.3", "5.4", "5.5",
    "6.1", "6.2", "6.3",
    "7.1", "7.2", "7.3", "7.4",
    "8.1", "8.2",
    "gender-scorecard",
    "client-voices",
)


def _caregiver_table_labels() -> list:
    """Lazy import -- driver.build_child_wellbeing pulls in the full analysis stack (LLM
    client, section_configs, etc.) just to define this one constant list; deferring the import
    to render time keeps `import report_render.section_layout` itself lightweight.
    """
    from driver.build_child_wellbeing import CAREGIVER_TABLE_LABELS

    return CAREGIVER_TABLE_LABELS


_current_dashboard_visuals: Optional[dict] = None  # see render_report()'s docstring


def _visual(doc, subsection_id: str) -> None:
    assert subsection_id in ALL_SUBSECTION_IDS, f"{subsection_id!r} is missing from ALL_SUBSECTION_IDS"
    resolved = _current_dashboard_visuals.get(subsection_id) if _current_dashboard_visuals is not None else None
    h.add_dashboard_visual(doc, resolved if resolved is not None else find_dashboard_visual(subsection_id))


def _prose(doc, written: WrittenText | None) -> None:
    if written is not None:
        h.add_body_paragraph(doc, written.text)
    else:
        h.add_body_paragraph(doc, "[ No analysis was generated for this subsection. ]", italic=True)


def _significance_label(sig) -> str:
    """Renders the real test name and p-value already computed by metrics_engine.engine's
    two_proportion_ztest (GapComparison.significance) -- confirmed the hard way that just
    printing "(sig.)" with no test or threshold named was inconsistent with how the Insurance
    report cites significance (with real p-values), and gave a reviewer nothing to check.
    Only called where a row is already known to be significant (same gating as before this
    fix); the p-value itself is what makes the claim checkable, not a bare tag.
    """
    if sig is None:
        return ""
    p_display = "<0.001" if sig.p_value < 0.001 else f"={sig.p_value:.3f}"
    return f" ({sig.method}, p{p_display})"


def _verbatim_profile(v: Verbatim) -> str:
    parts = [v.gender or "unknown gender", f"age {v.age or 'unknown'}", v.country or "unknown country"]
    if v.loan_cycle:
        parts.append(f"loan cycle {v.loan_cycle}")
    if v.branch:
        parts.append(v.branch)
    if v.segment_tags:
        parts.append(", ".join(v.segment_tags))
    return ", ".join(parts)


def add_verbatims(doc, verbatims: list) -> None:
    for v in verbatims:
        if v.english_gloss:
            # Non-English verbatim, already translated by report_assembly.translate_verbatims
            # before render -- English gloss leads so an English-speaking reviewer can read it
            # immediately, original retained underneath and labelled, per the actual client's
            # words never being silently replaced.
            h.add_body_paragraph(doc, f'"{v.english_gloss}"', italic=True)
            h.add_caption(doc, f'Original ({v.language or "untranslated"}): "{v.quote}"')
        else:
            h.add_body_paragraph(doc, f'"{v.quote}"', italic=True)
        h.add_caption(doc, f"-- {_verbatim_profile(v)}")


def add_theme_list(doc, qualitative: QualitativeSynthesis | None, top_n: int = 5) -> None:
    """Renders a QualitativeSynthesis directly (theme + frequency + representative verbatims)
    for the one subsection (3.3) whose whole content IS the theme list -- there's no separate
    Analysis prose to fall back on here.
    """
    if qualitative is None or not qualitative.themes:
        h.add_body_paragraph(doc, "[ No theme-tagged free text available for this subsection. ]", italic=True)
        return
    for theme in qualitative.themes[:top_n]:
        share = f"{theme.share_of_respondents:.0%}" if theme.share_of_respondents is not None else "n/a"
        h.add_body_paragraph(doc, f"{theme.theme} (n={theme.frequency}, {share} of respondents)")
        add_verbatims(doc, theme.representative_verbatims[:2])


SEVERITY_TIERS = ["high", "medium", "low"]


def add_protection_signals(doc, qualitative: QualitativeSynthesis | None, cap_per_tier: int = 5) -> None:
    """Groups protection_signals into high/medium/low severity tiers and caps each tier to the
    top `cap_per_tier` themes by frequency -- the template's own instruction ("cap what is shown
    to the most serious items in each tier, for example the top three to five"). A theme with no
    severity set shouldn't occur (PROTECTION_SIGNALS_TASK requires it on every theme the model
    creates), but is grouped under "Other" rather than silently dropped if it ever does.
    """
    if qualitative is None or not qualitative.themes:
        h.add_body_paragraph(
            doc, "[ No client-protection signals were identified in this wave's free text. ]", italic=True
        )
        return

    by_tier: dict = {tier: [] for tier in SEVERITY_TIERS}
    other = []
    for theme in qualitative.themes:
        (by_tier[theme.severity] if theme.severity in by_tier else other).append(theme)

    any_shown = False
    for tier in SEVERITY_TIERS + (["other"] if other else []):
        themes = other if tier == "other" else by_tier[tier]
        if not themes:
            continue
        any_shown = True
        h.add_body_paragraph(doc, f"{tier.capitalize()} severity", italic=False)
        ranked = sorted(themes, key=lambda t: t.frequency, reverse=True)[:cap_per_tier]
        for theme in ranked:
            h.add_body_paragraph(doc, f"{theme.theme} (n={theme.frequency})")
            add_verbatims(doc, theme.representative_verbatims[:2])

    if not any_shown:
        h.add_body_paragraph(
            doc, "[ No client-protection signals were identified in this wave's free text. ]", italic=True
        )


def render_client_profile(doc, section) -> None:
    h.add_section_heading(doc, "Client Profile & Methodology")
    _visual(doc, "client-profile")
    _prose(doc, section.analysis_text)


def render_executive_summary(doc, section) -> None:
    """Four columns: Theme, Score, VisionFund (benchmark-comparable basis), MFI Index Benchmark.

    The third column exists because Score and the benchmark can be on different box definitions
    (e.g. Resilience's headline 77.5% "any savings increase" vs. its 27.8% figure on the
    benchmark's stricter "very much" basis) -- a reader comparing Score against the benchmark by
    eye would get the wrong gap, and the prose below correctly uses the stricter figure. This
    column carries VisionFund's own number on the benchmark's basis: the stricter-box
    `benchmark_comparable_value` where one exists, otherwise the Score itself (the boxes match,
    or -- for the CC-011 averaged themes -- there is no single benchmark to be comparable to).
    It always prints a number; the earlier "same as Score" string read as a null to reviewers
    (CC-014).

    After CC-011 only Client Satisfaction retains an MFI Index benchmark (the five averaged
    themes carry benchmark=None, and Poverty Likelihood / Child Wellbeing never had one), so the
    last two columns read "n/a" for seven of the eight rows. The benchmark year is printed on
    the cell, not the header, so it does not imply a wave for the n/a rows (CC-015).
    """
    h.add_section_heading(doc, "Executive Summary")
    _visual(doc, "executive-summary")
    headers = ["Theme", "Score", "VisionFund (benchmark-comparable basis)", "MFI Index Benchmark"]
    rows = []
    for s in section.theme_scores:
        value = f"{s.headline_value:.0f} (NPS)" if not s.is_percentage else f"{s.headline_value:.1%}"

        bench_text = "n/a"
        if s.benchmark and s.benchmark.external_mfi_index is not None:
            bench = s.benchmark.external_mfi_index if not s.is_percentage else s.benchmark.external_mfi_index * 100
            unit = "" if not s.is_percentage else "%"
            bench_text = f"{bench:.1f}{unit}"
            if s.benchmark.external_mfi_index_year is not None:
                bench_text += f" ({s.benchmark.external_mfi_index_year})"

        if s.benchmark_comparable_value is not None:
            comparable = s.benchmark_comparable_value if not s.is_percentage else s.benchmark_comparable_value * 100
            unit = "" if not s.is_percentage else "%"
            comparable_text = f"{comparable:.1f}{unit}"
        else:
            comparable_text = value  # no stricter-box figure: the Score is already this basis

        rows.append([s.theme_name, value, comparable_text, bench_text])
    h.add_table(doc, headers, rows)
    _prose(doc, section.analysis_text)


def render_financial_access(doc, section) -> None:
    h.add_section_heading(doc, "Part 1 -- Financial Access")
    h.add_subheading(doc, "1.1 First time access to credit")
    _visual(doc, "1.1")
    _prose(doc, section.first_time_access_analysis)
    h.add_subheading(doc, "1.2 How easily clients could find another lender")
    _visual(doc, "1.2")
    _prose(doc, section.alternative_lender_hard_to_find_analysis)
    h.add_subheading(doc, "Insight for Financial Access")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_poverty_likelihood(doc, section) -> None:
    h.add_section_heading(doc, "Part 2 -- Poverty Likelihood (PPI)")
    h.add_subheading(doc, "2.1 Poverty likelihood across poverty lines")
    _visual(doc, "2.1")
    _prose(doc, section.poverty_line_shares_analysis)
    if section.na_footnote:
        # CC-016: the PPI coverage caveat used to render in small italics at the very end of
        # Part 2, well past the 2.1 figures it qualifies (Kenya on 90 of 271 clients, Zambia on
        # 32 of 281). It now sits directly under 2.1, at body size. na_footnote carries its own
        # neutral "PPI scoring coverage by country this wave" opening; this line only adds the
        # data-quality framing (CC-013: genuine scorecard outcomes, not estimates or omissions)
        # and ties it to the figures above.
        h.add_body_paragraph(
            doc,
            "These are genuine scorecard outcomes, not estimates or omissions -- incomplete PPI "
            "answers, a guide or survey-version gap, or a country where PPI was not collected. "
            "Read the 2.1 figures alongside them.",
            italic=True,
        )
        h.add_body_paragraph(doc, section.na_footnote)
    h.add_subheading(doc, "2.2 The MFI against the national poverty rate")
    _visual(doc, "2.2")
    _prose(doc, section.national_comparison_analysis)
    h.add_subheading(doc, "Insight for Poverty Likelihood")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_business_household_impact(doc, section) -> None:
    h.add_section_heading(doc, "Part 3 -- Business & Household Impact")
    h.add_subheading(doc, "3.1 Business income change")
    _visual(doc, "3.1")
    _prose(doc, section.business_income_analysis)
    h.add_subheading(doc, "3.2 Change in quality of life")
    _visual(doc, "3.2")
    _prose(doc, section.quality_of_life_analysis)
    h.add_subheading(doc, "3.3 What drove the improvement")
    add_theme_list(doc, section.qol_drivers)
    h.add_subheading(doc, "Insight for Business and Household Impact")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_child_wellbeing(doc, section) -> None:
    h.add_section_heading(doc, "Part 4 -- Child Wellbeing")
    h.add_subheading(doc, "4.1 Improved child wellbeing and what improved")
    _visual(doc, "4.1")
    _prose(doc, section.improved_child_wellbeing_analysis)
    h.add_subheading(doc, "4.2 Caregivers against other clients")
    _visual(doc, "4.2")
    headers = [
        "Outcome",
        "Caregiver %",
        "Non-caregiver %",
        "Raw gap (sig?)",
        "Country-standardised gap",
        "Composition share",
    ]
    # GapComparison itself carries no per-row label -- group_a_label is just "Caregiver" for
    # every one of these 8 rows. The real outcome names only exist as
    # driver.build_child_wellbeing.CAREGIVER_TABLE_LABELS, in the same order the driver built
    # caregiver_vs_other in; zipped back together here by position, with a hard check that the
    # two lists are still the same length so a future schema/driver change fails loudly instead
    # of silently mislabeling a row.
    labels = _caregiver_table_labels()
    if len(labels) != len(section.caregiver_vs_other):
        raise ValueError(
            f"CAREGIVER_TABLE_LABELS has {len(labels)} entries but caregiver_vs_other has "
            f"{len(section.caregiver_vs_other)} -- can't safely zip labels to rows by position."
        )
    std_by_outcome = {r.outcome: r for r in section.caregiver_standardisation}
    rows = []
    for label, row in zip(labels, section.caregiver_vs_other):
        a = f"{row.group_a_share:.1%}" if row.group_a_share is not None else "n/a"
        b = f"{row.group_b_share:.1%}" if row.group_b_share is not None else "n/a"
        gap = f"{row.gap:+.1%}" if row.gap is not None else "n/a"
        sig = _significance_label(row.significance) if row.significance and row.significance.significant else ""
        std = std_by_outcome.get(label)
        if std is None:
            std_gap = comp_share = "n/a"
        elif std.standardised_gap is None:
            std_gap = comp_share = "not computable this wave"
        else:
            std_gap = f"{std.standardised_gap:+.1%}"
            comp_share = f"{std.composition_share:.0%}" if std.composition_share is not None else "n/a"
        rows.append([label, a, b, f"{gap}{sig}", std_gap, comp_share])
    h.add_table(doc, headers, rows)
    support = section.caregiver_standardisation_support
    if support is not None:
        excluded = ", ".join(f"{c} (n={n})" for c, n in support.excluded.items()) or "none"
        h.add_caption(
            doc,
            f"Country-standardised gap: {support.method}, computed per outcome over the "
            f"{len(support.included)} countries with a non-caregiver base of {support.n_threshold} "
            f"or more. Excluded for a thin or absent non-caregiver base: {excluded}. "
            f"Composition share is the fraction of the raw gap that country mix accounts for; a "
            f"value above 100% means the standardised gap runs the other way. Standardisation "
            f"removes country as a confounder, it does not make the residual comparison causal.",
        )
    _prose(doc, section.caregiver_vs_other_analysis)
    h.add_subheading(doc, "Insight for Child Wellbeing")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_client_protection(doc, section) -> None:
    h.add_section_heading(doc, "Part 5 -- Client Protection")
    h.add_subheading(doc, "5.1 Financial worry")
    _visual(doc, "5.1")
    _prose(doc, section.financial_worry_decreased_analysis)
    h.add_subheading(doc, "5.2 Clarity of loan terms")
    _visual(doc, "5.2")
    _prose(doc, section.loan_terms_clear_analysis)
    h.add_subheading(doc, "5.3 Complaints mechanism")
    _visual(doc, "5.3")
    _prose(doc, section.complaints_mechanism_trusted_analysis)
    h.add_subheading(doc, "5.4 Fair treatment & reporting")
    _visual(doc, "5.4")
    _prose(doc, section.no_unfair_treatment_analysis)
    h.add_subheading(doc, "5.5 Reduced food intake to service the loan")
    _visual(doc, "5.5")
    _prose(doc, section.did_not_reduce_food_analysis)
    h.add_subheading(doc, "Client protection signals (free text)")
    add_protection_signals(doc, section.protection_signals)
    h.add_subheading(doc, "Insight for Client Protection")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_agency(doc, section) -> None:
    h.add_section_heading(doc, "Part 6 -- Agency")
    h.add_subheading(doc, "6.1 Achievement of the loan's purpose")
    _visual(doc, "6.1")
    _prose(doc, section.loan_purpose_achieved_analysis)
    h.add_subheading(doc, "6.2 Influence over household decisions")
    _visual(doc, "6.2")
    _prose(doc, section.household_influence_improved_analysis)
    h.add_subheading(doc, "6.3 Respect in the community")
    _visual(doc, "6.3")
    _prose(doc, section.community_respect_improved_analysis)
    h.add_subheading(doc, "Insight for Agency")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_resilience(doc, section) -> None:
    h.add_section_heading(doc, "Part 7 -- Resilience")
    h.add_subheading(doc, "7.1 Change in savings")
    _visual(doc, "7.1")
    _prose(doc, section.savings_increased_analysis)
    h.add_subheading(doc, "7.2 Shocks and their impact")
    _visual(doc, "7.2")
    _prose(doc, section.shock_incidence_analysis)
    h.add_subheading(doc, "7.3 Coping mechanisms")
    _visual(doc, "7.3")
    _prose(doc, section.coping_mechanisms_analysis)
    h.add_subheading(doc, "7.4 Effect of VisionFund on the severity of the shock")
    _visual(doc, "7.4")
    _prose(doc, section.vf_reduced_shock_severity_analysis)
    h.add_subheading(doc, "Insight for Resilience")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_client_satisfaction(doc, section) -> None:
    h.add_section_heading(doc, "Part 8 -- Client Satisfaction")
    h.add_subheading(doc, "8.1 NPS and the split")
    _visual(doc, "8.1")
    _prose(doc, section.nps_analysis)
    h.add_subheading(doc, "8.2 What drives recommendation and dissatisfaction")
    _visual(doc, "8.2")
    _prose(doc, section.drivers_analysis)
    h.add_subheading(doc, "Insight for Client Satisfaction")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_gender_scorecard(doc, section) -> None:
    h.add_section_heading(doc, "Part 9 -- Gender")
    _visual(doc, "gender-scorecard")
    headers = ["Metric", "Female %", "Male %", "Gap (if significant)"]
    rows = []
    for row in section.rows:
        f = f"{row.female_share:.1%}" if row.female_share is not None else "n/a"
        m = f"{row.male_share:.1%}" if row.male_share is not None else "n/a"
        gap = f"{row.gap:+.1%}" if row.gap is not None else "n/a"
        sig = _significance_label(row.significance) if row.significance and row.significance.significant else ""
        rows.append([row.metric_label, f, m, f"{gap}{sig}"])
    h.add_table(doc, headers, rows)
    _prose(doc, section.analysis_text)
    h.add_subheading(doc, "Insight for Gender")
    _prose(doc, section.insight_text)
    add_verbatims(doc, section.insight_verbatims)


def render_client_voices(doc, section) -> None:
    h.add_section_heading(doc, "Part 10 -- Client Voices")
    _visual(doc, "client-voices")
    h.add_subheading(doc, "Green lights (promoters)")
    if section.green_lights:
        add_verbatims(doc, section.green_lights)
    else:
        h.add_body_paragraph(doc, "[ No promoter verbatims available. ]", italic=True)
    h.add_subheading(doc, "Red flags (detractors)")
    if section.red_flags:
        add_verbatims(doc, section.red_flags)
    else:
        h.add_body_paragraph(doc, "[ No detractor verbatims available. ]", italic=True)


def render_report(doc, report, dashboard_visuals: Optional[dict] = None) -> None:
    """`dashboard_visuals`, when given, is a pre-resolved {subsection_id: DashboardVisual} map
    (e.g. from the orchestrator's resolve_dashboard_visuals node, which runs the same lookup
    independently and earlier) -- used instead of each _visual() call hitting the filesystem
    itself. Standalone/direct usage (dashboard_visuals=None) is unchanged: every _visual() call
    resolves its own screenshot via dashboard_visuals.lookup, same as before this was wired
    into the orchestrator.

    Set on a module-level variable rather than threaded through all 12 render_* functions'
    signatures -- deliberately, to avoid touching every one of them for what's an optional
    override; scoped by the try/finally below so it never leaks into an unrelated call.
    """
    global _current_dashboard_visuals
    _current_dashboard_visuals = dashboard_visuals
    try:
        h.setup_page(doc)
        h.setup_default_style(doc)
        h.setup_header(doc)
        h.setup_footer(doc, run_id=report.run_id, model_version=report.model_version)

        h.add_title(doc, f"Core Credit Impact Report -- Global Portfolio, {report.reporting_period}")
        h.add_subtitle(
            doc,
            f"Covering {report.client_profile.n_respondents:,} client responses across "
            f"{report.client_profile.n_mfis} VisionFund MFIs in {report.client_profile.n_countries} "
            f"countries. Generated: {report.generated_at}.",
        )
        h.add_caption(
            doc,
            f"The {report.client_profile.n_respondents:,} figure above is the total number of survey "
            "submissions received. Each metric and table in this report is calculated among the "
            "respondents who answered that specific question, so the base count (n) printed beside "
            "a figure may be slightly lower where some respondents left that question blank -- this "
            "is expected and is not a data error.",
        )
        h.add_divider(doc)

        render_client_profile(doc, report.client_profile)
        h.add_divider(doc)
        if report.executive_summary is not None:
            render_executive_summary(doc, report.executive_summary)
            h.add_divider(doc)
        render_financial_access(doc, report.financial_access)
        h.add_divider(doc)
        render_poverty_likelihood(doc, report.poverty_likelihood)
        h.add_divider(doc)
        render_business_household_impact(doc, report.business_household_impact)
        h.add_divider(doc)
        render_child_wellbeing(doc, report.child_wellbeing)
        h.add_divider(doc)
        render_client_protection(doc, report.client_protection)
        h.add_divider(doc)
        render_agency(doc, report.agency)
        h.add_divider(doc)
        render_resilience(doc, report.resilience)
        h.add_divider(doc)
        render_client_satisfaction(doc, report.client_satisfaction)
        h.add_divider(doc)
        if report.gender_scorecard is not None:
            render_gender_scorecard(doc, report.gender_scorecard)
            h.add_divider(doc)
        if report.client_voices is not None:
            render_client_voices(doc, report.client_voices)
    finally:
        _current_dashboard_visuals = None
