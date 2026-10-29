"""Pattern handlers: turn a FieldSpec + the document's words/lines into zero
or more FieldResult candidates. Each handler only ever *looks for* known
anchor text; it never invents a value it can't geometrically justify.
"""
from __future__ import annotations

import logging
import re

from ..pdf_extraction.bbox_extractor import Line
from ..pdf_extraction.geometry import (
    CHECKMARK,
    detect_selected_option,
    line_text,
    nearest_line_above,
    nearest_line_below,
    x_overlap_fraction,
)
from ..template.schema import FieldSpec, Pattern
from .confidence import choice_confidence, grid_confidence
from .models import FieldResult, Source

logger = logging.getLogger(__name__)

MIN_CONFIDENCE_TO_EMIT = 0.55


# pdftotext flips a number glued to a Hebrew prefix letter: the form says
# "ב-5" and the text layer may come out as "5-ב". Normalize both spellings to
# the logical one so anchors match either way.
_FLIPPED_PREFIX = re.compile(r"(\d+)-([א-ת])(?![א-ת])")


def _normalize(text: str) -> str:
    text = _FLIPPED_PREFIX.sub(r"\2-\1", text)
    return text.replace(" ", "").replace("‏", "").strip()


def _find_anchor_lines(lines: list[Line], pages: tuple[int, ...], anchor_text: str) -> list[Line]:
    target = _normalize(anchor_text)
    matches = [
        ln
        for ln in lines
        if ln.page in pages and _normalize(line_text(ln)) == target
    ]
    matches.sort(key=lambda ln: (ln.page, ln.y0))
    return matches


def _find_anchor_lines_contains(
    lines: list[Line], pages: tuple[int, ...], anchor_text: str
) -> list[Line]:
    target = _normalize(anchor_text)
    matches = [
        ln
        for ln in lines
        if ln.page in pages and target in _normalize(line_text(ln))
    ]
    matches.sort(key=lambda ln: (ln.page, ln.y0))
    return matches


def _column_bounds(page_width: float, column: str | None, x_split: float | None) -> tuple[float, float]:
    split = x_split if x_split is not None else page_width / 2.0
    if column == "right":
        return (split, page_width + 1000)
    if column == "left":
        return (-1000, split)
    return (-1000, page_width + 1000)


def extract_grid_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    anchors = _find_anchor_lines(lines, spec.pages, spec.anchor_text)
    if not anchors:
        logger.debug("grid field %r: no anchor match", spec.field_name)
        return None
    if spec.occurrence >= len(anchors):
        logger.debug(
            "grid field %r: occurrence %d out of range (%d matches)",
            spec.field_name, spec.occurrence, len(anchors),
        )
        return None
    anchor = anchors[spec.occurrence]

    if spec.direction == "below":
        value_line = nearest_line_below(lines, anchor)
    else:
        value_line = nearest_line_above(lines, anchor)
    if value_line is None or not value_line.words:
        return None

    x_overlap = x_overlap_fraction(value_line.x0, value_line.x1, anchor.x0, anchor.x1)
    gap = (
        value_line.y0 - anchor.y1 if spec.direction == "below" else anchor.y0 - value_line.y1
    )
    # Repeated occurrences of the same label elsewhere on the page (e.g. the
    # same "שם פרטי" heading for the owner/candidate-1/candidate-2 blocks)
    # are expected and already disambiguated by `spec.occurrence` -- they
    # are not evidence that *this* match is ambiguous, so they must not
    # feed into the confidence penalty.
    confidence = grid_confidence(x_overlap, gap, ambiguous_candidates=1)

    value_text = line_text(value_line).strip()
    if not value_text:
        return None

    result = FieldResult(
        field_name=spec.field_name,
        value=value_text,
        confidence=confidence,
        page_number=value_line.page,
        section=spec.section,
        source=Source(
            type="text_grid",
            raw_value=value_text,
            anchor_label=spec.anchor_text,
            bbox=[value_line.x0, value_line.y0, value_line.x1, value_line.y1],
            anchor_bbox=[anchor.x0, anchor.y0, anchor.x1, anchor.y1],
        ),
    )
    return result if confidence >= MIN_CONFIDENCE_TO_EMIT else None


def _selection_to_result(spec: FieldSpec, anchor: Line, selection, page: int) -> FieldResult:
    confidence = choice_confidence(selection.gap, alternative_selected_count=0)
    return FieldResult(
        field_name=spec.field_name,
        value=selection.option_text,
        confidence=confidence,
        page_number=page,
        section=spec.section,
        source=Source(
            type="checkbox",
            raw_value=f"{selection.matched_word.text} + checkmark",
            anchor_label=spec.anchor_text,
            bbox=[selection.matched_word.x0, selection.matched_word.y0,
                  selection.matched_word.x1, selection.matched_word.y1],
            anchor_bbox=[anchor.x0, anchor.y0, anchor.x1, anchor.y1],
        ),
    )


def extract_choice_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    if spec.layout == "above_label":
        return _extract_choice_above_label(spec, lines)
    return _extract_choice_inline(spec, lines, page_widths)


def _extract_choice_above_label(spec: FieldSpec, lines: list[Line]) -> FieldResult | None:
    anchors = _find_anchor_lines(lines, spec.pages, spec.anchor_text)
    if spec.occurrence >= len(anchors):
        return None
    anchor = anchors[spec.occurrence]

    # The checkbox row above a label can be split across more than one
    # <line> element (e.g. "✔ ז" and "נ" as two separate lines instead of
    # one merged "ז ✔ נ"), each only partially overlapping the label's
    # x-range on its own. Gather every word in the row directly above the
    # label -- within a generous x-margin around it, since this layout is
    # only used for a single, unambiguous value per occurrence rather than
    # side-by-side columns -- and evaluate them together.
    margin = 45.0
    candidate_lines = [
        ln
        for ln in lines
        if ln.page == anchor.page
        and ln.y1 <= anchor.y0 + 2.0
        and (anchor.y0 - ln.y1) <= 13.0
    ]
    band_words = [
        w
        for ln in candidate_lines
        for w in ln.words
        if (anchor.x0 - margin) <= w.xc <= (anchor.x1 + margin)
    ]
    if not band_words:
        return None
    value_line = Line(
        line_id=-1, page=anchor.page,
        x0=min(w.x0 for w in band_words), y0=min(w.y0 for w in band_words),
        x1=max(w.x1 for w in band_words), y1=max(w.y1 for w in band_words),
        words=sorted(band_words, key=lambda w: -w.x0),
    )
    selection = detect_selected_option(value_line, list(spec.options))
    if selection is None:
        return None
    result = _selection_to_result(spec, anchor, selection, value_line.page)
    return result if result.confidence >= MIN_CONFIDENCE_TO_EMIT else None


def _extract_choice_inline(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    anchor_lines = _find_anchor_lines_contains(lines, spec.pages, spec.anchor_text)
    if not anchor_lines:
        logger.debug("choice field %r: no anchor match", spec.field_name)
        return None

    best: FieldResult | None = None
    for anchor in anchor_lines:
        page_width = page_widths.get(anchor.page, 648.0)
        x0, x1 = _column_bounds(page_width, spec.column, spec.x_split)
        # Gather every word within a small vertical band of the anchor and
        # inside this column, merging across <line> elements -- a checkmark
        # can land in its own separate line from the option word it selects
        # (e.g. a lone "✔" line next to a multi-word brand name), so
        # evaluating one line at a time would miss it.
        band_words = [
            w
            for ln in lines
            if ln.page == anchor.page and abs(ln.yc - anchor.yc) <= 14.0
            for w in ln.words
            if x0 <= w.xc <= x1
        ]
        if not band_words:
            continue
        sub_line = Line(
            line_id=-1, page=anchor.page,
            x0=min(w.x0 for w in band_words), y0=min(w.y0 for w in band_words),
            x1=max(w.x1 for w in band_words), y1=max(w.y1 for w in band_words),
            words=sorted(band_words, key=lambda w: -w.x0),
        )
        selection = detect_selected_option(sub_line, list(spec.options))
        if selection is None:
            continue
        candidate = _selection_to_result(spec, anchor, selection, anchor.page)
        if best is None or candidate.confidence > best.confidence:
            best = candidate
    if best is not None and best.confidence >= MIN_CONFIDENCE_TO_EMIT:
        return best
    return None


ROW_MAX_LABEL_WORDS = 5     # a row label is short ("גובה (בס"מ)"), not a paragraph
ROW_X_PAD = 6.0             # points of slack around the column header's x-range


def _is_label_word(text: str, anchor_key: str) -> bool:
    """A word of the label itself (e.g. "סיגריות" of "כמה סיגריות ליום?")
    that happens to sit inside the value column. Numbers are never label
    words, so a value like "0" is kept."""
    t = _normalize(text)
    return bool(t) and not re.search(r"\d", t) and t in anchor_key


def header_span(header: Line, header_key: str) -> tuple[float, float]:
    """x-range of the words in `header` that spell `header_key` (normalized).
    pdftotext may merge several column headers into one line; fall back to
    the whole line when the words cannot be isolated."""
    ws = header.words
    for i in range(len(ws)):
        acc = ""
        for j in range(i, len(ws)):
            acc += _normalize(ws[j].text)
            if acc == header_key:
                return (min(w.x0 for w in ws[i:j + 1]), max(w.x1 for w in ws[i:j + 1]))
            if not header_key.startswith(acc):
                break
    return header.x0, header.x1


def extract_row_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    """Table row: the label sits in the question column and the value sits on
    the same row, under a column header (e.g. "מועמד ראשון לביטוח"). The
    column's x-range is taken from the header itself, not from coordinates."""
    anchors = [
        ln for ln in _find_anchor_lines_contains(lines, spec.pages, spec.anchor_text)
        if len(ln.words) <= ROW_MAX_LABEL_WORDS
    ]
    if spec.occurrence >= len(anchors):
        return None
    anchor = anchors[spec.occurrence]
    header_key = _normalize(spec.column_header or "")
    headers = [
        ln for ln in lines
        if ln.page == anchor.page and ln.y1 <= anchor.y0 + 1
        and header_key and header_key in _normalize(line_text(ln))
    ]
    if not headers:
        return None
    header = max(headers, key=lambda ln: ln.y1)  # nearest header above the row
    hx0, hx1 = header_span(header, header_key)
    lo, hi = hx0 - ROW_X_PAD, hx1 + ROW_X_PAD
    band = max(anchor.y1 - anchor.y0, 6.0)
    anchor_key = _normalize(spec.anchor_text)
    words = [
        w for ln in lines if ln.page == anchor.page
        for w in ln.words
        if lo <= w.xc <= hi and abs(w.yc - anchor.yc) <= band
        and not _is_label_word(w.text, anchor_key)
    ]
    if not words:
        return None
    words.sort(key=lambda w: -w.x1)  # RTL reading order
    value_text = " ".join(w.text for w in words).strip()
    if not value_text:
        return None
    x0, x1 = min(w.x0 for w in words), max(w.x1 for w in words)
    y0, y1 = min(w.y0 for w in words), max(w.y1 for w in words)
    x_overlap = x_overlap_fraction(x0, x1, hx0, hx1)
    gap = abs((y0 + y1) / 2 - anchor.yc)
    confidence = grid_confidence(x_overlap, gap, ambiguous_candidates=1)
    result = FieldResult(
        field_name=spec.field_name,
        value=value_text,
        confidence=confidence,
        page_number=anchor.page,
        section=spec.section,
        source=Source(
            type="table_row",
            raw_value=value_text,
            anchor_label=spec.anchor_text,
            bbox=[x0, y0, x1, y1],
            anchor_bbox=[anchor.x0, anchor.y0, anchor.x1, anchor.y1],
        ),
    )
    return result if confidence >= MIN_CONFIDENCE_TO_EMIT else None


DATE_RE = re.compile(r"\b\d{1,2}/\d{1,2}/\d{2,4}\b")


def _column_anchors(spec: FieldSpec, lines: list[Line], page_widths: dict[int, float]) -> list[Line]:
    anchors = _find_anchor_lines_contains(lines, spec.pages, spec.anchor_text)
    if spec.column is None:
        return anchors
    out = []
    for ln in anchors:
        lo, hi = _column_bounds(page_widths.get(ln.page, 648.0), spec.column, spec.x_split)
        if lo <= ln.xc <= hi:
            out.append(ln)
    return out


def _result(spec: FieldSpec, value: str, confidence: float, page: int, src_type: str,
            words: list, anchor: Line) -> FieldResult:
    bbox = ([min(w.x0 for w in words), min(w.y0 for w in words),
             max(w.x1 for w in words), max(w.y1 for w in words)] if words else [0, 0, 0, 0])
    return FieldResult(
        field_name=spec.field_name,
        value=value,
        confidence=confidence,
        page_number=page,
        section=spec.section,
        source=Source(
            type=src_type,
            raw_value=value,
            anchor_label=spec.anchor_text,
            bbox=bbox,
            anchor_bbox=[anchor.x0, anchor.y0, anchor.x1, anchor.y1],
        ),
    )


def extract_inline_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    """Value written on the same line right after the label, i.e. to its left
    in RTL ("כמה סיגריות ליום? 0", "עבור חברת הביטוח: ליברה"). Takes the
    run of words nearest to the label, stopping at a gap wider than a word
    space."""
    anchors = _column_anchors(spec, lines, page_widths)
    if spec.occurrence >= len(anchors):
        return None
    anchor = anchors[spec.occurrence]
    band = max(anchor.y1 - anchor.y0, 8.0)
    anchor_ids = {id(w) for w in anchor.words}
    cands = sorted(
        (
            w for ln in lines if ln.page == anchor.page for w in ln.words
            if id(w) not in anchor_ids
            and abs(w.yc - anchor.yc) <= band
            and w.x1 <= anchor.x0 + 1.0
            and anchor.x0 - w.x1 <= spec.max_gap
        ),
        key=lambda w: -w.x1,
    )
    picked: list = []
    edge = anchor.x0
    for w in cands:
        gap = edge - w.x1
        if picked and gap > 12.0:
            break
        if not picked and gap > spec.max_gap:
            break
        picked.append(w)
        edge = w.x0
    picked = [w for w in picked if w.text.strip() not in ("_", ".", ",")]
    if not picked:
        return None
    value = " ".join(w.text for w in picked).strip()
    gap = anchor.x0 - picked[0].x1
    confidence = round(max(0.6, 0.99 - gap / 400.0), 3)
    return _result(spec, value, confidence, anchor.page, "inline", picked, anchor)


def extract_signed_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    """Was this section signed? The anchor is the section title; the first
    signature slot below it whose label is `column_header` counts as signed
    when a date stamp sits on/just above the label (the signing service
    stamps the date next to every signature it places)."""
    anchors = _find_anchor_lines_contains(lines, spec.pages, spec.anchor_text)
    if spec.occurrence >= len(anchors):
        return None
    anchor = anchors[spec.occurrence]
    key = _normalize(spec.column_header or "")
    slots = sorted(
        (ln for ln in lines if ln.page == anchor.page and ln.y0 > anchor.y1
         and key and key in _normalize(line_text(ln))),
        key=lambda ln: ln.y0,
    )
    if not slots:
        return None
    slot = slots[0]
    hx0, hx1 = header_span(slot, key)
    dates = [
        w for ln in lines if ln.page == anchor.page for w in ln.words
        if DATE_RE.fullmatch(w.text.strip())
        and hx0 - 30 <= w.xc <= hx1 + 30
        and slot.y0 - 20 <= w.yc <= slot.y1 + 2
    ]
    if dates:
        d = min(dates, key=lambda w: abs(w.yc - slot.yc))
        return _result(spec, "כן", 0.9, anchor.page, "signature", [d], anchor)
    return _result(spec, "לא", 0.8, anchor.page, "signature", [], anchor)


def extract_checkbox_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    """Single checkbox next to a sentence: "כן" if a checkmark sits on the
    sentence's line (within 30pt of either end), "לא" otherwise."""
    anchors = _column_anchors(spec, lines, page_widths)
    if spec.occurrence >= len(anchors):
        return None
    anchor = anchors[spec.occurrence]
    band = max(anchor.y1 - anchor.y0, 8.0)
    marks = [
        w for ln in lines if ln.page == anchor.page for w in ln.words
        if w.text == CHECKMARK and abs(w.yc - anchor.yc) <= band
        and anchor.x0 - 30 <= w.xc <= anchor.x1 + 30
    ]
    if marks:
        return _result(spec, "כן", 0.9, anchor.page, "checkbox", marks, anchor)
    return _result(spec, "לא", 0.85, anchor.page, "checkbox", [], anchor)


def extract_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    if spec.pattern == Pattern.GRID:
        return extract_grid_field(spec, lines, page_widths)
    if spec.pattern == Pattern.CHOICE:
        return extract_choice_field(spec, lines, page_widths)
    if spec.pattern == Pattern.ROW:
        return extract_row_field(spec, lines, page_widths)
    if spec.pattern == Pattern.INLINE:
        return extract_inline_field(spec, lines, page_widths)
    if spec.pattern == Pattern.SIGNED:
        return extract_signed_field(spec, lines, page_widths)
    if spec.pattern == Pattern.CHECKBOX:
        return extract_checkbox_field(spec, lines, page_widths)
    raise ValueError(f"extract_field cannot handle pattern {spec.pattern} directly")
