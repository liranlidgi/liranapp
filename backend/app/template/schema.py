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


@dataclass(frozen=True)
class SectionMeta:
    """Placeholder for Step-2 forward-compatibility: lets us later enumerate
    ALL template fields (filled or not) grouped by section without changing
    the extraction engine."""
    name: str
    description: str = ""
