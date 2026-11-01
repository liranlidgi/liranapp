"""External panel -> form PDF: the PDF read back gives the panel values."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from app.formgen import from_panel, service

STATE = json.loads((Path(__file__).parent / "data_panel_state.json").read_text(encoding="utf-8"))
needs_template = pytest.mark.skipif(not service.ready()[0], reason="no form template")


def test_scenario_basics():
    sc, notes = from_panel.panel_to_scenario(STATE, seed=1)
    t = sc["text"]
    assert t["פרטי הסוכן|מספר סוכן"] == "839"
    assert t["פרטי הסוכן|קוד הנחה"] == "178"
    assert t["הצהרת בריאות|גובה - מועמד ראשון"] == "170"
    assert t["מוטב בלתי חוזר|מספר בנק - מועמד ראשון"] == "31"
    assert t["הרשאה לחיוב חשבון|בנק"] == "54"
    assert sc["checkbox"]["מוטבים|יורשים חוקיים - מועמד ראשון"] is True
    assert any("יום גבייה 13" in n for n in notes)
    assert any("מספר זהות פיקטיבי" in n for n in notes)


@needs_template
def test_roundtrip_default_state():
    out = service.render_from_panel(STATE)
    assert out["roundtrip"]["bad"] == []
    assert out["check"]["fields_bad"] == [] and out["check"]["mapped_bad"] == []


@needs_template
def test_roundtrip_beneficiaries_and_no_lien():
    p = copy.deepcopy(STATE)
    p["owner"]["idNumber"] = "807302153"
    p["lien"] = {"type": "none"}
    p["payment"]["collectionDay"] = "10"
    p["beneficiaries"] = [
        {"firstName": "דנה", "lastName": "בדיקה", "idNumber": "", "birthDate": "01/02/2010",
         "gender": "female", "relation": "ילד/ה", "percent": 60},
        {"firstName": "רון", "lastName": "בדיקה", "idNumber": "", "birthDate": "03/04/1990",
         "gender": "male", "relation": "בן / בת זוג", "percent": 40},
    ]
    out = service.render_from_panel(p)
    assert out["roundtrip"]["bad"] == []
