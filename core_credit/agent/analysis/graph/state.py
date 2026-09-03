"""Graph state for the generic, config-driven section builder.

The pandas DataFrame never enters this state -- only a CSV path does; nodes that need it load
it once via a cached loader keyed on the path (see nodes.py). Everything that used to be two
hardcoded fields in the Part-3-only version of this file (income_result/qol_result,
income_analysis/qol_analysis) is now a dict keyed by metric_id / subsection_id, since a
section can have any number of metrics and subsections -- SectionConfig is what tells the
nodes how many of each to expect and where to route each result.
"""

from __future__ import annotations

import operator
from typing import Annotated

from typing_extensions import TypedDict

from schemas.common import QualitativeSynthesis, Verbatim, WrittenText
from section_configs.config import MetricConfig, SectionConfig
from writer.section_prompts import SubsectionPrompt


class MetricBatchInput(TypedDict):
    """Send() payload for computing one metric -- independent metrics run in parallel."""

    metric_config: MetricConfig
    csv_path: str
    benchmarks_path: str


class QualitativeBatchInput(TypedDict):
    """Send() payload for one batch of free-text responses."""

    section_label: str
    task_instructions: str
    batch_index: int
    responses: list
    reasoning_effort: str


class WriteSubsectionInput(TypedDict):
    """Send() payload for one plain (non-insight) subsection write. Carries the full
    SubsectionPrompt (not just its id) because a Send payload is the entire input the target
    node receives -- it has no separate access to graph state to look anything up.
    """

    prompt_config: SubsectionPrompt
    data_summary: str
    acceptable_percentages: list


class GraphState(TypedDict, total=False):
    # --- inputs (set once, at graph.invoke time) ---
    section_config: SectionConfig
    csv_path: str
    benchmarks_path: str
    batch_size: int
    reasoning_effort: str
    sample: int  # optional: truncate the free-text dataset to the first N responses (smoke tests)

    # --- derived by load_data_node ---
    qualitative_responses: list  # list[FreeTextResponse], empty if the section has no qualitative config

    # --- filled by the Send-fanned-out metric nodes; merged across all of them ---
    metric_results: Annotated[dict, operator.or_]  # metric_id -> MetricResult

    # --- filled once by metrics_ready_node (CC-024); empty unless the section has ranked_metrics ---
    ranked_metric_results: dict  # ranked metric_id -> RankedOptions

    # --- filled by the Send-fanned-out qualitative batch nodes; concatenated across all of them ---
    batch_results: Annotated[list, operator.add]

    # --- filled by merge_qualitative_node, or immediately by skip_qualitative_node ---
    qualitative: QualitativeSynthesis

    # --- filled by the Send-fanned-out subsection write nodes; merged across all of them ---
    written_texts: Annotated[dict, operator.or_]  # subsection_id -> WrittenText

    # --- filled by write_insight_node ---
    insight_text: WrittenText
    insight_verbatims: list  # list[Verbatim]

    # --- filled by assemble_section_node, once every field above the config expects is present ---
    section: object
