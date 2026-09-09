"""Pattern handlers: turn a FieldSpec + the document's words/lines into zero
or more FieldResult candidates. Each handler only ever *looks for* known
anchor text; it never invents a value it can't geometrically justify.
"""
from __future__ import annotations

import logging

from ..pdf_extraction.bbox_extractor import Line
from ..pdf_extraction.geometry import (
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


def _normalize(text: str) -> str:
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


def extract_field(
    spec: FieldSpec,
    lines: list[Line],
    page_widths: dict[int, float],
) -> FieldResult | None:
    if spec.pattern == Pattern.GRID:
        return extract_grid_field(spec, lines, page_widths)
    if spec.pattern == Pattern.CHOICE:
        return extract_choice_field(spec, lines, page_widths)
    raise ValueError(f"extract_field cannot handle pattern {spec.pattern} directly")
