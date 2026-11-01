"""Expected results of a scenario, and the comparison with what the reader
extracts from the generated PDF."""
from __future__ import annotations

import re
from typing import Any

from app.extraction.models import ExtractionResult, FieldResult, Source, Summary
from app.insurtix.mapping import to_insurtix

YES, NO = "כן", "לא"


def _f(section: str, name: str, value: str, typ: str) -> FieldResult:
    return FieldResult(field_name=name, value=value, confidence=0.99, page_number=1, section=section,
                       source=Source(type=typ, raw_value=value, anchor_label="", bbox=[0, 0, 0, 0],
                                     anchor_bbox=[0, 0, 0, 0]))


def expected_fields(sc: dict) -> list[FieldResult]:
    out = []
    for k, v in sc["text"].items():
        s, n = k.split("|", 1)
        out.append(_f(s, n, v, "text_grid"))
    for k, v in sc["choice"].items():
        s, n = k.split("|", 1)
        out.append(_f(s, n, v, "checkbox"))
    for k, v in sc["checkbox"].items():
        s, n = k.split("|", 1)
        out.append(_f(s, n, YES if v else NO, "checkbox"))
    for k, v in sc["signature"].items():
        s, n = k.split("|", 1)
        out.append(_f(s, n, YES if v else NO, "signature_image"))
    for k, v in sc["findings"].items():
        s, n = k.split("|", 1)
        out.append(_f(s, n, v, "findings_table"))
    for table, rows in sc["beneficiaries"].items():
        for i, row in enumerate(rows, 1):
            for lab, v in row.items():
                out.append(_f("מוטבים", "%s - שורה %d - %s" % (table, i, lab), v,
                              "table_row_cell"))
    for i, row in enumerate(sc["signing_log"], 1):
        for col, v in row.items():
            out.append(_f("חתימות",
                          "רשימת החתמות - שורה %d - %s" % (i, col),
                          v, "table_cell"))
    return out


def expected_result(sc: dict) -> ExtractionResult:
    fs = expected_fields(sc)
    return ExtractionResult(document_pages=0, fields=fs,
                            summary=Summary(total_fields_detected=len(fs), high_confidence=len(fs),
                                            medium_confidence=0, low_confidence=0, pages=0, potential_issues=[]))


def _n(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v)).strip()


def compare(sc: dict, got: ExtractionResult) -> dict:
    """Field by field (what the reader read) and Insurtix values (what the
    panel would key)."""
    exp = expected_fields(sc)
    plain_boxes = {k for k in sc["checkbox"]} | {k for k in sc["signature"]}
    have = {}
    for f in got.fields:
        have.setdefault((f.section, f.field_name), f.value)
    fields_bad = []
    for f in exp:
        g = have.get((f.section, f.field_name))
        if f.value == NO and g is None and (f.section + "|" + f.field_name) in plain_boxes:
            continue  # an empty box reads as nothing
        if _n(g) != _n(f.value):
            fields_bad.append({"field": f.section + " | " + f.field_name, "expected": f.value, "got": g})
    m_exp = to_insurtix(expected_result(sc))["values"]
    m_got = to_insurtix(got)["values"]
    map_bad = []
    for k in sorted(set(m_exp) | set(m_got)):
        a = m_exp.get(k, {}).get("value")
        b = m_got.get(k, {}).get("value")
        if a != b:
            map_bad.append({"path": k, "expected": a, "got": b})
    return {"fields": len(exp), "fields_bad": fields_bad, "mapped": len(m_exp), "mapped_bad": map_bad}
