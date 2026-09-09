"""Extraction pipeline tests.

The real sample form contains personal data (ID numbers, phone numbers,
health declarations) and is never committed to the repo. Point
INSURANCE_FORM_SAMPLE_PDF at a local copy to run the full-pipeline checks;
they're skipped otherwise. The unit tests for text normalization and
geometry helpers always run since they don't need a real PDF.
"""
from __future__ import annotations

import os

import pytest

from app.pdf_extraction.text_normalize import fix_word, strip_niqqud
from app.pdf_extraction.geometry import x_overlap_fraction

SAMPLE_PDF = os.environ.get("INSURANCE_FORM_SAMPLE_PDF")
requires_sample = pytest.mark.skipif(
    not SAMPLE_PDF, reason="INSURANCE_FORM_SAMPLE_PDF not set; skipping full-pipeline test"
)


def test_strip_niqqud_removes_combining_marks():
    assert strip_niqqud("ֹל") == "ל"
    assert strip_niqqud("ִד") == "ד"


def test_fix_word_reverses_hebrew_tokens():
    assert fix_word("םש") == "שם"
    assert fix_word("רדִגמ") == "מגדר"


def test_fix_word_leaves_numbers_untouched():
    assert fix_word("318677267") == "318677267"
    assert fix_word("07/04/1999") == "07/04/1999"


def test_x_overlap_full_containment_is_one():
    # a narrow span fully inside a wider one
    assert x_overlap_fraction(10, 20, 5, 30) == 1.0


def test_x_overlap_disjoint_is_zero():
    assert x_overlap_fraction(10, 20, 30, 40) == 0.0


@requires_sample
def test_full_pipeline_against_sample():
    from app.extraction.engine import run_extraction
    from app.template.shlomo_life_insurance import FIELDS, TABLES

    result = run_extraction(SAMPLE_PDF, FIELDS, TABLES)

    assert result.document_pages == 16
    assert result.summary.total_fields_detected > 100
    assert result.summary.low_confidence == 0
    assert not result.warnings

    by_name = {f.field_name: f.value for f in result.fields if f.page_number == 1}
    assert by_name["שם משפחה"] == "וינטר"
