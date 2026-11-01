"""Build the layout profile of a blank proposal form: where every value and
every selection mark goes, in the blank's own coordinates.

Inputs are layout dumps made by panel_reader/dump_layout.js (the in-browser
reader, same coordinates as the extraction): the blank form and one or more
filled forms of the SAME form version. Only positions are kept; no value of
the filled forms ends up in the profile.

Usage (developer tool):
  node panel_reader/dump_layout.js blank.pdf blank.json
  node panel_reader/dump_layout.js filled1.pdf f1.json   (and more)
  python -m app.formgen.build_profile template.json blank.json f1.json [f3.json ...] > profile.json
"""
from __future__ import annotations

import json
import re
import statistics as st
import sys
from collections import Counter, defaultdict

CHECK = "✔"
# one wide box for the full name of the account owner, written from its right
# edge (the value spans both name labels on real forms)
RIGHT_ALIGNED = {"\u05d4\u05e8\u05e9\u05d0\u05d4 \u05dc\u05d7\u05d9\u05d5\u05d1 \u05d7\u05e9\u05d1\u05d5\u05df|\u05e9\u05dd \u05de\u05e9\u05e4\u05d7\u05d4 (\u05d1\u05e2\u05dc \u05d4\u05d7\u05e9\u05d1\u05d5\u05df)"}
FLIPPED = re.compile(r"(\d+)-([֐-׿])")


def norm(t: str) -> str:
    t = FLIPPED.sub(r"\2-\1", str(t))
    return t.replace(" ", "").replace("‏", "").strip()


def key(section: str, name: str) -> str:
    return section + "|" + name


def page_shift(filled: dict, blank: dict, pages: int) -> dict[int, tuple[float, float]]:
    """Per page translation filled -> blank, from label lines found once in both."""
    out = {}
    for pi in range(pages):
        a = Counter(l["t"] for l in filled["pages"][pi]["lines"])
        b = Counter(l["t"] for l in blank["pages"][pi]["lines"])
        la = {l["t"]: l for l in filled["pages"][pi]["lines"]}
        lb = {l["t"]: l for l in blank["pages"][pi]["lines"]}
        common = [t for t in a if a[t] == 1 and b.get(t) == 1 and len(t) > 3]
        if len(common) < 3:
            continue
        dx = st.median(lb[t]["x1"] - la[t]["x1"] for t in common)
        dy = st.median(lb[t]["y1"] - la[t]["y1"] for t in common)
        out[pi + 1] = (dx, dy)
    return out


def words_on(page: dict):
    for l in page["lines"]:
        for w in l["words"]:
            yield w


def yc(b) -> float:
    return (b["y0"] + b["y1"]) / 2 if isinstance(b, dict) else (b[1] + b[3]) / 2


def build(template: dict, blank: dict, filled: list[dict]) -> dict:
    n_pages = len(blank["pages"])
    specs = template["fields"]
    prof = {
        "pages": n_pages,
        "size": [[p["w"], p["h"]] for p in blank["pages"]],
        "text": {}, "choice": {}, "checkbox": {}, "signature": {}, "findings": {},
        "unsupported": [],
    }
    mark_dx, mark_dy, mark_w, mark_h = [], [], [], []
    seen_text = defaultdict(list)
    seen_choice = defaultdict(list)
    seen_cb = defaultdict(list)
    seen_sig = defaultdict(list)
    seen_find = defaultdict(list)
    spec_by = {key(s["section"], s["field_name"]): s for s in specs}

    for d in filled:
        shift = page_shift(d, blank, n_pages)
        for f in d["fields"]:
            pg = f["page_number"]
            if pg > n_pages or pg not in shift:
                continue
            dx, dy = shift[pg]
            s = f["source"]
            b = s["bbox"]
            bb = [b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy]
            k = key(f["section"], f["field_name"])
            sp = spec_by.get(k)
            t = s["type"]
            if t in ("text_grid", "inline", "table_row"):
                seen_text[k].append({"page": pg, "bbox": bb, "type": t})
            elif t == "findings_table":
                seen_find[k].append({"page": pg, "bbox": bb})
            elif t == "signature":
                seen_sig[k].append({"page": pg, "bbox": bb})
            elif t == "checkbox" and sp and sp["pattern"] == "choice":
                # selected option word, and the mark drawn right of it
                page = d["pages"][pg - 1]
                ws = [w for w in words_on(page) if w["t"] == CHECK and w["x0"] >= b[2] - 2
                      and w["x0"] - b[2] <= 25 and abs(yc(w) - yc(b)) <= 6]
                if ws:
                    m = min(ws, key=lambda w: w["x0"] - b[2])
                    mark_dx.append(m["x0"] - b[2])
                    mark_dy.append(yc(m) - yc(b))
                    mark_w.append(m["x1"] - m["x0"])
                    mark_h.append(m["y1"] - m["y0"])
                seen_choice[k].append({"page": pg, "word": bb, "option": f["value"],
                                       "text": s["raw_value"].replace(" + checkmark", "")})
            elif t == "checkbox":
                if f["value"] == "כן":
                    seen_cb[k].append({"page": pg, "bbox": bb})

    def avg_box(lst):
        return [round(st.mean(x["bbox"][i] for x in lst), 2) for i in range(4)]

    for k, lst in seen_text.items():
        b = avg_box(lst)
        prof["text"][k] = {"page": lst[0]["page"], "xc": round((b[0] + b[2]) / 2, 2), "y1": b[3],
                           "w": round(max(x["bbox"][2] - x["bbox"][0] for x in lst), 1), "type": lst[0]["type"]}
        if k in RIGHT_ALIGNED:
            prof["text"][k]["x1"] = b[2]
    for k, lst in seen_sig.items():
        prof["signature"][k] = {"page": lst[0]["page"], "bbox": avg_box(lst)}
    for k, lst in seen_cb.items():
        prof["checkbox"][k] = {"page": lst[0]["page"], "bbox": avg_box(lst)}
    for k, lst in seen_find.items():
        b = avg_box(lst)
        prof["findings"][k] = {"page": lst[0]["page"], "bbox": b}

    # the other candidate's findings column: the same box moved by the
    # distance between the two "question" column headers of the table
    for k in list(prof["findings"]):
        for a_, b_ in (("\u05de\u05d5\u05e2\u05de\u05d3 \u05e9\u05e0\u05d9", "\u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df"),
                       ("\u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df", "\u05de\u05d5\u05e2\u05de\u05d3 \u05e9\u05e0\u05d9")):
            k2 = k.replace(a_, b_)
            if a_ not in k or k2 in prof["findings"]:
                continue
            f = prof["findings"][k]
            page = blank["pages"][f["page"] - 1]
            q = sorted([l for l in page["lines"] if l["t"] == "\u05e9\u05d0\u05dc\u05d4" and l["y0"] < f["bbox"][1]],
                       key=lambda l: l["x0"])
            if len(q) >= 2:
                d = q[1]["x0"] - q[0]["x0"]
                if a_.endswith("\u05e8\u05d0\u05e9\u05d5\u05df"):
                    d = -d
                b = f["bbox"]
                prof["findings"][k2] = {"page": f["page"], "bbox": [b[0] + d, b[1], b[2] + d, b[3]], "rule": True}

    mdx = st.median(mark_dx) if mark_dx else 4.3
    mdy = st.median(mark_dy) if mark_dy else 0.0
    prof["mark"] = {"dx": round(mdx, 2), "dy": round(mdy, 2), "size": 9,
                    "w": round(st.median(mark_w), 2) if mark_w else 7.6,
                    "h": round(st.median(mark_h), 2) if mark_h else 11.7}

    # choices: every option of the field, from the option words of the blank
    for k, lst in seen_choice.items():
        sp = spec_by[k]
        o = lst[0]
        pg = o["page"]
        page = blank["pages"][pg - 1]
        sel = o["word"]
        cands = [w for w in words_on(page) if abs(yc(w) - yc(sel)) <= 4]
        opts = {}
        for opt in sp["options"]:
            ws = [w for w in cands if w["t"] == opt or w["t"].strip(",.:;*") == opt]
            if not ws:
                continue
            w = min(ws, key=lambda w: abs((w["x0"] + w["x1"]) / 2 - (sel[0] + sel[2]) / 2))
            if abs((w["x0"] + w["x1"]) / 2 - (sel[0] + sel[2]) / 2) > 160:
                continue
            opts[opt] = {"x": round(w["x1"] + mdx, 2), "yc": round(yc(w) + mdy, 2)}
        if opts:
            prof["choice"][k] = {"page": pg, "options": opts}

    # grid fields never seen filled: the anchor in the blank and the rule seen
    # on every filled grid value: centered above the label, 3.7pt gap
    gaps = [b["y1"] for b in []]
    for s in specs:
        k = key(s["section"], s["field_name"])
        if s["pattern"] == "grid" and k not in prof["text"] and s.get("direction") != "below":
            anchors = sorted(
                [l for p_i, p in enumerate(blank["pages"]) if (p_i + 1) in s["pages"]
                 for l in p["lines"] if norm(l["t"]) == norm(s["anchor_text"])
                 for _ in [l.setdefault("_page", p_i + 1)]],
                key=lambda l: (l["_page"], l["y0"]))
            if len(anchors) > s["occurrence"]:
                a = anchors[s["occurrence"]]
                prof["text"][k] = {"page": a["_page"], "xc": round((a["x0"] + a["x1"]) / 2, 2),
                                   "y1": round(a["y0"] - 3.7, 2), "w": round(a["x1"] - a["x0"] + 20, 1),
                                   "type": "text_grid", "rule": True}
        covered = k in prof["text"] or k in prof["choice"] or k in prof["checkbox"] or k in prof["signature"]
        if not covered:
            prof["unsupported"].append(k)
    return prof


def beneficiary_rows(template: dict, blank: dict, prof: dict) -> None:
    """Rows of the beneficiaries tables: each row has its own label line;
    values sit centered above the labels like every grid value."""
    out = {}
    for spec in template["beneficiaries"]:
        pg = spec["page"]
        page = blank["pages"][pg - 1]
        title = [l for l in page["lines"] if norm(spec["title_text"]) in norm(l["t"])]
        end = [l for l in page["lines"] if norm(spec["end_text"]) in norm(l["t"])]
        if not title:
            continue
        top = title[0]["y1"]
        bottom = min([l["y0"] for l in end if l["y0"] > top] or [10 ** 6])
        labels = {}
        for lab in spec["labels"]:
            ls = sorted([l for l in page["lines"] if norm(l["t"]) == norm(lab) and top < l["y0"] < bottom],
                        key=lambda l: l["y0"])
            labels[lab] = ls
        n = min(len(v) for v in labels.values()) if labels else 0
        rows = []
        for r in range(n):
            row = {}
            for lab, ls in labels.items():
                a = ls[r]
                if lab == spec["choice_column"]:
                    # options on the line above the label
                    cands = [w for w in words_on(page) if a["y0"] - 16 < w["y1"] <= a["y0"] + 1
                             and a["x0"] - 40 <= w["x0"] <= a["x1"] + 40]
                    opts = {}
                    for opt in spec["choice_options"]:
                        ws = [w for w in cands if w["t"] == opt]
                        if ws:
                            w = min(ws, key=lambda w: abs(w["x0"] - a["x0"]))
                            opts[opt] = {"x": round(w["x1"] + prof["mark"]["dx"], 2),
                                         "yc": round(yc(w) + prof["mark"]["dy"], 2)}
                    row[lab] = {"choice": opts}
                else:
                    row[lab] = {"xc": round((a["x0"] + a["x1"]) / 2, 2), "y1": round(a["y0"] - 3.7, 2),
                                "w": round(a["x1"] - a["x0"] + 30, 1)}
            rows.append(row)
        out[spec["table_name"]] = {"page": pg, "rows": rows}
    prof["beneficiaries"] = out


def signing_log(filled: dict) -> dict:
    """Geometry of the signing-log page (the page the signing system adds):
    title lines, column headers and row lines; no row values."""
    for pi, p in enumerate(filled["pages"]):
        heads = [l for l in p["lines"] if norm(l["t"]) == norm("רשימת החתמות")]
        if not heads:
            continue
        title = heads[0]
        hdr_y = min(l["y0"] for l in p["lines"] if l["y0"] > title["y1"])
        headers = [l for l in p["lines"] if abs(l["y0"] - hdr_y) < 2]
        rows_y = sorted({round(l["y0"], 1) for l in p["lines"] if l["y0"] > hdr_y + 5})
        step = st.median([b - a for a, b in zip(rows_y, rows_y[1:])]) if len(rows_y) > 1 else 21.5
        notice = [l for l in p["lines"] if l["y1"] <= title["y0"] + 1 and l["y0"] > title["y0"] - 30]
        return {
            "size": [p["w"], p["h"]],
            "title": {"t": title["t"], "x0": title["x0"], "y1": title["y1"]},
            "notice": [{"t": l["t"], "x0": l["x0"], "y1": l["y1"]} for l in notice],
            "headers": [{"t": l["t"], "x0": l["x0"], "x1": l["x1"], "y1": l["y1"]} for l in
                        sorted(headers, key=lambda l: -l["x0"])],
            "row0": rows_y[0] if rows_y else hdr_y + 22, "step": step,
            "page_index_in_filled": pi + 1,
        }
    return {}


if __name__ == "__main__":
    template = json.load(open(sys.argv[1], encoding="utf-8"))
    blank = json.load(open(sys.argv[2], encoding="utf-8"))
    filled = [json.load(open(p, encoding="utf-8")) for p in sys.argv[3:]]
    prof = build(template, blank, filled)
    beneficiary_rows(template, blank, prof)
    prof["signing_log"] = signing_log(filled[0])
    json.dump(prof, sys.stdout, ensure_ascii=False, indent=1)
