"""Template for Shlomo Insurance's life-insurance proposal form
("טופס הצעה לביטוח חיים - ביטוח למקרה מוות").

This encodes the FIXED structure of the form -- section layout, field
labels, question wording, table headers -- derived once from inspecting the
document's geometry. It contains no values from any specific filled copy of
the form. Two spatial conventions repeat throughout the document and are
captured by the two pattern types below:

  GRID   -- a typed value sits directly above its printed label, in the same
            horizontal column (name/ID/address grids, coverage amounts).
  CHOICE -- a question is followed by option words (e.g. "כן"/"לא"); a
            checkmark glyph sits immediately to the reading-start side of
            whichever option was chosen. Two sub-layouts:
              - "inline": both candidates' checkboxes sit near the question
                text itself, side by side (right column = candidate 1, left
                column = candidate 2). Used across the health declaration.
              - "above_label": the checkbox row sits directly above a short
                field label, same geometry as GRID (used for the gender
                field, which repeats once per person).

Where the document repeats the *same* label for multiple people (e.g. "שם
פרטי" appears for the policy owner, candidate 1 and candidate 2), the
`occurrence` index picks which top-to-bottom match is meant -- this is safe
because the sections always appear in the same fixed order.
"""
from __future__ import annotations

from dataclasses import replace

from .schema import FieldSpec, FindingsSpec, Pattern, RowsTableSpec, TableSpec

YES_NO = ("לא", "כן")


def _grid(field_name, section, page, anchor_text, occurrence=0, direction="above"):
    return FieldSpec(
        field_name=field_name, section=section, pages=(page,), pattern=Pattern.GRID,
        anchor_text=anchor_text, occurrence=occurrence, direction=direction,
    )


def _gender(field_name, section, page, occurrence):
    return FieldSpec(
        field_name=field_name, section=section, pages=(page,), pattern=Pattern.CHOICE,
        anchor_text="מגדר", options=("ז", "נ"), occurrence=occurrence, layout="above_label",
    )


def _yn_pair(base_name, section, page, anchor_text, x_split, options=YES_NO):
    """One question, two people side by side -> two FieldSpecs."""
    return [
        FieldSpec(
            field_name=f"{base_name} - מועמד ראשון", section=section, pages=(page,),
            pattern=Pattern.CHOICE, anchor_text=anchor_text, options=options,
            column="right", x_split=x_split,
        ),
        FieldSpec(
            field_name=f"{base_name} - מועמד שני", section=section, pages=(page,),
            pattern=Pattern.CHOICE, anchor_text=anchor_text, options=options,
            column="left", x_split=x_split,
        ),
    ]


FIELDS: list[FieldSpec] = []

# ---------------------------------------------------------------------------
# Page 1: agent block, effective date, owner / candidate 1 / candidate 2 grids
# ---------------------------------------------------------------------------
FIELDS += [
    _grid("מועד תחילת הביטוח", "פרטי הסוכן", 1, "מועד תחילת הביטוח", direction="below"),
    _grid("קוד הנחה", "פרטי הסוכן", 1, "קוד הנחה"),
    _grid("שם סוכן", "פרטי הסוכן", 1, "שם סוכן"),
    _grid("מספר סוכן", "פרטי הסוכן", 1, "מספר סוכן"),
    _grid("שם מפקח", "פרטי הסוכן", 1, "שם מפקח"),
    _grid("מספר הצעה", "פרטי הסוכן", 1, "מספר הצעה"),
]

_PERSON_SECTIONS = [
    ("פרטי בעל הפוליסה", 0),
    ("פרטי המועמד הראשון לביטוח", 1),
    ("פרטי המועמד השני לביטוח", 2),
]
for section, occ in _PERSON_SECTIONS:
    FIELDS += [
        _grid("שם פרטי", section, 1, "שם פרטי", occurrence=occ),
        _grid("שם משפחה", section, 1, "שם משפחה", occurrence=occ),
        _grid("תאריך לידה", section, 1, "תאריך לידה", occurrence=occ),
        _gender("מגדר", section, 1, occurrence=occ),
    ]
# ID / phone: owner uses a combined "/חברה" label (unique, occurrence 0);
# candidates use the shorter label (occurrence 0/1 among just the two of them).
FIELDS += [
    _grid("מספר זהות / חברה", "פרטי בעל הפוליסה", 1, "מספר זהות / חברה"),
    _grid("מספר טלפון נייד / חברה", "פרטי בעל הפוליסה", 1, "מספר טלפון נייד / חברה"),
    _grid("מספר זהות", "פרטי המועמד הראשון לביטוח", 1, "מספר זהות", occurrence=0),
    _grid("מספר טלפון נייד", "פרטי המועמד הראשון לביטוח", 1, "מספר טלפון נייד", occurrence=0),
    _grid("מספר זהות", "פרטי המועמד השני לביטוח", 1, "מספר זהות", occurrence=1),
    _grid("מספר טלפון נייד", "פרטי המועמד השני לביטוח", 1, "מספר טלפון נייד", occurrence=1),
]
for section, occ in _PERSON_SECTIONS:
    FIELDS += [
        _grid("כתובת: רחוב", section, 1, "כתובת: רחוב", occurrence=occ),
        _grid("מספר בית", section, 1, "מספר", occurrence=occ),
        _grid("דירה", section, 1, "דירה", occurrence=occ),
        _grid("עיר / יישוב", section, 1, "עיר / יישוב", occurrence=occ),
        _grid("מיקוד", section, 1, "מיקוד", occurrence=occ),
        _grid("ת.ד", section, 1, "ת.ד", occurrence=occ),
        _grid("דואר אלקטרוני", section, 1, "דואר אלקטרוני", occurrence=occ),
    ]
FIELDS += [
    _grid("עיסוק בפועל", "פרטי המועמד הראשון לביטוח", 1, "עיסוק בפועל", occurrence=0),
    _grid("קופת חולים", "פרטי המועמד הראשון לביטוח", 1, "קופת חולים", occurrence=0),
    _grid("עיסוק בפועל", "פרטי המועמד השני לביטוח", 1, "עיסוק בפועל", occurrence=1),
    _grid("קופת חולים", "פרטי המועמד השני לביטוח", 1, "קופת חולים", occurrence=1),
]

BENEFICIARY_COLUMNS = ("שם פרטי", "שם משפחה", "מספר זהות", "תאריך לידה", "מגדר", "קרבה", "% חלוקה")
TABLES: list[TableSpec] = []
# Beneficiary tables: every row repeats its labels under the values (checked
# on real forms with named beneficiaries), so they are read row by row.
BENEFICIARIES: list[RowsTableSpec] = [
    RowsTableSpec(
        table_name="מוטבים למועמד ראשון לביטוח", section="מוטבים", page=1,
        title_text="פרטי מוטבים למועמד ראשון לביטוח", labels=BENEFICIARY_COLUMNS,
    ),
    RowsTableSpec(
        table_name="מוטבים למועמד שני לביטוח", section="מוטבים", page=2,
        title_text="פרטי מוטבים למועמד שני לביטוח", labels=BENEFICIARY_COLUMNS,
    ),
]

# ---------------------------------------------------------------------------
# Page 2: product selection, coverage amounts, additional questions
# ---------------------------------------------------------------------------
FIELDS.append(
    FieldSpec(
        field_name="סוג הכיסוי הביטוחי", section="פרטי הכיסוי הביטוחי", pages=(2,),
        pattern=Pattern.CHOICE, anchor_text="ביטוח למקרה מוות", options=('"ריסק"',),
    )
)
FIELDS += [
    _grid("גיל תום ביטוח - מועמד ראשון", "פרטי הכיסוי הביטוחי", 2, "גיל תום ביטוח*", occurrence=0),
    _grid("גיל תום ביטוח - מועמד שני", "פרטי הכיסוי הביטוחי", 2, "גיל תום ביטוח*", occurrence=1),
    _grid("סכום הביטוח המבוקש - מועמד ראשון", "פרטי הכיסוי הביטוחי", 2,
          "סכום הביטוח המבוקש למועמד ראשון לביטוח"),
    _grid("סכום הביטוח המבוקש - מועמד שני", "פרטי הכיסוי הביטוחי", 2,
          "סכום הביטוח המבוקש למועמד השני לביטוח"),
]

_ADDITIONAL_QUESTIONS = [
    ("תחביב או אורח חיים בסיכון מיוחד", "האם יש לך תחביב או אורח חיים עם סיכון מיוחד,", YES_NO),
    ("רשיון טיס / צוות אוויר", "האם אתה בעל רשיון טיס / או איש צוות אויר / או", YES_NO),
    ("שהייה בחו\"ל מעל 180 יום", "האם הנך שוהה בחו\"ל, במהלך שנה, לתקופה של", YES_NO),
    ("אזרחות ישראלית", "האם הנך בעל אזרחות ישראלית?", ("לא*", "כן")),
]
for name, anchor, options in _ADDITIONAL_QUESTIONS:
    FIELDS += _yn_pair(name, "פרטים נוספים", 2, anchor, x_split=290)

# ---------------------------------------------------------------------------
# Pages 3-6: health declaration (main screening questions per category)
# ---------------------------------------------------------------------------
_HEALTH_QUESTIONS = [
    # (field name, page, anchor text as it appears at/near the checkbox row, x_split)
    ("שינוי משמעותי במשקל בשנתיים האחרונות", 3, "האם חל שינוי במשקלך בשנתיים האחרונות?", 250),
    ("2.1 עישון בשנתיים האחרונות", 3, "האם הנך מעשן או עישנת בשנתיים האחרונות לרבות סיגריה", 250),
    ("2.2 צריכת אלכוהול קבועה", 3, "האם הנך צורך באופן קבוע משקאות אלכוהוליים בכמות של", 250),
    ("2.3 שימוש בסמים", 3, "האם אתה צורך או צרכת סמים מסוג כלשהו?", 250),
    ("2.4 אשפוז ב-5 שנים אחרונות", 3, "אשפוזים: האם אושפזת או הופנית לבית חולים לצורך אשפוז", 250),
    ("2.5 ניתוח / בדיקות הדמיה ב-5 שנים אחרונות", 3, "ניתוחים: האם עברת או הומלץ לך לעבור ניתוח או האם", 250),
    ("2.6 נטילת תרופות קבועה", 3, "תרופות: האם אתה נוטל תרופות או הומלץ לך ליטול תרופות", 250),
    ("2.7 חריגה בבדיקות דם/שתן ב-5 שנים אחרונות", 3, "האם בבדיקות דם ושתן שביצעת ב-5 השנים האחרונות", 250),
    ("2.8 נכות / תהליך קביעת נכות", 3, "האם נקבעה לך נכות או שאתה נמצא בתהליך לקבלת אחוזי", 250),
    ("2.9 בדיקה רפואית אבחנתית לא הושלמה", 3, "האם ב-5 השנים האחרונות עברת בדיקה רפואית אבחנתית", 250),
    ("2.10 מחלות רקע משפחתי מדרגה ראשונה", 3, "בלבד )אב/אם/אחים/אחיות(, היו או יש את המחלות הבאות:", 250),
    ("3.1 מחלות מערכת העצבים והמוח", 4, "לרבות אירוע מוחי/שבץ, גידול במוח, אפילפסיה, פרקינסון, ניוון", 250),
    ("3.2 מחלות לב וכלי דם", 4, "לרבות לחץ דם, כאבים בחזה, תעוקת חזה, הפרעות קצב,", 250),
    ("3.3 מחלות דרכי עיכול", 4, "לרבות הרניה/בקע, קיב קיבה/תריסריון, צליאק, ושט, לבלב,", 250),
    ("3.4 מחלות ריאות ודרכי נשימה", 4, "לרבות אסטמה, ברונכיטיס, מחלת ריאות חסימתית )COPD,(", 250),
    ("3.5 מחלות כליות ודרכי השתן", 4, "לרבות מחלת כליה כרונית, אי ספיקת כליות, כליה קטנה או", 250),
    ("3.6 מחלות ממאירות וגידולים", 4, "דוח היסטולוגיה מלא", 250),
    ("3.7 מחלה מטבולית / הורמונלית (סוכרת, שומנים)", 4, "לרבות סכרת )כולל סכרת הריון(, שומנים בדם, שיגדון )גאוט(,", 250),
    ("3.8 מחלות ראומטיות", 4, "לרבות דלקות מפרקים )דלקת מפרקים ניוונית, שגרונית", 250),
    ("3.9 מחלות זיהומיות / דלקתיות / מערכת חיסון / מערכת הדם", 4,
     "לרבות אנמיה, הפרעה בקרישת הדם APLA, טחול מוגדל,", 250),
    ("3.10 מערכת הרבייה", 4, "3.10לרבות גוש בשד, דימומים בלא קשר למחזור, האם כעת", 250),
    ("3.11 מצב נפשי", 4, "3.11לרבות דיכאון, חרדה, סכיזופרניה, מניה דפרסיה - הפרעה", 250),
]
for name, page, anchor, xs in _HEALTH_QUESTIONS:
    FIELDS += _yn_pair(name, "הצהרת בריאות", page, anchor, x_split=xs)

# Height / weight: first rows of the health-declaration table on page 3. The
# label sits in the question column ("גובה (בס"מ)", "משקל (בק"ג)") and each
# candidate's value sits on the same row under that candidate's column header.
def _row(field_name, page, anchor_text, column_header):
    return FieldSpec(
        field_name=field_name, section="הצהרת בריאות", pages=(page,), pattern=Pattern.ROW,
        anchor_text=anchor_text, column_header=column_header,
    )


FIELDS += [
    _row("גובה - מועמד ראשון", 3, "גובה", "מועמד ראשון לביטוח"),
    _row("משקל - מועמד ראשון", 3, "משקל", "מועמד ראשון לביטוח"),
    _row("גובה - מועמד שני", 3, "גובה", "מועמד שני לביטוח"),
    _row("משקל - מועמד שני", 3, "משקל", "מועמד שני לביטוח"),
]

# ---------------------------------------------------------------------------
# Page 5: existing-insurance comparison/cancellation questions
# ---------------------------------------------------------------------------
_EXISTING_INSURANCE = [
    ("קיימת פוליסת ריסק אחרת", "האם יש ברשותך פוליסה / וביטוח חיים מסוג ריסק למקרה מוות", 200),
]
for name, anchor, xs in _EXISTING_INSURANCE:
    FIELDS += _yn_pair(name, "ביטוחים קיימים", 5, anchor, x_split=xs)

# ---------------------------------------------------------------------------
# Pages 7-8: payment method, credit card, bank authorization
# ---------------------------------------------------------------------------
FIELDS += [
    # Two separate stacked option rows (not side-by-side), each with its own
    # checkmark slot -- modeled as two candidates for the same field name,
    # since only one of them will ever carry a checkmark in a real document.
    FieldSpec(
        field_name="אמצעי תשלום", section="אמצעי גביה", pages=(8,), pattern=Pattern.CHOICE,
        anchor_text="הוראת קבע בנקאית", options=("הוראת", "בנקאית"),
    ),
    FieldSpec(
        field_name="אמצעי תשלום", section="אמצעי גביה", pages=(8,), pattern=Pattern.CHOICE,
        anchor_text="כרטיס אשראי", options=("כרטיס",),
    ),
    FieldSpec(
        field_name="יום גביה מבוקש", section="אמצעי גביה", pages=(8,), pattern=Pattern.CHOICE,
        anchor_text="בחודש", options=("10", "2"),
    ),
    _grid("שם בעל הכרטיס", "אמצעי תשלום - כרטיס אשראי", 8, "שם בעל הכרטיס"),
    _grid("מספר זהות (בעל הכרטיס)", "אמצעי תשלום - כרטיס אשראי", 8, "מספר זהות"),
    _grid("תוקף הכרטיס - חודש", "אמצעי תשלום - כרטיס אשראי", 8, "תוקף הכרטיס", occurrence=0),
    _grid("מספר כרטיס אשראי", "אמצעי תשלום - כרטיס אשראי", 8, "מספר כרטיס אשראי"),
    FieldSpec(
        field_name="סוג הכרטיס", section="אמצעי תשלום - כרטיס אשראי", pages=(8,),
        pattern=Pattern.CHOICE, anchor_text="סוג הכרטיס",
        # Each brand name is tokenized as separate words by pdftotext (e.g.
        # "ויזה" / "-" / "כאל", not one merged token), so list the
        # individual words rather than the visually-joined brand name.
        options=("ויזה", "כאל", "ישראכרט", "לאומי", "קארד", "דיינרס", "אמריקן", "אקספרס"),
    ),
]

FIELDS += [
    # Verified on a real form: the account row is "בנק | סניף | מספר חשבון |
    # סוג חשבון", values above the labels (the row is often left empty for
    # the bank to fill). The first "בנק" label on the page is this row; the
    # value printed BELOW it ("00840") is the institution code, not a bank.
    _grid("מספר סניף", "הרשאה לחיוב חשבון", 9, "סניף"),
    _grid("מספר חשבון", "הרשאה לחיוב חשבון", 9, "מספר חשבון"),
    _grid("בנק", "הרשאה לחיוב חשבון", 9, "בנק"),
    _grid("קוד המוסד )המוטב(", "הרשאה לחיוב חשבון", 9, "קוד המוסד )המוטב("),
    _grid("שם המוסד )המוטב(", "הרשאה לחיוב חשבון", 9, "שם המוסד )המוטב("),
    _grid("שם פרטי (בעל החשבון)", "הרשאה לחיוב חשבון", 9, "שם פרטי"),
    replace(_grid("שם משפחה (בעל החשבון)", "הרשאה לחיוב חשבון", 9, "שם משפחה"), wide_cell=True),
    _grid("מספר זהות / חברה (בעל החשבון)", "הרשאה לחיוב חשבון", 9, "מספר זהות / חברה"),
]

# ---------------------------------------------------------------------------
# Page 16: signing log (fully tabular, real multi-row data)
# ---------------------------------------------------------------------------
SIGNING_LOG_HEADERS = ("תחנה", "שם תחנה", "שם החותם", "דואר אלקטרוני", "טלפון נייד",
                       "כתובת ממנה נחתם", "תאריך חתימה")
TABLES.append(
    TableSpec(
        table_name="רשימת החתמות", section="חתימות", page=16,
        header_texts=SIGNING_LOG_HEADERS, column_names=SIGNING_LOG_HEADERS, max_rows=20,
        search_pages=tuple(range(30, 0, -1)),  # last page; count depends on appendices
    )
)

# ---------------------------------------------------------------------------
# Health declaration, section 4: positive findings ("פירוט ממצאים חיוביים").
# Question number + free-text details per candidate. Searched on pages 3-5
# because the continuation page depends on how much the form wraps.
# ---------------------------------------------------------------------------
FINDINGS: list[FindingsSpec] = [
    FindingsSpec(
        table_name="ממצאים חיוביים", section="הצהרת בריאות", pages=(3, 4, 5),
        anchor_text="פירוט ממצאים חיוביים", column_header=header, candidate_label=label,
    )
    for header, label in (("מועמד ראשון לביטוח", "מועמד ראשון"),
                          ("מועמד שני לביטוח", "מועמד שני"))
]


# ---------------------------------------------------------------------------
# Added after checking a real form (2 candidates, cancellation appendix and
# an irrevocable beneficiary). Appendix pages (cancellation notice "נספח ג'",
# irrevocable beneficiary notice) follow the 9 form pages and only exist when
# relevant, so their fields search a page range rather than a fixed page.
# ---------------------------------------------------------------------------
APPENDIX_PAGES = tuple(range(6, 31))


def _two(base_name, section, pages, pattern, anchor_text, x_split, **kw):
    """Same question for both candidates, side by side (right = first)."""
    return [
        FieldSpec(field_name=f"{base_name} - {label}", section=section, pages=pages,
                  pattern=pattern, anchor_text=anchor_text, column=col, x_split=x_split, **kw)
        for label, col in (("מועמד ראשון", "right"), ("מועמד שני", "left"))
    ]


def _per_appendix(base_name, section, anchor_text, pattern=Pattern.GRID, **kw):
    """One appendix page per candidate, in candidate order."""
    return [
        FieldSpec(field_name=f"{base_name} - {label}", section=section, pages=APPENDIX_PAGES,
                  pattern=pattern, anchor_text=anchor_text, occurrence=i, **kw)
        for i, label in enumerate(("מועמד ראשון", "מועמד שני"))
    ]


# beneficiaries: the "legal heirs" checkbox under each beneficiary table
FIELDS += [
    FieldSpec(field_name="יורשים חוקיים - מועמד ראשון", section="מוטבים", pages=(1,),
              pattern=Pattern.CHECKBOX, anchor_text="יורשים חוקיים"),
    FieldSpec(field_name="יורשים חוקיים - מועמד שני", section="מוטבים", pages=(2,),
              pattern=Pattern.CHECKBOX, anchor_text="יורשים חוקיים"),
]

# health 2.1: cigarettes per day, written right after the label
FIELDS += _two("כמות סיגריות ליום", "הצהרת בריאות", (3,), Pattern.INLINE,
               "כמה סיגריות ליום?", 255, max_gap=40.0)

# existing insurance (page 5): what to do with the existing policy, and how
# to submit the cancellation (checkbox to the right of each option)
for _name, _anchor in (("להותיר את הפוליסה ללא שינוי", "להותיר את הפוליסה ללא שינוי"),
                       ("להקטין סכום ביטוח בפוליסה הקיימת", "להקטין סכום ביטוח בפוליסה הקיימת"),
                       ("לבטל את הפוליסה הקיימת", "לבטל את הפוליסה הקיימת")):
    FIELDS += _yn_pair(_name, "ביטוחים קיימים", 5, _anchor, x_split=190)
for _name, _anchor, _opt in (("הגשת ביטול באמצעות סוכן", "באמצעות סוכן הביטוח", "באמצעות"),
                             ("הגשת ביטול באמצעות שלמה", "באמצעות חברת הביטוח", "באמצעות"),
                             ("הגשת ביטול באופן עצמי", "ביטול באופן עצמי", "ביטול")):
    FIELDS += _two(_name, "ביטוחים קיימים", (5,), Pattern.CHOICE, _anchor, 190,
                   options=(_opt,))

# consents and declarations: signed = date stamp next to the signature slot
_C1_SIG = "חתימת מועמד ראשון לביטוח"
FIELDS += [
    FieldSpec(field_name=name, section="הצהרות והסכמות", pages=(5, 6, 7, 8), pattern=Pattern.SIGNED,
              anchor_text=anchor, column_header=sig)
    for name, anchor, sig in (
        ("חתום: ויתור על סודיות רפואית - מועמד ראשון", "ויתור על סודיות רפואית", _C1_SIG),
        ("חתום: הגנת הפרטיות - מועמד ראשון", "הגנת הפרטיות - שימוש במידע", _C1_SIG),
        ("חתום: פניה שיווקית - מועמד ראשון", "פניה שיווקית", _C1_SIG),
        ("חתום: הצהרת המועמדים לביטוח חיים - מועמד ראשון", "הצהרת המועמדים לביטוח חיים", _C1_SIG),
        ("חתום: הצהרת הסוכן", "הצהרת הסוכן", "חתימת הסוכן"),
    )
]
FIELDS.append(
    FieldSpec(field_name="מבקש מסמכים בדואר ישראל", section="הצהרות והסכמות", pages=(6, 7),
              pattern=Pattern.CHECKBOX, anchor_text="בדואר ישראל")
)

# cancellation notice appendix ("נספח ג'"): company and policy numbers
FIELDS += _per_appendix("חברת ביטוח לביטול", "נספח ג' - הודעת ביטול", "עבור חברת הביטוח:",
                        pattern=Pattern.INLINE, max_gap=160.0)
FIELDS += _per_appendix("מספר פוליסה לביטול", "נספח ג' - הודעת ביטול",
                        "להלן מספרי הפוליסות לביטול:", pattern=Pattern.INLINE, max_gap=60.0)

# irrevocable beneficiary appendix (the lending bank / financial institution)
for _name, _anchor in (("שם המוטב הבלתי חוזר (בנק)", "שם המוטב הבלתי חוזר )בנק("),
                       ("מספר בנק", "מספר בנק"),
                       ("מספר סניף", "מספר סניף"),
                       ("כתובת הסניף", "כתובת הסניף"),
                       ("שם המוטב הבלתי חוזר (מוסד פיננסי)", "שם המוטב הבלתי חוזר )המוסד הפיננסי("),
                       ("מספר חברה", "מספר חברה")):
    FIELDS += _per_appendix(_name, "מוטב בלתי חוזר", _anchor)

# date written in the first declaration's "תאריך" box (page 6) -- the
# signature date for forms that have no signing log page
FIELDS.append(
    FieldSpec(field_name="תאריך בהצהרות", section="הצהרות והסכמות", pages=(6,),
              pattern=Pattern.GRID, anchor_text="תאריך", grid_gap=30.0)
)

