r"""Generic graph node functions -- config-driven, so the same nodes build any section a
SectionConfig describes, not just Business & Household Impact.

Topology (see graph.py for the actual edges):

    load_data_node
        (a) fan_out_metrics (Send x N) -> compute_metric_node -> metrics_ready_node
              -> fan_out_subsection_writes (Send x N) -> write_subsection_node -> assemble_section_node
              -> write_insight_node (also feeds assemble_section_node)
        (b) route_qualitative -> EITHER theme_tag_batch_node (Send x N) -> merge_qualitative_node
                               OR       skip_qualitative_node
              -> (either path) -> write_insight_node

write_insight_node and assemble_section_node both have predecessors that complete at
different supersteps (the metrics path and the qualitative path aren't the same length, and
neither is the subsection-writes path vs the insight path) -- both are written defensively,
returning a no-op `{}` until every field they need is actually present, confirmed necessary
with a toy graph before writing this (see graph/__init__.py).
"""

from __future__ import annotations

from functools import lru_cache

import pandas as pd
from langgraph.types import Send

from benchmark_module.lookup import get_mfi_index_benchmark
from metrics_engine.engine import metric_result, top_box_mask
from metrics_engine.segments import clean_blank_strings, standard_categorical_segments
from qualitative_agent.agent import merge_batches, theme_tag_batch
from qualitative_agent.data_prep import load_free_text_responses_multi
from schemas.common import QualitativeSynthesis
from writer.chain import write_insight, write_subsection
from writer.formatting import format_metric_result
from writer.grounding import collect_acceptable_percentages

from .state import GraphState, MetricBatchInput, QualitativeBatchInput, WriteSubsectionInput


@lru_cache(maxsize=4)
def _load_df(csv_path: str) -> pd.DataFrame:
    return pd.read_csv(csv_path, dtype=str, keep_default_na=False)


# --- metrics ------------------------------------------------------------------------------


def load_data_node(state: GraphState) -> dict:
    """Deterministic: no LLM. Loads the CSV once and, if this section has a qualitative
    config, the full (or sampled) free-text dataset for it.
    """
    config = state["section_config"]
    responses: list = []
    if config.qualitative is not None:
        df = _load_df(state["csv_path"])
        responses = load_free_text_responses_multi(df, config.qualitative.source_columns)
        sample = state.get("sample")
        if sample is not None:
            responses = responses[:sample]
    return {"qualitative_responses": responses}


def fan_out_metrics(state: GraphState) -> list:
    config = state["section_config"]
    return [
        Send(
            "compute_metric_node",
            MetricBatchInput(
                metric_config=metric_config,
                csv_path=state["csv_path"],
                benchmarks_path=state["benchmarks_path"],
            ),
        )
        for metric_config in config.metrics
    ]


def compute_metric_node(payload: MetricBatchInput) -> dict:
    """Runs once per metric, in parallel with every other metric in the section."""
    metric_config = payload["metric_config"]
    df = _load_df(payload["csv_path"])
    segments = standard_categorical_segments(df)

    series = clean_blank_strings(df[metric_config.source_column])
    mask = top_box_mask(series, set(metric_config.top_box_values))

    base = None
    if metric_config.base_column:
        base_series = clean_blank_strings(df[metric_config.base_column])
        base = base_series.isin(set(metric_config.base_values))

    benchmark_comparable_mask = None
    if metric_config.benchmark_comparable_values is not None:
        benchmark_comparable_mask = top_box_mask(series, set(metric_config.benchmark_comparable_values))

    benchmark = None
    if metric_config.has_benchmark:
        benchmark = get_mfi_index_benchmark(metric_config.metric_id, payload["benchmarks_path"])

    result = metric_result(
        metric_config.metric_id,
        metric_config.label,
        mask,
        base=base,
        segments=segments,
        benchmark=benchmark,
        benchmark_comparable_mask=benchmark_comparable_mask,
    )
    return {"metric_results": {metric_config.metric_id: result}}


def metrics_ready_node(state: GraphState) -> dict:
    """Pass-through synchronization point: runs exactly once, after every Send-dispatched
    compute_metric_node has finished (same single-fire guarantee as a batch/merge join).
    Exists so the subsection-write fan-out (below) can be attached to a node that's
    guaranteed to fire once, not N times.
    """
    return {}


# --- qualitative ----------------------------------------------------------------------------


def route_qualitative(state: GraphState):
    """Either fans out to theme_tag_batch_node (real qualitative config) or routes straight
    to skip_qualitative_node (section has none) -- never both, so write_insight_node always
    gets exactly one path to a `qualitative` value, real or empty.
    """
    config = state["section_config"]
    if config.qualitative is None:
        return "skip_qualitative_node"

    responses = state["qualitative_responses"]
    batch_size = state.get("batch_size", 200)
    reasoning_effort = state.get("reasoning_effort", "high")
    batches = [responses[i : i + batch_size] for i in range(0, len(responses), batch_size)]
    return [
        Send(
            "theme_tag_batch_node",
            QualitativeBatchInput(
                section_label=config.qualitative.section_label,
                task_instructions=config.qualitative.task_instructions,
                batch_index=i,
                responses=batch,
                reasoning_effort=reasoning_effort,
            ),
        )
        for i, batch in enumerate(batches)
    ]


def theme_tag_batch_node(payload: QualitativeBatchInput) -> dict:
    result = theme_tag_batch(
        f"{payload['section_label']}[batch {payload['batch_index']}]",
        payload["responses"],
        payload["task_instructions"],
        reasoning_effort=payload["reasoning_effort"],
    )
    return {"batch_results": [result]}


def merge_qualitative_node(state: GraphState) -> dict:
    config = state["section_config"]
    total_n = len(state["qualitative_responses"])
    qualitative = merge_batches(
        config.qualitative.section_label, state["batch_results"], total_n, state.get("reasoning_effort", "high")
    )
    return {"qualitative": qualitative}


def skip_qualitative_node(state: GraphState) -> dict:
    config = state["section_config"]
    return {"qualitative": QualitativeSynthesis(source_field=config.section_id, base_n=0, themes=[])}


# --- writer -----------------------------------------------------------------------------


def fan_out_subsection_writes(state: GraphState) -> list:
    """Attached to metrics_ready_node, so this only ever runs once. Every plain (non-insight)
    SubsectionPrompt gets its own Send, formatted from exactly the metric_ids config says it
    summarizes.
    """
    config = state["section_config"]
    metric_results = state["metric_results"]
    acceptable = list(collect_acceptable_percentages(*metric_results.values()))

    sends = []
    for prompt_config in config.subsection_prompts:
        metric_ids = config.subsection_metric_ids.get(prompt_config.subsection_id, ())
        data_summary = "\n".join(format_metric_result(metric_results[mid]) for mid in metric_ids)
        sends.append(
            Send(
                "write_subsection_node",
                WriteSubsectionInput(
                    prompt_config=prompt_config,
                    data_summary=data_summary,
                    acceptable_percentages=acceptable,
                ),
            )
        )
    return sends


def write_subsection_node(payload: WriteSubsectionInput) -> dict:
    """Runs once per plain subsection, in parallel with every other subsection write."""
    out = write_subsection(
        payload["prompt_config"], payload["data_summary"], acceptable_percentages=set(payload["acceptable_percentages"])
    )
    return {"written_texts": {payload["prompt_config"].subsection_id: out}}


def write_insight_node(state: GraphState) -> dict:
    config = state["section_config"]
    metric_results = state.get("metric_results", {})
    qualitative = state.get("qualitative")

    metrics_complete = len(metric_results) == len(config.metrics)
    if not metrics_complete or qualitative is None:
        return {}  # not ready yet -- see module docstring

    acceptable = collect_acceptable_percentages(*metric_results.values(), qualitative)
    combined_summary = "\n".join(format_metric_result(metric_results[mid]) for mid in config.insight_metric_ids)
    written, verbatims = write_insight(
        config.insight_prompt, combined_summary, qualitative=qualitative, acceptable_percentages=acceptable
    )
    return {"insight_text": written, "insight_verbatims": verbatims}


# --- assembly -----------------------------------------------------------------------------


def assemble_section_node(state: GraphState) -> dict:
    config = state["section_config"]
    written_texts = state.get("written_texts", {})
    expected_subsections = set(config.written_text_fields.keys())

    if not expected_subsections.issubset(written_texts.keys()):
        return {}
    if state.get("insight_text") is None or state.get("insight_verbatims") is None:
        return {}

    kwargs = {}
    for metric_id, field_name in config.metric_schema_fields.items():
        kwargs[field_name] = state["metric_results"][metric_id]
    for subsection_id, field_name in config.written_text_fields.items():
        kwargs[field_name] = written_texts[subsection_id]
    if config.qualitative_schema_field:
        kwargs[config.qualitative_schema_field] = state["qualitative"]
    kwargs[config.insight_text_field] = state["insight_text"]
    kwargs[config.insight_verbatims_field] = state["insight_verbatims"]

    section = config.schema_class(**kwargs)
    return {"section": section}
