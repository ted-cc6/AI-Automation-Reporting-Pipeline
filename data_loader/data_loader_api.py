"""
data_loader_api.py — VisionFund Insurance Survey Data Loader
Public API for the analysis engine.

Usage:
    from data_loader.data_loader_api import load_survey_data
    ds = load_survey_data()                     # latest run in runs/
    ds = load_survey_data(run_id="2026_Q2")     # specific run
    ds = load_survey_data(run_dir=Path("..."))  # arbitrary path

    ds.df, ds.health, ds.promoters, ...
"""

import logging
import sys
from pathlib import Path

import pandas as pd

from report_spec import load_spec
from report_spec.models import ReportSpec

_SCRIPT_DIR = Path(__file__).parent
_PROJECT_ROOT = _SCRIPT_DIR.parent

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
_log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# CleanDataset
# ---------------------------------------------------------------------------

class CleanDataset:
    """Read-only wrapper around the validated survey parquet."""

    def __init__(self, df: pd.DataFrame, spec: ReportSpec) -> None:
        self._df = df
        self._spec = spec

    # ── Core ────────────────────────────────────────────────────────────────

    @property
    def df(self) -> pd.DataFrame:
        return self._df

    @property
    def spec(self) -> ReportSpec:
        return self._spec

    @property
    def n(self) -> int:
        return len(self._df)

    # ── Insurance-type splits ────────────────────────────────────────────────

    @property
    def health(self) -> pd.DataFrame:
        return self._df[self._df["is_health"] == True]  # noqa: E712

    @property
    def crop(self) -> pd.DataFrame:
        return self._df[self._df["is_crop"] == True]  # noqa: E712

    @property
    def credit_life(self) -> pd.DataFrame:
        return self._df[self._df["is_credit_life"] == True]  # noqa: E712

    # ── NPS segments ────────────────────────────────────────────────────────

    @property
    def promoters(self) -> pd.DataFrame:
        return self._df[self._df["q_nps_score"] >= 9]

    @property
    def passives(self) -> pd.DataFrame:
        s = self._df["q_nps_score"]
        return self._df[(s >= 7) & (s <= 8)]

    @property
    def detractors(self) -> pd.DataFrame:
        return self._df[self._df["q_nps_score"] <= 6]

    # ── Claims analysis ──────────────────────────────────────────────────────

    @property
    def claimants(self) -> pd.DataFrame:
        return self._df[self._df["q_claim_submitted"] == True]  # noqa: E712

    @property
    def paid_claimants(self) -> pd.DataFrame:
        return self._df[self._df["flag_paid_claimant"] == True]  # noqa: E712

    # ── Analysis bases ───────────────────────────────────────────────────────

    @property
    def insured_event_base(self) -> pd.DataFrame:
        return self._df[self._df["q_insured_event_12m"] == True]  # noqa: E712

    @property
    def child_wellbeing_base(self) -> pd.DataFrame:
        return self._df[self._df["flag_child_wellbeing_denominator"] == True]  # noqa: E712


# ---------------------------------------------------------------------------
# load_survey_data
# ---------------------------------------------------------------------------

def _find_latest_run(runs_dir: Path) -> Path:
    """Return the most recently modified subdirectory under runs_dir."""
    if not runs_dir.exists():
        raise FileNotFoundError(
            f"Runs directory not found: {runs_dir}. "
            "Run run_pipeline.py --csv path/to/export.csv first."
        )
    subdirs = [d for d in runs_dir.iterdir() if d.is_dir()]
    if not subdirs:
        raise FileNotFoundError(
            f"No run subdirectories found in {runs_dir}. "
            "Run run_pipeline.py --csv path/to/export.csv first."
        )
    return max(subdirs, key=lambda d: d.stat().st_mtime)


def load_survey_data(
    run_id: "str | None" = None,
    run_dir: "Path | str | None" = None,
    spec_yaml_path: "Path | str | None" = None,
    spec_schema_path: "Path | str | None" = None,
) -> CleanDataset:
    """Load the validated survey parquet for a given run and return a CleanDataset.

    Parameters
    ----------
    run_id:
        Name of a run folder under runs/ (e.g. "2026_Q2"). Ignored if run_dir is given.
    run_dir:
        Explicit path to a run folder. Takes precedence over run_id.
    spec_yaml_path:
        Path to insurance-report-spec.yaml. Defaults to project root.
    spec_schema_path:
        Path to insurance-report-spec.schema.json. Defaults to project root.

    Raises
    ------
    FileNotFoundError
        If no run folder or parquet is found.
    ValueError
        If required columns are missing from the parquet.
    RuntimeError
        If the report spec fails to load.
    """
    # 1. Resolve run directory
    if run_dir is not None:
        resolved_run_dir = Path(run_dir)
    elif run_id is not None:
        resolved_run_dir = _PROJECT_ROOT / "runs" / run_id
    else:
        resolved_run_dir = _find_latest_run(_PROJECT_ROOT / "runs")
        _log.info(f"Auto-selected latest run: {resolved_run_dir.name}")

    # 2. Resolve parquet path
    parquet_path = resolved_run_dir / "survey_clean.parquet"
    if not parquet_path.exists():
        raise FileNotFoundError(
            f"survey_clean.parquet not found at {parquet_path}. "
            "Run run_pipeline.py to generate it."
        )

    # 3. Resolve spec paths
    spec_yaml_path   = Path(spec_yaml_path)   if spec_yaml_path   is not None else _PROJECT_ROOT / "insurance-report-spec.yaml"
    spec_schema_path = Path(spec_schema_path) if spec_schema_path is not None else _PROJECT_ROOT / "insurance-report-spec.schema.json"

    # 4. Load parquet
    _log.info(f"Loading {parquet_path}")
    df = pd.read_parquet(parquet_path)
    _log.info(f"  {len(df):,} rows × {len(df.columns)} columns")

    # 5. Quick sanity check
    required = ["insurance_type", "flag_promoter", "flag_child_wellbeing_denominator"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise ValueError(
            f"Required column(s) missing from parquet: {missing}. "
            "Re-run data_loader_derived.py to regenerate derived flags."
        )

    # 6. Load spec
    _log.info(f"Loading spec from {spec_yaml_path.name}")
    result = load_spec(spec_yaml_path, spec_schema_path, strict=False)
    if result.spec is None:
        raise RuntimeError("Report spec failed to load")
    _log.info(f"  {len(result.spec.all_source_questions())} source questions")

    return CleanDataset(df, result.spec)


# ---------------------------------------------------------------------------
# __main__
# ---------------------------------------------------------------------------

def _pct(n: int, d: int) -> str:
    return f"{n / d * 100:5.1f}%" if d > 0 else "   N/A"


def main() -> None:
    ds = load_survey_data()
    df = ds.df

    n_total  = ds.n
    n_health = len(ds.health)
    n_crop   = len(ds.crop)
    n_credit = len(ds.credit_life)

    nps_valid   = df["q_nps_score"].notna().sum()
    n_promoters = len(ds.promoters)
    n_passives  = len(ds.passives)
    n_detractors = len(ds.detractors)

    n_insured  = len(ds.insured_event_base)
    n_claimants = len(ds.claimants)
    n_paid     = len(ds.paid_claimants)
    n_cwb      = len(ds.child_wellbeing_base)

    print(f"""
Survey Loader — VisionFund Insurance Survey
===========================================
Dataset  : {n_total:,} rows × {len(df.columns)} columns
Spec     : {len(ds.spec.all_source_questions())} source questions

Insurance-type split:
  Health       : {n_health:5,} respondents ({_pct(n_health, n_total)})
  Crop         : {n_crop:5,} respondents ({_pct(n_crop, n_total)})
  Credit Life  : {n_credit:5,} respondents ({_pct(n_credit, n_total)})

NPS (n={nps_valid:,} scored):
  Promoters (9–10) : {n_promoters:5,} ({_pct(n_promoters, nps_valid)})
  Passives  (7–8)  : {n_passives:5,} ({_pct(n_passives, nps_valid)})
  Detractors (0–6) : {n_detractors:5,} ({_pct(n_detractors, nps_valid)})

Claims:
  Experienced insured event : {n_insured:5,} ({_pct(n_insured, n_total)} of {n_total:,})
  Submitted a claim         : {n_claimants:5,} ({_pct(n_claimants, n_insured)} of insured-event base)
  Claim approved & paid     : {n_paid:5,} ({_pct(n_paid, n_claimants)} of claimants)

Analysis bases:
  Child wellbeing base      : {n_cwb:5,} (of {n_total:,})
  Negative coping base      : {n_insured:5,} (of {n_total:,})

All properties accessible.  Use load_survey_data() to get a CleanDataset.
""".lstrip())


if __name__ == "__main__":
    main()
