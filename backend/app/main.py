"""FastAPI app: upload an insurance proposal PDF, get back the extracted
fields as structured JSON (see app/extraction/models.py for the schema) plus
a summary. A static single-page UI (frontend/) renders the results as a
table.
"""
from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .extraction.engine import run_extraction
from .extraction.models import ExtractionResult
from .template.shlomo_life_insurance import FIELDS, TABLES

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Insurance Form Field Extraction")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


@app.post("/api/analyze", response_model=ExtractionResult)
async def analyze(file: UploadFile) -> ExtractionResult:
    if file.content_type not in ("application/pdf", "application/octet-stream"):
        raise HTTPException(status_code=400, detail="קובץ חייב להיות מסוג PDF")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="הקובץ ריק")
    if len(data) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=400, detail="הקובץ גדול מדי (מקסימום 25MB)")

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(data)
        tmp_path = tmp.name

    try:
        try:
            result = run_extraction(tmp_path, FIELDS, TABLES)
        except Exception:
            logger.exception("Extraction failed for uploaded file %s", file.filename)
            raise HTTPException(status_code=500, detail="חילוץ הנתונים מהמסמך נכשל")
    finally:
        os.remove(tmp_path)

    logger.info(
        "Analyzed %s: %d fields detected across %d pages",
        file.filename, result.summary.total_fields_detected, result.document_pages,
    )
    return result


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
