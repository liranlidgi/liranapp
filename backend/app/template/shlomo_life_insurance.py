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

from .schema import FieldSpec, Pattern, TableSpec

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
TABLES: list[TableSpec] = [
    TableSpec(
        table_name="מוטבים למועמד ראשון לביטוח", section="מוטבים", page=1,
        header_texts=BENEFICIARY_COLUMNS, column_names=BENEFICIARY_COLUMNS, max_rows=7,
    ),
    TableSpec(
        table_name="מוטבים למועמד שני לביטוח", section="מוטבים", page=2,
        header_texts=BENEFICIARY_COLUMNS, column_names=BENEFICIARY_COLUMNS, max_rows=7,
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
    _grid("בנק", "הרשאה לחיוב חשבון", 9, "בנק", direction="below"),
    _grid("שם המוסד )המוטב(", "הרשאה לחיוב חשבון", 9, "שם המוסד )המוטב("),
    _grid("שם פרטי (בעל החשבון)", "הרשאה לחיוב חשבון", 9, "שם פרטי"),
    _grid("שם משפחה (בעל החשבון)", "הרשאה לחיוב חשבון", 9, "שם משפחה"),
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
    )
)
