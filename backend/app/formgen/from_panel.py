"""The values of the Insurtix policy panel (its proposal state, ``state.p``)
-> a scenario of the proposal form (code 10), so the external copy of the
panel can export what the user entered as a filled form PDF.

This is the reverse of ``app.insurtix.mapping.to_insurtix``: reading the
exported PDF back gives the same panel values (``roundtrip`` checks that).
Values the form has no place for are listed in ``not_in_form``."""
from __future__ import annotations

import random
import re
from datetime import date, datetime
from typing import Any

from . import scenario as S

C1 = "מועמד ראשון"
SEC = S.SEC_I1
GENDER = {"male": "ז", "female": "נ"}
# panel relation -> the word written on the form, by the beneficiary's gender
RELATION = {
    "בן / בת זוג": ("בן זוג", "בת זוג"),
    "ילד/ה": ("בן", "בת"),
    "אח/אחות": ("אח", "אחות"),
    "נכד/ה": ("נכד", "נכדה"),
    "אחר": ("אחר", "אחר"),
}
HEALTH = {
    "WeightChange10p": "שינוי משמעותי במשקל בשנתיים האחרונות",
    "IsAlcohol": "2.2 צריכת אלכוהול קבועה",
    "IsDrugs": "2.3 שימוש בסמים",
    "HospitalizationInTheLast5Years": "2.4 אשפוז ב-5 שנים אחרונות",
    "SurgeriesInTheLast5Years": "2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות",
    "IsMedicinesRegularly": "2.6 נטילת תרופות קבועה",
    "BloodAndUrineTest": "2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות",
    "Disability": "2.8 נכות / תהליך קביעת נכות",
    "ClearProcess": "2.9 בדיקה רפואית אבחנתית לא הושלמה",
    "FamilyHistoryOfIllness": "2.10 מחלות רקע משפחתי מדרגה ראשונה",
    "NervousSystemAndBrain": "3.1 מחלות מערכת העצבים והמוח",
    "CardiovascularDiseases": "3.2 מחלות לב וכלי דם",
    "DigestiveTract": "3.3 מחלות דרכי עיכול",
    "LungsAndRespiratoryTract": "3.4 מחלות ריאות ודרכי נשימה",
    "KidneysAndUrinaryTract": "3.5 מחלות כליות ודרכי השתן",
    "MalignantDiseases": "3.6 מחלות ממאירות וגידולים",
    "EndoCrinology": "3.7 מחלה מטבולית / הורמונלית (סוכרת, שומנים)",
    "RheumaticDiseases": "3.8 מחלות ראומטיות",
    "InfectiousDiseases": "3.9 מחלות זיהומיות / דלקתיות / מערכת חיסון / מערכת הדם",
    "ReproductiveSystem": "3.10 מערכת הרבייה",
    "Soul": "3.11 מצב נפשי",
}
INSURED = {
    "IsSmoking": ("הצהרת בריאות", "2.1 עישון בשנתיים האחרונות"),
    "Hobbies": ("פרטים נוספים", "תחביב או אורח חיים בסיכון מיוחד"),
    "PilotsLicense": ("פרטים נוספים", "רשיון טיס / צוות אוויר"),
    "StayingAbroad": ("פרטים נוספים", 'שהייה בחו"ל מעל 180 יום'),
    "IsIsraeliCitizen": ("פרטים נוספים", "אזרחות ישראלית"),
}
# what the form cannot carry (no box for it, or only some values)
NOT_IN_FORM = {
    "p.dates.receivedDate": "תאריך קבלה – לא מופיע בטופס",
    "p.answers.MethodSale.MethodOfSale": "אופן מכירה – לא מופיע בטופס",
    "p.answers.FamilyBackgroundHelthComp": "שאלון רקע משפחתי – לא מופיע בטופס",
}


def _s(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip()


def _num_first(v: Any) -> str:
    """'839 - name' -> '839' (agents, discounts)."""
    m = re.match(r"\s*(\d+)", _s(v))
    return m.group(1) if m else re.sub(r"\D", "", _s(v))


def _num_last(v: Any) -> str:
    """'name - 54' -> '54' (banks, branches); a plain number stays."""
    s = _s(v)
    m = re.search(r"-\s*(\d+)\s*$", s)
    if m:
        return m.group(1)
    return s if re.fullmatch(r"\d+", s) else re.sub(r"\D", "", s)


def _name_part(v: Any) -> str:
    """'name - 31' or '31 - name' -> 'name'."""
    s = _s(v)
    parts = [p.strip() for p in s.split(" - ")]
    names = [p for p in parts if not re.fullmatch(r"\d+", p)]
    return names[0] if names else s


def _yn(v: Any) -> str | None:
    if v is True:
        return "כן"
    if v is False:
        return "לא"
    return None


def _date(v: Any) -> str:
    s = _s(v)
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d.%m.%Y"):
        try:
            return datetime.strptime(s[:10], fmt).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return s


def _number(v: Any) -> str:
    if v in (None, ""):
        return ""
    try:
        n = float(str(v).replace(",", ""))
    except ValueError:
        return _s(v)
    return str(int(n)) if n.is_integer() else str(n)


def _get(o: dict, path: str) -> Any:
    for k in path.split("."):
        if not isinstance(o, dict):
            return None
        o = o.get(k)
    return o


def panel_to_scenario(p: dict, seed: int | None = None) -> tuple[dict, list[str]]:
    """Panel values -> form scenario, and notes about what was changed or left out."""
    rnd = random.Random(seed)
    notes: list[str] = []
    t: dict[str, str] = {}
    ch: dict[str, str] = {}
    cb: dict[str, bool] = {}
    sig: dict[str, bool] = {}
    owner = p.get("owner") or {}
    ans = p.get("answers") or {}

    def put(key, v):
        v = _s(v)
        if v:
            t[key] = v

    # agent, start date, discount
    dates = p.get("dates") or {}
    put("פרטי הסוכן|מועד תחילת הביטוח", _date(dates.get("requestedStartDate")))
    agent = _s(p.get("agent"))
    put("פרטי הסוכן|מספר סוכן", _num_first(agent))
    if " - " in agent:
        put("פרטי הסוכן|שם סוכן", _name_part(agent))
    if _s(p.get("discount")):
        put("פרטי הסוכן|קוד הנחה", _num_first(p.get("discount")))

    # the person (owner = first insured in the panel)
    idn = re.sub(r"\D", "", _s(owner.get("idNumber")))
    if not idn:
        idn = S.id_number(rnd)
        notes.append("מספר הזהות ריק בפאנל – נכתב בטופס מספר זהות פיקטיבי תקין: " + idn)
    put(SEC + "|שם פרטי", owner.get("firstName"))
    put(SEC + "|שם משפחה", owner.get("lastName"))
    put(SEC + "|מספר זהות", idn)
    put(SEC + "|תאריך לידה", _date(owner.get("birthDate")))
    put(SEC + "|מספר טלפון נייד", owner.get("phone"))
    put(SEC + "|כתובת: רחוב", owner.get("street"))
    put(SEC + "|מספר בית", owner.get("houseNumber"))
    put(SEC + "|דירה", owner.get("apartment"))
    put(SEC + "|עיר / יישוב", owner.get("city"))
    put(SEC + "|ת.ד", owner.get("mailBox"))
    put(SEC + "|דואר אלקטרוני", owner.get("email"))
    if owner.get("gender") in GENDER:
        ch[SEC + "|מגדר"] = GENDER[owner["gender"]]

    ins = ans.get("InsuredDetailes") or {}
    put(SEC + "|עיסוק בפועל", ins.get("Occupation"))
    put(SEC + "|קופת חולים", ins.get("HMO"))
    for q, (sec, base) in INSURED.items():
        v = _yn(ins.get(q))
        if v:
            ch["%s|%s - %s" % (sec, base, C1)] = v

    # cover
    cover = p.get("cover") or {}
    put("פרטי הכיסוי הביטוחי|סכום הביטוח המבוקש - " + C1, _number(cover.get("insuranceSum")))
    put("פרטי הכיסוי הביטוחי|גיל תום ביטוח - " + C1, _number(cover.get("untilAge")))
    ch["פרטי הכיסוי הביטוחי|סוג הכיסוי הביטוחי"] = '"ריסק"'

    # health
    hd = ans.get("HealthDeclaration") or {}
    for q, base in HEALTH.items():
        v = _yn(hd.get(q))
        if v:
            ch["הצהרת בריאות|%s - %s" % (base, C1)] = v
    h = hd.get("Height")
    if h not in (None, ""):
        try:
            hv = float(h)
            put("הצהרת בריאות|גובה - " + C1, str(int(round(hv * 100))) if hv < 3 else _number(hv))
        except ValueError:
            put("הצהרת בריאות|גובה - " + C1, h)
    put("הצהרת בריאות|משקל - " + C1, _number(hd.get("Weight")))
    smoke = ins.get("IsSmoking")
    cig = _get(ans, "SmokeHelthComp.NumberSig")
    put("הצהרת בריאות|כמות סיגריות ליום - " + C1, _number(cig) if smoke and cig not in (None, "") else "0")
    if smoke:
        notes.append("שאלון ההמשך על עישון – בטופס יש רק כמות סיגריות ליום")

    # existing insurance and cancellation
    cq = ans.get("ComparisonQuestionnaire") or {}
    v = _yn(cq.get("OtherPolicy"))
    if v:
        ch["ביטוחים קיימים|קיימת פוליסת ריסק אחרת - " + C1] = v
    if cq.get("OtherPolicy") and cq.get("IsCancellationRequired") is not None:
        ch["ביטוחים קיימים|לבטל את הפוליסה הקיימת - " + C1] = _yn(cq.get("IsCancellationRequired"))
        if cq.get("IsCancellationRequired"):
            if cq.get("IsCancellationRequiredByShlomo"):
                ch["ביטוחים קיימים|הגשת ביטול באמצעות שלמה - " + C1] = "באמצעות"
            elif cq.get("IsCancellationRequiredByShlomo") is False:
                notes.append("ביטול שלא באמצעות שלמה – לסימון הזה אין מקום בתבנית, ולכן לא סומן")
            put("נספח ג' - הודעת ביטול|חברת ביטוח לביטול - " + C1, cq.get("InsuranceCompany"))
            put("נספח ג' - הודעת ביטול|מספר פוליסה לביטול - " + C1, str(rnd.randint(10 ** 7, 10 ** 8)))

    # irrevocable beneficiary
    lien = p.get("lien") or {}
    if lien.get("type") == "bank" and _s(lien.get("bank")):
        put("מוטב בלתי חוזר|שם המוטב הבלתי חוזר (בנק) - " + C1, _name_part(lien.get("bank")))
        put("מוטב בלתי חוזר|מספר בנק - " + C1, _num_last(lien.get("bank")))
        put("מוטב בלתי חוזר|מספר סניף - " + C1, _num_last(lien.get("branch")))
    elif lien.get("type") == "financial" and _s(lien.get("company")):
        put("מוטב בלתי חוזר|שם המוטב הבלתי חוזר (מוסד פיננסי) - " + C1, _name_part(lien.get("company")))

    # beneficiaries
    rows = []
    for b in (p.get("beneficiaries") or [])[:7]:
        g = b.get("gender") if b.get("gender") in GENDER else "male"
        rel = RELATION.get(_s(b.get("relation")), (_s(b.get("relation")),) * 2)[0 if g == "male" else 1]
        rows.append({"שם פרטי": _s(b.get("firstName")), "שם משפחה": _s(b.get("lastName")),
                     "מספר זהות": re.sub(r"\D", "", _s(b.get("idNumber"))) or S.id_number(rnd),
                     "תאריך לידה": _date(b.get("birthDate")), "מגדר": GENDER[g], "קרבה": rel,
                     "% חלוקה": _number(b.get("percent"))})
    if len(p.get("beneficiaries") or []) > 7:
        notes.append("בטופס יש מקום ל-7 מוטבים; נכתבו 7 הראשונים")
    ben = {"מוטבים למועמד ראשון לביטוח": rows} if rows else {}
    cb["מוטבים|יורשים חוקיים - " + C1] = not rows

    # payment (direct debit)
    pay = p.get("payment") or {}
    if _s(pay.get("bank")) or _s(pay.get("accountNumber")):
        put("הרשאה לחיוב חשבון|בנק", _num_last(pay.get("bank")))
        put("הרשאה לחיוב חשבון|מספר סניף", _num_last(pay.get("branch")))
        put("הרשאה לחיוב חשבון|מספר חשבון", re.sub(r"\D", "", _s(pay.get("accountNumber"))))
        put("הרשאה לחיוב חשבון|שם משפחה (בעל החשבון)",
            " ".join(x for x in (_s(owner.get("firstName")), _s(owner.get("lastName"))) if x))
        put("הרשאה לחיוב חשבון|מספר זהות / חברה (בעל החשבון)", idn)
    day = _s(pay.get("collectionDay"))
    if day in ("2", "10"):
        ch["אמצעי גביה|יום גביה מבוקש"] = day
    elif day:
        notes.append("יום גבייה %s – בטופס אפשר לסמן רק 2 או 10, ולכן לא סומן" % day)

    # declarations: a consent = a signed section
    pol = ans.get("PolicyOwnerAgreements") or {}
    decl = ans.get("InshuredAgreemntAndDeclarration") or {}
    ms = ans.get("MethodSale") or {}
    signed = {
        "חתום: ויתור על סודיות רפואית - מועמד ראשון": decl.get("MedicalConfidentiality"),
        "חתום: הגנת הפרטיות - מועמד ראשון": pol.get("PrivacyProtection") or decl.get("PrivacyProtection"),
        "חתום: פניה שיווקית - מועמד ראשון": owner.get("marketingApproval"),
        "חתום: הצהרת המועמדים לביטוח חיים - מועמד ראשון": decl.get("ConsentJoinInsuarnce"),
        "חתום: הצהרת הסוכן": ms.get("AgentStatementCopy") or ms.get("AgentStatementMaterialInfo"),
    }
    for k, v in signed.items():
        sig["הצהרות והסכמות|" + k] = bool(v)
    cb["הצהרות והסכמות|מבקש מסמכים בדואר ישראל"] = False
    if owner.get("digitalMailing") is False:
        notes.append("משלוח מסמכים בדואר ישראל – לסימון הזה אין מקום בתבנית, ולכן הטופס ייקרא כדיוור דיגיטלי")

    # signing date: the declarations date and the signing log
    sdate = _date(dates.get("signatureDate"))
    log = []
    if sdate:
        put("הצהרות והסכמות|תאריך בהצהרות", sdate)
        stamp = sdate + " %02d:%02d:%02d" % (rnd.randint(8, 19), rnd.randint(0, 59), rnd.randint(0, 59))
        name = " ".join(x for x in (_s(owner.get("firstName")), _s(owner.get("lastName"))) if x) or "לקוח"
        log = [{"תחנה": "1", "שם תחנה": "לקוח", "שם החותם": name, "תאריך חתימה": stamp},
               {"תחנה": "2", "שם תחנה": "משתמש", "שם החותם": t.get("פרטי הסוכן|שם סוכן", "סוכן"),
                "תאריך חתימה": stamp}]

    for path, why in NOT_IN_FORM.items():
        v = _get({"p": p}, path)
        if v not in (None, "", False, {}, []):
            notes.append(why)

    sc = {"seed": seed or 0, "edges": ["from_panel"], "text": t, "choice": ch, "checkbox": cb,
          "signature": sig, "beneficiaries": ben, "findings": {}, "signing_log": log}
    return sc, notes


# ---------- round trip: what the reader gets back vs the panel ----------

def _norm_panel(path: str, v: Any) -> Any:
    if path in ("p.agent", "p.discount"):
        return _num_first(v)
    if path in ("p.lien.bank", "p.lien.branch", "p.payment.bank", "p.payment.branch"):
        return _num_last(v)
    if path.endswith("Date") or path.endswith("birthDate"):
        return _date(v)
    if path == "p.owner.idNumber":
        return re.sub(r"\D", "", _s(v)).zfill(9)
    if path == "p.payment.accountNumber":
        return re.sub(r"\D", "", _s(v))
    if isinstance(v, bool) or v is None:
        return v
    if isinstance(v, (int, float)):
        return float(v)
    s = _s(v)
    try:
        return float(s.replace(",", "")) if re.fullmatch(r"[\d,.]+", s) else s
    except ValueError:
        return s


def _norm_ben(rows: list) -> list:
    out = []
    for b in rows or []:
        out.append({"firstName": _s(b.get("firstName")), "lastName": _s(b.get("lastName")),
                    "birthDate": _date(b.get("birthDate")),
                    "gender": b.get("gender") or "male", "relation": _s(b.get("relation")),
                    "percent": float(b.get("percent") or 0)})
    return out


def roundtrip(p: dict, read_values: dict) -> list[dict]:
    """Panel values that came back different (or not at all) from the PDF."""
    bad = []
    for path, item in read_values.items():
        got = item.get("value")
        if path == "p.beneficiaries":
            if _norm_ben(p.get("beneficiaries")) != _norm_ben(got):
                bad.append({"path": path, "expected": len(p.get("beneficiaries") or []),
                            "got": len(got or [])})
            continue
        exp = _get({"p": p}, path)
        if path == "p.owner.idNumber" and not _s(exp):
            continue  # a fictitious number was written
        if path == "p.lien.type" and exp == got:
            continue
        if path == "p.owner.digitalMailing" and exp is False:
            continue  # the form has no box for it (listed in the notes)
        a, b = _norm_panel(path, exp), _norm_panel(path, got)
        if a != b and not (a in (None, "") and b in (None, "")):
            bad.append({"path": path, "expected": exp, "got": got})
    return bad


def today_seed() -> int:
    d = date.today()
    return d.year * 10000 + d.month * 100 + d.day
