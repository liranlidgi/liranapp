"""Generic header-anchored table extraction (used for the signing-log table
and, in future documents, the beneficiary tables). Column boundaries are
derived from the header cells' own positions -- never hardcoded pixel
coordinates -- so this keeps working if the table shifts vertically between
documents (different amount of text above it) as long as the header row's
relative column layout doesn't change.
"""
from __future__ import annotations

import re

from ..pdf_extraction.bbox_extractor import Line, Word
from ..template.schema import TableSpec
from .confidence import table_confidence
from .models import FieldResult, Source

_ROW_NUMBER_RE = re.compile(r"^\.\d+$|^\d+\.$")
_BARE_GENDER_MARKS = {"ז", "נ", "ז נ", "נ ז"}


def _row_cluster(words: list[Word], y_tolerance: float = 4.0) -> list[list[Word]]:
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.y0):
        placed = False
        for row in rows:
            if abs(row[0].yc - w.yc) <= y_tolerance:
                row.append(w)
                placed = True
                break
        if not placed:
            rows.append([w])
    rows.sort(key=lambda row: min(w.y0 for w in row))
    return rows


def _find_headers(spec: TableSpec, page_lines: list[Line]) -> list[Line] | None:
    header_lines: list[Line] = []
    for header_text in spec.header_texts:
        target = header_text.replace(" ", "")
        match = next(
            (ln for ln in page_lines if ln.text.replace(" ", "") == target), None
        )
        if match is None:
            return None  # header not found -- table isn't on this page
        header_lines.append(match)
    return header_lines


def extract_table(spec: TableSpec, lines: list[Line]) -> list[FieldResult]:
    page = spec.page
    header_lines = None
    for candidate in (spec.search_pages or (spec.page,)):
        page_lines = [ln for ln in lines if ln.page == candidate]
        header_lines = _find_headers(spec, page_lines)
        if header_lines is not None:
            page = candidate
            break
    if header_lines is None:
        return []

    header_row_y1 = max(ln.y1 for ln in header_lines)
    # column boundaries: midpoints between consecutive header centers (RTL order
    # already matches spec.header_texts order), extended at both ends.
    centers = [ln.xc for ln in header_lines]
    bounds: list[tuple[float, float]] = []
    for i, c in enumerate(centers):
        left = (centers[i + 1] + c) / 2 if i + 1 < len(centers) else -10_000.0
        right = (centers[i - 1] + c) / 2 if i > 0 else 10_000.0
        bounds.append((left, right))

    body_words = [
        w
        for ln in page_lines
        for w in ln.words
        if ln.y0 > header_row_y1 + 1.0
    ]
    if not body_words:
        return []

    header_texts_normalized = {h.replace(" ", "") for h in spec.header_texts}
    rows = _row_cluster(body_words)[: spec.max_rows]
    results: list[FieldResult] = []
    for row_idx, row_words in enumerate(rows, start=1):
        cells: dict[str, str] = {}
        for col_name, (xlo, xhi) in zip(spec.column_names, bounds):
            col_words = sorted(
                (w for w in row_words if xlo <= w.xc <= xhi), key=lambda w: -w.x0
            )
            # Drop individual words that are themselves a header fragment
            # (column boundaries can let a neighbouring header word like
            # "מגדר" bleed into this column) before joining, rather than
            # only checking the joined text -- otherwise "מגדר" + "קרבה"
            # from two unfilled label rows joins into "מגדר קרבה", which
            # matches neither header exactly and would slip through.
            kept_words = [
                w for w in col_words
                if w.text.replace(" ", "") not in header_texts_normalized
            ]
            text = " ".join(w.text for w in kept_words).strip()
            if not text:
                continue
            normalized = text.replace(" ", "")
            if any(normalized == h or normalized in h for h in header_texts_normalized):
                continue
            if _ROW_NUMBER_RE.match(text):
                continue
            if text in _BARE_GENDER_MARKS:
                continue
            cells[col_name] = text
        if not cells:
            continue
        completeness = len(cells) / len(spec.column_names)
        confidence = table_confidence(completeness)
        for col_name, text in cells.items():
            results.append(
                FieldResult(
                    field_name=f"{spec.table_name} - שורה {row_idx} - {col_name}",
                    value=text,
                    confidence=confidence,
                    page_number=page,
                    section=spec.section,
                    source=Source(
                        type="table_cell",
                        raw_value=text,
                        anchor_label=f"{spec.table_name}/{col_name}",
                        bbox=[0, 0, 0, 0],
                        anchor_bbox=[0, 0, 0, 0],
                    ),
                )
            )
    return results
