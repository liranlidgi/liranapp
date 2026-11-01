"""Draw a scenario onto the blank proposal form: values in the boxes, a mark
next to the chosen options, signature images, and the signing-log page the
signing system adds at the end. The result reads like a real form."""
from __future__ import annotations

import io
import json
import os
import random
import re
from pathlib import Path

from pypdf import PdfReader, PdfWriter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

HERE = Path(__file__).resolve().parent
FONT_NAME = "FormValue"
FONT_CANDIDATES = [
    os.environ.get("FORMGEN_FONT", ""),
    "C:/Windows/Fonts/arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
VALUE_SIZE = 8.0

HEB = re.compile(r"[\u0590-\u05FF]")
LTR = re.compile(r"[A-Za-z0-9]")
MIRROR = {"(": ")", ")": "(", "[": "]", "]": "[", "<": ">", ">": "<"}


def _font() -> str:
    if FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return FONT_NAME
    for p in FONT_CANDIDATES:
        if p and Path(p).exists():
            pdfmetrics.registerFont(TTFont(FONT_NAME, p))
            return FONT_NAME
    raise RuntimeError("no font with Hebrew letters found; set FORMGEN_FONT to a .ttf file")


def visual(s: str) -> str:
    """Logical -> visual order, as the form stores Hebrew (right-to-left
    paragraph; numbers, Latin and dates keep their order)."""
    s = str(s)
    if not HEB.search(s) and " " not in s:
        return s
    kinds = ["R" if HEB.match(c) or c == " " else "L" if LTR.match(c) else "N" for c in s]
    # a neutral between two left-to-right characters stays with them
    for i, k in enumerate(kinds):
        if k != "N":
            continue
        left = next((kinds[j] for j in range(i - 1, -1, -1) if kinds[j] != "N"), "R")
        right = next((kinds[j] for j in range(i + 1, len(kinds)) if kinds[j] != "N"), "R")
        kinds[i] = "L" if left == "L" and right == "L" else "R"
    runs = []
    for c, k in zip(s, kinds):
        if runs and runs[-1][0] == k:
            runs[-1][1].append(c)
        else:
            runs.append([k, [c]])
    out = []
    for k, cs in reversed(runs):
        out.append("".join(cs) if k == "L" else "".join(MIRROR.get(c, c) for c in reversed(cs)))
    return "".join(out)


def _signature_png(seed: int) -> ImageReader:
    from PIL import Image, ImageDraw
    rnd = random.Random(seed)
    im = Image.new("RGB", (240, 60), "white")
    d = ImageDraw.Draw(im)
    x, y = 10, 30
    pts = []
    for i in range(14):
        x += rnd.randint(10, 18)
        y = max(8, min(52, y + rnd.randint(-16, 16)))
        pts.append((x, y))
    d.line([(10, 30)] + pts, fill=(20, 30, 120), width=3)
    buf = io.BytesIO()
    im.save(buf, "PNG")
    buf.seek(0)
    return ImageReader(buf)


class Renderer:
    def __init__(self, template_pdf: str, profile: dict | str):
        self.template_pdf = template_pdf
        self.profile = json.load(open(profile, encoding="utf-8")) if isinstance(profile, str) else profile
        self.font = _font()
        face = pdfmetrics.getFont(self.font).face
        self.descent = face.descent / 1000.0  # negative

    # coordinates: the profile is top-down (like the reader); reportlab is bottom-up
    def _text(self, c, h, xc, y1, text, size=VALUE_SIZE, width=None, x1=None):
        vis = visual(text)
        size_used = size
        if width:
            while size_used > 5 and pdfmetrics.stringWidth(vis, self.font, size_used) > width:
                size_used -= 0.5
        w = pdfmetrics.stringWidth(vis, self.font, size_used)
        base = h - y1 + (-self.descent) * size_used
        c.setFont(self.font, size_used)
        c.drawString(x1 - w if x1 is not None else xc - w / 2, base, vis)

    def _mark(self, c, h, x, yc):
        size = self.profile["mark"]["size"]
        c.setFont("ZapfDingbats", size)
        c.drawString(x, h - yc - 0.3 * size, "\u2714")

    def render(self, sc: dict, out_pdf: str) -> None:
        prof = self.profile
        reader = PdfReader(self.template_pdf)
        n = prof["pages"]
        keep = list(range(1, n + 1))
        if not sc.get("appendices", True):
            keep = [p for p in keep if p <= 9]
        layers = {p: io.BytesIO() for p in keep}
        cans = {}
        for p in keep:
            w, h = prof["size"][p - 1]
            cans[p] = canvas.Canvas(layers[p], pagesize=(w, h))

        def page_h(p):
            return prof["size"][p - 1][1]

        for k, v in sc.get("text", {}).items():
            spec = prof["text"].get(k)
            if not spec or v in (None, "") or spec["page"] not in cans:
                continue
            p = spec["page"]
            # the observed width is of one sample value: allow a wider value
            self._text(cans[p], page_h(p), spec["xc"], spec["y1"], v, width=max(spec.get("w") or 0, 110),
                       x1=spec.get("x1"))
        for k, opt in sc.get("choice", {}).items():
            spec = prof["choice"].get(k)
            if not spec or opt is None or spec["page"] not in cans:
                continue
            o = spec["options"].get(opt)
            if o:
                self._mark(cans[spec["page"]], page_h(spec["page"]), o["x"], o["yc"])
        for k, on in sc.get("checkbox", {}).items():
            spec = prof["checkbox"].get(k)
            if on and spec and spec["page"] in cans:
                b = spec["bbox"]
                self._mark(cans[spec["page"]], page_h(spec["page"]), b[0], (b[1] + b[3]) / 2)
        for i, (k, on) in enumerate(sc.get("signature", {}).items()):
            spec = prof["signature"].get(k)
            if on and spec and spec["page"] in cans:
                b = spec["bbox"]
                h = page_h(spec["page"])
                bw, bh = max(b[2] - b[0], 30), max(b[3] - b[1], 9)
                cans[spec["page"]].drawImage(_signature_png(i + 7), b[0], h - b[1] - bh, bw, bh)
        for table, rows in sc.get("beneficiaries", {}).items():
            spec = prof["beneficiaries"].get(table)
            if not spec or spec["page"] not in cans:
                continue
            p = spec["page"]
            for row, vals in zip(spec["rows"], rows):
                for lab, v in vals.items():
                    cell = row.get(lab)
                    if not cell or v in (None, ""):
                        continue
                    if "choice" in cell:
                        o = cell["choice"].get(v)
                        if o:
                            self._mark(cans[p], page_h(p), o["x"], o["yc"])
                    else:
                        self._text(cans[p], page_h(p), cell["xc"], cell["y1"], v, width=cell["w"])
        for k, v in sc.get("findings", {}).items():
            spec = prof["findings"].get(k)
            if not spec or not v or spec["page"] not in cans:
                continue
            p = spec["page"]
            b = spec["bbox"]
            self._wrap(cans[p], page_h(p), b, v)
        for c in cans.values():
            c.showPage()
            c.save()

        writer = PdfWriter()
        for p in keep:
            page = reader.pages[p - 1]
            layers[p].seek(0)
            page.merge_page(PdfReader(layers[p]).pages[0])
            writer.add_page(page)
        log = sc.get("signing_log")
        if log and prof.get("signing_log"):
            buf = io.BytesIO()
            self._signing_log(buf, log)
            buf.seek(0)
            writer.add_page(PdfReader(buf).pages[0])
        writer.add_metadata({"/Producer": "liranapp formgen (synthetic test form)"})
        with open(out_pdf, "wb") as f:
            writer.write(f)

    def _wrap(self, c, h, b, text):
        """Multi-line value (positive findings): right-aligned lines in the box."""
        width = b[2] - b[0] - 2  # a little padding inside the box
        words = str(text).split()
        lines, cur = [], ""
        for w in words:
            t = (cur + " " + w).strip()
            if pdfmetrics.stringWidth(visual(t), self.font, VALUE_SIZE) <= width or not cur:
                cur = t
            else:
                lines.append(cur)
                cur = w
        if cur:
            lines.append(cur)
        y1 = b[1] + 1.12 * VALUE_SIZE
        for ln in lines:
            vis = visual(ln)
            wd = pdfmetrics.stringWidth(vis, self.font, VALUE_SIZE)
            c.setFont(self.font, VALUE_SIZE)
            c.drawString(b[2] - wd, h - y1 + (-self.descent) * VALUE_SIZE, vis)
            y1 += 1.25 * VALUE_SIZE

    def _signing_log(self, buf, rows):
        g = self.profile["signing_log"]
        w, h = g["size"]
        c = canvas.Canvas(buf, pagesize=(w, h))
        for ln in g["notice"] + [g["title"]]:
            c.setFont(self.font, 10)
            c.drawString(ln["x0"], h - ln["y1"] + (-self.descent) * 10, visual(ln["t"]))
        for hd in g["headers"]:
            c.setFont(self.font, VALUE_SIZE)
            vis = visual(hd["t"])
            wd = pdfmetrics.stringWidth(vis, self.font, VALUE_SIZE)
            xc = (hd["x0"] + hd["x1"]) / 2
            c.drawString(xc - wd / 2, h - hd["y1"] + (-self.descent) * VALUE_SIZE, vis)
        for i, row in enumerate(rows):
            y1 = g["row0"] + i * g["step"] + 1.12 * VALUE_SIZE
            for hd in g["headers"]:
                v = row.get(hd["t"])
                if v in (None, ""):
                    continue
                self._text(c, h, (hd["x0"] + hd["x1"]) / 2, y1, v)
        c.showPage()
        c.save()
