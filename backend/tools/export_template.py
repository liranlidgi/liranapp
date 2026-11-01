"""Export the form template (field specs, tables, findings, beneficiaries) to
JSON for the in-browser reader of the Insurtix panel, so both readers use the
same definitions. Usage: python tools/export_template.py out.json"""
from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.template.shlomo_life_insurance import BENEFICIARIES, FIELDS, FINDINGS, TABLES  # noqa: E402
from app.insurtix import mapping as M  # noqa: E402


def _plain(spec):
    d = dataclasses.asdict(spec)
    for k, v in d.items():
        if hasattr(v, "value"):
            d[k] = v.value
        elif isinstance(v, tuple):
            d[k] = list(v)
    if hasattr(spec, "pattern"):
        d["pattern"] = spec.pattern.value
    return d


def export() -> dict:
    return {
        "fields": [_plain(f) for f in FIELDS],
        "tables": [_plain(t) for t in TABLES],
        "findings": [_plain(f) for f in FINDINGS],
        "beneficiaries": [_plain(b) for b in BENEFICIARIES],
        "mapping": {
            "OWNER": M.OWNER, "CAND1": M.CAND1, "CAND2": M.CAND2, "C1": M.C1,
            "REVIEW_BELOW": M.REVIEW_BELOW, "FORMAT": M.FORMAT, "VERSION": M.VERSION,
            "PERSON_FIELDS": [list(x) for x in M.PERSON_FIELDS],
            "ID_FIELD": M.ID_FIELD, "PHONE_FIELD": M.PHONE_FIELD,
            "HEALTH": list(M.HEALTH.items()), "INSURED_YES_NO": list(M.INSURED_YES_NO.items()),
            "HMO_NAMES": M.HMO_NAMES,
            "RELATIONS": [[list(w), t] for w, t in M.RELATIONS],
            "PANEL_RELATIONS": M.PANEL_RELATIONS, "INSURERS": M.INSURERS,
            "BENEF_TABLE": M.BENEF_TABLE, "SIGN_TABLE": M.SIGN_TABLE,
            "FINDINGS_TABLE": M.FINDINGS_TABLE, "SIGNED_NOTE": M.SIGNED_NOTE,
        },
    }


if __name__ == "__main__":
    out = json.dumps(export(), ensure_ascii=False, indent=1)
    if len(sys.argv) > 1:
        Path(sys.argv[1]).write_text(out, encoding="utf-8")
    else:
        print(out)
