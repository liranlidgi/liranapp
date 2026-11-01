"""FastAPI app: upload an insurance proposal PDF, get back the extracted
fields as structured JSON (see app/extraction/models.py for the schema) plus
a summary. A static single-page UI (frontend/) renders the results as a
table.
"""
from __future__ import annotations

import base64
import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .extraction.engine import run_extraction
from .extraction.models import ExtractionResult
from .template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES
from .insurtix.mapping import to_insurtix
from .formgen import scenario as fg_scenario
from .formgen import service as fg_service

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
            result = run_extraction(tmp_path, FIELDS, TABLES, FINDINGS + BENEFICIARIES)
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


@app.post("/api/insurtix")
async def insurtix_export(file: UploadFile) -> dict:
    """Same extraction as /api/analyze, returned in the format the Insurtix
    policy form panel loads ("insurtix-proposal" v1)."""
    result = await analyze(file)
    return to_insurtix(result, file.filename or "")


class FormgenRequest(BaseModel):
    count: int = 5
    seed: int = 1
    edges: list[str] = []
    random_edges: bool = False
    check: bool = True
    agents: list[str] = []
    discounts: list[str] = []
    occupations: list[str] = []


class FormgenRenderRequest(BaseModel):
    scenario: dict
    check: bool = True
    name: str = "form"


def _clean_list(xs: list[str]) -> list[str] | None:
    xs = [x.strip() for x in xs if x and x.strip()]
    return xs or None


@app.get("/api/formgen/options")
async def formgen_options() -> dict:
    """Edge cases the test-form generator offers, and whether its template is in place."""
    ok, why = fg_service.ready()
    return {"ready": ok, "reason": why, "edges": fg_scenario.EDGES}


@app.post("/api/formgen/generate")
def formgen_generate(req: FormgenRequest) -> dict:
    """Synthetic proposal forms (invented people only): a zip of PDFs with the
    expected values of each, and the reader's result on them."""
    if not 1 <= req.count <= 200:
        raise HTTPException(status_code=400, detail="כמות הטפסים צריכה להיות בין 1 ל-200")
    bad = [e for e in req.edges if e not in fg_scenario.EDGES]
    if bad:
        raise HTTPException(status_code=400, detail="מקרה קצה לא מוכר: " + ", ".join(bad))
    try:
        data, report = fg_service.generate(req.count, req.seed, req.edges, check=req.check,
                                           random_edges=req.random_edges, agents=_clean_list(req.agents),
                                           discounts=_clean_list(req.discounts),
                                           occupations=_clean_list(req.occupations))
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return {"report": report, "zip": base64.b64encode(data).decode("ascii")}


@app.get("/api/formgen/schema")
def formgen_schema() -> dict:
    """Every field the generator can write, for the hand-editing screen."""
    return fg_service.form_schema()


@app.post("/api/formgen/scenario")
def formgen_scenario(req: FormgenRequest) -> dict:
    """One random scenario (a starting point to edit by hand)."""
    bad = [e for e in req.edges if e not in fg_scenario.EDGES]
    if bad:
        raise HTTPException(status_code=400, detail="מקרה קצה לא מוכר: " + ", ".join(bad))
    return fg_service.make_scenario(req.seed, req.edges, req.random_edges, agents=_clean_list(req.agents),
                                    discounts=_clean_list(req.discounts),
                                    occupations=_clean_list(req.occupations))


class PanelExportRequest(BaseModel):
    p: dict
    check: bool = True


@app.post("/api/formgen/from-panel")
def formgen_from_panel(req: PanelExportRequest) -> dict:
    """The external policy panel's values -> a filled proposal form (PDF)."""
    try:
        out = fg_service.render_from_panel(req.p, check=req.check)
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    out["pdf"] = base64.b64encode(out["pdf"]).decode("ascii")
    return out


@app.post("/api/formgen/render")
def formgen_render(req: FormgenRenderRequest) -> dict:
    """A hand-edited scenario -> PDF (base64), expected values and check."""
    try:
        out = fg_service.render_one(req.scenario, check=req.check, name=req.name)
    except FileNotFoundError as e:
        raise HTTPException(status_code=409, detail=str(e))
    out["pdf"] = base64.b64encode(out["pdf"]).decode("ascii")
    return out


@app.get("/api/health")
async def health() -> dict:
    return {"status": "ok"}


_frontend_dir = Path(__file__).resolve().parent.parent.parent / "frontend"
if _frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(_frontend_dir), html=True), name="frontend")
