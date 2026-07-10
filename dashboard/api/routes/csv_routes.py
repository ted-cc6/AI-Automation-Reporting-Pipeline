"""dashboard/api/routes/csv_routes.py"""
import uuid

import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile

from dashboard.api.config import UPLOADS_DIR
from dashboard.api.models import CsvUploadResponse

router = APIRouter(prefix="/api/csv", tags=["csv"])


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
