"""Tests for the Insurtix panel mapping. They use synthetic extraction
results (no real proposal form, which holds personal data)."""
from __future__ import annotations

from app.extraction.models import ExtractionResult, FieldResult, Source, Summary
from app.insurtix.mapping import to_insurtix

OWNER = "פרטי בעל הפוליסה"
C1 = "פרטי המועמד הראשון לביטוח"
C2 = "פרטי המועמד השני לביטוח"


def F(section, name, value, conf=0.97, page=1):
    return FieldResult(field_name=name, value=value, confidence=conf, page_number=page,
                       section=section, source=Source(type="text_grid", raw_value=value,
                                                      anchor_label=name, bbox=[0, 0, 1, 1],
                                                      anchor_bbox=[0, 0, 1, 1]))


def R(fields, warnings=()):
    return ExtractionResult(document_pages=16, fields=fields, warnings=list(warnings),
                            summary=Summary(total_fields_detected=len(fields), high_confidence=0,
                                            medium_confidence=0, low_confidence=0, pages=16,
                                            potential_issues=[]))


def base():
    person = []
    for sec in (OWNER, C1):
        person += [F(sec, "שם פרטי", "ישראל"), F(sec, "שם משפחה", "ישראלי"),
                   F(sec, "תאריך לידה", "7/4/1999"), F(sec, "מגדר", "ז"),
                   F(sec, "כתובת: רחוב", "הבנים"), F(sec, "מספר בית", "21"),
                   F(sec, "עיר / יישוב", "ראשון לציון"), F(sec, "דואר אלקטרוני", "a @b.co")]
    return person + [
        F(OWNER, "מספר זהות / חברה", "22461018-8"), F(C1, "מספר זהות", "224610188"),
        F(OWNER, "מספר טלפון נייד / חברה", "054-4305748"), F(C1, "מספר טלפון נייד", "0544305748"),
        F("פרטי הסוכן", "מועד תחילת הביטוח", "01.11.2026"),
        F("פרטי הסוכן", "מספר סוכן", "839"), F("פרטי הסוכן", "קוד הנחה", "178"),
        F("פרטי הסוכן", "מספר הצעה", "123456"),
        F("פרטי הכיסוי הביטוחי", "סכום הביטוח המבוקש - מועמד ראשון", "1,000,000 ₪"),
        F("פרטי הכיסוי הביטוחי", "גיל תום ביטוח - מועמד ראשון", "84"),
        F(C1, "עיסוק בפועל", "מהנדס תוכנה", conf=0.85), F(C1, "קופת חולים", "מכבי"),
        F("פרטים נוספים", "תחביב או אורח חיים בסיכון מיוחד - מועמד ראשון", "לא"),
        F("פרטים נוספים", "אזרחות ישראלית - מועמד ראשון", "כן"),
        F("הצהרת בריאות", "2.1 עישון בשנתיים האחרונות - מועמד ראשון", "כן"),
        F("הצהרת בריאות", "3.2 מחלות לב וכלי דם - מועמד ראשון", "כן"),
        F("הצהרת בריאות", "2.10 מחלות רקע משפחתי מדרגה ראשונה - מועמד ראשון", "לא"),
        F("הצהרת בריאות", "גובה - מועמד ראשון", "175"),
        F("הצהרת בריאות", "משקל - מועמד ראשון", "80"),
        F("ביטוחים קיימים", "קיימת פוליסת ריסק אחרת - מועמד ראשון", "לא"),
        F("אמצעי גביה", "אמצעי תשלום", "הוראת קבע בנקאית"),
        F("אמצעי גביה", "יום גביה מבוקש", "10"),
        F("הרשאה לחיוב חשבון", "בנק", "12"), F("הרשאה לחיוב חשבון", "מספר סניף", "123"),
        F("הרשאה לחיוב חשבון", "מספר חשבון", "65-4654"),
        F("חתימות", "רשימת החתמות - שורה 1 - תאריך חתימה", "28/10/2026 14:31"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - שם פרטי", "דנה"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - שם משפחה", "ישראלי"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - מספר זהות", "332389659"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - תאריך לידה", "23/09/2019"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - מגדר", "נ"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - קרבה", "בת"),
        F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - % חלוקה", "100%"),
    ]


def v(out, path):
    return out["values"][path]["value"]


def test_full_mapping_and_normalization():
    out = to_insurtix(R(base()), "x.pdf")
    assert out["format"] == "insurtix-proposal" and out["version"] == 1
    assert out["source"]["proposal_number"] == "123456"
    assert v(out, "p.owner.firstName") == "ישראל"
    assert v(out, "p.owner.birthDate") == "07/04/1999"
    assert v(out, "p.owner.gender") == "male"
    assert v(out, "p.owner.idNumber") == "224610188"
    assert v(out, "p.owner.phone") == "0544305748"
    assert v(out, "p.owner.email") == "a@b.co"
    assert v(out, "p.dates.requestedStartDate") == "01/11/2026"
    assert v(out, "p.dates.signatureDate") == "28/10/2026"
    assert v(out, "p.agent") == "839" and v(out, "p.discount") == "178"
    assert v(out, "p.cover.insuranceSum") == 1000000 and v(out, "p.cover.untilAge") == 84
    assert v(out, "p.answers.InsuredDetailes.HMO") == "מכבי"
    assert v(out, "p.answers.InsuredDetailes.IsSmoking") is True
    assert v(out, "p.answers.InsuredDetailes.Hobbies") is False
    assert v(out, "p.answers.HealthDeclaration.CardiovascularDiseases") is True
    assert v(out, "p.answers.HealthDeclaration.FamilyHistoryOfIllness") is False
    assert v(out, "p.answers.HealthDeclaration.Height") == 1.75
    assert v(out, "p.answers.HealthDeclaration.Weight") == 80
    assert v(out, "p.answers.ComparisonQuestionnaire.OtherPolicy") is False
    assert v(out, "p.payment.collectionDay") == "10"
    assert v(out, "p.payment.bank") == "12" and v(out, "p.payment.branch") == "123"
    assert v(out, "p.payment.accountNumber") == "654654"
    ben = v(out, "p.beneficiaries")
    assert ben == [{"firstName": "דנה", "lastName": "ישראלי", "idNumber": "332389659",
                    "birthDate": "23/09/2019", "gender": "female", "relation": "ילד/ה",
                    "percent": 100}]
    assert out["warnings"] == []


def test_review_flags():
    out = to_insurtix(R(base()))
    assert out["values"]["p.answers.InsuredDetailes.Occupation"]["needs_review"]
    assert out["values"]["p.owner.city"]["needs_review"]
    assert not out["values"]["p.owner.firstName"]["needs_review"]
    low = [f for f in base() if f.field_name != "שם פרטי"] + [F(C1, "שם פרטי", "ישראל", conf=0.7)]
    out = to_insurtix(R(low))
    assert out["values"]["p.owner.firstName"]["needs_review"]


def test_owner_differs_uses_candidate_one():
    fields = [f for f in base() if not (f.section == OWNER and f.field_name == "שם פרטי")]
    fields.append(F(OWNER, "שם פרטי", "חברה בעמ"))
    out = to_insurtix(R(fields))
    assert v(out, "p.owner.firstName") == "ישראל"
    assert any("שונה מהמועמד הראשון" in w for w in out["warnings"])


def test_owner_only_when_no_candidate_block():
    fields = [f for f in base() if f.section != C1]
    out = to_insurtix(R(fields))
    assert v(out, "p.owner.idNumber") == "224610188"
    assert v(out, "p.owner.phone") == "0544305748"


def test_second_candidate_and_credit_card_warn():
    fields = base() + [F(C2, "שם פרטי", "שני"), F("אמצעי גביה", "אמצעי תשלום", "כרטיס אשראי")]
    out = to_insurtix(R(fields))
    assert any("מועמד שני" in w for w in out["warnings"])
    assert any("כרטיס אשראי" in w for w in out["warnings"])


def test_bad_values_become_warnings_not_values():
    fields = [f for f in base() if f.field_name != "תאריך לידה"] + [F(C1, "תאריך לידה", "31/02/1999")]
    out = to_insurtix(R(fields))
    assert "p.owner.birthDate" not in out["values"]
    assert any("31/02/1999" in w for w in out["warnings"])


def test_beneficiary_percent_and_relation_review():
    fields = [f for f in base() if "% חלוקה" not in f.field_name and "קרבה" not in f.field_name]
    fields += [F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - % חלוקה", "50"),
               F("מוטבים", "מוטבים למועמד ראשון לביטוח - שורה 1 - קרבה", "דודה")]
    out = to_insurtix(R(fields))
    b = out["values"]["p.beneficiaries"]
    assert b["needs_review"] and b["value"][0]["relation"] == "אחר"
    assert any("100" in w for w in out["warnings"])


def test_empty_result():
    out = to_insurtix(R([], warnings=["סרוק"]))
    assert out["values"] == {} and out["warnings"] == ["סרוק"]


def test_api_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    import app.main as m
    monkeypatch.setattr(m, "run_extraction", lambda path, f, t, *rest: R(base()))
    c = TestClient(m.app)
    r = c.post("/api/insurtix", files={"file": ("p.pdf", b"%PDF-1.4 x", "application/pdf")})
    assert r.status_code == 200
    j = r.json()
    assert j["format"] == "insurtix-proposal" and j["source"]["file"] == "p.pdf"
    assert j["values"]["p.owner.idNumber"]["value"] == "224610188"
    r = c.post("/api/insurtix", files={"file": ("p.txt", b"x", "text/plain")})
    assert r.status_code == 400


def test_two_digit_year_dates():
    from datetime import datetime
    from app.insurtix.mapping import _date
    assert _date("01/09/26") == "01/09/2026"
    assert _date("1.9.26") == "01/09/2026"
    assert _date("01/09/2026") == "01/09/2026"
    assert _date("07/04/99", past=True) == "07/04/1999"
    assert _date("07/04/05", past=True) == "07/04/2005"
    nxt = (datetime.now().year + 1) % 100
    assert _date(f"01/01/{nxt:02d}") == f"01/01/{2000 + nxt}"           # start date next year
    assert _date(f"01/01/{nxt:02d}", past=True) == f"01/01/{1900 + nxt}"  # birth date
    assert _date("31/02/26") is None
    assert _date("01/09/2026 10:15") == "01/09/2026"

