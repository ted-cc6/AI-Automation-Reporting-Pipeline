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
from metrics_engine.engine import metric_result, multiselect_distribution, top_box_mask
from metrics_engine.segments import clean_blank_strings, standard_categorical_segments
from qualitative_agent.agent import merge_batches, theme_tag_batch
from qualitative_agent.data_prep import load_free_text_responses_multi
from schemas.common import QualitativeSynthesis, SegmentAxis
from writer.chain import write_insight, write_subsection
from writer.formatting import format_metric_result, format_ranked_options
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
    """Synchronization point: runs exactly once, after every Send-dispatched compute_metric_node
    has finished (same single-fire guarantee as a batch/merge join). The subsection-write fan-out
    is attached here so it fires once, not N times.

    Also computes the section's ranked multi-select distributions (CC-024) -- pure pandas, cheap,
    one to two per section at most, so serial here rather than a second Send fan-out. Their
    output is on state before fan_out_subsection_writes / assemble_section_node read it.
    """
    config = state["section_config"]
    if not config.ranked_metrics:
        return {}
    df = _load_df(state["csv_path"])
    ranked: dict = {}
    for rm in config.ranked_metrics:
        slots = [clean_blank_strings(df[c]) for c in rm.slot_columns]
        base = None
        if rm.base_column:
            base = clean_blank_strings(df[rm.base_column]).isin(set(rm.base_values or ()))
        ranked[rm.metric_id] = multiselect_distribution(slots, base=base, exclude_labels=rm.exclude_labels)
    return {"ranked_metric_results": ranked}


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
    ranked_results = state.get("ranked_metric_results", {})
    ranked_labels = {rm.metric_id: rm.label for rm in config.ranked_metrics}
    acceptable = list(collect_acceptable_percentages(*metric_results.values(), *ranked_results.values()))

    sends = []
    for prompt_config in config.subsection_prompts:
        metric_ids = config.subsection_metric_ids.get(prompt_config.subsection_id, ())
        blocks = []
        for mid in metric_ids:
            if mid in metric_results:
                blocks.append(format_metric_result(metric_results[mid]))
            elif mid in ranked_results:
                blocks.append(format_ranked_options(ranked_labels[mid], ranked_results[mid]))
        data_summary = "\n".join(blocks)
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


# CC-012: Core Credit has no shared low-n constant, so this mirrors the Insurance pipeline's
# analysis_engine.stats.LOW_N_THRESHOLD. A per-country cell on any protection indicator below
# this base is dropped from that country's average rather than silently averaged in.
_LOW_N_THRESHOLD = 30
# A country needs at least this many of the six protection indicators above _LOW_N_THRESHOLD
# before it can be NAMED as the highest-scoring country. Reporting Behavior is denominated on
# clients who experienced unfair treatment (~267 globally across 21 countries), so nearly every
# country is single-digit on that one indicator alone; requiring all six would leave no country
# rankable, so a country ranks on >= 5 solid indicators and Reporting Behavior folds in only
# where its base is real.
_CP_MIN_INDICATORS_TO_RANK = 5

# Readable names for the six protection indicators, for the insight data block.
_CP_INDICATOR_LABELS = {
    "financial_worry_decreased": "financial worry",
    "loan_terms_clear": "loan understanding",
    "complaints_mechanism_trusted": "complaints mechanism",
    "no_unfair_treatment": "fair treatment",
    "reported_when_unfair": "reporting behaviour",
    "did_not_reduce_food": "reduced food intake",
}


def _client_protection_country_scores(metric_results: dict, indicator_ids) -> list:
    """Per-country unweighted mean of the six client-protection indicators, computed from each
    metric's own COUNTRY segment cuts. Returns a list of dicts sorted best-first:

      {country, avg, k, n_ind, rankable,
       thin    -- indicator_ids present but dropped for base < _LOW_N_THRESHOLD,
       absent  -- indicator_ids with no country cell at all (for reporting behaviour that means
                  no client there reported experiencing unfair treatment -- a clean record, not
                  a gap in the data)}
    """
    from collections import defaultdict

    cells: dict = defaultdict(dict)  # country -> {indicator_id: (share, n)}
    for mid in indicator_ids:
        mr = metric_results.get(mid)
        if mr is None:
            continue
        for sv in mr.by_segment:
            if sv.axis == SegmentAxis.COUNTRY and sv.share is not None:
                cells[sv.value_label][mid] = (sv.share, sv.n)

    rows = []
    for country, per_indicator in cells.items():
        usable = {mid: v for mid, v in per_indicator.items() if v[1] >= _LOW_N_THRESHOLD}
        thin = sorted(set(per_indicator) - set(usable))
        absent = sorted(set(indicator_ids) - set(per_indicator))
        avg = sum(share for share, _ in usable.values()) / len(usable) if usable else None
        rows.append(
            {
                "country": country,
                "avg": avg,
                "k": len(usable),
                "n_ind": len(indicator_ids),
                "thin": thin,
                "absent": absent,
                "rankable": len(usable) >= _CP_MIN_INDICATORS_TO_RANK,
            }
        )
    rows.sort(key=lambda r: (r["avg"] is not None, r["avg"] or 0.0), reverse=True)
    return rows


def _cp_labels(ids) -> str:
    return ", ".join(_CP_INDICATOR_LABELS.get(i, i) for i in ids)


def _format_client_protection_country_block(rows: list) -> str:
    lines = [
        "Six-indicator client-protection average by country (unweighted mean of the six 5.x "
        f"indicators above; a country's per-indicator cell is dropped when its base is below "
        f"n={_LOW_N_THRESHOLD}, and a country is not rankable unless at least "
        f"{_CP_MIN_INDICATORS_TO_RANK} of 6 cells survive):"
    ]
    for r in rows:
        pct = f"{r['avg']:.1%}" if r["avg"] is not None else "no usable data"
        notes = []
        if r["thin"]:
            notes.append(f"low-n dropped: {_cp_labels(r['thin'])}")
        if r["absent"]:
            notes.append(f"no cell: {_cp_labels(r['absent'])}")
        note = f" ({'; '.join(notes)})" if notes else ""
        flag = "" if r["rankable"] else "  [coverage too thin to rank]"
        lines.append(f"  - {r['country']}: {pct} over {r['k']} of {r['n_ind']} indicators{note}{flag}")

    full = [r["country"] for r in rows if r["k"] == r["n_ind"]]
    n_ind = rows[0]["n_ind"] if rows else 6
    lines.append(
        f"State in the Insight that only {', '.join(full) if full else 'no country'} "
        f"{'is' if len(full) == 1 else 'are'} scored on all {n_ind} protection indicators above "
        f"n={_LOW_N_THRESHOLD}; every other country's average, including the highest, omits reporting "
        f"behaviour because its base (clients who experienced unfair treatment) is below n={_LOW_N_THRESHOLD} "
        f"or is zero."
    )

    rankable = [r for r in rows if r["rankable"] and r["avg"] is not None]
    if rankable:
        top = rankable[0]
        line = (
            f"Highest client-protection score among adequately-covered countries: {top['country']} at "
            f"{top['avg']:.1%} (mean of {top['k']} of {top['n_ind']} indicators). Name THIS country as the "
            f"strongest on client protection in the Insight, and describe the score as a multi-indicator "
            f"average, not a single figure."
        )
        if "reported_when_unfair" in top["absent"]:
            line += (
                " Note in the prose that this average omits reporting behaviour because no client there "
                "reported experiencing unfair treatment -- a clean conduct record, but it means the country "
                "is not scored on how it handles complaints from mistreated clients, so its lead is partly "
                "the absence of that indicator."
            )
        elif "reported_when_unfair" in top["thin"]:
            line += " Note that this average omits reporting behaviour, whose base was below the n threshold there."
        lines.append(line)
    else:
        lines.append(
            "No country has adequate indicator coverage this wave -- do NOT name a highest-protection "
            "country in the Insight."
        )
    return "\n".join(lines)


def write_insight_node(state: GraphState) -> dict:
    config = state["section_config"]
    metric_results = state.get("metric_results", {})
    qualitative = state.get("qualitative")

    metrics_complete = len(metric_results) == len(config.metrics)
    if not metrics_complete or qualitative is None:
        return {}  # not ready yet -- see module docstring

    acceptable = collect_acceptable_percentages(*metric_results.values(), qualitative)
    combined_summary = "\n".join(format_metric_result(metric_results[mid]) for mid in config.insight_metric_ids)

    if config.section_id == "client_protection":
        # CC-012: give the Part 5 Insight a per-country six-indicator protection average so it can
        # name the strongest country. The per-country averages are derived, so whitelist them for
        # the grounding check (per-indicator country shares are already covered by
        # collect_acceptable_percentages via MetricResult.by_segment).
        cp_rows = _client_protection_country_scores(metric_results, config.insight_metric_ids)
        combined_summary += "\n\n" + _format_client_protection_country_block(cp_rows)
        for r in cp_rows:
            if r["avg"] is not None:
                acceptable |= {round(r["avg"] * 100), round(r["avg"] * 100, 1)}

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
    if config.ranked_metrics and len(state.get("ranked_metric_results", {})) != len(config.ranked_metrics):
        return {}

    kwargs = {}
    for metric_id, field_name in config.metric_schema_fields.items():
        kwargs[field_name] = state["metric_results"][metric_id]
    for metric_id, field_name in config.ranked_metric_schema_fields.items():
        kwargs[field_name] = state["ranked_metric_results"][metric_id]
    for subsection_id, field_name in config.written_text_fields.items():
        kwargs[field_name] = written_texts[subsection_id]
    if config.qualitative_schema_field:
        kwargs[config.qualitative_schema_field] = state["qualitative"]
    kwargs[config.insight_text_field] = state["insight_text"]
    kwargs[config.insight_verbatims_field] = state["insight_verbatims"]

    section = config.schema_class(**kwargs)
    return {"section": section}
