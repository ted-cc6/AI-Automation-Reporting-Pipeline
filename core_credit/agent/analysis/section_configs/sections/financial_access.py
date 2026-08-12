"""Part 1 -- Financial Access. The second full section, chosen deliberately to exercise a
genuinely different code path than Part 3: this section has NO dedicated free-text field in
the survey (ACCESS01/ACCESS02 have no follow-up open text), so qualitative=None here, and
write_insight() is expected to fall back to a plain write with zero verbatims -- a real,
worth-knowing content gap for the report, not a bug.
"""

from __future__ import annotations

from schemas.financial_access import FinancialAccessSection
from writer.section_prompts import ALTERNATIVE_LENDER_HARD_TO_FIND, FINANCIAL_ACCESS_INSIGHT, FIRST_TIME_ACCESS

from ..config import MetricConfig, SectionConfig

FINANCIAL_ACCESS_CONFIG = SectionConfig(
    section_id="financial_access",
    schema_class=FinancialAccessSection,
    metrics=(
        MetricConfig(
            metric_id="first_time_access",
            label="No prior access to a comparable loan (first-time access)",
            source_column="Financial Access/ACCESS01_resp_en",
            top_box_values=frozenset({"No"}),
            # 60dB's "First Access" definition is a direct single-category match to ours --
            # no benchmark_comparable_values needed, unlike almost every other metric.
        ),
        MetricConfig(
            metric_id="alternative_lender_hard_to_find",
            label="Would find it hard to find another lender",
            source_column="Financial Access/ACCESS02_resp_en",
            top_box_values=frozenset({"a. Very difficult", "b. Slightly difficult"}),
            # MFI Index's "Access to Alternatives" is scored on "very difficult" alone --
            # same box-type mismatch pattern as Part 3's income/QoL benchmarks.
            benchmark_comparable_values=frozenset({"a. Very difficult"}),
        ),
    ),
    metric_schema_fields={
        "first_time_access": "first_time_access",
        "alternative_lender_hard_to_find": "alternative_lender_hard_to_find",
    },
    subsection_prompts=(FIRST_TIME_ACCESS, ALTERNATIVE_LENDER_HARD_TO_FIND),
    subsection_metric_ids={
        "1.1": ("first_time_access",),
        "1.2": ("alternative_lender_hard_to_find",),
    },
    written_text_fields={
        "1.1": "first_time_access_analysis",
        "1.2": "alternative_lender_hard_to_find_analysis",
    },
    insight_prompt=FINANCIAL_ACCESS_INSIGHT,
    insight_metric_ids=("first_time_access", "alternative_lender_hard_to_find"),
    insight_text_field="insight_text",
    insight_verbatims_field="insight_verbatims",
    qualitative=None,  # no dedicated free-text field exists for this section -- see module docstring
    qualitative_schema_field=None,
    validated=True,
)
