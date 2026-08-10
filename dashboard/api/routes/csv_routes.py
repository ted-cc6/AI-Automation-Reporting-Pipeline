"""dashboard/api/routes/csv_routes.py"""
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile

from data_loader import data_loader_transformer
from dashboard.api.config import PROJECT_ROOT, UPLOADS_DIR
from dashboard.api.models import CountryOption, CsvUploadResponse

router = APIRouter(prefix="/api/csv", tags=["csv"])

CANONICAL_COLUMN_MAPPING_PATH = PROJECT_ROOT / "data_loader" / "column_mapping.csv"


@router.post("/upload", response_model=CsvUploadResponse)
async def upload_csv(file: UploadFile) -> CsvUploadResponse:
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(400, "Expected a .csv file (the raw KoBoToolbox export).")

    upload_id = uuid.uuid4().hex
    dest = UPLOADS_DIR / f"{upload_id}.csv"
    contents = await file.read()
    dest.write_bytes(contents)

    try:
        preview = pd.read_csv(dest, delimiter=";", encoding="utf-8", dtype=str,
                              keep_default_na=False, low_memory=False)
    except Exception as exc:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, f"Could not parse CSV as semicolon-delimited UTF-8: {exc}") from exc

    return CsvUploadResponse(
        upload_id=upload_id,
        filename=file.filename,
        size_bytes=len(contents),
        row_count_preview=len(preview),
        columns_detected=len(preview.columns),
    )


@router.get("/{upload_id}/countries", response_model=list[CountryOption])
async def list_upload_countries(upload_id: str) -> list[CountryOption]:
    """Distinct countries actually present in this upload's raw CSV, with
    respondent counts -- lets the frontend offer only countries that exist
    in the data, instead of a static list. Reads the raw upload directly
    (via the same column-mapping resolution data_loader_transformer.py
    uses) rather than requiring a full pipeline run first, since this is
    meant to populate the country picker right after upload/validation.
    """
    csv_path = UPLOADS_DIR / f"{upload_id}.csv"
    if not csv_path.exists():
        raise HTTPException(404, f"Upload not found: {upload_id}")

    # Mirrors dashboard/api/pipeline_runner.py's stage-1 mapping resolution:
    # prefer a reconciled per-upload mapping if the dataset validation flow
    # produced one, else fall back to the canonical mapping.
    reconciled_mapping = UPLOADS_DIR / f"{upload_id}_column_mapping.csv"
    mapping_path = reconciled_mapping if reconciled_mapping.exists() else CANONICAL_COLUMN_MAPPING_PATH

    mapping = data_loader_transformer.load_mapping(mapping_path)
    country_rows = mapping[mapping["output_name"] == "country"]
    if country_rows.empty:
        return []

    raw_df = data_loader_transformer.load_raw(csv_path)
    resolver = data_loader_transformer.build_index_resolver(mapping, list(raw_df.columns))
    col_idx = resolver(country_rows.iloc[0])
    if col_idx is None:
        return []

    country_values = raw_df.iloc[:, col_idx].astype(str).str.strip()
    counts = country_values[country_values != ""].value_counts()

    # value is lowercased but NOT otherwise slugified (no space/underscore
    # substitution): data_loader_screening.py's country filter only
    # lowercases when matching against the raw data (see
    # find_unselected_country_rows), and load_country_config() falls back to
    # default.yaml for any country without a dedicated config file -- a
    # value with underscores swapped in for spaces would silently fail to
    # match a multi-word country's raw data value (e.g. "Papua New Guinea").
    # Every current SCOPE_COUNTRIES entry is single-word, so this was
    # previously a dormant mismatch, not an active bug.
    options = [
        CountryOption(value=raw_value.lower(), label=raw_value, count=int(n))
        for raw_value, n in counts.items()
    ]
    return sorted(options, key=lambda o: (-o.count, o.label))
