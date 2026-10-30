"""Orchestrates the full pipeline: PDF -> words/lines -> template matching ->
ExtractionResult. This is the only module the API layer needs to call.
"""
from __future__ import annotations

import logging

from ..pdf_extraction.bbox_extractor import extract_words
from ..pdf_extraction.vector_marks import find_images, find_vector_marks
from ..template.schema import FieldSpec, FindingsSpec, Pattern, RowsTableSpec, TableSpec
from .findings import extract_findings
from .row_tables import extract_rows_table
from .models import ExtractionResult, FieldResult, Summary
from .patterns import extract_field
from .tables import extract_table

logger = logging.getLogger(__name__)

MIN_WORDS_PER_PAGE_FOR_TEXT_PDF = 3


def _looks_like_scanned_pdf(pages, words) -> bool:
    if not pages:
        return True
    words_per_page = len(words) / len(pages)
    return words_per_page < MIN_WORDS_PER_PAGE_FOR_TEXT_PDF


def run_extraction(
    pdf_path: str,
    field_specs: list[FieldSpec],
    table_specs: list[TableSpec],
    findings_specs: list[FindingsSpec | RowsTableSpec] = (),
) -> ExtractionResult:
    pages, words, lines = extract_words(pdf_path)
    warnings: list[str] = []

    if _looks_like_scanned_pdf(pages, words):
        warnings.append(
            "לא ניתן לקרוא את פרטי המסמך: אין בו טקסט. כנראה הוא נסרק או הודפס ל-PDF (למשל ב-Microsoft Print to PDF). יש להשתמש בקובץ המקורי ממערכת ההחתמות."
        )
        return ExtractionResult(
            document_pages=len(pages),
            fields=[],
            summary=Summary(
                total_fields_detected=0,
                high_confidence=0,
                medium_confidence=0,
                low_confidence=0,
                pages=len(pages),
                potential_issues=["PDF ריק מטקסט / דורש OCR"],
            ),
            warnings=warnings,
        )

    page_widths = {p.number: p.width for p in pages}
    # selection marks drawn as graphics (LiveCycle version of the form)
    try:
        marks = find_vector_marks(pdf_path, max((ln.line_id for ln in lines), default=0) + 1)
    except Exception:
        logger.exception("Failed reading vector selection marks")
        marks = []
    lines = lines + marks
    try:
        extras = {"images": find_images(pdf_path)}
    except Exception:
        logger.exception("Failed reading image positions")
        extras = {"images": []}

    results: list[FieldResult] = []
    for spec in field_specs:
        try:
            if spec.pattern != Pattern.TABLE:
                res = extract_field(spec, lines, page_widths, extras)
                if res is not None:
                    results.append(res)
        except Exception:
            logger.exception("Failed extracting field %r", spec.field_name)
            warnings.append(f"שגיאה בחילוץ השדה: {spec.field_name}")

    for tspec in table_specs:
        try:
            results.extend(extract_table(tspec, lines))
        except Exception:
            logger.exception("Failed extracting table %r", tspec.table_name)
            warnings.append(f"שגיאה בחילוץ הטבלה: {tspec.table_name}")

    for fspec in findings_specs:
        try:
            if isinstance(fspec, RowsTableSpec):
                results.extend(extract_rows_table(fspec, lines))
            else:
                results.extend(extract_findings(fspec, lines))
        except Exception:
            logger.exception("Failed extracting table %r", fspec.table_name)
            warnings.append(f"שגיאה בחילוץ הטבלה: {fspec.table_name}")

    summary = _build_summary(results, len(pages))
    return ExtractionResult(
        document_pages=len(pages), fields=results, summary=summary, warnings=warnings
    )


def _build_summary(results: list[FieldResult], page_count: int) -> Summary:
    high = sum(1 for r in results if r.confidence >= 0.90)
    medium = sum(1 for r in results if 0.70 <= r.confidence < 0.90)
    low = sum(1 for r in results if r.confidence < 0.70)
    issues = [
        f"{r.field_name} – confidence {round(r.confidence * 100)}%"
        for r in sorted(results, key=lambda r: r.confidence)
        if r.confidence < 0.80
    ]
    return Summary(
        total_fields_detected=len(results),
        high_confidence=high,
        medium_confidence=medium,
        low_confidence=low,
        pages=page_count,
        potential_issues=issues[:20],
    )
