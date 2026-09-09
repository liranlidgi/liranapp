"""Spatial helpers for pairing labels with values on a fixed-layout form.

The form this project targets prints each answer using one of two spatial
conventions (see docs in app/template/README-like docstring in
shlomo_life_insurance.py for the full writeup):

1. "Grid" fields: the value is printed directly ABOVE its label, in the same
   horizontal column (e.g. a name grid with "שם פרטי" as the label and the
   typed name sitting right above it).
2. "Inline choice" fields: a question/label is followed, on the same line,
   by one or more option words; a checkmark glyph ("✔") sits immediately to
   the reading-start side (highest x, since Hebrew is RTL) of whichever
   option was chosen.

Both conventions are handled generically here so the template only needs to
describe *which* labels/options to look for, not their pixel coordinates.
"""
from __future__ import annotations

from dataclasses import dataclass

from .bbox_extractor import Line, Word

CHECKMARK = "✔"


def line_text(line: Line) -> str:
    return "".join(w.text for w in line.words)


def find_lines_with_text(lines: list[Line], page: int | None, needle: str) -> list[Line]:
    """Lines on `page` (or any page if None) whose joined text contains
    `needle` as a contiguous substring, ignoring spaces."""
    target = needle.replace(" ", "")
    out = []
    for line in lines:
        if page is not None and line.page != page:
            continue
        if target in line_text(line).replace(" ", ""):
            out.append(line)
    return out


def x_overlap_fraction(a0: float, a1: float, b0: float, b1: float) -> float:
    """Intersection over the narrower of the two spans: 1.0 when one span is
    fully contained in the other (the common "short value under/over a wider
    label, or vice versa" case), falling off as they diverge."""
    inter = min(a1, b1) - max(a0, b0)
    if inter <= 0:
        return 0.0
    span = min(a1 - a0, b1 - b0)
    if span <= 0:
        return 0.0
    return inter / span


def _is_plausible_value_width(anchor_width: float, candidate_width: float) -> bool:
    """Reject candidates that are wildly wider than the label they'd be
    paired with -- e.g. a full disclaimer paragraph that happens to sit
    within `max_gap` points of a short label and fully contains its
    x-range. This is a coarse backstop only: the tight vertical gap and
    x-overlap requirements in nearest_line_above/below do most of the real
    discrimination, and genuine (if long) free-text answers -- like an
    occupation description sitting above "עיסוק בפועל" -- must not be
    rejected just for being a few times wider than their label."""
    if candidate_width <= 200:
        return True
    return candidate_width <= anchor_width * 5


def nearest_line_above(
    lines: list[Line],
    anchor: Line,
    min_x_overlap: float = 0.5,
    max_gap: float = 13.0,
) -> Line | None:
    """The closest line strictly above `anchor` on the same page whose
    x-range overlaps it enough to plausibly be "the same column", and whose
    width is plausible for a grid cell value (not a stray sentence)."""
    candidates = [
        ln
        for ln in lines
        if ln.page == anchor.page
        and ln.y1 <= anchor.y0 + 1.0
        and (anchor.y0 - ln.y1) <= max_gap
        and x_overlap_fraction(ln.x0, ln.x1, anchor.x0, anchor.x1) >= min_x_overlap
        and _is_plausible_value_width(anchor.x1 - anchor.x0, ln.x1 - ln.x0)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda ln: anchor.y0 - ln.y1)


def nearest_line_below(
    lines: list[Line],
    anchor: Line,
    min_x_overlap: float = 0.5,
    max_gap: float = 13.0,
) -> Line | None:
    """Mirror of nearest_line_above, for the handful of fields in this form
    where the value is printed below its label instead of above it."""
    candidates = [
        ln
        for ln in lines
        if ln.page == anchor.page
        and ln.y0 >= anchor.y1 - 1.0
        and (ln.y0 - anchor.y1) <= max_gap
        and x_overlap_fraction(ln.x0, ln.x1, anchor.x0, anchor.x1) >= min_x_overlap
        and _is_plausible_value_width(anchor.x1 - anchor.x0, ln.x1 - ln.x0)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda ln: ln.y0 - anchor.y1)


@dataclass(frozen=True)
class SelectedOption:
    option_text: str
    matched_word: Word
    checkmark: Word
    gap: float


def detect_selected_option(
    line: Line,
    option_texts: list[str],
    max_gap: float = 25.0,
) -> SelectedOption | None:
    """Given a line containing one or more option words plus (optionally) a
    checkmark glyph, return which option is selected: the option word whose
    reading-start edge (highest x) sits closest to a checkmark's low-x edge,
    within `max_gap` points and with no other word in between.
    """
    checkmarks = [w for w in line.words if w.text == CHECKMARK]
    if not checkmarks:
        return None

    best: SelectedOption | None = None
    for opt_text in option_texts:
        for w in line.words:
            if w.text != opt_text:
                continue
            for ck in checkmarks:
                # checkmark sits to the reading-start (right/high-x) side of
                # the option word: ck.x0 >= w.x1, minimal gap, same line height
                gap = ck.x0 - w.x1
                if gap < -2 or gap > max_gap:
                    continue
                if abs(ck.yc - w.yc) > max(w.y1 - w.y0, ck.y1 - ck.y0):
                    continue
                if best is None or gap < best.gap:
                    best = SelectedOption(option_text=opt_text, matched_word=w, checkmark=ck, gap=gap)
    return best


def value_words_in_column(
    lines: list[Line],
    value_line: Line,
    x0: float,
    x1: float,
) -> list[Word]:
    """Words on `value_line` whose horizontal center falls within [x0, x1]."""
    return [w for w in value_line.words if x0 <= w.xc <= x1]
