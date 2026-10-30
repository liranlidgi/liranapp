"""Tables whose every row repeats its labels under the values (the
beneficiary tables of the proposal form):

    .1   [first name] [last name] [id] [birth date] [ז☐ נ☐] [relation] [%]
         שם פרטי      שם משפחה    מספר זהות ...      מגדר    קרבה      % חלוקה
    .2   ...

The values of row N sit between the label line of row N-1 and the label line
of row N. Column boundaries are the midpoints between that row's own label
centers, so nothing depends on fixed coordinates.
"""
from __future__ import annotations

import re

from ..pdf_extraction.bbox_extractor import Line, Word
from ..pdf_extraction.geometry import CHECKMARK, detect_selected_option
from ..template.schema import RowsTableSpec
from .confidence import table_confidence
from .models import FieldResult, Source
from .patterns import _normalize, line_text

_ROW_NUMBER_RE = re.compile(r"^\.\d+$|^\d+\.$")
ROW_TOL = 4.0


def extract_rows_table(spec: RowsTableSpec, lines: list[Line]) -> list[FieldResult]:
    page_lines = [ln for ln in lines if ln.page == spec.page]
    title_key = _normalize(spec.title_text)
    titles = [ln for ln in page_lines if title_key in _normalize(line_text(ln))]
    if not titles:
        return []
    title = min(titles, key=lambda ln: ln.y0)
    end_key = _normalize(spec.end_text)
    ends = [ln.y0 for ln in page_lines
            if ln.y0 > title.y1 and end_key in _normalize(line_text(ln))]
    bottom = min(ends) if ends else float("inf")
    label_keys = {_normalize(t): t for t in spec.labels}
    first_key = _normalize(spec.first_label)
    starts = sorted(
        (ln for ln in page_lines if title.y1 < ln.y0 < bottom
         and _normalize(line_text(ln)) == first_key),
        key=lambda ln: ln.y0,
    )
    results: list[FieldResult] = []
    top = title.y1
    for row_no, start in enumerate(starts, start=1):
        labels = [
            ln for ln in page_lines
            if abs(ln.yc - start.yc) <= ROW_TOL and _normalize(line_text(ln)) in label_keys
        ]
        labels.sort(key=lambda ln: -ln.xc)           # RTL
        centers = [ln.xc for ln in labels]
        names = [label_keys[_normalize(line_text(ln))] for ln in labels]
        band = [
            w for ln in page_lines for w in ln.words
            if w.y0 >= top - 1.0 and w.yc < start.y0 + 1.0
            and not _ROW_NUMBER_RE.match(w.text.strip())
        ]
        cols: dict[str, list[Word]] = {n: [] for n in names}
        for w in band:
            for i, c in enumerate(centers):
                lo = (centers[i + 1] + c) / 2 if i + 1 < len(centers) else -10_000.0
                hi = (centers[i - 1] + c) / 2 if i > 0 else 10_000.0
                if lo <= w.xc < hi:
                    cols[names[i]].append(w)
                    break
        cells: dict[str, tuple[str, list[Word]]] = {}
        for name, ws in cols.items():
            if name == spec.choice_column:
                if not ws:
                    continue
                pseudo = Line(-1, spec.page, min(w.x0 for w in ws), min(w.y0 for w in ws),
                              max(w.x1 for w in ws), max(w.y1 for w in ws),
                              sorted(ws, key=lambda w: -w.x0))
                sel = detect_selected_option(pseudo, list(spec.choice_options))
                if sel is not None:
                    cells[name] = (sel.option_text, [sel.checkmark])
                continue
            ws = [w for w in ws if w.text != CHECKMARK]
            text = " ".join(w.text for w in sorted(ws, key=lambda w: (round(w.yc), -w.x1)))
            if text.strip():
                cells[name] = (text.strip(), ws)
        top = max(ln.y1 for ln in labels) if labels else start.y1
        if not any(n != spec.choice_column for n in cells):
            continue                                 # empty row (a gender mark alone is noise)
        confidence = table_confidence(len(cells) / max(len(names), 1))
        for name, (value, ws) in cells.items():
            results.append(FieldResult(
                field_name=f"{spec.table_name} - שורה {row_no} - {name}",
                value=value,
                confidence=confidence,
                page_number=spec.page,
                section=spec.section,
                source=Source(
                    type="table_row_cell",
                    raw_value=value,
                    anchor_label=f"{spec.table_name}/{name}",
                    bbox=[min(w.x0 for w in ws), min(w.y0 for w in ws),
                          max(w.x1 for w in ws), max(w.y1 for w in ws)] if ws else [0, 0, 0, 0],
                    anchor_bbox=[start.x0, start.y0, start.x1, start.y1],
                ),
            ))
    return results
