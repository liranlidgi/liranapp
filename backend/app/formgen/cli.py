"""Generate test proposal forms from the command line.

  cd backend
  python -m app.formgen.cli --count 20 --out ../generated
  python -m app.formgen.cli --count 5 --edges insured2,lien,health_yes --out ../generated
  python -m app.formgen.cli --list-edges
"""
from __future__ import annotations

import argparse
import io
import logging
import sys
import zipfile
from pathlib import Path

from . import scenario, service


def main() -> int:
    ap = argparse.ArgumentParser(description="test proposal forms (code 10)")
    ap.add_argument("--count", type=int, default=10)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--edges", default="", help="comma separated; see --list-edges")
    ap.add_argument("--random-edges", action="store_true", help="a random mix of edge cases per form")
    ap.add_argument("--out", default=str(service.ROOT / "generated"))
    ap.add_argument("--no-check", action="store_true", help="do not run the reader on the forms")
    ap.add_argument("--list-edges", action="store_true")
    a = ap.parse_args()
    if a.list_edges:
        for k, v in scenario.EDGES.items():
            print("%-20s %s" % (k, v))
        return 0
    logging.disable(logging.INFO)
    edges = [e for e in a.edges.split(",") if e]
    bad = [e for e in edges if e not in scenario.EDGES]
    if bad:
        print("unknown edge case:", ", ".join(bad))
        return 2
    data, rep = service.generate(a.count, a.seed, edges, check=not a.no_check, random_edges=a.random_edges)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    zipfile.ZipFile(io.BytesIO(data)).extractall(out)
    print("written to", out)
    if not a.no_check:
        for f in rep["forms"]:
            print("%s  edges=%s  fields %d/%d  insurtix %d/%d" % (
                f["file"], ",".join(f["edges"]) or "-", f["fields"] - len(f["fields_bad"]), f["fields"],
                f["mapped"] - len(f["mapped_bad"]), f["mapped"]))
            for b in f["fields_bad"][:5]:
                print("    field:", b["field"], "| expected:", b["expected"], "| read:", b["got"])
        print("TOTAL fields %d/%d  insurtix values %d/%d" % (
            rep["fields"] - rep["fields_bad"], rep["fields"], rep["mapped"] - rep["mapped_bad"], rep["mapped"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
