"""Runs `pdftotext -bbox-layout` and parses the result into positioned words.

We rely on Poppler's `pdftotext` (the `poppler-utils` package) rather than a
Python PDF library because it already solves the hard parts correctly for
this document: AES-encrypted-but-openable PDFs, embedded/subset Hebrew fonts
with unusual glyph-to-Unicode maps (including the checkmark glyph, which
comes from a ZapfDingbats symbol font with a non-standard encoding), and
per-word bounding boxes we need for spatial (not just linear) reading order.
"""
from __future__ import annotations

import logging
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from .text_normalize import fix_word

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Word:
    text: str          # normalized, logical reading order
    raw_text: str       # exactly as pdftotext emitted it
    x0: float
    y0: float
    x1: float
    y1: float
    page: int            # 1-indexed
    line_id: int          # unique id of the <line> this word came from

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class Line:
    line_id: int
    page: int
    x0: float
    y0: float
    x1: float
    y1: float
    words: list[Word]  # in RTL reading order (right/high-x to left/low-x)

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass(frozen=True)
class PageInfo:
    number: int
    width: float
    height: float


class PdfExtractionError(RuntimeError):
    pass


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def run_pdftotext_bbox(pdf_path: str) -> str:
    try:
        result = subprocess.run(
            ["pdftotext", "-bbox-layout", pdf_path, "-"],
            capture_output=True,
            check=True,
            timeout=120,
        )
    except FileNotFoundError as exc:
        raise PdfExtractionError(
            "pdftotext not found. Install poppler-utils (apt-get install poppler-utils)."
        ) from exc
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", errors="replace")
        raise PdfExtractionError(f"pdftotext failed: {stderr}") from exc
    except subprocess.TimeoutExpired as exc:
        raise PdfExtractionError("pdftotext timed out") from exc
    return result.stdout.decode("utf-8", errors="replace")


def parse_bbox_xml(xml_text: str) -> tuple[list[PageInfo], list[Word], list[Line]]:
    root = ET.fromstring(xml_text)
    pages: list[PageInfo] = []
    words: list[Word] = []
    lines: list[Line] = []

    page_number = 0
    line_id = 0
    for page_el in root.iter():
        if _local(page_el.tag) != "page":
            continue
        page_number += 1
        width = float(page_el.get("width", 0))
        height = float(page_el.get("height", 0))
        pages.append(PageInfo(number=page_number, width=width, height=height))

        for line_el in page_el.iter():
            if _local(line_el.tag) != "line":
                continue
            line_words: list[Word] = []
            for word_el in line_el.iter():
                if _local(word_el.tag) != "word":
                    continue
                raw = word_el.text or ""
                if not raw.strip():
                    continue
                line_words.append(
                    Word(
                        text=fix_word(raw),
                        raw_text=raw,
                        x0=float(word_el.get("xMin", 0)),
                        y0=float(word_el.get("yMin", 0)),
                        x1=float(word_el.get("xMax", 0)),
                        y1=float(word_el.get("yMax", 0)),
                        page=page_number,
                        line_id=line_id,
                    )
                )
            if not line_words:
                continue
            # RTL reading order: highest x (rightmost) first.
            line_words.sort(key=lambda w: -w.x0)
            words.extend(line_words)
            lines.append(
                Line(
                    line_id=line_id,
                    page=page_number,
                    x0=min(w.x0 for w in line_words),
                    y0=min(w.y0 for w in line_words),
                    x1=max(w.x1 for w in line_words),
                    y1=max(w.y1 for w in line_words),
                    words=line_words,
                )
            )
            line_id += 1

    return pages, words, lines


def extract_words(pdf_path: str) -> tuple[list[PageInfo], list[Word], list[Line]]:
    logger.info("Extracting words from %s via pdftotext -bbox-layout", pdf_path)
    xml_text = run_pdftotext_bbox(pdf_path)
    pages, words, lines = parse_bbox_xml(xml_text)
    logger.info(
        "Extracted %d words in %d lines across %d pages", len(words), len(lines), len(pages)
    )
    return pages, words, lines
