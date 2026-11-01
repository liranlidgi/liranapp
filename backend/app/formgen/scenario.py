"""Random test scenarios for the proposal form (code 10): invented people,
valid ID numbers, and optional edge cases. A scenario is keyed exactly like
the extraction ("section|field"), so it is also the expected result."""
from __future__ import annotations

import random
from datetime import date, timedelta

FIRST_M = ["אבי", "יוסי", "דוד", "משה", "איתי", "עומר", "נועם", "אורי", "יונתן", "אליעזר", "רועי", "גיא"]
FIRST_F = ["נועה", "מיכל", "שירה", "יעל", "תמר", "רונית", "הדס", "אורית", "ליאת", "מאיה", "עדי", "אסתר"]
LAST = ["כהן", "לוי", "מזרחי", "פרץ", "ביטון", "אברהם", "פרידמן", "שטרן", "דהן", "אזולאי", "גבאי", "ברקוביץ",
        "בן דוד", "אלמוג", "שפירא"]
CITIES = [("תל אביב - יפו", ["דיזנגוף", "אבן גבירול", "הרצל"]), ("חיפה", ["מוריה", "הנביאים", "חורב"]),
          ("רחובות", ["הרצל", "ביל\"ו", "יעקב"]), ("באר שבע", ["רגר", "שז\"ר", "הנשיאים"]),
          ("מודיעין-מכבים-רעות", ["עמק דותן", "צאלון", "יהלום"]), ("ירושלים", ["יפו", "הנביאים", "בצלאל"])]
HMO = ["כללית", "מכבי", "מאוחדת", "לאומית"]
OCC = ["מורה", "מהנדס תוכנה", "רואה חשבון", "אחות", "נהג", "עורך דין", "מנהל מכירות", "טכנאי"]
OCC_UNKNOWN = ["בעלת בית קפה", "מדריך טיולים ג'יפים", "מאלף כלבים"]
RELATIONS = ["בן", "בת", "בן זוג", "בת זוג", "אח", "אחות", "אב", "אם"]
BANKS = [("12", "בנק הפועלים"), ("10", "בנק לאומי"), ("20", "בנק מזרחי טפחות"), ("11", "בנק דיסקונט"),
         ("31", "הבינלאומי")]
INSURERS = ["מגדל", "הראל", "כלל", "הפניקס", "מנורה", "איילון"]
FINDINGS = ["ניתוח תוספתן לפני 4 שנים, החלמה מלאה",
            "יתר לחץ דם מאוזן בטיפול תרופתי",
            "ניתוח מיניסקוס בברך ימין לפני 3 שנים, ללא מגבלה כיום"]
HEALTH_Q = [
    "שינוי משמעותי במשקל בשנתיים האחרונות", "2.1 עישון בשנתיים האחרונות", "2.2 צריכת אלכוהול קבועה",
    "2.3 שימוש בסמים", "2.4 אשפוז ב-5 שנים אחרונות", "2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות",
    "2.6 נטילת תרופות קבועה", "2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות", "2.8 נכות / תהליך קביעת נכות",
    "2.9 בדיקה רפואית אבחנתית לא הושלמה", "2.10 מחלות רקע משפחתי מדרגה ראשונה",
    "3.1 מחלות מערכת העצבים והמוח", "3.2 מחלות לב וכלי דם", "3.3 מחלות דרכי עיכול",
    "3.4 מחלות ריאות ודרכי נשימה", "3.5 מחלות כליות ודרכי השתן", "3.6 מחלות ממאירות וגידולים",
    "3.7 מחלה מטבולית / הורמונלית (סוכרת, שומנים)", "3.8 מחלות ראומטיות",
    "3.9 מחלות זיהומיות / דלקתיות / מערכת חיסון / מערכת הדם", "3.10 מערכת הרבייה", "3.11 מצב נפשי"]
MORE_Q = ["תחביב או אורח חיים בסיכון מיוחד", "רשיון טיס / צוות אוויר", "שהייה בחו\"ל מעל 180 יום"]
SIGNED = ["חתום: ויתור על סודיות רפואית - מועמד ראשון", "חתום: הגנת הפרטיות - מועמד ראשון",
          "חתום: פניה שיווקית - מועמד ראשון", "חתום: הצהרת המועמדים לביטוח חיים - מועמד ראשון",
          "חתום: הצהרת הסוכן"]

EDGES = {
    "insured2": "מועמד שני לביטוח",
    "beneficiaries": "מוטבים נקובים (1-3) במקום יורשים חוקיים",
    "lien": "מוטב בלתי חוזר (בנק)",
    "no_bank": "בלי פרטי חשבון להוראת קבע",
    "discount_percent": "הנחה באחוזים במקום קוד",
    "health_yes": "תשובת כן בהצהרת הבריאות עם פירוט",
    "unknown_occupation": "עיסוק שלא קיים ברשימה",
    "long_date": "מועד תחילה בפורמט dd/mm/yyyy",
    "no_signing_log": "בלי יומן החתימות (תאריך מההצהרות)",
    "cancel_policy": "ביטול פוליסה קיימת בחברה אחרת",
    "missing_signature": "חתימה חסרה בהצהרות",
}

SEC_I1 = "פרטי המועמד הראשון לביטוח"
SEC_I2 = "פרטי המועמד השני לביטוח"


def id_number(rnd: random.Random) -> str:
    base = [rnd.randint(0, 9) for _ in range(8)]
    s = 0
    for i, d in enumerate(base):
        n = d * (1 + i % 2)
        s += n - 9 if n > 9 else n
    return "".join(map(str, base)) + str((10 - s % 10) % 10)


def ddmmyyyy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def person(rnd: random.Random, gender: str | None = None, occupations: list[str] | None = None) -> dict:
    g = gender or rnd.choice(["ז", "נ"])
    born = date(rnd.randint(1965, 2003), rnd.randint(1, 12), rnd.randint(1, 28))
    city, streets = rnd.choice(CITIES)
    return {
        "first": rnd.choice(FIRST_M if g == "ז" else FIRST_F), "last": rnd.choice(LAST), "gender": g,
        "id": id_number(rnd), "birth": ddmmyyyy(born),
        "phone": "05" + str(rnd.choice([0, 2, 3, 4, 8])) + "".join(str(rnd.randint(0, 9)) for _ in range(7)),
        "city": city, "street": rnd.choice(streets), "house": str(rnd.randint(1, 120)),
        "email": "test%d@example.co.il" % rnd.randint(100, 999),
        "hmo": rnd.choice(HMO), "occ": rnd.choice(occupations or OCC),
        "height": str(rnd.randint(150, 192)), "weight": str(rnd.randint(50, 105)),
    }


def make(seed: int, edges: set[str] | None = None, agents: list[str] | None = None,
         discounts: list[str] | None = None, today: date | None = None,
         occupations: list[str] | None = None) -> dict:
    """One scenario. `edges` picks edge cases from EDGES; None = random mix.
    `agents` ("412 - name"), `discounts` and `occupations` are the values that
    exist in the target environment; without them, sample values are used."""
    rnd = random.Random(seed)
    if edges is None:
        edges = {e for e in EDGES if rnd.random() < 0.25}
    today = today or date.today()
    p1 = person(rnd, occupations=occupations)
    p2 = person(rnd, "נ" if p1["gender"] == "ז" else "ז", occupations) if "insured2" in edges else None
    if p2:
        p2["last"] = p1["last"]
        p2.update({k: p1[k] for k in ("city", "street", "house")})
    if "unknown_occupation" in edges:
        p1["occ"] = rnd.choice(OCC_UNKNOWN)
    agent = rnd.choice(agents or ["412 - סוכנות לדוגמה"])
    a_no, a_name = [x.strip() for x in agent.split(" - ", 1)] if " - " in agent else (agent, "סוכנות")
    start = (today.replace(day=1) + timedelta(days=32)).replace(day=1)
    sign_dt = today - timedelta(days=rnd.randint(1, 10))
    t, ch, cb, sig = {}, {}, {}, {}

    t["פרטי הסוכן|מועד תחילת הביטוח"] = start.strftime("%d/%m/%Y" if "long_date" in edges else "%d/%m/%y")
    t["פרטי הסוכן|מספר סוכן"] = a_no
    t["פרטי הסוכן|שם סוכן"] = a_name
    if "discount_percent" in edges:
        t["פרטי הסוכן|קוד הנחה"] = "%d%%" % rnd.choice([10, 15, 20])
    elif discounts:
        t["פרטי הסוכן|קוד הנחה"] = rnd.choice(discounts).split(" - ")[0].strip()

    def fill_person(sec, pp, n):
        t[sec + "|שם פרטי"] = pp["first"]
        t[sec + "|שם משפחה"] = pp["last"]
        t[sec + "|מספר זהות"] = pp["id"]
        t[sec + "|תאריך לידה"] = pp["birth"]
        t[sec + "|מספר טלפון נייד"] = pp["phone"]
        t[sec + "|כתובת: רחוב"] = pp["street"]
        t[sec + "|מספר בית"] = pp["house"]
        t[sec + "|עיר / יישוב"] = pp["city"]
        t[sec + "|דואר אלקטרוני"] = pp["email"]
        t[sec + "|עיסוק בפועל"] = pp["occ"]
        t[sec + "|קופת חולים"] = pp["hmo"]
        ch[sec + "|מגדר"] = pp["gender"]
        t["פרטי הכיסוי הביטוחי|גיל תום ביטוח - " + n] = "84"
        t["הצהרת בריאות|גובה - " + n] = pp["height"]
        t["הצהרת בריאות|משקל - " + n] = pp["weight"]
        t["הצהרת בריאות|כמות סיגריות ליום - " + n] = "0"
        for q in HEALTH_Q:
            ch["הצהרת בריאות|%s - %s" % (q, n)] = "לא"
        for q in MORE_Q:
            ch["פרטים נוספים|%s - %s" % (q, n)] = "לא"
        ch["פרטים נוספים|אזרחות ישראלית - " + n] = "כן"
        ch["ביטוחים קיימים|קיימת פוליסת ריסק אחרת - " + n] = "לא"

    fill_person(SEC_I1, p1, "מועמד ראשון")
    total = rnd.choice([500000, 1000000, 1500000, 2000000, 3000000])
    t["פרטי הכיסוי הביטוחי|סכום הביטוח המבוקש - מועמד ראשון"] = "{:,}".format(total) if rnd.random() < .5 else str(total)
    ch["פרטי הכיסוי הביטוחי|סוג הכיסוי הביטוחי"] = '"ריסק"'
    if p2:
        fill_person(SEC_I2, p2, "מועמד שני")
        t["פרטי הכיסוי הביטוחי|סכום הביטוח המבוקש - מועמד שני"] = t[
            "פרטי הכיסוי הביטוחי|סכום הביטוח המבוקש - מועמד ראשון"]

    findings = {}
    if "health_yes" in edges:
        who = "מועמד שני" if p2 and rnd.random() < .5 else "מועמד ראשון"
        ch["הצהרת בריאות|2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות - " + who] = "כן"
        findings["הצהרת בריאות|ממצאים חיוביים - %s - שורה 1 - מס' שאלה" % who] = "2.5"
        findings["הצהרת בריאות|ממצאים חיוביים - %s - שורה 1 - פרטים" % who] = rnd.choice(FINDINGS)

    benef = {}
    if "beneficiaries" in edges:
        n = rnd.randint(1, 3)
        pcts = {1: [100], 2: [50, 50], 3: [40, 30, 30]}[n]
        rows = []
        for i in range(n):
            b = person(rnd)
            born = date(rnd.randint(1990, 2015), rnd.randint(1, 12), rnd.randint(1, 28))
            rows.append({"שם פרטי": b["first"], "שם משפחה": p1["last"], "מספר זהות": b["id"],
                         "תאריך לידה": ddmmyyyy(born), "מגדר": b["gender"],
                         "קרבה": rnd.choice(RELATIONS), "% חלוקה": str(pcts[i])})
        benef["מוטבים למועמד ראשון לביטוח"] = rows
        cb["מוטבים|יורשים חוקיים - מועמד ראשון"] = False
    else:
        cb["מוטבים|יורשים חוקיים - מועמד ראשון"] = True
    if p2:
        cb["מוטבים|יורשים חוקיים - מועמד שני"] = True

    if "no_bank" not in edges:
        bank_no, _ = rnd.choice(BANKS)
        t["הרשאה לחיוב חשבון|בנק"] = bank_no
        t["הרשאה לחיוב חשבון|מספר סניף"] = str(rnd.randint(100, 899))
        t["הרשאה לחיוב חשבון|מספר חשבון"] = str(rnd.randint(10000, 999999))
        # the signing system writes the full name in one box (seen on real forms)
        t["הרשאה לחיוב חשבון|שם משפחה (בעל החשבון)"] = p1["first"] + " " + p1["last"]
        t["הרשאה לחיוב חשבון|מספר זהות / חברה (בעל החשבון)"] = p1["id"]
        ch["אמצעי גביה|יום גביה מבוקש"] = rnd.choice(["10", "2"])

    appendices = False
    if "lien" in edges:
        appendices = True
        bno, bname = rnd.choice(BANKS)
        for n in (["מועמד ראשון"] + (["מועמד שני"] if p2 else [])):
            t["מוטב בלתי חוזר|שם המוטב הבלתי חוזר (בנק) - " + n] = bname
            t["מוטב בלתי חוזר|מספר בנק - " + n] = bno
            t["מוטב בלתי חוזר|מספר סניף - " + n] = str(rnd.randint(100, 899))
    if "cancel_policy" in edges:
        appendices = True
        ch["ביטוחים קיימים|קיימת פוליסת ריסק אחרת - מועמד ראשון"] = "כן"
        ch["ביטוחים קיימים|לבטל את הפוליסה הקיימת - מועמד ראשון"] = "כן"
        t["נספח ג' - הודעת ביטול|חברת ביטוח לביטול - מועמד ראשון"] = rnd.choice(INSURERS)
        t["נספח ג' - הודעת ביטול|מספר פוליסה לביטול - מועמד ראשון"] = str(rnd.randint(10 ** 7, 10 ** 8))

    cb["הצהרות והסכמות|מבקש מסמכים בדואר ישראל"] = False
    for s in SIGNED:
        sig["הצהרות והסכמות|" + s] = True
    if "missing_signature" in edges:
        sig["הצהרות והסכמות|" + rnd.choice(SIGNED[:4])] = False
    t["הצהרות והסכמות|תאריך בהצהרות"] = ddmmyyyy(sign_dt)

    log = []
    if "no_signing_log" not in edges:
        stamp = sign_dt.strftime("%d/%m/%Y") + " %02d:%02d:%02d" % (rnd.randint(8, 19), rnd.randint(0, 59),
                                                                     rnd.randint(0, 59))
        log.append({"תחנה": "1", "שם תחנה": "לקוח", "שם החותם": p1["first"] + " " + p1["last"],
                    "תאריך חתימה": stamp})
        if p2:
            log.append({"תחנה": "2", "שם תחנה": "בן / בת זוג", "שם החותם": p2["first"] + " " + p2["last"],
                        "תאריך חתימה": stamp})
        log.append({"תחנה": str(len(log) + 1), "שם תחנה": "משתמש", "שם החותם": a_name,
                    "תאריך חתימה": stamp})

    return {"seed": seed, "edges": sorted(edges), "appendices": appendices, "text": t, "choice": ch,
            "checkbox": cb, "signature": sig, "beneficiaries": benef, "findings": findings,
            "signing_log": log}


def clean(sc: dict, profile: dict) -> dict:
    """A scenario edited by hand: drop empty values (an empty box is not a
    value the reader can read), drop empty beneficiary / signing-log rows,
    and include the appendix pages only when something on them is filled."""
    out = dict(sc)
    out["text"] = {k: str(v).strip() for k, v in (sc.get("text") or {}).items() if str(v or "").strip()}
    out["choice"] = {k: v for k, v in (sc.get("choice") or {}).items() if v}
    out["checkbox"] = {k: bool(v) for k, v in (sc.get("checkbox") or {}).items()}
    out["signature"] = {k: bool(v) for k, v in (sc.get("signature") or {}).items()}
    out["findings"] = {k: str(v).strip() for k, v in (sc.get("findings") or {}).items() if str(v or "").strip()}
    ben = {}
    for table, rows in (sc.get("beneficiaries") or {}).items():
        rows = [{c: str(v).strip() for c, v in r.items() if str(v or "").strip()} for r in rows]
        rows = [r for r in rows if r]
        if rows:
            ben[table] = rows
    out["beneficiaries"] = ben
    out["signing_log"] = [r for r in ({c: str(v).strip() for c, v in r.items() if str(v or "").strip()}
                                      for r in (sc.get("signing_log") or [])) if r]
    last_page = 9
    out["appendices"] = any(
        profile[kind][k]["page"] > last_page for kind in ("text", "choice")
        for k in out[kind] if k in profile[kind])
    out.setdefault("edges", [])
    out.setdefault("seed", 0)
    return out
