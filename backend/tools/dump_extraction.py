"""Write <name>.py.json (extraction + Insurtix mapping) next to every PDF in a
folder, for the parity test of the in-browser reader (panel_reader/parity.js).
Usage: python tools/dump_extraction.py <folder>"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
logging.disable(logging.INFO)

from app.extraction.engine import run_extraction  # noqa: E402
from app.insurtix.mapping import to_insurtix  # noqa: E402
from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES  # noqa: E402

folder = Path(sys.argv[1])
for pdf in sorted(folder.glob("*.pdf")):
    r = run_extraction(str(pdf), FIELDS, TABLES, FINDINGS + BENEFICIARIES)
    out = {"r": r.model_dump(), "m": to_insurtix(r, pdf.name)}
    pdf.with_suffix(".py.json").write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(pdf.name, len(r.fields), "fields")
