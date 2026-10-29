"""Extraction of the health declaration's "positive findings" table
(section 4, "פירוט ממצאים חיוביים").

Layout (RTL): question column | candidate 1 | candidate 2 | extra documents.
Each candidate column is split into a narrow question-number sub-column
("מס' שאלה", on the right) and a wide details sub-column ("פרטים"). An entry
starts at every question number; the details text belonging to it may wrap
over several lines until the next number. All x-ranges come from the header
words themselves, never from fixed coordinates.
"""
from __future__ import annotations

from ..pdf_extraction.bbox_extractor import Line, Word
from ..template.schema import FindingsSpec
from .confidence import table_confidence
from .models import FieldResult, Source
from .patterns import _find_anchor_lines_contains, _normalize, header_span, line_text

X_PAD = 6.0         # slack around header x-ranges
SUBHEADER_BAND = 40.0  # sub-headers sit at most this far below the anchor top
ROW_TOL = 4.0       # words closer than this vertically belong to one text line

NUMBER_COL = "מס' שאלה"
DETAILS_COL = "פרטים"


def _cluster(words: list[Word], tol: float = ROW_TOL) -> list[list[Word]]:
    rows: list[list[Word]] = []
    for w in sorted(words, key=lambda w: w.yc):
        if rows and abs(rows[-1][-1].yc - w.yc) <= tol:
            rows[-1].append(w)
        else:
            rows.append([w])
    return rows


def _text(words: list[Word]) -> str:
    """Join words top-to-bottom, each text line in RTL order."""
    return " ".join(
        " ".join(w.text for w in sorted(row, key=lambda w: -w.x1))
        for row in _cluster(words)
    ).strip()


def _is_number_header(word: Word, key: str) -> bool:
    t = _normalize(word.text)
    return t == key or t.startswith("מס")


def extract_findings(spec: FindingsSpec, lines: list[Line]) -> list[FieldResult]:
    anchors = _find_anchor_lines_contains(lines, spec.pages, spec.anchor_text)
    if not anchors:
        return []
    anchor = anchors[0]
    page = anchor.page
    page_lines = [ln for ln in lines if ln.page == page]
    header_key = _normalize(spec.column_header)
    headers = [
        ln for ln in page_lines
        if ln.y1 <= anchor.y0 + 1 and header_key in _normalize(line_text(ln))
    ]
    if not headers:
        return []
    header = max(headers, key=lambda ln: ln.y1)  # nearest candidate header above
    hx0, hx1 = header_span(header, header_key)
    lo, hi = hx0 - X_PAD, hx1 + X_PAD

    col_words = [w for ln in page_lines for w in ln.words if lo <= w.xc <= hi]
    sub = [
        w for w in col_words
        if w.y0 >= header.y1 - 1 and w.yc <= anchor.y0 + SUBHEADER_BAND
    ]
    details_hdr = [w for w in sub if _normalize(w.text) == _normalize(spec.details_header)]
    if not details_hdr:
        return []  # not the expected layout
    number_key = _normalize(spec.number_header)
    number_hdr = [
        w for w in sub
        if _is_number_header(w, number_key) and w.x0 > max(d.x1 for d in details_hdr) - 1
    ]
    if number_hdr:
        split = min(w.x0 for w in number_hdr) - X_PAD / 2
    else:
        d_x1 = max(w.x1 for w in details_hdr)
        split = d_x1 + (hx1 - d_x1) / 2
    body_top = max(w.y1 for w in details_hdr + number_hdr)

    end_key = _normalize(spec.end_text)
    ends = [
        ln.y0 for ln in page_lines
        if ln.y0 > body_top and _normalize(line_text(ln)).startswith(end_key)
    ]
    body_bottom = min(ends) if ends else float("inf")

    body = [w for w in col_words if body_top < w.y0 and w.y1 <= body_bottom + 0.5]
    numbers = [w for w in body if w.xc >= split]
    details = [w for w in body if w.xc < split]

    # one entry per question-number text line
    entries: list[dict] = [
        {"y": min(w.y0 for w in row), "num": row, "det": []}
        for row in _cluster(numbers)
    ]
    if not entries and details:
        entries = [{"y": float("-inf"), "num": [], "det": []}]
    for w in details:
        idx = 0
        for i, e in enumerate(entries):
            if e["y"] - ROW_TOL <= w.yc:
                idx = i
        entries[idx]["det"].append(w)

    results: list[FieldResult] = []
    prefix = f"{spec.table_name} - {spec.candidate_label}"
    for row_no, e in enumerate(entries[: spec.max_rows], start=1):
        cells = {NUMBER_COL: _text(e["num"]), DETAILS_COL: _text(e["det"])}
        cells = {k: v for k, v in cells.items() if v}
        if not cells:
            continue
        confidence = table_confidence(len(cells) / 2)
        for col, value in cells.items():
            ws = e["num"] if col == NUMBER_COL else e["det"]
            results.append(FieldResult(
                field_name=f"{prefix} - שורה {row_no} - {col}",
                value=value,
                confidence=confidence,
                page_number=page,
                section=spec.section,
                source=Source(
                    type="findings_table",
                    raw_value=value,
                    anchor_label=f"{spec.anchor_text}/{spec.column_header}/{col}",
                    bbox=[min(w.x0 for w in ws), min(w.y0 for w in ws),
                          max(w.x1 for w in ws), max(w.y1 for w in ws)],
                    anchor_bbox=[anchor.x0, anchor.y0, anchor.x1, anchor.y1],
                ),
            ))
    return results
