"""Static mappings between our own identifiers and External Benchmarks.xlsx's own spellings.

metric_id values here match the field names already used in schemas/*.py
(e.g. FinancialAccessSection.first_time_access), so whoever wires up the
section-metrics computation later can pass the same string straight into
get_mfi_index_benchmark without inventing a second naming scheme.
"""

from __future__ import annotations

# --- Indicator (60 DB Benchmarks tab) <-> our metric_id ---------------------------

INDICATOR_NAME_TO_METRIC_ID = {
    "First Access": "first_time_access",
    "Access to Alternatives": "alternative_lender_hard_to_find",
    "Business Income": "business_income_change",
    "Quality of Life": "quality_of_life_change",
    "Financial Worry": "financial_worry_decreased",
    "Loan Understanding": "loan_terms_clear",
    "Complaints Handling Mechanism": "complaints_mechanism_trusted",
    "Fair Treatment": "no_unfair_treatment",
    "Reduced Food Intake": "did_not_reduce_food",
    "Goal Achievement": "loan_purpose_achieved_fully",
    "Respect in Community": "community_respect_improved",
    "Savings": "savings_increased",
    "Climate Shocks": "shock_incidence",
    "NPS": "nps",
}
METRIC_ID_TO_INDICATOR_NAME = {v: k for k, v in INDICATOR_NAME_TO_METRIC_ID.items()}

# Rows that exist in the sheet, or metrics named in the report template, that we
# deliberately never show an MFI Index overlay for -- reasons come straight from
# the template's own exclusion list and the sheet's own comments, not a guess.
DELIBERATELY_EXCLUDED_METRICS = {
    "improved_child_wellbeing": (
        "A Global 60 Decibels figure exists (34%), but the source sheet's own comment says it "
        "isn't comparable to our 5-point child-wellbeing scale, and the report template gives the "
        "same instruction -- excluded on purpose, not missing data."
    ),
    "reported_when_unfair": (
        "No 2025 benchmark available (per the source sheet's comment on 'Reporting Behavior'); "
        "also on the report template's own list of indicators with no MFI Index benchmark."
    ),
    "household_influence_improved": (
        "No 2025 benchmark available (per the source sheet's comment on 'Influence in Household'); "
        "also on the report template's own list of indicators with no MFI Index benchmark."
    ),
    "vf_reduced_shock_severity": (
        "No 2025 benchmark available (per the source sheet's comment on 'Realized Preparedness'); "
        "also on the report template's own list of indicators with no MFI Index benchmark."
    ),
}

# metric_ids whose scale/box-type interpretation was a best-reading guess pending confirmation
# with whoever maintains the 60 Decibels figures -- all three were confirmed correct by Lorenz
# (2026-08-05 email): 0.58 in the sheet means NPS 58, not "58% promoters"; loan_terms_clear
# compares against "strongly agree" only; loan_purpose_achieved_fully binds to "fully achieved"
# only. Nothing about the scoring logic below changed -- this dict just no longer needs to
# flag those three as provisional. Kept as an empty dict (not deleted) since
# get_mfi_index_benchmark() and PROVISIONAL_CAVEATS.get() are written to expect it to exist,
# and a future indicator could reintroduce a genuinely provisional reading.
PROVISIONAL_CAVEATS = {}

# The NPS benchmark is stored as a 0-1 fraction in the sheet like everything else; our own NPS
# score runs -100..100. This is the one place that scale conversion happens.
NPS_BENCHMARK_SCALE_FACTOR = 100

# --- Country name (either tab) <-> our 3-letter VF_Country_Code -------------------

COUNTRY_NAME_TO_CODE = {
    "Ghana": "GHA",
    "Kenya": "KEN",
    "Tanzania": "TZA",
    "India": "IND",
    "Myanmar": "MMR",
    "Philippines": "PHL",
    "Ecuador": "ECU",
    "Mexico": "MEX",
    "Malawi": "MWI",
    "Mali": "MLI",
    "Rwanda": "RWA",
    "Senegal": "SEN",
    "Uganda": "UGA",
    "Zambia": "ZMB",
    "Mongolia": "MNG",
    "Vietnam": "VNM",
    "Bolivia": "BOL",
    "Dominican Republic": "DOM",
    "Guatemala": "GTM",
    "Honduras": "HND",
}
COUNTRY_CODE_TO_NAME = {v: k for k, v in COUNTRY_NAME_TO_CODE.items()}

# --- Region name (60 DB Benchmarks tab) <-> our SegmentAxis region values ---------

# Our survey data's region field is "LACRO"; the benchmark sheet spells it "LAC". MEER has
# no regional benchmark column at all -- those ~530 respondents (Kosovo, Montenegro) only
# ever get a global comparison, which lookup.py's fallback handles.
OUR_REGION_TO_SHEET_REGION = {
    "Africa": "Africa",
    "Asia": "Asia",
    "LACRO": "LAC",
    "MEER": None,
}
