"""Pydantic models for the extraction result: the JSON contract described in
the task (field_name/value/confidence/page_number, plus a `source` block for
debugging *why* the engine paired a value with a field)."""
from __future__ import annotations

from pydantic import BaseModel


class Source(BaseModel):
    type: str                    # "text_grid" | "checkbox" | "table_cell"
    raw_value: str
    anchor_label: str
    bbox: list[float]             # [x0, y0, x1, y1] of the matched value
    anchor_bbox: list[float]      # [x0, y0, x1, y1] of the label/anchor it was paired with


class FieldResult(BaseModel):
    field_name: str
    value: str
    confidence: float
    page_number: int
    section: str
    source: Source
    status: str = "filled"        # forward-compatible with Step 2 ("filled" | "empty")
    needs_review: bool = False

    def model_post_init(self, __context) -> None:
        self.needs_review = self.confidence < 0.80


class Summary(BaseModel):
    total_fields_detected: int
    high_confidence: int          # >= 0.90
    medium_confidence: int        # 0.70 - 0.899
    low_confidence: int           # < 0.70
    pages: int
    potential_issues: list[str]


class ExtractionResult(BaseModel):
    document_pages: int
    fields: list[FieldResult]
    summary: Summary
    warnings: list[str] = []
