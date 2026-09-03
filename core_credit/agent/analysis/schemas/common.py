"""Shared building blocks reused across every section's structured output.

These are the "contract" types: the metrics engine, the PPI module, and
(later) the qualitative agent all produce these shapes, and the writer step
consumes them. Nothing in this file talks to pandas, an LLM, or a file on
disk -- it is pure data definition.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class SegmentAxis(str, Enum):
    """The standard client segments the template asks sections to disaggregate by."""

    OVERALL = "overall"
    FIRST_TIME_ACCESS = "first_time_access"
    LOAN_CYCLE = "loan_cycle"
    CAREGIVER = "caregiver"
    GENDER = "gender"
    FEMALE_HH_HEAD = "female_hh_head"
    PWD_HOUSEHOLD = "pwd_household"
    CLIMATE_SHOCK = "climate_shock"
    OTHER_SERVICES = "other_services"
    SAVINGS_USER = "savings_user"
    COUNTRY = "country"
    REGION = "region"


class SegmentedValue(BaseModel):
    """One cut of a metric: a segment axis/value pair with its own base size."""

    axis: SegmentAxis
    value_label: str = Field(..., description="e.g. 'Female', 'Loan cycle 3', 'Caregiver'")
    share: Optional[float] = Field(default=None, ge=0, le=1, description="Proportion, 0-1")
    mean: Optional[float] = Field(default=None, description="Mean, for scale-type metrics")
    n: int = Field(..., ge=0)


class SignificanceResult(BaseModel):
    method: str = Field(..., description="e.g. 'two-proportion z-test'")
    p_value: float
    significant: bool
    alpha: float = 0.05


class GapComparison(BaseModel):
    """A two-group comparison, e.g. caregiver vs non-caregiver, female vs male."""

    group_a_label: str
    group_a_share: Optional[float] = Field(default=None, ge=0, le=1)
    group_a_n: int
    group_b_label: str
    group_b_share: Optional[float] = Field(default=None, ge=0, le=1)
    group_b_n: int
    gap: Optional[float] = Field(default=None, description="group_a_share minus group_b_share")
    significance: Optional[SignificanceResult] = None


class BenchmarkComparison(BaseModel):
    """External/internal comparison points. All optional -- most indicators only have some subset."""

    internal_regional: Optional[float] = None
    internal_global: Optional[float] = None
    external_mfi_index: Optional[float] = None
    external_mfi_index_year: Optional[int] = None
    external_mfi_index_definition: Optional[str] = Field(
        default=None, description="Verbatim 60 Decibels definition text, for traceability against our own metric"
    )
    external_mfi_index_caveat: Optional[str] = Field(
        default=None,
        description="Flags a benchmark whose scale/box-type interpretation is provisional, pending confirmation "
        "with the source -- e.g. NPS's fraction-vs-score ambiguity. Null once confirmed.",
    )
    not_available_reason: Optional[str] = Field(
        default=None, description="Why no benchmark exists, per the template's own exclusion list"
    )


class MetricResult(BaseModel):
    """A single reportable metric: overall value, standard segment cuts, optional benchmark."""

    metric_id: str = Field(..., description="Stable key, e.g. 'first_time_access_share'")
    label: str = Field(..., description="Human-readable description of what this measures")
    overall: SegmentedValue
    by_segment: list[SegmentedValue] = Field(default_factory=list)
    benchmark: Optional[BenchmarkComparison] = None
    benchmark_comparable_value: Optional[SegmentedValue] = Field(
        default=None,
        description="The box definition that actually matches the benchmark's own scoring basis -- "
        "usually 'very much' only, since the MFI Index scores most improvement indicators on that "
        "single box while our own `overall` is a top-2-box ('very much' + 'slightly') figure. Compare "
        "`benchmark.external_mfi_index` against THIS value, not `overall`, whenever both are present.",
    )
    notes: Optional[str] = Field(default=None, description="Base/definition caveats worth surfacing")


class RankedOption(BaseModel):
    label: str
    share: float = Field(..., ge=0, le=1)
    n: int = Field(..., ge=0)


class RankedOptions(BaseModel):
    """A ranked multi-select list, e.g. 'what improved for your children'."""

    base_n: int
    options: list[RankedOption] = Field(default_factory=list)


class Verbatim(BaseModel):
    """A single client free-text quote with the profile tags the template requires."""

    quote: str
    gender: Optional[str] = None
    age: Optional[int] = None
    branch: Optional[str] = None
    country: Optional[str] = None
    loan_cycle: Optional[int] = None
    segment_tags: list[str] = Field(default_factory=list)
    source_field: str = Field(..., description="Which survey question this quote answers")
    client_id: Optional[str] = None
    language: Optional[str] = Field(
        default=None, description="The language `quote` is written in, e.g. 'English', 'Spanish', 'Kinyarwanda'"
    )
    english_gloss: Optional[str] = Field(
        default=None,
        description="English translation of `quote`, filled in for every non-English verbatim shortly before "
        "render. None while `language` is unset, and also None once set if `language` is already English.",
    )


class ThemeFinding(BaseModel):
    """One theme-tagging agent output: a cluster of free-text responses."""

    theme: str
    frequency: int = Field(..., ge=0)
    share_of_respondents: Optional[float] = Field(default=None, ge=0, le=1)
    representative_verbatims: list[Verbatim] = Field(default_factory=list)
    severity: Optional[str] = Field(
        default=None, description="For client-protection signals: high / medium / low"
    )


class QualitativeSynthesis(BaseModel):
    """Reusable qualitative-agent output block, attached to any section with free text."""

    source_field: str
    base_n: int = Field(..., description="Respondents with a non-empty answer to this field")
    themes: list[ThemeFinding] = Field(default_factory=list)


class WrittenText(BaseModel):
    """The writer chain's output for one template subsection -- the actual report prose,
    plus enough metadata to spot-check it (word count vs. the template's target, and any
    percentage claim that didn't trace back to the data it was given).
    """

    subsection_id: str = Field(..., description="e.g. '3.1', '3-insight' -- matches SubsectionPrompt.subsection_id")
    text: str
    word_count: int
    within_cap: bool = Field(..., description="Whether word_count is at or under the template's target -- a guideline, not a hard requirement")
    ungrounded_percentages: list[str] = Field(
        default_factory=list, description="Percentage claims in `text` that didn't match any value in the input data"
    )
    ungrounded_quotes: list[str] = Field(
        default_factory=list,
        description="Quoted spans in `text` that trace to no real Verbatim in the pool, whole or in part -- "
        "i.e. fabrication. Catches an invented illustrative quote, since only IDs formally resolved via "
        "used_verbatim_ids are otherwise checked against real client records. A span that is an exact "
        "contiguous fragment of a real verbatim goes in partial_quotes instead, not here.",
    )
    partial_quotes: list[str] = Field(
        default_factory=list,
        description="Quoted spans in `text` that are an exact contiguous substring of a real pool verbatim -- "
        "the client's real words, but only a fragment of them, which can change what the client actually said. "
        "Not fabrication (that is ungrounded_quotes) and deliberately NOT a _writer_violations trigger: the "
        "corrective rewrite replaces quotes rather than restoring dropped context, so it would likely make a "
        "truncation worse. Surfaced for a human reviewer to judge.",
    )
    orphan_markers: list[str] = Field(
        default_factory=list,
        description="Literal '[N]' citation-style markers left in `text` -- these look like references but "
        "resolve to nothing once the numbered pool isn't printed alongside the final prose",
    )
    banned_punctuation: list[str] = Field(
        default_factory=list,
        description="Em dashes and semicolons in `text` -- the house style bans both. One retry is attempted "
        "before this is populated; a non-empty list means the retry still didn't fully clear it",
    )
    misattributed_quotes: list[str] = Field(
        default_factory=list,
        description="Real, pool-matched quotes in `text` wrapped in a profile detail (usually country) that "
        "doesn't match that quote's actual record -- a genuine quote is not proof the attribution around it "
        "is real too. One retry is attempted before this is populated.",
    )


class SectionStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    NOT_AVAILABLE = "not_available"
