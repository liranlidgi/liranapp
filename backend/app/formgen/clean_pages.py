"""Make blank template pages out of filled pages: drop every text drawn in
the value fonts (the filled-in data), the selection marks and the images
(signatures, stamps). The form itself is drawn in other fonts and stays.

Used for the appendix pages the signing system adds after the form
(cancellation notice, irrevocable beneficiary notice) when no blank copy of
them exists. Always check the result: python -m app.formgen.clean_pages
in.pdf out.pdf 10-13 prints what is left in the value fonts (must be none).
"""
from __future__ import annotations

import sys

import pikepdf

VALUE_FONTS = ("ArialMT", "ZapfDingbats", "Brush445BT", "TimesNewRoman")
TEXT_OPS = {"Tj", "TJ", "'", '"'}


def _is_value_font(font) -> bool:
    try:
        base = str(font.get("/BaseFont", ""))
    except Exception:
        return False
    return any(v in base for v in VALUE_FONTS)


def _clean_form(pdf: pikepdf.Pdf, xo) -> int:
    """Filled form fields are flattened into small forms: all their text
    is data (Helvetica values, ZapfDingbats marks); boxes stay."""
    ops = pikepdf.parse_content_stream(xo)
    out = [(o, op) for o, op in ops if str(op) not in TEXT_OPS]
    n = len(ops) - len(out)
    if n:
        xo.write(pikepdf.unparse_content_stream(out))
    return n


def clean_page(pdf: pikepdf.Pdf, page: pikepdf.Page) -> int:
    """Remove value text and images from one page. Returns removed ops."""
    res = page.obj.get("/Resources", {})
    fonts = res.get("/Font", {}) if res else {}
    xobjs = res.get("/XObject", {}) if res else {}
    ops = pikepdf.parse_content_stream(page)
    out = []
    cur_value_font = False
    removed = 0
    for operands, op in ops:
        name = str(op)
        if name == "Tf":
            f = fonts.get(operands[0]) if operands else None
            cur_value_font = bool(f is not None and _is_value_font(f))
        if name in TEXT_OPS and cur_value_font:
            removed += 1
            continue
        if name == "Do" and operands:
            xo = xobjs.get(operands[0]) if xobjs else None
            if xo is not None and xo.get("/Subtype") == "/Image":
                removed += 1
                continue
            if xo is not None and xo.get("/Subtype") == "/Form":
                removed += _clean_form(pdf, xo)
        out.append((operands, op))
    page.obj["/Contents"] = pdf.make_stream(pikepdf.unparse_content_stream(out))
    return removed


def clean(src: str, dst: str, pages: list[int]) -> None:
    pdf = pikepdf.open(src)
    keep = pikepdf.new()
    for p in pages:
        page = pdf.pages[p - 1]
        clean_page(pdf, page)
        if "/Annots" in page.obj:
            del page.obj["/Annots"]
        keep.pages.append(page)
    keep.save(dst)


if __name__ == "__main__":
    a, b = sys.argv[3].split("-")
    clean(sys.argv[1], sys.argv[2], list(range(int(a), int(b) + 1)))
    import pdfplumber
    with pdfplumber.open(sys.argv[2]) as pdf:
        for i, pg in enumerate(pdf.pages):
            left = [c["text"] for c in pg.chars if any(v in c["fontname"] for v in VALUE_FONTS)]
            print("page", i + 1, "value-font chars left:", len(left), "images:", len(pg.images))
