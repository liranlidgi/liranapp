"""Declarative field specifications for a specific form template.

A FieldSpec never encodes pixel coordinates. It encodes what the field is
called, which known static label/question text anchors it in the document,
and which *pattern* the extraction engine should use to find its value
relative to that anchor. This is what makes the template "template-aware but
data-independent": re-running it against a different filled copy of the same
Shlomo Insurance form should work unchanged, because it never looks at the
values themselves to find the anchors.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Pattern(str, Enum):
    GRID = "grid"            # value printed directly above the label
    CHOICE = "choice"        # checkmark selects one of several option words
    TABLE = "table"          # repeating rows under a header
    ROW = "row"              # value in the same table row, under a column header
    INLINE = "inline"        # value on the same line, right after the label (to its left)
    SIGNED = "signed"        # "כן" when a section's signature slot carries a date stamp
    CHECKBOX = "checkbox"    # "כן"/"לא": is there a checkmark next to the anchor text


@dataclass(frozen=True)
class FieldSpec:
    field_name: str
    section: str
    pages: tuple[int, ...]
    pattern: Pattern
    anchor_text: str
    options: tuple[str, ...] = ()
    occurrence: int = 0          # which match of anchor_text on the page(s), 0-indexed
    column: str | None = None    # "right" | "left" | None -- disambiguates side-by-side candidate columns
    x_split: float | None = None  # override the right/left split point (page-width units)
    direction: str = "above"      # GRID only: "above" (default) or "below" the anchor label
    layout: str = "inline"        # CHOICE only: "inline" (checkboxes near the question text,
                                    # split left/right by column) or "above_label" (checkboxes
                                    # sit in the value row above a short field label, like GRID)
    column_header: str | None = None  # ROW: header of the value column;
                                      # SIGNED: label of the signature slot
    max_gap: float = 60.0             # INLINE only: max distance from label to value
    grid_gap: float = 13.0            # GRID only: max vertical gap between value and label
    notes: str = ""

    def __post_init__(self):
        if self.pattern == Pattern.CHOICE and not self.options:
            raise ValueError(f"{self.field_name}: CHOICE pattern requires options")


@dataclass(frozen=True)
class TableSpec:
    table_name: str
    section: str
    page: int
    header_texts: tuple[str, ...]   # column headers, in RTL reading (right-to-left) order
    column_names: tuple[str, ...]   # human field-name per column, same order as header_texts
    max_rows: int = 20
    # When set, the table is looked up on these pages (first page holding all
    # headers wins) instead of the fixed `page`: the signing log is the last
    # page, and the page count depends on which appendices are attached.
    search_pages: tuple[int, ...] = ()


@dataclass(frozen=True)
class FindingsSpec:
    """The "positive findings" table of the health declaration: under each
    candidate column there are two sub-columns, a question number ("מס' שאלה")
    and free-text details ("פרטים") that can wrap over several lines. One
    entry starts at each question number."""
    table_name: str               # field-name prefix, e.g. "ממצאים חיוביים"
    section: str
    pages: tuple[int, ...]        # pages to search for the anchor
    anchor_text: str              # question text of the row, e.g. "פירוט ממצאים חיוביים"
    column_header: str            # candidate column header, e.g. "מועמד ראשון לביטוח"
    candidate_label: str          # used in field names, e.g. "מועמד ראשון"
    number_header: str = "שאלה"   # second word of the "מס' שאלה" sub-header
    details_header: str = "פרטים"
    end_text: str = "חתימות"      # band that closes the table (page end if missing)
    max_rows: int = 10


@dataclass(frozen=True)
class RowsTableSpec:
    """A table whose every row repeats its own labels under the values (the
    beneficiary tables): ".1" | values... over "שם פרטי | שם משפחה | ...",
    then ".2" and so on. Columns come from each row's own label words."""
    table_name: str               # field-name prefix, same as the old TableSpec
    section: str
    page: int
    title_text: str               # table title line, e.g. "פרטי מוטבים למועמד ראשון לביטוח"
    labels: tuple[str, ...]       # label texts of one row, RTL order
    first_label: str = "שם פרטי"  # label that marks the start of each row
    end_text: str = "יורשים חוקיים"
    choice_column: str = "מגדר"   # checkbox column (options below)
    choice_options: tuple[str, ...] = ("ז", "נ")


@dataclass(frozen=True)
class SectionMeta:
    """Placeholder for Step-2 forward-compatibility: lets us later enumerate
    ALL template fields (filled or not) grouped by section without changing
    the extraction engine."""
    name: str
    description: str = ""
