"""Per-subsection prompt configs. Word caps and framing are copied directly from the
Core Credit Impact Report Template v2.0 -- these are not our own paraphrase.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SubsectionPrompt:
    subsection_id: str
    title: str
    word_cap: int
    instructions: str


# --- Part 1: Financial Access -----------------------------------------------------------

FIRST_TIME_ACCESS = SubsectionPrompt(
    subsection_id="1.1",
    title="First time access to credit",
    word_cap=80,
    instructions=(
        "Report the share who had no prior access to a comparable loan before VisionFund. "
        "This is the headline inclusion metric. Give it overall and by gender, and note "
        "whether women make up more than their share of the clients borrowing for the first "
        "time. Bring in female household heads or households with a person with a disability "
        "only where it makes the point clearer."
    ),
)

ALTERNATIVE_LENDER_HARD_TO_FIND = SubsectionPrompt(
    subsection_id="1.2",
    title="How easily clients could find another lender",
    word_cap=70,
    instructions=(
        "Report the headline figure for clients who would find it hard to find another "
        "lender, joining very difficult and slightly difficult. Read it for the competitive "
        "moat, for retention, and for the responsibility that comes with limited competition. "
        "Note any pattern by gender or country."
    ),
)

FINANCIAL_ACCESS_INSIGHT = SubsectionPrompt(
    subsection_id="1-insight",
    title="Insight for Financial Access",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on, folding "
        "the headline figures into what they mean. Include two or three representative client "
        "verbatims with profile (gender, age, branch, loan cycle) if any are available."
    ),
)


# --- Client Profile & Methodology ----------------------------------------------------------
# Unlike every Part below, this has exactly one write step (no per-metric subsections, no
# Insight) -- the template's own structure for this section is a single Analysis block.

CLIENT_PROFILE_ANALYSIS = SubsectionPrompt(
    subsection_id="client-profile",
    title="Client Profile & Methodology",
    word_cap=120,
    instructions=(
        "Summarise the sample: give the number of respondents and the number of MFIs and "
        "countries, the gender split, age, household size, and the loan cycle mix. Include "
        "the profile breakdown by household head status, client education level, and main "
        "source of income. State which standard segments are populated in this wave, and "
        "note any conventions about the base that recur later -- for example, that PPI and "
        "other worked scores are calculated upstream and reported elsewhere as finished "
        "figures. Flag any segment that is not available in this wave."
    ),
)


# --- Executive Summary (cross-cutting) ------------------------------------------------------

EXECUTIVE_SUMMARY_ANALYSIS = SubsectionPrompt(
    subsection_id="executive-summary",
    title="Executive Summary",
    word_cap=120,
    instructions=(
        "State the eight theme scores at a glance. Where a benchmark exists, state how the "
        "figure compares with the external MFI Index by 60 Decibels. Leave out any benchmark "
        "that has no data. Lead with the two or three themes that carry the strongest impact "
        "story, and the one or two that flag a concern. The Client Satisfaction score (NPS) "
        "runs on a -100 to 100 scale, not a percentage -- never compare it directly against "
        "the other seven themes' shares."
    ),
)


# --- Part 2: Poverty Likelihood (PPI) ------------------------------------------------------

POVERTY_LIKELIHOOD_ACROSS_LINES = SubsectionPrompt(
    subsection_id="2.1",
    title="Poverty likelihood across poverty lines",
    word_cap=90,
    instructions=(
        "Report the share of clients below the $1.90/day, $2.15/day, and $3.20/day poverty "
        "lines. Interpret what the poverty profile says about who the portfolio reaches, and "
        "compare to the regional/global figures where available. Note any country or segment "
        "concentration worth flagging. State the portfolio-wide scored base (the 'Note' line "
        "gives you this) at least once. If you cite any country's figure whose label says "
        '"only N of M clients scored," you must include that coverage caveat right next to the '
        "figure, in the same sentence -- a headline number resting on a small fraction of a "
        "country's clients is not safe to state without it."
    ),
)

MFI_VS_NATIONAL_POVERTY_RATE = SubsectionPrompt(
    subsection_id="2.2",
    title="The MFI against the national poverty rate",
    word_cap=70,
    instructions=(
        "Compare the poverty likelihood of the client base with the national rate for each "
        "country served. Note where VisionFund reaches a client base that is poorer than the "
        "national average, which shows stronger targeting of the poor, and where the opposite "
        "holds. Any row marked [LOW COVERAGE: ...] must carry that same caveat when you cite "
        "its figure -- do not state a low-coverage country's number as if it were as reliable "
        "as the others."
    ),
)

POVERTY_LIKELIHOOD_INSIGHT = SubsectionPrompt(
    subsection_id="2-insight",
    title="Insight for Poverty Likelihood",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on, covering "
        "who the portfolio reaches and what that means for targeting. Name the poverty lines "
        "used and any country that stands out. State the portfolio-wide scored base at least "
        "once (see the 'Note' line in the data). If you name a specific country's figure and "
        "its label or row says it rests on low coverage, carry that caveat into your sentence."
    ),
)


# --- Part 4: Child Wellbeing ----------------------------------------------------------------

IMPROVED_CHILD_WELLBEING = SubsectionPrompt(
    subsection_id="4.1",
    title="Improved child wellbeing and what improved",
    word_cap=90,
    instructions=(
        "State the share of caregiver clients who report improved child wellbeing. Rank the "
        "top items that improved, such as healthcare access, nutrition, fewer missed school "
        "days, and supplies. Where the data makes the story clearer, name the item most "
        "associated with improvement and describe the likely pathway, for example higher "
        "income leading to school fees and then to wellbeing -- but only draw a connection "
        "the data actually supports, never a fabricated causal claim."
    ),
)

CAREGIVER_VS_OTHER = SubsectionPrompt(
    subsection_id="4.2",
    title="Caregivers against other clients",
    word_cap=80,
    instructions=(
        "Compare caregivers with other clients across the shared outcomes in the table: "
        "quality of life, financial worry, community respect, business income, loan goal "
        "achievement, household influence, savings, and the Net Promoter Score. Report both "
        "rates and the gap. Report significance only where it makes the point clearer. Note "
        "whether caregivers are reaching the households that most need a buffer."
    ),
)

CHILD_WELLBEING_INSIGHT = SubsectionPrompt(
    subsection_id="4-insight",
    title="Insight for Child Wellbeing",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on. Fold in "
        "the child wellbeing share and the widest caregiver gap. Include two or three "
        "verbatims with profile if any are available."
    ),
)


# --- Part 3: Business & Household Impact --------------------------------------------------

BUSINESS_INCOME_CHANGE = SubsectionPrompt(
    subsection_id="3.1",
    title="Business income change",
    word_cap=80,
    instructions=(
        "Report the share whose business income increased since engaging with VisionFund "
        "(top-box), using the top two boxes (very much and slightly improved), the same basis "
        "as quality of life. Give the gender pattern and any gradient across loan cycles -- "
        "later cycles should show more improvement, so flag it if they do not. When a benchmark "
        "is shown, compare the 'very much' figure specifically, since that is how the MFI Index "
        "is scored."
    ),
)

QUALITY_OF_LIFE_CHANGE = SubsectionPrompt(
    subsection_id="3.2",
    title="Change in quality of life",
    word_cap=80,
    instructions=(
        "Report the share who report an improved quality of life, using the top two boxes "
        "(very much and slightly improved). Give the gender split and any segment that stands "
        "out, and tie it back to business income above."
    ),
)

BUSINESS_HOUSEHOLD_IMPACT_INSIGHT = SubsectionPrompt(
    subsection_id="3-insight",
    title="Insight for Business and Household Impact",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on, folding "
        "the income and quality of life figures into what they mean. Include two or three "
        "verbatims with profile (gender, age, branch, loan cycle)."
    ),
)


# --- Part 5: Client Protection -------------------------------------------------------------

FINANCIAL_WORRY_DECREASED = SubsectionPrompt(
    subsection_id="5.1",
    title="Financial worry",
    word_cap=70,
    instructions=(
        "Report the share whose financial worry fell since they borrowed. Note any segment, "
        "such as clients affected by a shock or female household heads, where worry did not ease."
    ),
)

LOAN_TERMS_CLEAR = SubsectionPrompt(
    subsection_id="5.2",
    title="Clarity of loan terms",
    word_cap=70,
    instructions=(
        "Report the share who find VisionFund fees, interest rates, and penalties easy to "
        "understand and clear. Flag any pattern by education or country, because low clarity "
        "carries a risk of misselling and of clients taking on too much debt."
    ),
)

COMPLAINTS_MECHANISM_TRUSTED = SubsectionPrompt(
    subsection_id="5.3",
    title="Complaints mechanism",
    word_cap=70,
    instructions=(
        "Report the share who feel they can raise a complaint safely, at no cost, and in a way "
        "that is easy for them. A low figure is a client protection gap."
    ),
)

FAIR_TREATMENT_AND_REPORTING = SubsectionPrompt(
    subsection_id="5.4",
    title="Fair treatment & reporting",
    word_cap=80,
    instructions=(
        "Report the share who experienced no harassment, unwanted pressure, or unfair "
        "treatment from a VisionFund representative; among those who did, report whether they "
        "felt able to report it. Treat unfair-treatment incidents and non-reporting as a "
        "conduct signal for follow-up, even at low volume."
    ),
)

REDUCED_FOOD_INTAKE = SubsectionPrompt(
    subsection_id="5.5",
    title="Reduced food intake to service the loan",
    word_cap=80,
    instructions=(
        "Report the share who did NOT reduce household food to make repayments (top-box), and "
        "quantify those who did (reduced meals, portion sizes, borrowed food) -- a core "
        "over-indebtedness / client-protection flag; note any segment concentration."
    ),
)

CLIENT_PROTECTION_INSIGHT = SubsectionPrompt(
    subsection_id="5-insight",
    title="Insight for Client Protection",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on. Lead with "
        "the strongest protection indicator, and with any signal of conduct that needs follow "
        "up. Include two or three verbatims with profile if any are available."
    ),
)


# --- Part 6: Agency ------------------------------------------------------------------------

LOAN_PURPOSE_ACHIEVED = SubsectionPrompt(
    subsection_id="6.1",
    title="Achievement of the loan's purpose",
    word_cap=70,
    instructions=(
        "Report the share who achieved the purpose they took the loan for, giving the fully "
        "achieved and the partially achieved shares separately. Note the leading loan purposes "
        "and any pattern by segment or loan cycle."
    ),
)

HOUSEHOLD_INFLUENCE_IMPROVED = SubsectionPrompt(
    subsection_id="6.2",
    title="Influence over household decisions",
    word_cap=80,
    instructions=(
        "Report the share whose influence over household resource decisions improved. Lead "
        "with the gender read, because this is a core measure of women's empowerment, and "
        "describe what changed, drawing on the free text where it helps."
    ),
)

COMMUNITY_RESPECT_IMPROVED = SubsectionPrompt(
    subsection_id="6.3",
    title="Respect in the community",
    word_cap=70,
    instructions=(
        "Report the share who report improved standing in the community, using the top two "
        "boxes. Give the gender split and any country that stands out."
    ),
)

AGENCY_INSIGHT = SubsectionPrompt(
    subsection_id="6-insight",
    title="Insight for Agency",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on, covering "
        "goal achievement and empowerment, and lead with the gender read. Include two or three "
        "verbatims with profile."
    ),
)


# --- Part 7: Resilience --------------------------------------------------------------------

SAVINGS_INCREASED = SubsectionPrompt(
    subsection_id="7.1",
    title="Change in savings",
    word_cap=70,
    instructions=(
        "Report the share whose savings rose since they took the loan. Note any gradient "
        "across segments and the link to resilience below."
    ),
)

SHOCK_INCIDENCE_AND_IMPACT = SubsectionPrompt(
    subsection_id="7.2",
    title="Shocks and their impact",
    word_cap=80,
    instructions=(
        "Report the share of clients and communities that met a shock in the last 24 months, "
        "and the main impacts on income, assets, and health. Note where it concentrates by "
        "geography or climate exposure."
    ),
)

COPING_MECHANISMS = SubsectionPrompt(
    subsection_id="7.3",
    title="Coping mechanisms",
    word_cap=90,
    instructions=(
        "Report the main coping mechanisms and quantify negative coping, such as cutting food "
        "or essential spending, selling assets or livestock, taking children out of school, "
        "and migration. Flag whether it concentrates in any segment, such as clients affected "
        "by a shock, female household heads, or households with a person with a disability. "
        "This is a client protection signal. Fold in the free text on other coping."
    ),
)

VF_REDUCED_SHOCK_SEVERITY = SubsectionPrompt(
    subsection_id="7.4",
    title="Effect of VisionFund on the severity of the shock",
    word_cap=70,
    instructions=(
        "Report the share who said VisionFund services reduced the severity of the shock, "
        "joining significantly and somewhat. Read it as realized preparedness, the resilience "
        "dividend that comes with access."
    ),
)

RESILIENCE_INSIGHT = SubsectionPrompt(
    subsection_id="7-insight",
    title="Insight for Resilience",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on. Fold in "
        "savings, the share who faced a shock, and the negative coping flag. Include two or "
        "three verbatims with profile."
    ),
)


# --- Gender Scorecard (cross-cutting) -------------------------------------------------------

GENDER_SCORECARD_ANALYSIS = SubsectionPrompt(
    subsection_id="gender-scorecard",
    title="Gender scorecard",
    word_cap=100,
    instructions=(
        "Summarise where women do better or worse than men, and only where the gap matters. "
        "Note significance where it makes the point clearer. Draw out what it means for equity "
        "and the clearest action. Tie it back to first time access in Part 1 and to "
        "satisfaction in Part 8. Every row already states which gender has the higher share as "
        "a bracketed [FACT: ...] -- use that fact directly rather than comparing the two "
        "percentages yourself, and never state or imply the opposite of what it says. Use each "
        "metric's own label exactly as given; do not rename or rephrase a metric (e.g. "
        'inverting "hard to find" into "easy to find") to make a sentence read more smoothly.'
    ),
)

GENDER_INSIGHT = SubsectionPrompt(
    subsection_id="gender-insight",
    title="Insight for Gender",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on, covering "
        "the gender story for the whole report. Include two or three verbatims with profile. "
        "Every row already states which gender has the higher share as a bracketed "
        "[FACT: ...] -- use that fact directly rather than comparing the two percentages "
        "yourself, and never state or imply the opposite of what it says. Use each metric's "
        'own label exactly as given; do not rename or rephrase a metric (e.g. inverting "hard '
        'to find" into "easy to find") to make a sentence read more smoothly.'
    ),
)


# --- Part 8: Client Satisfaction -------------------------------------------------------------

NPS_AND_SPLIT = SubsectionPrompt(
    subsection_id="8.1",
    title="NPS and the split",
    word_cap=80,
    instructions=(
        "Report the headline NPS and the split into promoters, passives, and detractors, and "
        "the gender pattern. Note any country that clearly does better or worse than the rest."
    ),
)

NPS_DRIVERS = SubsectionPrompt(
    subsection_id="8.2",
    title="What drives recommendation and dissatisfaction",
    word_cap=90,
    instructions=(
        "Rank the top promoter drivers and the top detractor pain points, drawing on the "
        "theme-tagged NPS follow-up text (split by score band: 9-10, 7-8, and 0-6). Name the "
        "single fix with the most leverage."
    ),
)

CLIENT_SATISFACTION_INSIGHT = SubsectionPrompt(
    subsection_id="8-insight",
    title="Insight for Client Satisfaction",
    word_cap=120,
    instructions=(
        "Bring the section together in three to five sentences a reader can act on. Fold in "
        "the NPS and the top driver on each side, and name the fix with the most leverage. "
        "Include two or three verbatims with profile."
    ),
)
