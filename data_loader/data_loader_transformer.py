"""
data_loader_transformer.py — VisionFund Insurance Survey Data Loader
Step 2 of 4: Transform raw CSV into typed, clean parquet.

Usage:
    python data_loader/data_loader_transformer.py --csv path/to/export.csv --output-dir runs/2026_Q3
"""

import re
import sys
import logging
import argparse
from pathlib import Path

import pandas as pd
import yaml

# ---------------------------------------------------------------------------
# Paths (static reference files live alongside this script)
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).parent
DEFAULT_MAPPING = SCRIPT_DIR / "column_mapping.csv"
DEFAULT_YAML = SCRIPT_DIR / "value_coding_map.yaml"

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_raw(csv_path: Path) -> pd.DataFrame:
    return pd.read_csv(
        csv_path,
        delimiter=";",
        encoding="utf-8",
        dtype=str,
        keep_default_na=False,
        low_memory=False,
    )


def load_mapping(mapping_path: Path) -> pd.DataFrame:
    df = pd.read_csv(mapping_path, dtype=str, keep_default_na=False)
    df["raw_index"] = df["raw_index"].astype(int)
    return df


def load_yaml(yaml_path: Path) -> dict:
    with open(yaml_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_val(v: str) -> str:
    return v.strip() if isinstance(v, str) else v


def _is_empty(v: str, sentinel: str) -> bool:
    sv = _strip_val(v)
    return sv == "" or sv == sentinel


def strip_letter_prefix(v: str) -> str:
    return re.sub(r"^[a-z]\.\s+", "", v)


def extract_option_letter(header: str) -> str | None:
    m = re.search(r"/([a-z])\.\s", header)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# Warning tracker
# ---------------------------------------------------------------------------

class WarnTracker:
    def __init__(self):
        self._msgs: list[str] = []

    def warn(self, col_idx: int, raw_val: str, context: str) -> None:
        msg = f"Col {col_idx}: unexpected value {raw_val!r} in [{context}]"
        log.warning(msg)
        self._msgs.append(msg)

    @property
    def count(self) -> int:
        return len(self._msgs)

    @property
    def messages(self) -> list[str]:
        return self._msgs


# ---------------------------------------------------------------------------
# Step a — Insurance-type routing + scope sentinels
# ---------------------------------------------------------------------------

def apply_insurance_routing(df: pd.DataFrame, cmap: dict, col_names: list[str], wt: WarnTracker):
    routing = cmap["insurance_type_routing"]
    scope = cmap["scope_rules"]
    sentinel = scope["sentinel"]

    ins_col = col_names[8]
    ins_raw = df[ins_col].str.strip()
    insurance_type = ins_raw.map(routing)
    unknown = ins_raw[~ins_raw.isin(routing) & (ins_raw != "")]
    for v in unknown.unique():
        wt.warn(8, v, "insurance_type_routing")

    def _apply_sentinel(indices: list[int], wrong_type_mask: pd.Series) -> None:
        for idx in indices:
            if idx >= len(col_names):
                log.warning(f"Scope sentinel: raw_index {idx} out of range, skipped.")
                continue
            c = col_names[idx]
            empty_mask = df[c].str.strip() == ""
            bad_mask = wrong_type_mask & ~empty_mask
            if bad_mask.any():
                log.warning(
                    f"Col {idx}: {bad_mask.sum()} non-empty values outside expected "
                    "insurance type scope — NOT overwritten (investigate routing error)"
                )
            df.loc[wrong_type_mask & empty_mask, c] = sentinel

    _apply_sentinel(scope["health_only_cols"],      insurance_type != "health")
    _apply_sentinel(scope["crop_only_cols"],         insurance_type != "crop")
    _apply_sentinel(scope["credit_life_only_cols"],  insurance_type != "credit_life")

    return insurance_type


# ---------------------------------------------------------------------------
# Step c — Likert coding
# ---------------------------------------------------------------------------

def code_likert(series: pd.Series, lmap: dict, col_idx: int, qref: str,
                sentinel: str, wt: WarnTracker) -> tuple[pd.array, pd.array]:
    int_vals, lbl_vals = [], []
    for v in series:
        sv = _strip_val(v)
        if _is_empty(sv, sentinel):
            int_vals.append(pd.NA)
            lbl_vals.append(pd.NA)
        elif sv in lmap:
            int_vals.append(lmap[sv]["int"])
            lbl_vals.append(lmap[sv]["label"])
        else:
            wt.warn(col_idx, sv, f"likert ({qref})")
            int_vals.append(pd.NA)
            lbl_vals.append(pd.NA)
    return (
        pd.array(int_vals, dtype=pd.Int8Dtype()),
        pd.array(lbl_vals, dtype=pd.StringDtype()),
    )


# ---------------------------------------------------------------------------
# Step d — Binary standalone coding
# ---------------------------------------------------------------------------

def code_binary(series: pd.Series, bmap: dict, col_idx: int, qref: str,
                sentinel: str, wt: WarnTracker) -> pd.array:
    vals = []
    for v in series:
        sv = _strip_val(v)
        if _is_empty(sv, sentinel):
            vals.append(pd.NA)
        elif sv in bmap:
            vals.append(bmap[sv])
        else:
            wt.warn(col_idx, sv, f"binary_standalone ({qref})")
            vals.append(pd.NA)
    return pd.array(vals, dtype=pd.BooleanDtype())


# ---------------------------------------------------------------------------
# Step e — Multi-select child coding
# ---------------------------------------------------------------------------

def code_ms_child(series: pd.Series, ms_map: dict, col_idx: int,
                  parent_ref: str, sentinel: str, wt: WarnTracker) -> pd.array:
    vals = []
    for v in series:
        sv = _strip_val(v)
        if _is_empty(sv, sentinel):
            vals.append(pd.NA)
        elif sv in ms_map:
            vals.append(ms_map[sv])
        else:
            wt.warn(col_idx, sv, f"multi_select_child (parent={parent_ref})")
            vals.append(pd.NA)
    return pd.array(vals, dtype=pd.BooleanDtype())


# ---------------------------------------------------------------------------
# Step f — Multi-select list derivation
# ---------------------------------------------------------------------------

def derive_ms_list(out: pd.DataFrame, children_by_parent: dict[str, list[tuple[str, str]]],
                   option_labels: dict) -> None:
    for parent_ref, children in children_by_parent.items():
        labels_map = option_labels.get(parent_ref, {})
        children_sorted = sorted(children, key=lambda x: x[0])
        child_col_names = [c for _, c in children_sorted]
        letters = [letter for letter, _ in children_sorted]

        def make_list_for_row(row: pd.Series) -> list[str]:
            result = []
            for letter, child_col in zip(letters, child_col_names):
                val = row[child_col]
                if pd.notna(val) and val == True:  # noqa: E712
                    result.append(labels_map.get(letter, letter))
            return result

        out[parent_ref] = out[child_col_names].apply(make_list_for_row, axis=1)


# ---------------------------------------------------------------------------
# Step j — Single-select strip + Categorical
# ---------------------------------------------------------------------------

def code_single_select(series: pd.Series, col_idx: int, qref: str,
                       sentinel: str, wt: WarnTracker) -> pd.Categorical:
    clean = []
    for v in series:
        sv = _strip_val(v)
        if sv == "":
            clean.append(None)
        elif sv == sentinel:
            clean.append(sentinel)
        else:
            clean.append(strip_letter_prefix(sv))
    return pd.Categorical(clean)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(csv_path: Path, mapping_path: Path, yaml_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "survey_clean.parquet"

    log.info(f"Loading survey CSV: {csv_path.name}")
    df = load_raw(csv_path)
    col_names = list(df.columns)
    n_rows = len(df)
    log.info(f"  {n_rows} rows, {len(col_names)} columns")

    log.info(f"Loading column mapping: {mapping_path.name}")
    mapping = load_mapping(mapping_path)

    log.info(f"Loading coding map: {yaml_path.name}")
    cmap = load_yaml(yaml_path)
    sentinel = cmap["scope_rules"]["sentinel"]

    wt = WarnTracker()

    def raw(idx: int) -> pd.Series:
        return df.iloc[:, idx]

    def mrows(category=None, question_ref=None, parent_ref=None):
        mask = pd.Series([True] * len(mapping), index=mapping.index)
        if category:
            mask &= mapping["category"] == category
        if question_ref:
            if isinstance(question_ref, list):
                mask &= mapping["question_ref"].isin(question_ref)
            else:
                mask &= mapping["question_ref"] == question_ref
        if parent_ref:
            mask &= mapping["parent_ref"] == parent_ref
        return mapping[mask]

    # ---- STEP a: Insurance-type routing ----
    log.info("Step a: Insurance-type routing + scope sentinels")
    insurance_type = apply_insurance_routing(df, cmap, col_names, wt)

    out = pd.DataFrame(index=df.index)

    # ---- STEP b: Metadata/identity renames ----
    log.info("Step b: Column renames (metadata/identity)")
    col_renames_yaml = cmap["column_renames"]
    for _, row in mrows(category="keep_metadata").iterrows():
        idx = int(row["raw_index"])
        hdr = row["raw_column_header"].strip()
        target = col_renames_yaml.get(hdr)
        if target is None:
            log.warning(f"Col {idx}: no rename target for metadata header '{hdr}' — skipped")
            continue
        if idx < len(col_names):
            out[target] = df.iloc[:, idx]

    for _, row in mrows(category="keep_identity").iterrows():
        idx = int(row["raw_index"])
        hdr = row["raw_column_header"].strip()
        target = col_renames_yaml.get(hdr)
        if target is None:
            log.warning(f"Col {idx}: no rename target for identity header '{hdr}' — skipped")
            continue
        if idx < len(col_names):
            out[target] = df.iloc[:, idx]

    out["insurance_type"] = insurance_type
    out["is_health"] = (insurance_type == "health")
    out["is_crop"] = (insurance_type == "crop")
    out["is_credit_life"] = (insurance_type == "credit_life")

    # ---- STEP c: Likert coding ----
    log.info("Step c: Likert coding")
    likert4_map = cmap["likert_4"]
    likert4_qrefs = ["q_coverage_understanding", "q_claim_process_understanding"]
    for _, row in mrows(category="question_ref", question_ref=likert4_qrefs).iterrows():
        idx = int(row["raw_index"])
        qref = row["question_ref"]
        int_col, lbl_col = code_likert(raw(idx), likert4_map, idx, qref, sentinel, wt)
        out[qref] = int_col
        out[f"{qref}__label"] = lbl_col

    likert5_maps = cmap["likert_5"]
    for qref, lmap in likert5_maps.items():
        rows = mrows(category="question_ref", question_ref=qref)
        if rows.empty:
            log.warning(f"Likert-5: no mapping row found for {qref}")
            continue
        idx = int(rows.iloc[0]["raw_index"])
        int_col, lbl_col = code_likert(raw(idx), lmap, idx, qref, sentinel, wt)
        out[qref] = int_col
        out[f"{qref}__label"] = lbl_col

    # ---- STEP d: Binary standalone coding ----
    log.info("Step d: Binary standalone coding")
    binary_map = cmap["binary_standalone"]
    binary_qrefs = [
        "q_insured_event_12m", "q_claim_submitted",
        "q_claim_challenges_experienced", "q_prior_access",
    ]
    for _, row in mrows(category="question_ref", question_ref=binary_qrefs).iterrows():
        idx = int(row["raw_index"])
        qref = row["question_ref"]
        out[qref] = code_binary(raw(idx), binary_map, idx, qref, sentinel, wt)

    # ---- STEP e: Multi-select children → bool + rename ----
    log.info("Step e: Multi-select children coding")
    ms_map = cmap["multi_select_child"]
    children_by_parent: dict[str, list[tuple[str, str]]] = {}

    for _, row in mrows(category="multi_select_child").iterrows():
        idx = int(row["raw_index"])
        parent_ref = row["parent_ref"].strip()
        if idx >= len(col_names):
            log.warning(f"Col {idx}: out of range, skipped multi_select_child")
            continue
        actual_header = col_names[idx]
        letter = extract_option_letter(actual_header)
        if letter is None:
            log.warning(f"Col {idx}: could not extract option letter from '{actual_header[:80]}' — skipped")
            continue
        child_col_name = f"{parent_ref}__{letter}"
        out[child_col_name] = code_ms_child(raw(idx), ms_map, idx, parent_ref, sentinel, wt)
        children_by_parent.setdefault(parent_ref, []).append((letter, child_col_name))

    # ---- STEP f: Multi-select list derivation ----
    log.info("Step f: Multi-select list derivation")
    derive_ms_list(out, children_by_parent, cmap["multi_select_option_labels"])

    # ---- STEP h: NPS → int ----
    log.info("Step h: NPS score → int")
    nps_rows = mrows(category="question_ref", question_ref="q_nps_score")
    if not nps_rows.empty:
        idx = int(nps_rows.iloc[0]["raw_index"])
        nps_vals = []
        for v in raw(idx):
            sv = _strip_val(v)
            if sv == "":
                nps_vals.append(pd.NA)
            else:
                try:
                    n = int(sv)
                    if 0 <= n <= 10:
                        nps_vals.append(n)
                    else:
                        wt.warn(idx, sv, "q_nps_score out-of-range")
                        nps_vals.append(pd.NA)
                except (ValueError, TypeError):
                    wt.warn(idx, sv, "q_nps_score non-integer")
                    nps_vals.append(pd.NA)
        out["q_nps_score"] = pd.array(nps_vals, dtype=pd.Int16Dtype())

    # ---- STEP i: q_client_age → int ----
    log.info("Step i: q_client_age → int")
    age_rows = mrows(category="question_ref", question_ref="q_client_age")
    if not age_rows.empty:
        idx = int(age_rows.iloc[0]["raw_index"])
        age_vals = []
        for v in raw(idx):
            sv = _strip_val(v)
            if sv == "":
                age_vals.append(pd.NA)
            else:
                try:
                    age_vals.append(int(float(sv)))
                except (ValueError, TypeError):
                    wt.warn(idx, sv, "q_client_age non-numeric")
                    age_vals.append(pd.NA)
        out["q_client_age"] = pd.array(age_vals, dtype=pd.Int16Dtype())

    # ---- STEP j: Single-select → Categorical ----
    log.info("Step j: Single-select coding")
    ss_qrefs = [
        "q_claim_result", "q_payout_cost_coverage", "q_no_claim_reason",
        "q_claim_channel_preferred", "q_child_wellbeing", "q_healthcare_access",
        "q_medical_cost_change", "q_alternative_access", "q_crop_recovery_speed",
        "q_crop_farming_change", "q_credit_additional_value", "q_services_helped",
        "q_client_education", "q_household_size", "q_sex", "q_disability",
    ]
    for _, row in mrows(category="question_ref", question_ref=ss_qrefs).iterrows():
        idx = int(row["raw_index"])
        qref = row["question_ref"]
        out[qref] = code_single_select(raw(idx), idx, qref, sentinel, wt)

    # ---- STEP k: Free-text ----
    log.info("Step k: Free-text columns")
    free_text_renames = cmap.get("free_text_renames", {})
    for _, row in mrows(category="free_text_child").iterrows():
        idx = int(row["raw_index"])
        target_name = free_text_renames.get(str(idx))
        if target_name is None:
            parent_ref = row.get("parent_ref", "").strip()
            target_name = f"{parent_ref}__other_text" if parent_ref else f"free_text_col_{idx}"
        if idx < len(col_names):
            series = df.iloc[:, idx].str.strip()
            out[target_name] = series.where(series != "", other=pd.NA).astype(pd.StringDtype())

    open_text_qrefs = [
        "q_nps_detractor_followup",
        "q_nps_passive_followup",
        "q_nps_promoter_followup",
    ]
    for qref in open_text_qrefs:
        rows = mrows(category="question_ref", question_ref=qref)
        if rows.empty:
            continue
        idx = int(rows.iloc[0]["raw_index"])
        series = raw(idx).str.strip()
        out[qref] = series.where(series != "", other=pd.NA).astype(pd.StringDtype())

    # ---- Purge scope sentinel from Categorical columns ----
    sentinel_purged = 0
    for col in out.columns:
        if hasattr(out[col], "cat") and sentinel in out[col].cat.categories:
            out[col] = out[col].cat.remove_categories([sentinel])
            sentinel_purged += 1
    if sentinel_purged:
        log.info(f"Purged '{sentinel}' sentinel from {sentinel_purged} Categorical column(s)")

    # ---- Write output ----
    log.info(f"Writing parquet: {output_path}")
    out.to_parquet(output_path, engine="pyarrow", index=False)

    print(
        f"\nTransformer complete.\n"
        f"  Input rows  : {n_rows}\n"
        f"  Output cols : {len(out.columns)}\n"
        f"  Unexpected-value warnings: {wt.count}\n"
        f"  Output path : {output_path}"
    )
    if wt.count:
        print(f"\nFirst {min(wt.count, 10)} unexpected-value warnings:")
        for msg in wt.messages[:10]:
            print(f"  {msg}")
        if wt.count > 10:
            print(f"  … and {wt.count - 10} more")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="VisionFund Survey Transformer")
    parser.add_argument("--csv",        type=Path, required=True,        help="Path to the KoBoToolbox CSV export")
    parser.add_argument("--mapping",    type=Path, default=DEFAULT_MAPPING, help="Path to column_mapping.csv")
    parser.add_argument("--yaml",       type=Path, default=DEFAULT_YAML,    help="Path to value_coding_map.yaml")
    parser.add_argument("--output-dir", type=Path, required=True,        help="Directory to write survey_clean.parquet")
    args = parser.parse_args()

    missing = [str(p) for p in [args.csv, args.mapping, args.yaml] if not p.exists()]
    if missing:
        for m in missing:
            log.error(f"File not found: {m}")
        sys.exit(1)

    main(args.csv, args.mapping, args.yaml, args.output_dir)
