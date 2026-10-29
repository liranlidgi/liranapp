"""Patterns added after checking a real proposal form: INLINE (value right
after the label), SIGNED (date stamp at a section's signature slot),
CHECKBOX, the "5-ב" / "ב-5" anchor normalization and tables that are
searched on several pages. Geometry is copied from the real form; the values
are made up."""
from __future__ import annotations

from app.extraction.models import ExtractionResult, FieldResult, Source, Summary
from app.extraction.patterns import _normalize, extract_field
from app.extraction.tables import extract_table
from app.insurtix.mapping import to_insurtix
from app.pdf_extraction.bbox_extractor import Line, Word
from app.template.schema import FieldSpec, Pattern
from app.template.shlomo_life_insurance import FIELDS, TABLES

_id = [0]
SPECS = {f.field_name: f for f in FIELDS}


def line(words, y0, page, y1=None):
    y1 = y0 + 11.7 if y1 is None else y1
    _id[0] += 1
    ws = [Word(t, t, x0, y0, x1, y1, page, _id[0]) for t, x0, x1 in words]
    ws.sort(key=lambda w: -w.x1)
    return Line(_id[0], page, min(w.x0 for w in ws), y0, max(w.x1 for w in ws), y1, ws)


def get(name, lines, page_w=648.0):
    r = extract_field(SPECS[name], lines, {p: page_w for p in range(1, 31)})
    return None if r is None else r.value


def test_flipped_number_prefix_matches_anchor():
    assert _normalize("שביצעת 5-ב השנים האחרונות") == _normalize("שביצעת ב-5 השנים האחרונות")
    assert _normalize("גיל 65") == "גיל65"


def test_health_2_7_found_with_flipped_prefix():
    lines = [
        line([("האם", 553, 570), ("בבדיקות", 515, 550), ("דם", 503, 512), ("ושתן", 480, 500),
              ("שביצעת", 445, 477), ("5-ב", 430, 442), ("השנים", 405, 427),
              ("האחרונות", 380, 402)], 522.0, 3),
        line([("נמצאה", 540, 570), ("חריגה", 512, 537), ("שדרשה", 482, 509), ("המשך", 455, 479),
              ("בירור?", 442, 452)], 533.3, 3),
        line([("✔", 318, 325), ("לא", 304, 315), ("כן", 278, 285)], 533.3, 3),
        line([("✔", 219, 226), ("לא", 205, 216), ("כן", 179, 186)], 533.3, 3),
    ]
    assert get("2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות - מועמד ראשון", lines) == "לא"
    assert get("2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות - מועמד שני", lines) == "לא"


def test_inline_cigarettes_per_candidate():
    lines = [
        line([("כמה", 333, 347), ("סיגריות", 300, 330), ("ליום?", 282, 298)], 306.8, 3),
        line([("7", 266, 271)], 307.1, 3, 316.0),
        line([("כמה", 234, 248), ("סיגריות", 201, 231), ("ליום?", 183, 199)], 306.8, 3),
        line([("0", 167, 172)], 307.4, 3, 316.3),
    ]
    assert get("כמות סיגריות ליום - מועמד ראשון", lines) == "7"
    assert get("כמות סיגריות ליום - מועמד שני", lines) == "0"


def test_inline_company_on_cancellation_appendix():
    lines = [
        line([("עבור", 570, 594), ("חברת", 545, 567), ("הביטוח:", 523, 542)], 174.5, 10),
        line([("מגדל", 422, 441)], 166.5, 10, 175.4),
    ]
    assert get("חברת ביטוח לביטול - מועמד ראשון", lines) == "מגדל"
    assert get("חברת ביטוח לביטול - מועמד שני", lines) is None


def _signature_block(page, signed):
    out = [
        line([("פניה", 570, 589), ("שיווקית", 546, 567)], 628.8, page),
        line([("חתימת", 530, 555), ("בעל", 515, 528), ("הפוליסה", 480, 512)], 730.6, page),
        line([("חתימת", 375, 401), ("מועמד", 345, 372), ("ראשון", 320, 342),
              ("לביטוח", 299, 318)], 730.6, page),
        line([("X", 436, 443)], 719.1, page, 729.5),
    ]
    if signed:
        out.append(line([("01/02/2026", 374, 404)], 726.2, page, 732.9))
    return out


def test_signed_section():
    assert get("חתום: פניה שיווקית - מועמד ראשון", _signature_block(6, True)) == "כן"
    assert get("חתום: פניה שיווקית - מועמד ראשון", _signature_block(6, False)) == "לא"


def test_date_in_the_date_column_is_not_a_signature():
    lines = _signature_block(6, False) + [line([("01/02/2026", 498, 538)], 700.0, 6, 709.0)]
    assert get("חתום: פניה שיווקית - מועמד ראשון", lines) == "לא"


def test_checkbox():
    ticked = [line([("✔", 578, 588), ("יורשים", 552, 575), ("חוקיים", 528, 550)], 719.5, 1)]
    empty = [line([("יורשים", 552, 575), ("חוקיים", 528, 550)], 719.5, 1)]
    assert get("יורשים חוקיים - מועמד ראשון", ticked) == "כן"
    assert get("יורשים חוקיים - מועמד ראשון", empty) == "לא"
    assert get("יורשים חוקיים - מועמד ראשון", []) is None


def test_signing_log_found_on_any_page():
    spec = next(t for t in TABLES if t.table_name == "רשימת החתמות")
    heads = [("תחנה", 585, 605), ("שם תחנה", 534, 569), ("שם החותם", 462, 503),
             ("דואר אלקטרוני", 333, 390), ("טלפון נייד", 227, 266),
             ("כתובת ממנה נחתם", 131, 201), ("תאריך חתימה", 38, 90)]
    lines = [line([h], 234.5, 14) for h in heads] + [
        line([("1", 592, 598)], 255.8, 14), line([("לקוח", 542, 561)], 255.8, 14),
        line([("01/02/2026 12:56:59", 16, 112)], 255.8, 14),
    ]
    got = {r.field_name: (r.value, r.page_number) for r in extract_table(spec, lines)}
    assert got["רשימת החתמות - שורה 1 - תאריך חתימה"] == ("01/02/2026 12:56:59", 14)


def _fr(name, value, section="x", conf=0.95):
    return FieldResult(field_name=name, value=value, confidence=conf, page_number=1,
                       section=section, source=Source(type="t", raw_value=value,
                       anchor_label="", bbox=[0, 0, 0, 0], anchor_bbox=[0, 0, 0, 0]))


def _map(fields):
    r = ExtractionResult(document_pages=14, fields=fields, warnings=[], summary=Summary(
        total_fields_detected=len(fields), high_confidence=0, medium_confidence=0,
        low_confidence=0, pages=14, potential_issues=[]))
    out = to_insurtix(r)
    return {k: v["value"] for k, v in out["values"].items()}, out["warnings"]


C1 = " - מועמד ראשון"


def test_mapping_new_fields():
    v, w = _map([
        _fr("2.1 עישון בשנתיים האחרונות" + C1, "כן"),
        _fr("כמות סיגריות ליום" + C1, "7"),
        _fr("יורשים חוקיים" + C1, "כן"),
        _fr("להותיר את הפוליסה ללא שינוי" + C1, "לא"),
        _fr("לבטל את הפוליסה הקיימת" + C1, "כן"),
        _fr("הגשת ביטול באמצעות שלמה" + C1, "באמצעות"),
        _fr("חברת ביטוח לביטול" + C1, "ליברה"),
        _fr("שם המוטב הבלתי חוזר (בנק)" + C1, "דיסקונט"),
        _fr("מספר בנק" + C1, "11"),
        _fr("מספר סניף" + C1, "10"),
        _fr("חתום: פניה שיווקית" + C1, "לא"),
        _fr("חתום: הגנת הפרטיות" + C1, "כן"),
        _fr("חתום: הצהרת הסוכן", "כן"),
        _fr("מבקש מסמכים בדואר ישראל", "לא"),
        _fr("אמצעי תשלום", "הוראת", section="אמצעי גביה"),
    ])
    assert v["p.answers.SmokeHelthComp.NumberSig"] == 7
    assert v["p.beneficiaries"] == []
    assert v["p.answers.ComparisonQuestionnaire.IsCancellationRequired"] is True
    assert v["p.answers.ComparisonQuestionnaire.IsCancellationRequiredByShlomo"] is True
    assert v["p.answers.ComparisonQuestionnaire.InsuranceCompany"] == "ליברה חברה לביטוח"
    assert (v["p.lien.type"], v["p.lien.bank"], v["p.lien.branch"]) == ("bank", "11", "10")
    assert v["p.owner.marketingApproval"] is False
    assert v["p.answers.PolicyOwnerAgreements.PrivacyProtection"] is True
    assert v["p.answers.InshuredAgreemntAndDeclarration.PrivacyProtection"] is True
    assert v["p.answers.MethodSale.AgentStatementCopy"] is True
    assert v["p.owner.digitalMailing"] is True
    assert any("פרטי חשבון הבנק" in x for x in w)


def test_no_cigarettes_when_not_smoking():
    v, _ = _map([_fr("2.1 עישון בשנתיים האחרונות" + C1, "לא"),
                 _fr("כמות סיגריות ליום" + C1, "0")])
    assert "p.answers.SmokeHelthComp.NumberSig" not in v
