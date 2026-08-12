"""analysis_engine/sections/about_survey.py — "About This Survey" section.

Deterministic respondent-composition summary (country, product mix, age,
sex, fieldwork dates) -- pure descriptive statistics from the dataset, no LLM
call involved anywhere in its pipeline (see generation/assembler.py's
_add_about_survey_section(), which renders this section's JSON directly with
no report_spec.yaml entry, no orchestrator.py package, no writer.py prompt).
Runs for every dataset schema (Africa/Vietnam and LARCO alike) -- unlike
Parts 9/10, this is not LARCO-only.
"""
import logging

import pandas as pd

from analysis_engine.segments import COL_SEX

log = logging.getLogger("analysis_engine.sections.about_survey")

COL_COUNTRY = "country"
COL_AGE = "q_client_age"
COL_INTERVIEW_START = "interview_start"

# Product-mix classification is derived from these three flags (each schema's
# data_loader_*/column_mapping.csv maps its own raw questions onto them), not
# from the raw insurance_type/insurance_type_raw text column -- LARCO's
# insurance_type is populated from a CLAIM-history question (~87% NaN, since
# most respondents never filed a claim), not a product-enrollment question,
# so it would misrepresent the vast majority of LARCO respondents as
# "unclassified" when they simply never claimed. is_health/is_crop/
# is_credit_life have the same LARCO coverage gap for the same underlying
# reason -- _PRODUCT_MIX_MIN_COVERAGE below guards against rendering a
# product-mix table built from an unreliable minority of respondents.
_PRODUCT_FLAGS = [
    ("health", "is_health"),
    ("crop", "is_crop"),
    ("credit_life", "is_credit_life"),
]
_PRODUCT_MIX_MIN_COVERAGE = 0.5


def _by_country(df: pd.DataFrame) -> list:
    if COL_COUNTRY not in df.columns:
        return []
    n_total = len(df)
    vc = df[COL_COUNTRY].value_counts()
    return [
        {"country": str(c), "n": int(n), "pct": n / n_total if n_total > 0 else 0.0}
        for c, n in vc.items()
    ]


def _product_mix(df: pd.DataFrame) -> dict:
    n_total = len(df)
    available_flags = [(label, col) for label, col in _PRODUCT_FLAGS if col in df.columns]
    if not available_flags:
        return {"available": False, "reason": "no product-classification columns in this schema",
                "n_classified": 0, "n_total": n_total, "coverage": 0.0, "distribution": []}

    n_classified = 0
    distribution = []
    for label, col in available_flags:
        n = int((df[col] == True).sum())  # noqa: E712
        n_classified += n
        distribution.append({"product": label, "n": n, "pct": n / n_total if n_total > 0 else 0.0})

    coverage = n_classified / n_total if n_total > 0 else 0.0
    available = coverage >= _PRODUCT_MIX_MIN_COVERAGE
    return {
        "available": available,
        "reason": None if available else (
            f"only {coverage:.0%} of respondents have a classified product on file in this "
            "dataset's schema (product enrollment is not captured as a reliable single field "
            "here) -- omitted rather than shown as mostly unclassified"
        ),
        "n_classified": n_classified,
        "n_total": n_total,
        "coverage": coverage,
        "distribution": distribution if available else [],
    }


def _age_summary(df: pd.DataFrame) -> dict:
    if COL_AGE not in df.columns:
        return {"n_valid": 0, "mean": None, "median": None, "min": None, "max": None}
    valid = df[COL_AGE].dropna()
    if len(valid) == 0:
        return {"n_valid": 0, "mean": None, "median": None, "min": None, "max": None}
    return {
        "n_valid": int(len(valid)),
        "mean":   float(valid.mean()),
        "median": float(valid.median()),
        "min":    int(valid.min()),
        "max":    int(valid.max()),
    }


def _by_sex(df: pd.DataFrame) -> list:
    if COL_SEX not in df.columns:
        return []
    n_total_valid = df[COL_SEX].notna().sum()
    if n_total_valid == 0:
        return []
    vc = df[COL_SEX].value_counts()
    return [
        {"sex": str(s), "n": int(n), "pct": n / n_total_valid}
        for s, n in vc.items()
    ]


def _fieldwork_window(df: pd.DataFrame) -> dict:
    if COL_INTERVIEW_START not in df.columns:
        return {"available": False, "start_date": None, "end_date": None}
    parsed = pd.to_datetime(df[COL_INTERVIEW_START], utc=True, errors="coerce")
    valid = parsed.dropna()
    if len(valid) == 0:
        return {"available": False, "start_date": None, "end_date": None}
    return {
        "available":  True,
        "start_date": valid.min().strftime("%Y-%m-%d"),
        "end_date":   valid.max().strftime("%Y-%m-%d"),
    }


def calculate(ds, segment_masks: dict) -> dict:
    """About This Survey: deterministic respondent-composition summary.

    segment_masks is accepted for signature-compatibility with every other
    section calculator (see run_analysis.py's SECTIONS loop) but unused --
    this section describes the whole surveyed population, not segments.
    """
    df = ds.df
    log.info(f"About This Survey: calculating (n_total={len(df)})")
    return {
        "n_total":   len(df),
        "by_country": _by_country(df),
        "product_mix": _product_mix(df),
        "age":        _age_summary(df),
        "by_sex":     _by_sex(df),
        "fieldwork":  _fieldwork_window(df),
    }
