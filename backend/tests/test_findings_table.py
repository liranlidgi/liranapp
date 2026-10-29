"""Positive-findings table (health declaration section 4, "פירוט ממצאים
חיוביים"). Synthetic geometry copied from a screenshot of the real form:
question column on the right, then candidate 1, candidate 2 and the extra
documents column. Each candidate column has a narrow "מס' שאלה" sub-column
on its right and a wide "פרטים" sub-column on its left."""
from __future__ import annotations

from app.extraction.findings import extract_findings
from app.extraction.models import ExtractionResult, FieldResult, Source, Summary
from app.insurtix.mapping import to_insurtix
from app.pdf_extraction.bbox_extractor import Line, Word
from app.template.shlomo_life_insurance import FINDINGS

_id = [0]
PAGE = 4


def line(words, y0, y1=None, page=PAGE):
    """words: list of (text, x0, x1)."""
    y1 = y0 + 12 if y1 is None else y1
    _id[0] += 1
    ws = [Word(t, t, x0, y0, x1, y1, page, _id[0]) for t, x0, x1 in words]
    ws.sort(key=lambda w: -w.x1)
    return Line(_id[0], page, min(w.x0 for w in ws), y0, max(w.x1 for w in ws), y1, ws)


def column_headers():
    return [
        line([("השאלה", 780, 830)], 48),
        line([("מועמד", 530, 575), ("ראשון", 487, 525), ("לביטוח", 435, 482)], 48),
        line([("מועמד", 333, 378), ("שני", 305, 328), ("לביטוח", 255, 300)], 48),
        line([("מסמכים", 160, 210), ("נוספים", 105, 155), ("שדרושים", 40, 100)], 48),
    ]


def sub_headers():
    return [
        line([("4.", 1030, 1045)], 85),
        line([("פירוט", 950, 990), ("ממצאים", 890, 945), ("חיוביים:", 830, 885)], 85),
        line([("בעת", 990, 1015), ("מענה", 950, 985), ("חיובי", 910, 945)], 105),
        # candidate 1
        line([("מס'", 560, 590)], 85), line([("שאלה", 548, 592)], 105),
        line([("פרטים", 455, 500)], 85),
        # candidate 2
        line([("מס'", 372, 400)], 85), line([("שאלה", 360, 405)], 105),
        line([("פרטים", 267, 312)], 85),
    ]


CAND2_DETAILS = [
    line([("דוגמה", 310, 350), ("לטקסט", 280, 306), ("חופשי", 245, 276)], 145),
    line([("שנכתב", 318, 350), ("בעמודת", 292, 314), ("הפרטים", 268, 288), ("לבדיקה", 235, 264)], 160),
    line([("בלבד", 325, 350), ("ואינו", 298, 321), ("מתאר", 268, 294), ("מקרה", 240, 264)], 175),
    line([("אמיתי", 315, 350), ("כלשהו.", 285, 311)], 190),
]
END = [line([("חתימות", 995, 1050)], 638), line([("ת.ז", 600, 620)], 660)]


def run(lines):
    out = {}
    for spec in FINDINGS:
        for r in extract_findings(spec, lines):
            out[r.field_name] = r.value
    return out


def test_screenshot_layout_candidate_two():
    lines = column_headers() + sub_headers() + [line([("2.5", 372, 395)], 143)] \
        + CAND2_DETAILS + END
    got = run(lines)
    assert got == {
        "ממצאים חיוביים - מועמד שני - שורה 1 - מס' שאלה": "2.5",
        "ממצאים חיוביים - מועמד שני - שורה 1 - פרטים":
            "דוגמה לטקסט חופשי שנכתב בעמודת הפרטים לבדיקה בלבד ואינו מתאר מקרה אמיתי כלשהו.",
    }


def test_two_entries_candidate_one():
    lines = column_headers() + sub_headers() + [
        line([("2.5", 560, 583)], 143),
        line([("ניתוח", 505, 538), ("בברך", 470, 500)], 145),
        line([("בשנת", 505, 538), ("2023", 470, 500)], 160),
        line([("2.6", 560, 583)], 200),
        line([("כדורים", 495, 538), ("ללחץ", 460, 490), ("דם", 440, 455)], 202),
    ] + END
    got = run(lines)
    p = "ממצאים חיוביים - מועמד ראשון - "
    assert got[p + "שורה 1 - מס' שאלה"] == "2.5"
    assert got[p + "שורה 1 - פרטים"] == "ניתוח בברך בשנת 2023"
    assert got[p + "שורה 2 - מס' שאלה"] == "2.6"
    assert got[p + "שורה 2 - פרטים"] == "כדורים ללחץ דם"
    assert not any("מועמד שני" in k for k in got)


def test_merged_column_header_line():
    merged = line([
        ("השאלה", 780, 830),
        ("מועמד", 530, 575), ("ראשון", 487, 525), ("לביטוח", 435, 482),
        ("מועמד", 333, 378), ("שני", 305, 328), ("לביטוח", 255, 300),
        ("מסמכים", 160, 210), ("נוספים", 105, 155), ("שדרושים", 40, 100),
    ], 48)
    lines = [merged] + sub_headers() + [line([("2.5", 372, 395)], 143)] + CAND2_DETAILS + END
    got = run(lines)
    assert got["ממצאים חיוביים - מועמד שני - שורה 1 - מס' שאלה"] == "2.5"
    assert not any("מועמד ראשון" in k for k in got)


def test_text_below_end_band_is_ignored():
    lines = column_headers() + sub_headers() + [
        line([("2.5", 372, 395)], 143), CAND2_DETAILS[0],
        line([("חתימה", 300, 340)], 700),  # signatures area, below "חתימות"
    ] + END
    got = run(lines)
    assert got["ממצאים חיוביים - מועמד שני - שורה 1 - פרטים"] == "דוגמה לטקסט חופשי"


def test_no_anchor_no_results():
    assert run(column_headers() + END) == {}


def _fr(name, value, section="הצהרת בריאות", conf=0.95):
    return FieldResult(field_name=name, value=value, confidence=conf, page_number=PAGE,
                       section=section, source=Source(type="t", raw_value=value,
                       anchor_label="", bbox=[0, 0, 0, 0], anchor_bbox=[0, 0, 0, 0]))


def _result(fields):
    return ExtractionResult(document_pages=16, fields=fields, warnings=[], summary=Summary(
        total_fields_detected=len(fields), high_confidence=0, medium_confidence=0,
        low_confidence=0, pages=16, potential_issues=[]))


def test_mapping_findings_warnings():
    p1 = "ממצאים חיוביים - מועמד ראשון - שורה 1 - "
    p2 = "ממצאים חיוביים - מועמד שני - שורה 1 - "
    out = to_insurtix(_result([
        _fr(p1 + "מס' שאלה", "2.5"), _fr(p1 + "פרטים", "ניתוח בברך"),
        _fr("2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות - מועמד ראשון", "לא"),
        _fr(p2 + "מס' שאלה", "2.5"), _fr(p2 + "פרטים", "טיפול לדוגמה"),
    ]))
    assert out["findings"] == [
        {"candidate": 1, "question": "2.5",
         "question_title": "2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות",
         "details": "ניתוח בברך", "confidence": 0.95, "needs_review": False},
        {"candidate": 2, "question": "2.5",
         "question_title": "2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות",
         "details": "טיפול לדוגמה", "confidence": 0.95, "needs_review": False},
    ]
    w = "\n".join(out["warnings"])
    assert "ממצא חיובי של המועמד הראשון, שאלה 2.5 ניתוח / בדיקות הדמיה" in w
    assert "ניתוח בברך" in w
    assert "סומן 'לא'" in w
    assert "למועמד השני יש 1 ממצאים חיוביים (שאלות: 2.5)" in w
