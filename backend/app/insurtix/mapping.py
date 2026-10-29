"""Map an ExtractionResult onto the field paths of the Insurtix policy form
panel (the in-browser form that creates a pure-risk policy).

The output is a small JSON document ("insurtix-proposal" v1) that the panel
can load with its "load proposal data" button. Keys are the panel's own field
paths (e.g. ``p.owner.firstName``); every value carries the confidence of the
field it came from and a ``needs_review`` flag.

Business decisions encoded here (agreed with the product owner):
  * The panel supports one person who is both policy owner and insured. The
    first candidate is used for the person fields; if the policy owner in the
    form is a different person, a warning is added.
  * A second candidate is not supported: warning, ignored.
  * Credit-card payment is not supported (direct debit only): warning.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from ..extraction.models import ExtractionResult, FieldResult

FORMAT = "insurtix-proposal"
VERSION = 1

OWNER = "פרטי בעל הפוליסה"
CAND1 = "פרטי המועמד הראשון לביטוח"
CAND2 = "פרטי המועמד השני לביטוח"
C1 = " - מועמד ראשון"

REVIEW_BELOW = 0.80

# person fields: (field name in the form, panel key under p.owner, kind)
PERSON_FIELDS = [
    ("שם פרטי", "firstName", "text"),
    ("שם משפחה", "lastName", "text"),
    ("תאריך לידה", "birthDate", "date"),
    ("מגדר", "gender", "gender"),
    ("כתובת: רחוב", "street", "text"),
    ("מספר בית", "houseNumber", "text"),
    ("דירה", "apartment", "text"),
    ("עיר / יישוב", "city", "text"),
    ("ת.ד", "mailBox", "text"),
    ("דואר אלקטרוני", "email", "email"),
]
ID_FIELD = {OWNER: "מספר זהות / חברה", CAND1: "מספר זהות"}
PHONE_FIELD = {OWNER: "מספר טלפון נייד / חברה", CAND1: "מספר טלפון נייד"}

# health declaration: form field base name -> panel question name
HEALTH = {
    "שינוי משמעותי במשקל בשנתיים האחרונות": "WeightChange10p",
    "2.2 צריכת אלכוהול קבועה": "IsAlcohol",
    "2.3 שימוש בסמים": "IsDrugs",
    "2.4 אשפוז ב-5 שנים אחרונות": "HospitalizationInTheLast5Years",
    "2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות": "SurgeriesInTheLast5Years",
    "2.6 נטילת תרופות קבועה": "IsMedicinesRegularly",
    "2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות": "BloodAndUrineTest",
    "2.8 נכות / תהליך קביעת נכות": "Disability",
    "2.9 בדיקה רפואית אבחנתית לא הושלמה": "ClearProcess",
    "2.10 מחלות רקע משפחתי מדרגה ראשונה": "FamilyHistoryOfIllness",
    "3.1 מחלות מערכת העצבים והמוח": "NervousSystemAndBrain",
    "3.2 מחלות לב וכלי דם": "CardiovascularDiseases",
    "3.3 מחלות דרכי עיכול": "DigestiveTract",
    "3.4 מחלות ריאות ודרכי נשימה": "LungsAndRespiratoryTract",
    "3.5 מחלות כליות ודרכי השתן": "KidneysAndUrinaryTract",
    "3.6 מחלות ממאירות וגידולים": "MalignantDiseases",
    "3.7 מחלה מטבולית / הורמונלית (סוכרת, שומנים)": "EndoCrinology",
    "3.8 מחלות ראומטיות": "RheumaticDiseases",
    "3.9 מחלות זיהומיות / דלקתיות / מערכת חיסון / מערכת הדם": "InfectiousDiseases",
    "3.10 מערכת הרבייה": "ReproductiveSystem",
    "3.11 מצב נפשי": "Soul",
}
INSURED_YES_NO = {
    "2.1 עישון בשנתיים האחרונות": "IsSmoking",
    "תחביב או אורח חיים בסיכון מיוחד": "Hobbies",
    "רשיון טיס / צוות אוויר": "PilotsLicense",
    'שהייה בחו"ל מעל 180 יום': "StayingAbroad",
    "אזרחות ישראלית": "IsIsraeliCitizen",
}
HMO_NAMES = ["כללית", "מכבי", "מאוחדת", "לאומית"]
RELATIONS = [
    (("בן זוג", "בת זוג", "אשה", "אישה", "בעל", "רעיה", "בן/בת זוג"), "בן / בת זוג"),
    (("נכד", "נכדה"), "נכד/ה"),
    (("אח", "אחות"), "אח/אחות"),
    (("בן", "בת", "ילד", "ילדה"), "ילד/ה"),
]
BENEF_TABLE = "מוטבים למועמד ראשון לביטוח"
SIGN_TABLE = "רשימת החתמות"
FINDINGS_TABLE = "ממצאים חיוביים"
# names as they appear in the panel's insurance-company list
INSURERS = ["איילון", "ביטוח ישיר", "הכשרה חברה לביטוח", "הפניקס", "הראל", "כלל",
            "מנורה מבטחים", "פסגות", "שומרה", "שלמה חברה לביטוח", "ליברה חברה לביטוח",
            "מגדל", "AIG"]
SIGNED_NOTE = "לפי חתימה על הסעיף בטופס"
FINDINGS_ROW_RE = re.compile(r"^שורה (\d+) - (.+)$")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", str(s or "")).strip()


DATE_RE = re.compile(r"(?<!\d)(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)")
FUTURE_YEARS = 10  # a 2-digit start date may be up to this many years ahead


def _year(y: str, past: bool) -> int:
    """'2026' -> 2026; '26' -> 2026. A 2-digit year that would land in the
    future (beyond today for birth dates, beyond FUTURE_YEARS otherwise)
    belongs to the previous century: birth date '99' -> 1999."""
    if len(y) == 4:
        return int(y)
    now = datetime.now().year
    full = 2000 + int(y)
    return full if full <= now + (0 if past else FUTURE_YEARS) else full - 100


def _date(s: str, past: bool = False) -> str | None:
    """dd/mm/yyyy or dd/mm/yy (also with . or -) -> dd/mm/yyyy."""
    m = DATE_RE.search(s or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), _year(m.group(3), past)
    try:
        datetime(y, mo, d)
    except ValueError:
        return None
    return f"{d:02d}/{mo:02d}/{y}"


def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _yes_no(s: str) -> bool | None:
    v = _norm(s).replace("*", "")
    if v == "כן":
        return True
    if v == "לא":
        return False
    return None


def _number(s: str) -> float | None:
    v = re.sub(r"[^\d.]", "", (s or "").replace(",", ""))
    if not v or v.count(".") > 1:
        return None
    n = float(v)
    return int(n) if n.is_integer() else n


def _gender(s: str) -> str | None:
    v = _norm(s)
    if v.startswith("ז"):
        return "male"
    if v.startswith("נ"):
        return "female"
    return None


def _relation(s: str) -> tuple[str, bool]:
    v = _norm(s)
    for words, target in RELATIONS:
        if any(v == w or v.startswith(w + " ") for w in words):
            return target, False
    return "אחר", True


class _Builder:
    def __init__(self, result: ExtractionResult):
        self.by_key: dict[tuple[str, str], FieldResult] = {}
        self.by_name: dict[str, list[FieldResult]] = {}
        for f in result.fields:
            self.by_key.setdefault((f.section, f.field_name), f)
            self.by_name.setdefault(f.field_name, []).append(f)
        self.values: dict[str, dict[str, Any]] = {}
        self.warnings: list[str] = list(result.warnings)
        self.used: set[int] = set()

    def get(self, section: str, name: str) -> FieldResult | None:
        return self.by_key.get((section, name))

    def any_named(self, name: str) -> FieldResult | None:
        lst = self.by_name.get(name)
        return lst[0] if lst else None

    def put(self, path: str, value: Any, src: FieldResult | None,
            review: bool = False, note: str = "") -> None:
        if value is None or value == "":
            if src is not None:
                self.warnings.append(
                    f"לא ניתן לפרש את הערך '{src.value}' בשדה {src.section} / {src.field_name}")
            return
        conf = src.confidence if src else 1.0
        self.values[path] = {
            "value": value,
            "confidence": round(conf, 3),
            "needs_review": bool(review or conf < REVIEW_BELOW),
            "from": f"{src.section} / {src.field_name}" if src else "",
            **({"note": note} if note else {}),
        }
        if src is not None:
            self.used.add(id(src))


def _person_section(b: _Builder) -> str:
    """Candidate 1 is the insured; fall back to the owner block if empty."""
    has_c1 = any(b.get(CAND1, n) for n, _, _ in PERSON_FIELDS) or b.get(CAND1, ID_FIELD[CAND1])
    if not has_c1:
        return OWNER
    owner_id = b.get(OWNER, ID_FIELD[OWNER])
    c1_id = b.get(CAND1, ID_FIELD[CAND1])
    owner_name = " ".join(_norm(f.value) for f in (b.get(OWNER, "שם פרטי"), b.get(OWNER, "שם משפחה")) if f)
    c1_name = " ".join(_norm(f.value) for f in (b.get(CAND1, "שם פרטי"), b.get(CAND1, "שם משפחה")) if f)
    differs = (owner_id and c1_id and _digits(owner_id.value) != _digits(c1_id.value)) or (
        owner_name and c1_name and owner_name != c1_name)
    if differs:
        b.warnings.append(
            "בעל הפוליסה בטופס שונה מהמועמד הראשון. הפאנל תומך באדם אחד, "
            "ולכן נלקחו הפרטים של המועמד הראשון לביטוח.")
    return CAND1


def _fill_person(b: _Builder, sec: str) -> None:
    for name, key, kind in PERSON_FIELDS:
        f = b.get(sec, name) or (b.get(OWNER, name) if sec == CAND1 and key in ("email",) else None)
        if not f:
            continue
        v = _norm(f.value)
        if kind == "date":
            b.put(f"p.owner.{key}", _date(v, past=key == "birthDate"), f)
        elif kind == "gender":
            b.put(f"p.owner.{key}", _gender(v), f)
        elif kind == "email":
            b.put(f"p.owner.{key}", v.replace(" ", ""), f)
        elif key in ("city", "street"):
            b.put(f"p.owner.{key}", v, f, review=True,
                  note="יש לוודא שהשם תואם לרשימת המערכת")
        else:
            b.put(f"p.owner.{key}", v, f)
    f = b.get(sec, ID_FIELD[sec])
    if f:
        d = _digits(f.value)
        b.put("p.owner.idNumber", d.zfill(9) if 5 <= len(d) <= 9 else None, f)
    f = b.get(sec, PHONE_FIELD[sec]) or (b.get(OWNER, PHONE_FIELD[OWNER]) if sec == CAND1 else None)
    if f:
        d = _digits(f.value)
        if d.startswith("972"):
            d = "0" + d[3:]
        b.put("p.owner.phone", d if re.fullmatch(r"05\d{8}", d) else None, f)


def _fill_offer(b: _Builder) -> None:
    f = b.any_named("מועד תחילת הביטוח")
    if f:
        b.put("p.dates.requestedStartDate", _date(f.value), f)
    f = b.any_named(f"{SIGN_TABLE} - שורה 1 - תאריך חתימה")
    if f:
        b.put("p.dates.signatureDate", _date(f.value), f, review=True,
              note="נלקח מהשורה הראשונה ברשימת ההחתמות")
    f = b.any_named("מספר סוכן")
    if f:
        b.put("p.agent", _digits(f.value) or None, f)
    f = b.any_named("קוד הנחה")
    if f:
        b.put("p.discount", _digits(f.value) or None, f)
    f = b.any_named(f"סכום הביטוח המבוקש{C1}")
    if f:
        b.put("p.cover.insuranceSum", _number(f.value), f)
    f = b.any_named(f"גיל תום ביטוח{C1}")
    if f:
        n = _number(f.value)
        b.put("p.cover.untilAge", int(n) if n else None, f)


def _fill_insured(b: _Builder) -> None:
    f = b.get(CAND1, "עיסוק בפועל")
    if f:
        b.put("p.answers.InsuredDetailes.Occupation", _norm(f.value), f, review=True,
              note="יש לוודא שהעיסוק תואם לרשימת המערכת")
    f = b.get(CAND1, "קופת חולים")
    if f:
        hit = next((h for h in HMO_NAMES if h in _norm(f.value)), None)
        b.put("p.answers.InsuredDetailes.HMO", hit, f)
    for base, q in INSURED_YES_NO.items():
        f = b.any_named(base + C1)
        if f:
            b.put(f"p.answers.InsuredDetailes.{q}", _yes_no(f.value), f)


def _fill_health(b: _Builder) -> None:
    for base, q in HEALTH.items():
        f = b.any_named(base + C1)
        if f:
            b.put(f"p.answers.HealthDeclaration.{q}", _yes_no(f.value), f)
    f = b.any_named(f"גובה{C1}")
    if f:
        n = _number(f.value)
        if n and n > 3:
            n = round(n / 100, 2)  # given in centimetres
        b.put("p.answers.HealthDeclaration.Height", n, f)
    f = b.any_named(f"משקל{C1}")
    if f:
        b.put("p.answers.HealthDeclaration.Weight", _number(f.value), f)
    f = b.any_named(f"קיימת פוליסת ריסק אחרת{C1}")
    if f:
        b.put("p.answers.ComparisonQuestionnaire.OtherPolicy", _yes_no(f.value), f)


def _question_title(num: str) -> str:
    """'2.5' -> '2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות' (or '' if unknown)."""
    num = _norm(num)
    if not num:
        return ""
    for base in list(HEALTH) + list(INSURED_YES_NO):
        if base.split(" ", 1)[0] == num:
            return base
    return ""


def _findings_rows(b: _Builder, label: str) -> list[dict[str, Any]]:
    prefix = f"{FINDINGS_TABLE} - {label} - "
    rows: dict[int, dict[str, Any]] = {}
    for name, lst in b.by_name.items():
        if not name.startswith(prefix):
            continue
        m = FINDINGS_ROW_RE.match(name[len(prefix):])
        if not m:
            continue
        row = rows.setdefault(int(m.group(1)), {"question": "", "details": "", "conf": 1.0})
        f = lst[0]
        key = "question" if m.group(2).startswith("מס") else "details"
        row[key] = _norm(f.value)
        row["conf"] = min(row["conf"], f.confidence)
        b.used.add(id(f))
    return [rows[k] for k in sorted(rows)]


def _fill_findings(b: _Builder) -> list[dict[str, Any]]:
    """Positive findings (health declaration section 4). The panel has no
    free-text field for them: they go into the warnings so the user fills the
    matching follow-up questionnaire, and are listed under "findings"."""
    out: list[dict[str, Any]] = []
    for cand, label in ((1, "מועמד ראשון"), (2, "מועמד שני")):
        for row in _findings_rows(b, label):
            title = _question_title(row["question"])
            out.append({
                "candidate": cand,
                "question": row["question"],
                "question_title": title,
                "details": row["details"],
                "confidence": round(row["conf"], 3),
                "needs_review": row["conf"] < REVIEW_BELOW,
            })
            if cand != 1:
                continue
            q = title or row["question"] or "(ללא מספר שאלה)"
            b.warnings.append(
                f"ממצא חיובי של המועמד הראשון, שאלה {q}: {row['details'] or '(ללא פירוט)'}. "
                "יש להשלים את הפרטים בשאלון ההשלמה במערכת.")
            f = b.any_named(title + C1) if title else None
            if f is not None and _yes_no(f.value) is False:
                b.warnings.append(
                    f"בשאלה {title} סומן 'לא', אבל יש לה פירוט בטבלת הממצאים החיוביים. כדאי לבדוק.")
    second = [r for r in out if r["candidate"] == 2]
    if second:
        nums = ", ".join(r["question"] or "?" for r in second)
        b.warnings.append(
            f"למועמד השני יש {len(second)} ממצאים חיוביים (שאלות: {nums}). "
            "הם לא נטענו כי הפאנל תומך במבוטח אחד.")
    return out


def _insurer(name: str) -> str | None:
    v = _norm(name)
    if not v:
        return None
    for ins in INSURERS:
        if v == ins or ins.startswith(v + " ") or v.startswith(ins.split(" ")[0]):
            return ins
    return None


def _fill_more(b: _Builder) -> None:
    """Fields added after checking a real form: smoking follow-up, legal
    heirs, existing-insurance answers, cancellation appendix, irrevocable
    beneficiary, consents (signed sections) and agent declarations."""
    # smoking follow-up: only when the candidate smokes
    smoke = b.values.get("p.answers.InsuredDetailes.IsSmoking", {}).get("value")
    f = b.any_named(f"כמות סיגריות ליום{C1}")
    if f and smoke is True:
        b.put("p.answers.SmokeHelthComp.NumberSig", _number(f.value), f)

    # existing insurance
    keep = b.any_named(f"להותיר את הפוליסה ללא שינוי{C1}")
    reduce_ = b.any_named(f"להקטין סכום ביטוח בפוליסה הקיימת{C1}")
    cancel = b.any_named(f"לבטל את הפוליסה הקיימת{C1}")
    answers = [x for x in (reduce_, cancel) if x is not None]
    if answers:
        required = any(_yes_no(x.value) is True for x in answers)
        src = next((x for x in answers if _yes_no(x.value) is True), answers[0])
        b.put("p.answers.ComparisonQuestionnaire.IsCancellationRequired", required, src,
              note="ביטול או הקטנה של הפוליסה הקיימת")
        for x in answers + ([keep] if keep else []):
            b.used.add(id(x))
        if required:
            via = b.any_named(f"הגשת ביטול באמצעות שלמה{C1}")
            other = b.any_named(f"הגשת ביטול באמצעות סוכן{C1}") or b.any_named(
                f"הגשת ביטול באופן עצמי{C1}")
            if via is not None:
                b.put("p.answers.ComparisonQuestionnaire.IsCancellationRequiredByShlomo", True, via)
            elif other is not None:
                b.put("p.answers.ComparisonQuestionnaire.IsCancellationRequiredByShlomo", False, other)
    f = b.any_named(f"חברת ביטוח לביטול{C1}")
    if f:
        ins = _insurer(f.value)
        b.put("p.answers.ComparisonQuestionnaire.InsuranceCompany", ins or _norm(f.value), f,
              review=ins is None, note="" if ins else "לא נמצאה ברשימת החברות")

    # irrevocable beneficiary (first candidate's appendix)
    bank_no = b.any_named(f"מספר בנק{C1}")
    fin = b.any_named(f"שם המוטב הבלתי חוזר (מוסד פיננסי){C1}")
    if bank_no and _digits(bank_no.value):
        name = b.any_named(f"שם המוטב הבלתי חוזר (בנק){C1}")
        note = f"בנק: {_norm(name.value)}" if name else ""
        b.put("p.lien.type", "bank", bank_no, note=note)
        b.put("p.lien.bank", _digits(bank_no.value), bank_no, note=note)
        br = b.any_named(f"מספר סניף{C1}")
        if br:
            b.put("p.lien.branch", _digits(br.value) or None, br)
        if name:
            b.used.add(id(name))
    elif fin and _norm(fin.value):
        b.put("p.lien.type", "financial", fin, review=True)
        b.put("p.lien.company", _norm(fin.value), fin, review=True,
              note="יש לבחור את החברה מהרשימה")

    # consents: a signed section counts as consent
    for name, paths in (
        ("חתום: פניה שיווקית - מועמד ראשון", ["p.owner.marketingApproval"]),
        ("חתום: הגנת הפרטיות - מועמד ראשון",
         ["p.answers.PolicyOwnerAgreements.PrivacyProtection",
          "p.answers.InshuredAgreemntAndDeclarration.PrivacyProtection"]),
        ("חתום: ויתור על סודיות רפואית - מועמד ראשון",
         ["p.answers.InshuredAgreemntAndDeclarration.MedicalConfidentiality"]),
        ("חתום: הצהרת המועמדים לביטוח חיים - מועמד ראשון",
         ["p.answers.InshuredAgreemntAndDeclarration.ConsentJoinInsuarnce"]),
        ("חתום: הצהרת הסוכן", ["p.answers.MethodSale.AgentStatementCopy",
                               "p.answers.MethodSale.AgentStatementMaterialInfo"]),
    ):
        f = b.any_named(name)
        if f:
            for path in paths:
                b.put(path, _yes_no(f.value), f, note=SIGNED_NOTE)
    f = b.any_named("מבקש מסמכים בדואר ישראל")
    if f:
        by_post = _yes_no(f.value)
        b.put("p.owner.digitalMailing", None if by_post is None else not by_post, f,
              note="לא סומן משלוח בדואר ישראל" if by_post is False else "סומן משלוח בדואר ישראל")


def _fill_payment(b: _Builder) -> None:
    for f in b.by_name.get("אמצעי תשלום", []):
        if "כרטיס" in _norm(f.value):
            b.warnings.append(
                "בטופס נבחר תשלום בכרטיס אשראי. הפאנל תומך רק בהוראת קבע, "
                "ולכן נשארה הוראת קבע.")
    f = b.any_named("יום גביה מבוקש")
    if f:
        b.put("p.payment.collectionDay", _digits(f.value) or None, f)
    PAY = "הרשאה לחיוב חשבון"
    if not any(b.get(PAY, n) for n in ("בנק", "מספר סניף", "מספר חשבון")) and any(
            "הוראת" in _norm(x.value) for x in b.by_name.get("אמצעי תשלום", [])):
        b.warnings.append("נבחרה הוראת קבע, אבל פרטי חשבון הבנק (בנק, סניף, מספר חשבון) "
                          "ריקים בטופס. יש להשלים אותם ידנית.")
    f = b.get(PAY, "בנק")
    if f:
        v = _norm(f.value)
        b.put("p.payment.bank", _digits(v) if re.fullmatch(r"\d{1,3}", v) else v, f,
              review=True, note="יש לוודא שהבנק תואם לרשימת המערכת")
    f = b.get(PAY, "מספר סניף")
    if f:
        b.put("p.payment.branch", _digits(f.value) or None, f, review=True)
    f = b.get(PAY, "מספר חשבון")
    if f:
        b.put("p.payment.accountNumber", _digits(f.value) or None, f)


def _fill_beneficiaries(b: _Builder) -> None:
    rows: dict[int, dict[str, FieldResult]] = {}
    pat = re.compile(re.escape(BENEF_TABLE) + r" - שורה (\d+) - (.+)$")
    for f_name, lst in b.by_name.items():
        m = pat.match(f_name)
        if m:
            rows.setdefault(int(m.group(1)), {})[m.group(2)] = lst[0]
    out = []
    review = False
    conf = 1.0
    for idx in sorted(rows):
        r = rows[idx]
        def val(col):
            return _norm(r[col].value) if col in r else ""
        if not (val("שם פרטי") or val("מספר זהות")):
            continue
        rel, rel_review = _relation(val("קרבה"))
        pct = _number(val("% חלוקה"))
        item = {
            "firstName": val("שם פרטי"),
            "lastName": val("שם משפחה"),
            "idNumber": _digits(val("מספר זהות")),
            "birthDate": _date(val("תאריך לידה"), past=True) or "",
            "gender": _gender(val("מגדר")) or "male",
            "relation": rel,
            "percent": pct if pct is not None else 0,
        }
        out.append(item)
        review = review or rel_review or not item["birthDate"] or pct is None
        conf = min([conf] + [c.confidence for c in r.values()])
        for c in r.values():
            b.used.add(id(c))
    if out:
        total = sum(x["percent"] for x in out)
        if abs(total - 100) > 0.01:
            b.warnings.append(f"סכום אחוזי המוטבים בטופס הוא {total} ולא 100")
            review = True
        b.values["p.beneficiaries"] = {
            "value": out, "confidence": round(conf, 3),
            "needs_review": bool(review or conf < REVIEW_BELOW),
            "from": BENEF_TABLE,
        }
    else:
        heirs = b.any_named(f"יורשים חוקיים{C1}")
        if heirs and _yes_no(heirs.value) is True:
            b.values["p.beneficiaries"] = {
                "value": [], "confidence": round(heirs.confidence, 3),
                "needs_review": heirs.confidence < REVIEW_BELOW,
                "from": f"{heirs.section} / {heirs.field_name}",
                "note": "יורשים חוקיים",
            }
            b.used.add(id(heirs))


def to_insurtix(result: ExtractionResult, source_file: str = "") -> dict[str, Any]:
    b = _Builder(result)
    sec = _person_section(b)
    _fill_person(b, sec)
    _fill_offer(b)
    _fill_insured(b)
    _fill_health(b)
    _fill_payment(b)
    _fill_beneficiaries(b)
    _fill_more(b)
    findings = _fill_findings(b)
    if any(f.section == CAND2 and _norm(f.value) for f in result.fields):
        b.warnings.append("בטופס יש מועמד שני לביטוח. הפאנל תומך במבוטח אחד, "
                          "ולכן הפרטים שלו לא נטענו.")
    proposal = b.any_named("מספר הצעה")
    return {
        "format": FORMAT,
        "version": VERSION,
        "source": {
            "file": source_file,
            "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "proposal_number": _norm(proposal.value) if proposal else "",
            "pages": result.document_pages,
        },
        "values": b.values,
        "findings": findings,
        "warnings": b.warnings,
    }
