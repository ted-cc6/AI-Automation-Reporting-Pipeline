"""
Code-level validation rules R1–R13.
Each function takes a ReportSpec and returns a (possibly empty) list of Findings.
All functions are pure — no I/O, no side effects.
"""
from __future__ import annotations

from .errors import Category, Finding, Severity
from .models import FillMode, MetricMethod, OutputType, ReportSpec

# Variable references in these methods require the 'against' field (R6)
_AGAINST_REQUIRED = {MetricMethod.correlation, MetricMethod.significance_test, MetricMethod.gap_analysis}

# Derived-variable names that are intentionally computed from raw columns
# (composite flags, promoter flags, etc.). R5 violations for these are
# downgraded to KNOWN_GAP WARNING instead of ERROR.
_KNOWN_DERIVED_VARIABLES: set[str] = {
    "q_coping_mechanisms",  # negative coping composite (options c/d/e/f)
    "q_nps_score",          # promoter flag derived as score >= 9
    "q_claim_result",       # binary paid-claimant flag derived from single_select
}


def _loc(part_id: int, sub_id: str | None = None, metric_idx: int | None = None) -> str:
    base = f"parts[{part_id - 1}]"
    if sub_id is None:
        return base
    sub_part = f"{base}.subsections[{sub_id}]"
    if metric_idx is None:
        return sub_part
    return f"{sub_part}.metrics[{metric_idx}]"


def _sub_loc(part_id: int, subsection_id: str, metric_idx: int | None = None) -> str:
    return _loc(part_id, subsection_id, metric_idx)


# ---------------------------------------------------------------------------
# R1 — part_ids unique and exactly {1..7} in order
# ---------------------------------------------------------------------------

def check_r1(spec: ReportSpec) -> list[Finding]:
    ids = [p.part_id for p in spec.parts]
    if ids == list(range(1, 8)):
        return []
    return [
        Finding(
            rule_id="R1",
            severity=Severity.ERROR,
            location="$.parts",
            message=f"part_id sequence must be exactly [1,2,3,4,5,6,7] in order; got {ids}",
            category=Category.STRUCTURAL,
        )
    ]


# ---------------------------------------------------------------------------
# R2 — each part has exactly one N.insight subsection
# ---------------------------------------------------------------------------

def check_r2(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        insight_subs = [s for s in part.subsections if s.subsection_id == f"{part.part_id}.insight"]
        if len(insight_subs) != 1:
            findings.append(
                Finding(
                    rule_id="R2",
                    severity=Severity.ERROR,
                    location=f"parts[{part.part_id - 1}].subsections",
                    message=(
                        f"Part {part.part_id} must contain exactly one subsection with id "
                        f"'{part.part_id}.insight'; found {len(insight_subs)}"
                    ),
                    category=Category.STRUCTURAL,
                )
            )
    return findings


# ---------------------------------------------------------------------------
# R3 — subsection_id prefix matches enclosing part_id
# ---------------------------------------------------------------------------

def check_r3(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            prefix = sub.subsection_id.split(".")[0]
            if int(prefix) != part.part_id:
                findings.append(
                    Finding(
                        rule_id="R3",
                        severity=Severity.ERROR,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message=(
                            f"subsection_id '{sub.subsection_id}' prefix '{prefix}' "
                            f"does not match enclosing part_id {part.part_id}"
                        ),
                        category=Category.STRUCTURAL,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# R4 — no duplicate segment in disaggregation
# ---------------------------------------------------------------------------

def check_r4(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if not sub.disaggregation:
                continue
            seen: set[str] = set()
            for item in sub.disaggregation:
                seg = item.segment.value
                if seg in seen:
                    findings.append(
                        Finding(
                            rule_id="R4",
                            severity=Severity.ERROR,
                            location=_sub_loc(part.part_id, sub.subsection_id),
                            message=f"Duplicate segment '{seg}' in disaggregation",
                            category=Category.STRUCTURAL,
                        )
                    )
                seen.add(seg)
    return findings


# ---------------------------------------------------------------------------
# R5 — every metric variable/against must appear in source_questions
#       KNOWN_GAP: downgrade to WARNING for intentionally derived variables
# ---------------------------------------------------------------------------

def check_r5(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if not sub.metrics:
                continue
            declared = sub.source_question_refs()
            for idx, metric in enumerate(sub.metrics):
                candidates = list(metric.variables)
                if metric.against:
                    candidates.append(metric.against)
                for var in candidates:
                    if var not in declared:
                        is_known_derived = var in _KNOWN_DERIVED_VARIABLES
                        findings.append(
                            Finding(
                                rule_id="R5",
                                severity=Severity.WARNING if is_known_derived else Severity.ERROR,
                                location=_sub_loc(part.part_id, sub.subsection_id, idx),
                                message=(
                                    f"Variable '{var}' not in source_questions"
                                    + (" (derived variable — expected)" if is_known_derived else "")
                                ),
                                category=Category.KNOWN_GAP if is_known_derived else Category.REFERENTIAL_INTEGRITY,
                            )
                        )
    return findings


# ---------------------------------------------------------------------------
# R6 — correlation / significance_test / gap_analysis require `against`
# ---------------------------------------------------------------------------

def check_r6(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if not sub.metrics:
                continue
            for idx, metric in enumerate(sub.metrics):
                if metric.method in _AGAINST_REQUIRED and metric.against is None:
                    findings.append(
                        Finding(
                            rule_id="R6",
                            severity=Severity.ERROR,
                            location=_sub_loc(part.part_id, sub.subsection_id, idx),
                            message=f"method '{metric.method.value}' requires 'against' field",
                            category=Category.CONDITIONAL_FIELD,
                        )
                    )
    return findings


# ---------------------------------------------------------------------------
# R7 — frequency_rank requires top_n
# ---------------------------------------------------------------------------

def check_r7(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if not sub.metrics:
                continue
            for idx, metric in enumerate(sub.metrics):
                if metric.method == MetricMethod.frequency_rank and metric.top_n is None:
                    findings.append(
                        Finding(
                            rule_id="R7",
                            severity=Severity.ERROR,
                            location=_sub_loc(part.part_id, sub.subsection_id, idx),
                            message="method 'frequency_rank' requires 'top_n' field",
                            category=Category.CONDITIONAL_FIELD,
                        )
                    )
    return findings


# ---------------------------------------------------------------------------
# R8 — benchmark_comparison is out of scope; flag if used
# ---------------------------------------------------------------------------

def check_r8(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if not sub.metrics:
                continue
            for idx, metric in enumerate(sub.metrics):
                if metric.method == MetricMethod.benchmark_comparison:
                    findings.append(
                        Finding(
                            rule_id="R8",
                            severity=Severity.ERROR,
                            location=_sub_loc(part.part_id, sub.subsection_id, idx),
                            message=(
                                "method 'benchmark_comparison' is out of scope for this report run. "
                                "Remove the metric or change the method."
                            ),
                            category=Category.STRUCTURAL,
                        )
                    )
    return findings


# ---------------------------------------------------------------------------
# R9 — verbatims_required:true requires verbatim_count
# ---------------------------------------------------------------------------

def check_r9(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            q = sub.qualitative
            if q and q.verbatims_required and q.verbatim_count is None:
                findings.append(
                    Finding(
                        rule_id="R9",
                        severity=Severity.ERROR,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message="qualitative.verbatims_required is true but verbatim_count is not set",
                        category=Category.CONDITIONAL_FIELD,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# R10 — verbatim_block output requires qualitative.verbatims_required:true
# ---------------------------------------------------------------------------

def check_r10(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if OutputType.verbatim_block not in sub.outputs:
                continue
            q = sub.qualitative
            if q is None or not q.verbatims_required:
                findings.append(
                    Finding(
                        rule_id="R10",
                        severity=Severity.ERROR,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message=(
                            "outputs contains 'verbatim_block' but qualitative is null or "
                            "verbatims_required is false"
                        ),
                        category=Category.CONDITIONAL_FIELD,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# R11 — analysis_prose / insight_prose output requires word_cap != null
# ---------------------------------------------------------------------------

def check_r11(spec: ReportSpec) -> list[Finding]:
    prose_outputs = {OutputType.analysis_prose, OutputType.insight_prose}
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if prose_outputs.intersection(sub.outputs) and sub.word_cap is None:
                findings.append(
                    Finding(
                        rule_id="R11",
                        severity=Severity.ERROR,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message=(
                            f"outputs contains prose type(s) "
                            f"{[o.value for o in prose_outputs.intersection(sub.outputs)]} "
                            f"but word_cap is null"
                        ),
                        category=Category.CONDITIONAL_FIELD,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# R12 — benchmark_overlay:true requires benchmark_dataset_id in metadata
# ---------------------------------------------------------------------------

def check_r12(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    if spec.report_metadata.benchmark_dataset_id:
        return findings
    for part in spec.parts:
        for sub in part.subsections:
            if sub.benchmark_overlay:
                findings.append(
                    Finding(
                        rule_id="R12",
                        severity=Severity.ERROR,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message=(
                            "benchmark_overlay is true but report_metadata.benchmark_dataset_id is not set"
                        ),
                        category=Category.CONDITIONAL_FIELD,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# R13 — auto subsection with powerbi_screenshot visual → advisory WARNING
# ---------------------------------------------------------------------------

def check_r13(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for part in spec.parts:
        for sub in part.subsections:
            if (
                sub.fill_mode == FillMode.auto
                and sub.visual is not None
                and sub.visual.source.value == "powerbi_screenshot"
            ):
                findings.append(
                    Finding(
                        rule_id="R13",
                        severity=Severity.WARNING,
                        location=_sub_loc(part.part_id, sub.subsection_id),
                        message=(
                            "auto subsection references visual.source 'powerbi_screenshot'; "
                            "a human must paste this image — confirm the pipeline has an automated "
                            "screenshot extraction step or change fill_mode to hybrid/bespoke"
                        ),
                        category=Category.STRUCTURAL,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# Aggregate runner
# ---------------------------------------------------------------------------

_ALL_CHECKS = [
    check_r1, check_r2, check_r3, check_r4, check_r5,
    check_r6, check_r7, check_r8, check_r9, check_r10,
    check_r11, check_r12, check_r13,
]


def run_all_rules(spec: ReportSpec) -> list[Finding]:
    findings: list[Finding] = []
    for check in _ALL_CHECKS:
        findings.extend(check(spec))
    return findings
