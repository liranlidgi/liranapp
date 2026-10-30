"""Selection marks drawn as vector graphics instead of a checkmark glyph.

Some versions of the proposal form (the Adobe LiveCycle one) mark a selected
checkbox with a small black filled circle drawn over the box, so nothing
shows up in the text layer. Those marks are turned into synthetic "✔"
words placed where the checkbox square is, so the existing CHOICE /
CHECKBOX logic (checkmark to the reading-start side of the option word)
works unchanged.
"""
from __future__ import annotations

import logging

from .bbox_extractor import Line, Word
from .geometry import CHECKMARK

logger = logging.getLogger(__name__)

MARK_MIN, MARK_MAX = 5.5, 11.0   # points: a selection dot, not a logo or bullet
BOX_MIN, BOX_MAX = 6.0, 12.0     # points: the checkbox square it is drawn on


def _is_black(color) -> bool:
    if color is None:
        return False
    if isinstance(color, (int, float)):
        return color <= 0.25                          # DeviceGray
    c = tuple(color)
    if len(c) == 1:
        return c[0] <= 0.25
    if len(c) == 3:
        return max(c) <= 0.25                         # RGB
    if len(c) == 4:
        return c[3] >= 0.85 and max(c[:3]) <= 0.25    # CMYK
    return False


def _square(w: float, h: float, lo: float, hi: float) -> bool:
    return lo <= w <= hi and lo <= h <= hi and abs(w - h) <= 1.5


def _overlap(a, b) -> bool:
    return a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def find_images(pdf_path: str) -> list[tuple[int, float, float, float, float]]:
    """(page, x0, y0, x1, y1) of every placed image -- used to tell that a
    signature slot holds a signature picture."""
    try:
        import pdfplumber
    except ImportError:
        return []
    out = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            for im in page.images:
                out.append((page_no, im["x0"], im["top"], im["x1"], im["bottom"]))
    return out


def find_vector_marks(pdf_path: str, first_line_id: int) -> list[Line]:
    """One single-word Line per selection mark, page numbers 1-based."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning("pdfplumber not installed: vector selection marks are ignored")
        return []
    out: list[Line] = []
    line_id = first_line_id
    with pdfplumber.open(pdf_path) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            dots = [
                (c["x0"], c["top"], c["x1"], c["bottom"])
                for c in page.curves
                if c.get("fill") and _is_black(c.get("non_stroking_color"))
                and _square(c["x1"] - c["x0"], c["bottom"] - c["top"], MARK_MIN, MARK_MAX)
            ]
            if not dots:
                continue
            boxes = [
                (r["x0"], r["top"], r["x1"], r["bottom"])
                for r in page.rects
                if r.get("stroke") and _square(r["x1"] - r["x0"], r["bottom"] - r["top"],
                                               BOX_MIN, BOX_MAX)
            ]
            for dot in dots:
                box = next((b for b in boxes if _overlap(b, dot)), dot)
                x0, y0, x1, y1 = box
                word = Word(text=CHECKMARK, raw_text=CHECKMARK, x0=x0, y0=y0, x1=x1, y1=y1,
                            page=page_no, line_id=line_id)
                out.append(Line(line_id=line_id, page=page_no, x0=x0, y0=y0, x1=x1, y1=y1,
                                words=[word]))
                line_id += 1
    return out
