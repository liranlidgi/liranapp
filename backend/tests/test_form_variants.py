"""Behaviours found on more real forms (values here are made up):
- LiveCycle version: selection marks drawn as black dots, values right-
  aligned in their cell instead of centered over the label;
- beneficiary tables: every row repeats its labels under the values;
- no collection day ticked, a discount written as a percent, no signing log,
  no named beneficiaries, mirrored brackets, geresh at the word start."""
from __future__ import annotations

from app.extraction.models import ExtractionResult, FieldResult, Source, Summary
from app.extraction.patterns import extract_field
from app.extraction.row_tables import extract_rows_table
from app.insurtix.mapping import _relation, to_insurtix
from app.pdf_extraction.bbox_extractor import Line, Word
from app.pdf_extraction.text_normalize import fix_word
from app.pdf_extraction.vector_marks import _is_black, _square
from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS

_id = [0]
SPECS = {f.field_name: f for f in FIELDS}


def line(words, y0, page=1, y1=None):
    y1 = y0 + 11.7 if y1 is None else y1
    _id[0] += 1
    ws = [Word(t, t, x0, y0, x1, y1, page, _id[0]) for t, x0, x1 in words]
    ws.sort(key=lambda w: -w.x1)
    return Line(_id[0], page, min(w.x0 for w in ws), y0, max(w.x1 for w in ws), y1, ws)


def mark(x0, y0, page=1, size=8.5):
    return line([("✔", x0, x0 + size)], y0, page, y0 + size)


def test_vector_mark_filters():
    assert _is_black(0.0) and _is_black((0, 0, 0)) and _is_black((0, 0, 0, 1.0))
    assert not _is_black((0.81, 0.0, 0.93, 0.0))          # the green of the logo
    assert _square(8.0, 8.0, 5.5, 11.0) and not _square(5.0, 7.0, 5.5, 11.0)


def test_dot_mark_selects_option_with_comma_text():
    # "לא ☐  כן ☐, פרט:" with the dot on "כן"
    lines = [
        line([("האם", 556, 578), ("יש", 540, 553), ("לך", 527, 537), ("תחביב", 495, 524),
              ("או", 482, 492), ("אורח", 455, 479), ("חיים", 430, 452), ("עם", 415, 427),
              ("סיכון", 386, 412), ("מיוחד,", 368, 384)], 501.0, 2),
        line([("לא", 355.5, 365.9)], 513.1, 2),
        line([("כן,", 320, 336.6), ("פרט:", 307.9, 318)], 513.1, 2),
        mark(340.6, 513.2, 2),
    ]
    spec = SPECS["תחביב או אורח חיים בסיכון מיוחד - מועמד ראשון"]
    assert extract_field(spec, lines, {2: 626.0}).value == "כן"


def test_right_aligned_value_above_label():
    lines = [
        line([("מאוחדת", 535.4, 568.2)], 359.5, 1, 367.2),
        line([("קופת", 518, 539.2), ("חולים", 498, 515)], 371.4),
        line([("בית", 345, 360), ("קפה", 322, 340)], 359.8, 1, 367.6),
        line([("עיסוק", 345, 367.2), ("בפועל", 322.2, 342)], 371.4),
    ]
    spec = next(f for f in FIELDS if f.field_name == "קופת חולים")
    assert extract_field(spec, lines, {1: 626.0}).value == "מאוחדת"


def _ben_row(y_vals, y_labels, values, gender_mark=None):
    labels = [("שם פרטי", 506, 539), ("שם משפחה", 405, 448), ("מספר זהות", 302, 342),
              ("תאריך לידה", 204, 247), ("מגדר", 142, 162), ("קרבה", 93, 114),
              ("% חלוקה", 47, 80)]
    out = [line([(t, a, b)], y_labels) for t, a, b in labels]
    out += [line([("ז", 156.3, 159.7)], y_vals + 3), line([("נ", 130.6, 134.3)], y_vals + 3)]
    out += [line([(t, a, b)], y_vals) for t, a, b in values]
    if gender_mark:
        out.append(mark(gender_mark, y_vals + 4))
    return out


def test_beneficiary_rows_values_above_labels():
    title = line([("פרטי", 555, 579), ("מוטבים", 520, 552), ("למועמד", 480, 517),
                  ("ראשון", 450, 477), ("לביטוח*", 402, 447)], 504.6)
    rows = _ben_row(521.7, 536.0, [(".1", 573.7, 579.6), ("דנה", 513, 532), ("כהן", 420, 440),
                                    ("1 2 3 4 5 6 7 8 2", 276, 367), ("01/02/2010", 200, 250),
                                    ("ילד/ה", 95, 119), ("60.00", 51, 74)], gender_mark=137.0)
    rows += _ben_row(549.9, 564.3, [(".2", 573.7, 579.6), ("יואב", 513, 532), ("כהן", 420, 440),
                                     ("01/03/2012", 200, 250), ("ילד/ה", 95, 119),
                                     ("40.00", 51, 74)], gender_mark=162.0)
    rows += _ben_row(578.0, 592.7, [(".3", 573.7, 579.6)])
    end = [line([("יורשים", 552, 575), ("חוקיים", 528, 550)], 620.0)]
    spec = BENEFICIARIES[0]
    got = {r.field_name.split(" - ", 1)[1]: r.value for r in extract_rows_table(spec, [title] + rows + end)}
    assert got == {
        "שורה 1 - שם פרטי": "דנה", "שורה 1 - שם משפחה": "כהן",
        "שורה 1 - מספר זהות": "1 2 3 4 5 6 7 8 2", "שורה 1 - תאריך לידה": "01/02/2010",
        "שורה 1 - מגדר": "נ", "שורה 1 - קרבה": "ילד/ה", "שורה 1 - % חלוקה": "60.00",
        "שורה 2 - שם פרטי": "יואב", "שורה 2 - שם משפחה": "כהן",
        "שורה 2 - תאריך לידה": "01/03/2012", "שורה 2 - מגדר": "ז",
        "שורה 2 - קרבה": "ילד/ה", "שורה 2 - % חלוקה": "40.00",
    }


def test_geresh_moved_back_to_the_end():
    assert fix_word("ץינולפ'") == "פלוניץ'"
    assert fix_word(",ןכ") == "כן,"


def test_relation_in_panel_wording():
    assert _relation("ילד/ה") == ("ילד/ה", False)
    assert _relation("בן / בת זוג") == ("בן / בת זוג", False)


def _fr(name, value, section="x", conf=0.95):
    return FieldResult(field_name=name, value=value, confidence=conf, page_number=1,
                       section=section, source=Source(type="t", raw_value=value,
                       anchor_label="", bbox=[0, 0, 0, 0], anchor_bbox=[0, 0, 0, 0]))


def _map(fields):
    r = ExtractionResult(document_pages=9, fields=fields, warnings=[], summary=Summary(
        total_fields_detected=len(fields), high_confidence=0, medium_confidence=0,
        low_confidence=0, pages=9, potential_issues=[]))
    out = to_insurtix(r)
    return out["values"], out["warnings"]


def test_form_rules():
    v, w = _map([
        _fr("אמצעי תשלום", "הוראת", section="אמצעי גביה"),
        _fr("קוד הנחה", "72%"),
        _fr("תאריך בהצהרות", "22/10/2026"),
        _fr("יורשים חוקיים - מועמד ראשון", "לא"),
        _fr("עיסוק בפועל", "תלמידי ישיבה )מעל דרג תיכון(", section="פרטי המועמד הראשון לביטוח"),
        _fr("שם פרטי", "דנה", section="פרטי המועמד הראשון לביטוח"),
    ])
    assert v["p.payment.collectionDay"]["value"] == "2" and v["p.payment.collectionDay"]["needs_review"]
    assert "p.discount" not in v and any("72%" in x for x in w)
    assert v["p.dates.signatureDate"]["value"] == "22/10/2026"
    assert v["p.beneficiaries"]["value"] == [] and "יורשים חוקיים" in v["p.beneficiaries"]["note"]
    assert v["p.answers.InsuredDetailes.Occupation"]["value"] == "תלמידי ישיבה (מעל דרג תיכון)"


def test_signing_log_date_wins_over_declaration_date():
    v, _ = _map([_fr("רשימת החתמות - שורה 1 - תאריך חתימה", "21/10/2026 12:00:00"),
                 _fr("תאריך בהצהרות", "19/10/2026")])
    assert v["p.dates.signatureDate"]["value"] == "21/10/2026"
