"""ROW pattern: value on the same table row, under a candidate column header
(height/weight rows of the health declaration). Synthetic geometry modelled
on the real form: question column on the right, candidate 1 then candidate 2
columns to its left."""
from __future__ import annotations

from app.extraction.patterns import extract_field
from app.pdf_extraction.bbox_extractor import Line, Word
from app.template.shlomo_life_insurance import FIELDS

_id = [0]


def line(words, y0, y1, page=3):
    """words: list of (text, x0, x1) in any order."""
    _id[0] += 1
    ws = [Word(t, t, x0, y0, x1, y1, page, _id[0]) for t, x0, x1 in words]
    ws.sort(key=lambda w: -w.x1)
    return Line(_id[0], page, min(w.x0 for w in ws), y0, max(w.x1 for w in ws), y1, ws)


HEADERS = [
    line([("מסמכים", 97, 140), ("נוספים", 62, 95), ("שדרושים", 20, 60)], 300, 310),
    line([("מועמד", 282, 315), ("שני", 262, 280), ("לביטוח", 230, 260)], 300, 310),
    line([("מועמד", 422, 455), ("ראשון", 392, 420), ("לביטוח", 360, 390)], 300, 310),
    line([("השאלה", 520, 550)], 300, 310),
]
SPECS = {f.field_name: f for f in FIELDS if f.field_name.startswith(("גובה", "משקל"))}


def run(lines):
    return {n: extract_field(s, lines, {3: 595}) for n, s in SPECS.items()}


def test_separate_lines():
    lines = HEADERS + [
        line([("1.", 570, 580)], 318, 328),
        line([("גובה", 520, 545), ('(בס"מ)', 490, 518)], 318, 328),
        line([("172", 398, 415)], 318, 328),
        line([("157", 265, 282)], 318, 328),
        line([("משקל", 520, 548), ('(בק"ג)', 490, 518)], 338, 348),
        line([("82", 400, 412)], 338, 348),
        line([("62", 268, 280)], 338, 348),
    ]
    r = run(lines)
    assert r["גובה - מועמד ראשון"].value == "172"
    assert r["גובה - מועמד שני"].value == "157"
    assert r["משקל - מועמד ראשון"].value == "82"
    assert r["משקל - מועמד שני"].value == "62"
    assert all(x.confidence >= 0.9 for x in r.values())
    assert r["גובה - מועמד ראשון"].source.type == "table_row"


def test_values_merged_into_label_line():
    lines = HEADERS + [
        line([("1.", 570, 580), ("גובה", 520, 545), ('(בס"מ)', 490, 518),
              ("172", 398, 415), ("157", 265, 282)], 318, 328),
    ]
    r = run(lines)
    assert r["גובה - מועמד ראשון"].value == "172"
    assert r["גובה - מועמד שני"].value == "157"
    assert r["משקל - מועמד ראשון"] is None


def test_empty_second_candidate_and_no_header():
    lines = HEADERS + [
        line([("גובה", 520, 545), ('(בס"מ)', 490, 518)], 318, 328),
        line([("172", 398, 415)], 318, 328),
    ]
    r = run(lines)
    assert r["גובה - מועמד ראשון"].value == "172"
    assert r["גובה - מועמד שני"] is None
    no_header = [l for l in lines if "ראשון" not in l.text]
    assert run(no_header)["גובה - מועמד ראשון"] is None


def test_headers_merged_into_one_line():
    merged = [line([("מסמכים", 97, 140), ("נוספים", 62, 95), ("שדרושים", 20, 60)], 300, 310),
              line([("השאלה", 520, 550), ("מועמד", 422, 455), ("ראשון", 392, 420),
                    ("לביטוח", 360, 390), ("מועמד", 282, 315), ("שני", 262, 280),
                    ("לביטוח", 230, 260)], 300, 310)]
    lines = merged + [
        line([("גובה", 520, 545), ('(בס"מ)', 490, 518)], 318, 328),
        line([("172", 398, 415)], 318, 328),
        line([("157", 265, 282)], 318, 328),
    ]
    r = run(lines)
    assert r["גובה - מועמד ראשון"].value == "172"
    assert r["גובה - מועמד שני"].value == "157"
