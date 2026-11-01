"""Generate a batch of test forms: PDFs, the expected values of each, and a
check report (what the reader got right)."""
from __future__ import annotations

import io
import json
import logging
import tempfile
import zipfile
from datetime import date
from pathlib import Path

from . import scenario
from .check import compare, expected_result
from .render import Renderer

ROOT = Path(__file__).resolve().parents[3]          # the liranapp folder
TEMPLATE = ROOT / "templates" / "proposal10_template.pdf"
PROFILE = Path(__file__).resolve().parent / "profiles" / "proposal10.json"
logger = logging.getLogger(__name__)


def ready() -> tuple[bool, str]:
    if not TEMPLATE.exists():
        return False, "חסרה תבנית הטופס: " + str(TEMPLATE)
    if not PROFILE.exists():
        return False, "חסר קובץ המיקומים: " + str(PROFILE)
    return True, ""


def generate(count: int = 10, seed: int = 1, edges: list[str] | None = None, check: bool = True,
             random_edges: bool = False, agents: list[str] | None = None,
             discounts: list[str] | None = None,
             occupations: list[str] | None = None) -> tuple[bytes, dict]:
    """A zip with NNN.pdf + NNN.expected.json for every form, and report.json."""
    ok, why = ready()
    if not ok:
        raise FileNotFoundError(why)
    renderer = Renderer(str(TEMPLATE), str(PROFILE))
    report = {"forms": [], "fields": 0, "fields_bad": 0, "mapped": 0, "mapped_bad": 0}
    if check:
        from app.extraction.engine import run_extraction
        from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES
        from app.insurtix.mapping import to_insurtix
    else:
        from app.insurtix.mapping import to_insurtix
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z, tempfile.TemporaryDirectory() as tmp:
        for i in range(count):
            s = seed + i
            sel = None if random_edges else set(edges or [])
            sc = scenario.make(s, sel, agents=agents, discounts=discounts, today=date.today(),
                               occupations=occupations)
            name = "%03d" % (i + 1)
            pdf = Path(tmp) / (name + ".pdf")
            renderer.render(sc, str(pdf))
            z.write(pdf, name + ".pdf")
            exp = to_insurtix(expected_result(sc), name + ".pdf")
            z.writestr(name + ".expected.json", json.dumps(
                {"scenario": sc, "insurtix": exp}, ensure_ascii=False, indent=1))
            row = {"file": name + ".pdf", "seed": s, "edges": sc["edges"]}
            if check:
                got = run_extraction(str(pdf), FIELDS, TABLES, FINDINGS + BENEFICIARIES)
                c = compare(sc, got)
                row.update({"fields": c["fields"], "fields_bad": c["fields_bad"],
                            "mapped": c["mapped"], "mapped_bad": c["mapped_bad"]})
                for k in ("fields", "mapped"):
                    report[k] += c[k]
                    report[k + "_bad"] += len(c[k + "_bad"])
            report["forms"].append(row)
        z.writestr("report.json", json.dumps(report, ensure_ascii=False, indent=1))
    return buf.getvalue(), report


def _profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def form_schema() -> dict:
    """Every value the generator can write, grouped by section in form order,
    for the hand-editing screen."""
    prof = _profile()
    items = []

    def add(kind, key, page, y, **extra):
        sec, name = key.split("|", 1)
        items.append(dict(kind=kind, key=key, section=sec, name=name, page=page, y=y, **extra))

    for k, v in prof["text"].items():
        add("text", k, v["page"], v["y1"])
    for k, v in prof["choice"].items():
        add("choice", k, v["page"], min(o["yc"] for o in v["options"].values()), options=list(v["options"]))
    for k, v in prof["checkbox"].items():
        add("checkbox", k, v["page"], v["bbox"][1])
    for k, v in prof["signature"].items():
        add("signature", k, v["page"], v["bbox"][1])
    for k, v in prof["findings"].items():
        add("finding", k, v["page"], v["bbox"][1])
    items.sort(key=lambda i: (i["page"], i["y"]))
    sections = []
    for it in items:
        if not sections or sections[-1]["name"] != it["section"]:
            sec = next((s for s in sections if s["name"] == it["section"]), None)
            if sec is None:
                sec = {"name": it["section"], "page": it["page"], "fields": []}
                sections.append(sec)
        else:
            sec = sections[-1]
        sec["fields"].append({k: it[k] for k in ("kind", "key", "name", "options") if k in it})
    tables = {}
    for t, v in prof["beneficiaries"].items():
        cols = list(v["rows"][0])
        tables[t] = {"rows": len(v["rows"]), "columns": cols,
                     "options": {c: list(v["rows"][0][c]["choice"]) for c in cols if "choice" in v["rows"][0][c]}}
    log = [h["t"] for h in prof["signing_log"]["headers"]] if prof.get("signing_log") else []
    return {"sections": sections, "beneficiaries": tables, "signing_log": log,
            "unsupported": prof.get("unsupported", [])}


def make_scenario(seed: int, edges: list[str] | None, random_edges: bool, agents=None, discounts=None,
                  occupations=None) -> dict:
    sel = None if random_edges else set(edges or [])
    return scenario.make(seed, sel, agents=agents, discounts=discounts, today=date.today(),
                         occupations=occupations)


def render_one(sc: dict, check: bool = True, name: str = "form") -> dict:
    """One hand-edited scenario -> the PDF, its expected values, and (with
    `check`) what the reader read from it."""
    ok, why = ready()
    if not ok:
        raise FileNotFoundError(why)
    from app.insurtix.mapping import to_insurtix
    sc = scenario.clean(sc, _profile())
    with tempfile.TemporaryDirectory() as tmp:
        pdf = Path(tmp) / (name + ".pdf")
        Renderer(str(TEMPLATE), str(PROFILE)).render(sc, str(pdf))
        data = pdf.read_bytes()
        out = {"pdf": data, "expected": {"scenario": sc, "insurtix": to_insurtix(expected_result(sc), name + ".pdf")}}
        if check:
            from app.extraction.engine import run_extraction
            from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES
            c = compare(sc, run_extraction(str(pdf), FIELDS, TABLES, FINDINGS + BENEFICIARIES))
            out["check"] = {"fields": c["fields"], "fields_bad": c["fields_bad"],
                            "mapped": c["mapped"], "mapped_bad": c["mapped_bad"]}
    return out


def render_from_panel(p: dict, check: bool = True) -> dict:
    """The external panel's values -> a filled form PDF. With `check`, the PDF
    is read back and compared with the panel values (what would be keyed)."""
    from . import from_panel
    sc, notes = from_panel.panel_to_scenario(p, seed=from_panel.today_seed())
    out = render_one(sc, check=check, name="proposal")
    out["notes"] = notes
    if check:
        from app.extraction.engine import run_extraction
        from app.insurtix.mapping import to_insurtix
        from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES
        with tempfile.TemporaryDirectory() as tmp:
            pdf = Path(tmp) / "proposal.pdf"
            pdf.write_bytes(out["pdf"])
            read = to_insurtix(run_extraction(str(pdf), FIELDS, TABLES, FINDINGS + BENEFICIARIES))
        out["roundtrip"] = {"values": len(read["values"]),
                            "bad": from_panel.roundtrip(p, read["values"])}
    return out
