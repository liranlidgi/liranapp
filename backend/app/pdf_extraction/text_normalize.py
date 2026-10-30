"""Text normalization for Hebrew text pulled out of pdftotext -bbox-layout.

pdftotext's per-word bounding-box output does not run the same bidi/shaping
pipeline as its plain -layout text mode: Hebrew words come back with their
characters in visual (reversed) order, and some letters (e.g. Lamed, Dalet)
are represented as a base letter plus a stray Hebrew point (niqqud) character
picked up from this PDF's embedded font cmap. Both issues are fixed here so
that downstream matching can compare against plain, correctly-ordered Hebrew
strings.
"""
from __future__ import annotations

import unicodedata

_HEBREW_LOW = "֐"
_HEBREW_HIGH = "׿"


def _is_hebrew_char(ch: str) -> bool:
    return _HEBREW_LOW <= ch <= _HEBREW_HIGH


def strip_niqqud(text: str) -> str:
    """Remove Hebrew combining marks (niqqud/cantillation) that this PDF's
    font encoding attaches to otherwise-plain consonants."""
    decomposed = unicodedata.normalize("NFD", text)
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return unicodedata.normalize("NFC", stripped)


def is_mostly_hebrew(text: str) -> bool:
    letters = [c for c in text if not c.isspace()]
    if not letters:
        return False
    hebrew_count = sum(1 for c in letters if _is_hebrew_char(c))
    return hebrew_count >= max(1, len(letters) * 0.5)


def fix_word(raw: str) -> str:
    """Normalize a single whitespace-delimited token extracted from the bbox
    XML: strip stray niqqud, then reverse to logical reading order if it is
    a Hebrew token (bbox mode emits Hebrew glyphs in visual/reversed order)."""
    cleaned = strip_niqqud(raw)
    if is_mostly_hebrew(cleaned):
        word = cleaned[::-1]
        # a geresh/apostrophe is kept in logical position by pdftotext, so the
        # reversal moves it to the front ("'פלוניץ"): Hebrew words never
        # start with one, so put it back at the end.
        if len(word) > 1 and word[0] in "'׳" and _is_hebrew_char(word[1]):
            word = word[1:] + word[0]
        return word
    return cleaned
