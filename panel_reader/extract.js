/*
 * Port of the liranapp extraction (patterns, tables, findings, beneficiary
 * rows, vector marks, engine) and of the Insurtix mapping (to_insurtix).
 * The field definitions and mapping constants come from liranapp itself
 * (tools/export_template.py -> TEMPLATE), so this file holds only logic.
 * Keep it in step with the Python code: the parity test compares both.
 */
var ProposalExtract = (function () {
  'use strict';
  var CHECKMARK = '\u2714';
  var MIN_CONFIDENCE_TO_EMIT = 0.55;

  /* ------------------------------------------------------------ helpers */
  function xc(o) { return (o.x0 + o.x1) / 2; }
  function yc(o) { return (o.y0 + o.y1) / 2; }
  function lineText(ln) { return ln.words.map(function (w) { return w.text; }).join(' '); }
  var FLIPPED = /(\d+)-([\u05d0-\u05ea])(?![\u05d0-\u05ea])/g;
  function normalize(t) {
    t = String(t).replace(FLIPPED, '$2-$1');
    return t.replace(/ /g, '').replace(/\u200f/g, '').trim();
  }
  function minBy(arr, f) {
    var best = null;
    var bv = Infinity;
    arr.forEach(function (x) { var v = f(x); if (v < bv) { bv = v; best = x; } });
    return best;
  }
  function maxBy(arr, f) {
    var best = null;
    var bv = -Infinity;
    arr.forEach(function (x) { var v = f(x); if (v > bv) { bv = v; best = x; } });
    return best;
  }
  function mn(a) { return Math.min.apply(null, a); }
  function mx(a) { return Math.max.apply(null, a); }
  function clamp(x, lo, hi) { lo = lo === undefined ? 0 : lo; hi = hi === undefined ? 0.99 : hi; return Math.max(lo, Math.min(hi, x)); }
  function gridConfidence(xo, gap, amb) {
    var s = 0.99;
    s -= (1 - xo) * 0.18;
    if (gap > 4) { s -= Math.min((gap - 4) / 60, 0.2); }
    if (amb > 1) { s -= 0.1 * (amb - 1); }
    return clamp(s);
  }
  function choiceConfidence(gap, alt) {
    var s = 0.99 - (gap / 25) * 0.28;
    if (alt > 0) { s -= 0.25 * alt; }
    return clamp(s);
  }
  function tableConfidence(c) { return clamp(0.95 * c + 0.02); }
  function xOverlap(a0, a1, b0, b1) {
    var inter = Math.min(a1, b1) - Math.max(a0, b0);
    if (inter <= 0) { return 0; }
    var span = Math.min(a1 - a0, b1 - b0);
    if (span <= 0) { return 0; }
    return inter / span;
  }
  function plausibleWidth(aw, cw) { return cw <= 200 ? true : cw <= aw * 5; }
  function nearestAbove(lines, a, minXo, maxGap) {
    minXo = minXo === undefined ? 0.5 : minXo;
    var c = lines.filter(function (ln) {
      return ln.page === a.page && ln.y1 <= a.y0 + 1 && (a.y0 - ln.y1) <= maxGap &&
        xOverlap(ln.x0, ln.x1, a.x0, a.x1) >= minXo && plausibleWidth(a.x1 - a.x0, ln.x1 - ln.x0);
    });
    return c.length ? minBy(c, function (ln) { return a.y0 - ln.y1; }) : null;
  }
  function nearestBelow(lines, a, minXo, maxGap) {
    minXo = minXo === undefined ? 0.5 : minXo;
    var c = lines.filter(function (ln) {
      return ln.page === a.page && ln.y0 >= a.y1 - 1 && (ln.y0 - a.y1) <= maxGap &&
        xOverlap(ln.x0, ln.x1, a.x0, a.x1) >= minXo && plausibleWidth(a.x1 - a.x0, ln.x1 - ln.x0);
    });
    return c.length ? minBy(c, function (ln) { return ln.y0 - a.y1; }) : null;
  }
  function stripPunct(t) { return t.replace(/^[,.:;*]+|[,.:;*]+$/g, ''); }
  function detectSelected(line, options, maxGap) {
    maxGap = maxGap === undefined ? 25 : maxGap;
    var marks = line.words.filter(function (w) { return w.text === CHECKMARK; });
    if (!marks.length) { return null; }
    var best = null;
    options.forEach(function (opt) {
      line.words.forEach(function (w) {
        if (w.text !== opt && stripPunct(w.text) !== opt) { return; }
        marks.forEach(function (ck) {
          var gap = ck.x0 - w.x1;
          if (gap < -2 || gap > maxGap) { return; }
          if (Math.abs(yc(ck) - yc(w)) > Math.max(w.y1 - w.y0, ck.y1 - ck.y0)) { return; }
          if (best === null || gap < best.gap) { best = { option: opt, word: w, mark: ck, gap: gap }; }
        });
      });
    });
    return best;
  }
  function pseudoLine(page, ws, sortKey) {
    var sorted = ws.slice().sort(sortKey || function (a, b) { return b.x0 - a.x0; });
    return { line_id: -1, page: page, x0: mn(ws.map(function (w) { return w.x0; })), y0: mn(ws.map(function (w) { return w.y0; })),
      x1: mx(ws.map(function (w) { return w.x1; })), y1: mx(ws.map(function (w) { return w.y1; })), words: sorted };
  }
  function result(spec, value, conf, page, type, bbox, anchor) {
    return { field_name: spec.field_name || spec.table_name, value: value, confidence: conf, page_number: page,
      section: spec.section, source: { type: type, raw_value: value, anchor_label: spec.anchor_text || '',
        bbox: bbox || [0, 0, 0, 0], anchor_bbox: anchor ? [anchor.x0, anchor.y0, anchor.x1, anchor.y1] : [0, 0, 0, 0] } };
  }
  function wbbox(ws) {
    if (!ws.length) { return [0, 0, 0, 0]; }
    return [mn(ws.map(function (w) { return w.x0; })), mn(ws.map(function (w) { return w.y0; })),
      mx(ws.map(function (w) { return w.x1; })), mx(ws.map(function (w) { return w.y1; }))];
  }

  function anchorsExact(lines, pages, text) {
    var t = normalize(text);
    return lines.filter(function (ln) { return pages.indexOf(ln.page) >= 0 && normalize(lineText(ln)) === t; })
      .sort(function (a, b) { return a.page - b.page || a.y0 - b.y0; });
  }
  function anchorsContains(lines, pages, text) {
    var t = normalize(text);
    return lines.filter(function (ln) { return pages.indexOf(ln.page) >= 0 && normalize(lineText(ln)).indexOf(t) >= 0; })
      .sort(function (a, b) { return a.page - b.page || a.y0 - b.y0; });
  }
  function columnBounds(w, column, split) {
    var s = (split !== null && split !== undefined) ? split : w / 2;
    if (column === 'right') { return [s, w + 1000]; }
    if (column === 'left') { return [-1000, s]; }
    return [-1000, w + 1000];
  }
  function headerSpan(header, key) {
    var ws = header.words;
    for (var i = 0; i < ws.length; i++) {
      var acc = '';
      for (var j = i; j < ws.length; j++) {
        acc += normalize(ws[j].text);
        if (acc === key) {
          var part = ws.slice(i, j + 1);
          return [mn(part.map(function (w) { return w.x0; })), mx(part.map(function (w) { return w.x1; }))];
        }
        if (key.indexOf(acc) !== 0) { break; }
      }
    }
    return [header.x0, header.x1];
  }

  /* ----------------------------------------------------------- patterns */
  function rightAlignedAbove(lines, a, maxGap) {
    var c = lines.filter(function (ln) {
      return ln.page === a.page && ln.y1 <= a.y0 + 1 && a.y0 - ln.y1 <= maxGap &&
        a.x0 - 3 <= ln.x0 && ln.x0 <= a.x1 && ln.x1 > a.x1 && ln.x1 - ln.x0 <= 200 &&
        !ln.words.some(function (w) { return w.text === CHECKMARK; });
    });
    return c.length ? minBy(c, function (ln) { return a.y0 - ln.y1; }) : null;
  }
  function grid(spec, lines) {
    var anchors = anchorsExact(lines, spec.pages, spec.anchor_text);
    if (!anchors.length || spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var aligned = false;
    var v;
    if (spec.direction === 'below') { v = nearestBelow(lines, a, 0.5, spec.grid_gap); }
    else {
      v = nearestAbove(lines, a, 0.5, spec.grid_gap);
      if (!v) { v = rightAlignedAbove(lines, a, spec.grid_gap); aligned = !!v; }
    }
    if (!v || !v.words.length) { return null; }
    var xo = xOverlap(v.x0, v.x1, a.x0, a.x1);
    if (aligned) { xo = Math.max(xo, 0.75); }
    var gap = spec.direction === 'below' ? v.y0 - a.y1 : a.y0 - v.y1;
    var conf = gridConfidence(xo, gap, 1);
    var text = lineText(v).trim();
    if (!text) { return null; }
    var r = result(spec, text, conf, v.page, 'text_grid', [v.x0, v.y0, v.x1, v.y1], a);
    return conf >= MIN_CONFIDENCE_TO_EMIT ? r : null;
  }
  function selectionResult(spec, a, sel, page) {
    var conf = choiceConfidence(sel.gap, 0);
    var r = result(spec, sel.option, conf, page, 'checkbox', [sel.word.x0, sel.word.y0, sel.word.x1, sel.word.y1], a);
    r.source.raw_value = sel.word.text + ' + checkmark';
    return r;
  }
  function choiceAboveLabel(spec, lines) {
    var anchors = anchorsExact(lines, spec.pages, spec.anchor_text);
    if (spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var margin = 45;
    var cand = lines.filter(function (ln) { return ln.page === a.page && ln.y1 <= a.y0 + 2 && (a.y0 - ln.y1) <= 13; });
    var band = [];
    cand.forEach(function (ln) { ln.words.forEach(function (w) { if (a.x0 - margin <= xc(w) && xc(w) <= a.x1 + margin) { band.push(w); } }); });
    if (!band.length) { return null; }
    var sel = detectSelected(pseudoLine(a.page, band), spec.options);
    if (!sel) { return null; }
    var r = selectionResult(spec, a, sel, a.page);
    return r.confidence >= MIN_CONFIDENCE_TO_EMIT ? r : null;
  }
  function choiceInline(spec, lines, widths) {
    var anchors = anchorsContains(lines, spec.pages, spec.anchor_text);
    if (!anchors.length) { return null; }
    var best = null;
    anchors.forEach(function (a) {
      var b = columnBounds(widths[a.page] || 648, spec.column, spec.x_split);
      var band = [];
      lines.forEach(function (ln) {
        if (ln.page === a.page && Math.abs(yc(ln) - yc(a)) <= 14) {
          ln.words.forEach(function (w) { if (b[0] <= xc(w) && xc(w) <= b[1]) { band.push(w); } });
        }
      });
      if (!band.length) { return; }
      var sel = detectSelected(pseudoLine(a.page, band), spec.options);
      if (!sel) { return; }
      var c = selectionResult(spec, a, sel, a.page);
      if (best === null || c.confidence > best.confidence) { best = c; }
    });
    return best && best.confidence >= MIN_CONFIDENCE_TO_EMIT ? best : null;
  }
  function isLabelWord(text, key) {
    var t = normalize(text);
    return !!t && !/\d/.test(t) && key.indexOf(t) >= 0;
  }
  function row(spec, lines) {
    var anchors = anchorsContains(lines, spec.pages, spec.anchor_text).filter(function (ln) { return ln.words.length <= 5; });
    if (spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var hk = normalize(spec.column_header || '');
    var headers = lines.filter(function (ln) { return ln.page === a.page && ln.y1 <= a.y0 + 1 && hk && normalize(lineText(ln)).indexOf(hk) >= 0; });
    if (!headers.length) { return null; }
    var h = maxBy(headers, function (ln) { return ln.y1; });
    var sp = headerSpan(h, hk);
    var lo = sp[0] - 6, hi = sp[1] + 6;
    var band = Math.max(a.y1 - a.y0, 6);
    var ak = normalize(spec.anchor_text);
    var ws = [];
    lines.forEach(function (ln) {
      if (ln.page !== a.page) { return; }
      ln.words.forEach(function (w) {
        if (lo <= xc(w) && xc(w) <= hi && Math.abs(yc(w) - yc(a)) <= band && !isLabelWord(w.text, ak)) { ws.push(w); }
      });
    });
    if (!ws.length) { return null; }
    ws.sort(function (p, q) { return q.x1 - p.x1; });
    var text = ws.map(function (w) { return w.text; }).join(' ').trim();
    if (!text) { return null; }
    var bb = wbbox(ws);
    var conf = gridConfidence(xOverlap(bb[0], bb[2], sp[0], sp[1]), Math.abs((bb[1] + bb[3]) / 2 - yc(a)), 1);
    var r = result(spec, text, conf, a.page, 'table_row', bb, a);
    return conf >= MIN_CONFIDENCE_TO_EMIT ? r : null;
  }
  function columnAnchors(spec, lines, widths) {
    var anchors = anchorsContains(lines, spec.pages, spec.anchor_text);
    if (spec.column === null || spec.column === undefined) { return anchors; }
    return anchors.filter(function (ln) {
      var b = columnBounds(widths[ln.page] || 648, spec.column, spec.x_split);
      return b[0] <= xc(ln) && xc(ln) <= b[1];
    });
  }
  function inline(spec, lines, widths) {
    var anchors = columnAnchors(spec, lines, widths);
    if (spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var band = Math.max(a.y1 - a.y0, 8);
    var own = a.words;
    var cands = [];
    lines.forEach(function (ln) {
      if (ln.page !== a.page) { return; }
      ln.words.forEach(function (w) {
        if (own.indexOf(w) < 0 && Math.abs(yc(w) - yc(a)) <= band && w.x1 <= a.x0 + 1 && a.x0 - w.x1 <= spec.max_gap) { cands.push(w); }
      });
    });
    cands.sort(function (p, q) { return q.x1 - p.x1; });
    var picked = [];
    var edge = a.x0;
    for (var i = 0; i < cands.length; i++) {
      var w = cands[i];
      var gap = edge - w.x1;
      if (picked.length && gap > 12) { break; }
      if (!picked.length && gap > spec.max_gap) { break; }
      picked.push(w);
      edge = w.x0;
    }
    picked = picked.filter(function (w) { return ['_', '.', ','].indexOf(w.text.trim()) < 0; });
    if (!picked.length) { return null; }
    var text = picked.map(function (w) { return w.text; }).join(' ').trim();
    var g = a.x0 - picked[0].x1;
    var conf = Math.round(Math.max(0.6, 0.99 - g / 1000) * 1000) / 1000;
    return result(spec, text, conf, a.page, 'inline', wbbox(picked), a);
  }
  var DATE_RE = /^\d{1,2}\/\d{1,2}\/\d{2,4}$/;
  function signed(spec, lines, widths, extras) {
    var anchors = anchorsContains(lines, spec.pages, spec.anchor_text);
    if (spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var key = normalize(spec.column_header || '');
    var slots = lines.filter(function (ln) { return ln.page === a.page && ln.y0 > a.y1 && key && normalize(lineText(ln)).indexOf(key) >= 0; })
      .sort(function (p, q) { return p.y0 - q.y0; });
    if (!slots.length) { return null; }
    var slot = slots[0];
    var sp = headerSpan(slot, key);
    var dates = [];
    lines.forEach(function (ln) {
      if (ln.page !== a.page) { return; }
      ln.words.forEach(function (w) {
        if (DATE_RE.test(w.text.trim()) && sp[0] - 30 <= xc(w) && xc(w) <= sp[1] + 30 && slot.y0 - 20 <= yc(w) && yc(w) <= slot.y1 + 2) { dates.push(w); }
      });
    });
    if (dates.length) {
      var d = minBy(dates, function (w) { return Math.abs(yc(w) - yc(slot)); });
      return result(spec, '\u05db\u05df', 0.9, a.page, 'signature', wbbox([d]), a);
    }
    var pics = ((extras || {}).images || []).filter(function (im) {
      return im.page === a.page && im.x0 < sp[1] + 30 && im.x1 > sp[0] - 30 && im.bottom > slot.y0 - 40 && im.top < slot.y1 &&
        (im.x1 - im.x0) >= 8 && (im.bottom - im.top) >= 5;
    });
    if (pics.length) { return result(spec, '\u05db\u05df', 0.85, a.page, 'signature_image', null, a); }
    return result(spec, '\u05dc\u05d0', 0.8, a.page, 'signature', null, a);
  }
  function checkbox(spec, lines, widths) {
    var anchors = columnAnchors(spec, lines, widths);
    if (spec.occurrence >= anchors.length) { return null; }
    var a = anchors[spec.occurrence];
    var band = Math.max(a.y1 - a.y0, 8);
    var marks = [];
    lines.forEach(function (ln) {
      if (ln.page !== a.page) { return; }
      ln.words.forEach(function (w) {
        if (w.text === CHECKMARK && Math.abs(yc(w) - yc(a)) <= band && a.x0 - 30 <= xc(w) && xc(w) <= a.x1 + 30) { marks.push(w); }
      });
    });
    if (marks.length) { return result(spec, '\u05db\u05df', 0.9, a.page, 'checkbox', wbbox(marks), a); }
    return result(spec, '\u05dc\u05d0', 0.85, a.page, 'checkbox', null, a);
  }
  function field(spec, lines, widths, extras) {
    switch (spec.pattern) {
      case 'grid': return grid(spec, lines);
      case 'choice': return spec.layout === 'above_label' ? choiceAboveLabel(spec, lines) : choiceInline(spec, lines, widths);
      case 'row': return row(spec, lines);
      case 'inline': return inline(spec, lines, widths);
      case 'signed': return signed(spec, lines, widths, extras);
      case 'checkbox': return checkbox(spec, lines, widths);
      default: return null;
    }
  }

  /* ------------------------------------------------------------- tables */
  var ROW_NO = /^\.\d+$|^\d+\.$/;
  var BARE_GENDER = ['\u05d6', '\u05e0', '\u05d6 \u05e0', '\u05e0 \u05d6'];
  function rowCluster(words, tol) {
    tol = tol || 4;
    var rows = [];
    words.slice().sort(function (a, b) { return a.y0 - b.y0; }).forEach(function (w) {
      for (var i = 0; i < rows.length; i++) {
        if (Math.abs(yc(rows[i][0]) - yc(w)) <= tol) { rows[i].push(w); return; }
      }
      rows.push([w]);
    });
    rows.sort(function (a, b) { return mn(a.map(function (w) { return w.y0; })) - mn(b.map(function (w) { return w.y0; })); });
    return rows;
  }
  function table(spec, lines) {
    var page = spec.page;
    var heads = null;
    var pageLines = null;
    var pages = (spec.search_pages && spec.search_pages.length) ? spec.search_pages : [spec.page];
    for (var i = 0; i < pages.length; i++) {
      var pl = lines.filter(function (ln) { return ln.page === pages[i]; });
      var hs = [];
      var ok = spec.header_texts.every(function (h) {
        var t = h.replace(/ /g, '');
        var m = pl.filter(function (ln) { return lineText(ln).replace(/ /g, '') === t; })[0];
        if (!m) { return false; }
        hs.push(m);
        return true;
      });
      if (ok) { heads = hs; page = pages[i]; pageLines = pl; break; }
    }
    if (!heads) { return []; }
    var hy1 = mx(heads.map(function (ln) { return ln.y1; }));
    var centers = heads.map(xc);
    var bounds = centers.map(function (c, i) {
      return [i + 1 < centers.length ? (centers[i + 1] + c) / 2 : -10000, i > 0 ? (centers[i - 1] + c) / 2 : 10000];
    });
    var body = [];
    pageLines.forEach(function (ln) { if (ln.y0 > hy1 + 1) { ln.words.forEach(function (w) { body.push(w); }); } });
    if (!body.length) { return []; }
    var hn = spec.header_texts.map(function (h) { return h.replace(/ /g, ''); });
    var rows = rowCluster(body).slice(0, spec.max_rows);
    var out = [];
    rows.forEach(function (rw, ri) {
      var cells = {};
      var order = [];
      spec.column_names.forEach(function (col, ci) {
        var b = bounds[ci];
        var cw = rw.filter(function (w) { return b[0] <= xc(w) && xc(w) <= b[1]; }).sort(function (p, q) { return q.x0 - p.x0; });
        var kept = cw.filter(function (w) { return hn.indexOf(w.text.replace(/ /g, '')) < 0; });
        var text = kept.map(function (w) { return w.text; }).join(' ').trim();
        if (!text) { return; }
        var n = text.replace(/ /g, '');
        if (hn.some(function (h) { return n === h || h.indexOf(n) >= 0; })) { return; }
        if (ROW_NO.test(text)) { return; }
        if (BARE_GENDER.indexOf(text) >= 0) { return; }
        cells[col] = text;
        order.push(col);
      });
      if (!order.length) { return; }
      var conf = tableConfidence(order.length / spec.column_names.length);
      order.forEach(function (col) {
        var r = result({ field_name: spec.table_name + ' - \u05e9\u05d5\u05e8\u05d4 ' + (ri + 1) + ' - ' + col, section: spec.section },
          cells[col], conf, page, 'table_cell', null, null);
        r.source.anchor_label = spec.table_name + '/' + col;
        out.push(r);
      });
    });
    return out;
  }
  function textOf(ws) {
    var rows = [];
    ws.slice().sort(function (a, b) { return yc(a) - yc(b); }).forEach(function (w) {
      var last = rows[rows.length - 1];
      if (last && Math.abs(yc(last[last.length - 1]) - yc(w)) <= 4) { last.push(w); } else { rows.push([w]); }
    });
    return rows.map(function (r) {
      return r.slice().sort(function (a, b) { return b.x1 - a.x1; }).map(function (w) { return w.text; }).join(' ');
    }).join(' ').trim();
  }
  function findings(spec, lines) {
    var anchors = anchorsContains(lines, spec.pages, spec.anchor_text);
    if (!anchors.length) { return []; }
    var a = anchors[0];
    var page = a.page;
    var pl = lines.filter(function (ln) { return ln.page === page; });
    var hk = normalize(spec.column_header);
    var headers = pl.filter(function (ln) { return ln.y1 <= a.y0 + 1 && normalize(lineText(ln)).indexOf(hk) >= 0; });
    if (!headers.length) { return []; }
    var h = maxBy(headers, function (ln) { return ln.y1; });
    var sp = headerSpan(h, hk);
    var lo = sp[0] - 6, hi = sp[1] + 6;
    var col = [];
    pl.forEach(function (ln) { ln.words.forEach(function (w) { if (lo <= xc(w) && xc(w) <= hi) { col.push(w); } }); });
    var sub = col.filter(function (w) { return w.y0 >= h.y1 - 1 && yc(w) <= a.y0 + 40; });
    var dk = normalize(spec.details_header);
    var det = sub.filter(function (w) { return normalize(w.text) === dk; });
    if (!det.length) { return []; }
    var nk = normalize(spec.number_header);
    var dmax = mx(det.map(function (w) { return w.x1; }));
    var numH = sub.filter(function (w) {
      var t = normalize(w.text);
      return (t === nk || t.indexOf('\u05de\u05e1') === 0) && w.x0 > dmax - 1;
    });
    var split = numH.length ? mn(numH.map(function (w) { return w.x0; })) - 3 : dmax + (sp[1] - dmax) / 2;
    var top = mx(det.concat(numH).map(function (w) { return w.y1; }));
    var ek = normalize(spec.end_text);
    var ends = pl.filter(function (ln) { return ln.y0 > top && normalize(lineText(ln)).indexOf(ek) === 0; }).map(function (ln) { return ln.y0; });
    var bottom = ends.length ? mn(ends) : Infinity;
    var body = col.filter(function (w) { return top < w.y0 && w.y1 <= bottom + 0.5; });
    var nums = body.filter(function (w) { return xc(w) >= split; });
    var dets = body.filter(function (w) { return xc(w) < split; });
    var clusters = [];
    nums.slice().sort(function (p, q) { return yc(p) - yc(q); }).forEach(function (w) {
      var last = clusters[clusters.length - 1];
      if (last && Math.abs(yc(last[last.length - 1]) - yc(w)) <= 4) { last.push(w); } else { clusters.push([w]); }
    });
    var entries = clusters.map(function (r) { return { y: mn(r.map(function (w) { return w.y0; })), num: r, det: [] }; });
    if (!entries.length && dets.length) { entries = [{ y: -Infinity, num: [], det: [] }]; }
    dets.forEach(function (w) {
      var idx = 0;
      entries.forEach(function (e, i) { if (e.y - 4 <= yc(w)) { idx = i; } });
      entries[idx].det.push(w);
    });
    var out = [];
    var prefix = spec.table_name + ' - ' + spec.candidate_label;
    entries.slice(0, spec.max_rows).forEach(function (e, i) {
      var cells = [];
      var nt = textOf(e.num);
      var dt = textOf(e.det);
      if (nt) { cells.push(['\u05de\u05e1\x27 \u05e9\u05d0\u05dc\u05d4', nt, e.num]); }
      if (dt) { cells.push(['\u05e4\u05e8\u05d8\u05d9\u05dd', dt, e.det]); }
      if (!cells.length) { return; }
      var conf = tableConfidence(cells.length / 2);
      cells.forEach(function (c) {
        var r = result({ field_name: prefix + ' - \u05e9\u05d5\u05e8\u05d4 ' + (i + 1) + ' - ' + c[0], section: spec.section },
          c[1], conf, page, 'findings_table', wbbox(c[2]), a);
        r.source.anchor_label = spec.anchor_text + '/' + spec.column_header + '/' + c[0];
        out.push(r);
      });
    });
    return out;
  }
  function rowsTable(spec, lines) {
    var pl = lines.filter(function (ln) { return ln.page === spec.page; });
    var tk = normalize(spec.title_text);
    var titles = pl.filter(function (ln) { return normalize(lineText(ln)).indexOf(tk) >= 0; });
    if (!titles.length) { return []; }
    var title = minBy(titles, function (ln) { return ln.y0; });
    var ek = normalize(spec.end_text);
    var ends = pl.filter(function (ln) { return ln.y0 > title.y1 && normalize(lineText(ln)).indexOf(ek) >= 0; }).map(function (ln) { return ln.y0; });
    var bottom = ends.length ? mn(ends) : Infinity;
    var keys = {};
    spec.labels.forEach(function (t) { keys[normalize(t)] = t; });
    var fk = normalize(spec.first_label);
    var starts = pl.filter(function (ln) { return title.y1 < ln.y0 && ln.y0 < bottom && normalize(lineText(ln)) === fk; })
      .sort(function (p, q) { return p.y0 - q.y0; });
    var out = [];
    var top = title.y1;
    starts.forEach(function (start, si) {
      var rowNo = si + 1;
      var labels = pl.filter(function (ln) { return Math.abs(yc(ln) - yc(start)) <= 4 && keys[normalize(lineText(ln))] !== undefined; })
        .sort(function (p, q) { return xc(q) - xc(p); });
      var centers = labels.map(xc);
      var names = labels.map(function (ln) { return keys[normalize(lineText(ln))]; });
      var band = [];
      pl.forEach(function (ln) { ln.words.forEach(function (w) { if (w.y0 >= top - 1 && yc(w) < start.y0 + 1 && !ROW_NO.test(w.text.trim())) { band.push(w); } }); });
      var cols = {};
      names.forEach(function (n) { cols[n] = []; });
      band.forEach(function (w) {
        for (var i = 0; i < centers.length; i++) {
          var c = centers[i];
          var lo = i + 1 < centers.length ? (centers[i + 1] + c) / 2 : -10000;
          var hi = i > 0 ? (centers[i - 1] + c) / 2 : 10000;
          if (lo <= xc(w) && xc(w) < hi) { cols[names[i]].push(w); break; }
        }
      });
      var cells = [];
      names.forEach(function (name) {
        var ws = cols[name];
        if (name === spec.choice_column) {
          if (!ws.length) { return; }
          var sel = detectSelected(pseudoLine(spec.page, ws), spec.choice_options);
          if (sel) { cells.push([name, sel.option, [sel.mark]]); }
          return;
        }
        ws = ws.filter(function (w) { return w.text !== CHECKMARK; });
        var sorted = ws.slice().sort(function (p, q) { return Math.round(yc(p)) - Math.round(yc(q)) || q.x1 - p.x1; });
        var text = sorted.map(function (w) { return w.text; }).join(' ').trim();
        if (text) { cells.push([name, text, ws]); }
      });
      top = labels.length ? mx(labels.map(function (ln) { return ln.y1; })) : start.y1;
      if (!cells.some(function (c) { return c[0] !== spec.choice_column; })) { return; }
      var conf = tableConfidence(cells.length / Math.max(names.length, 1));
      cells.forEach(function (c) {
        var r = result({ field_name: spec.table_name + ' - \u05e9\u05d5\u05e8\u05d4 ' + rowNo + ' - ' + c[0], section: spec.section },
          c[1], conf, spec.page, 'table_row_cell', c[2].length ? wbbox(c[2]) : null, start);
        r.source.anchor_label = spec.table_name + '/' + c[0];
        out.push(r);
      });
    });
    return out;
  }

  /* ------------------------------------------------------------- marks */
  function isBlack(c) {
    if (!c || !c.length) { return false; }
    if (c.length === 1) { return c[0] <= 0.25; }
    if (c.length === 3) { return mx(c) <= 0.25; }
    if (c.length === 4) { return c[3] >= 0.85 && mx(c.slice(0, 3)) <= 0.25; }
    return false;
  }
  function square(w, h, lo, hi) { return lo <= w && w <= hi && lo <= h && h <= hi && Math.abs(w - h) <= 1.5; }
  function vectorMarks(pages, firstId) {
    var out = [];
    var id = firstId;
    pages.forEach(function (p) {
      var dots = p.shapes.filter(function (s) { return s.fill && s.curve && isBlack(s.color) && square(s.x1 - s.x0, s.bottom - s.top, 5.5, 11); });
      if (!dots.length) { return; }
      var boxes = p.shapes.filter(function (s) { return s.stroke && s.rect && square(s.x1 - s.x0, s.bottom - s.top, 6, 12); });
      dots.forEach(function (d) {
        var box = boxes.filter(function (b) { return b.x0 < d.x1 && d.x0 < b.x1 && b.top < d.bottom && d.top < b.bottom; })[0] || d;
        var w = { text: CHECKMARK, raw: CHECKMARK, x0: box.x0, y0: box.top, x1: box.x1, y1: box.bottom, page: p.number, line_id: id };
        out.push({ line_id: id, page: p.number, x0: w.x0, y0: w.y0, x1: w.x1, y1: w.y1, words: [w] });
        id++;
      });
    });
    return out;
  }

  /* ------------------------------------------------------------- engine */
  var UNREADABLE = '\u05dc\u05d0 \u05e0\u05d9\u05ea\u05df \u05dc\u05e7\u05e8\u05d5\u05d0 \u05d0\u05ea \u05e4\u05e8\u05d8\u05d9 \u05d4\u05de\u05e1\u05de\u05da: \u05d0\u05d9\u05df \u05d1\u05d5 \u05d8\u05e7\u05e1\u05d8. \u05db\u05e0\u05e8\u05d0\u05d4 \u05d4\u05d5\u05d0 \u05e0\u05e1\u05e8\u05e7 \u05d0\u05d5 \u05d4\u05d5\u05d3\u05e4\u05e1 \u05dc-PDF (\u05dc\u05de\u05e9\u05dc \u05d1-Microsoft Print to PDF). \u05d9\u05e9 \u05dc\u05d4\u05e9\u05ea\u05de\u05e9 \u05d1\u05e7\u05d5\u05d1\u05e5 \u05d4\u05de\u05e7\u05d5\u05e8\u05d9 \u05de\u05de\u05e2\u05e8\u05db\u05ea \u05d4\u05d4\u05d7\u05ea\u05de\u05d5\u05ea.';
  function run(doc, layout, T) {
    var lines = [];
    doc.pages.forEach(function (p) { lines = lines.concat(layout.build(p, lines.length)); });
    var nWords = 0;
    lines.forEach(function (l) { nWords += l.words.length; });
    var warnings = [];
    if (!doc.pages.length || nWords / doc.pages.length < 3) {
      return { document_pages: doc.pages.length, fields: [], warnings: [UNREADABLE], lines: lines };
    }
    var widths = {};
    doc.pages.forEach(function (p) { widths[p.number] = p.width; });
    var maxId = lines.length ? mx(lines.map(function (l) { return l.line_id; })) : 0;
    lines = lines.concat(vectorMarks(doc.pages, maxId + 1));
    var images = [];
    doc.pages.forEach(function (p) { p.images.forEach(function (im) { images.push({ page: p.number, x0: im.x0, top: im.top, x1: im.x1, bottom: im.bottom }); }); });
    var extras = { images: images };
    var fields = [];
    T.fields.forEach(function (spec) {
      try {
        var r = field(spec, lines, widths, extras);
        if (r) { fields.push(r); }
      } catch (e) { warnings.push('\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05d7\u05d9\u05dc\u05d5\u05e5 \u05d4\u05e9\u05d3\u05d4: ' + spec.field_name); }
    });
    T.tables.forEach(function (spec) {
      try { fields = fields.concat(table(spec, lines)); } catch (e) { warnings.push('\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05d7\u05d9\u05dc\u05d5\u05e5 \u05d4\u05d8\u05d1\u05dc\u05d4: ' + spec.table_name); }
    });
    T.findings.forEach(function (spec) {
      try { fields = fields.concat(findings(spec, lines)); } catch (e) { warnings.push('\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05d7\u05d9\u05dc\u05d5\u05e5 \u05d4\u05d8\u05d1\u05dc\u05d4: ' + spec.table_name); }
    });
    T.beneficiaries.forEach(function (spec) {
      try { fields = fields.concat(rowsTable(spec, lines)); } catch (e) { warnings.push('\u05e9\u05d2\u05d9\u05d0\u05d4 \u05d1\u05d7\u05d9\u05dc\u05d5\u05e5 \u05d4\u05d8\u05d1\u05dc\u05d4: ' + spec.table_name); }
    });
    fields.forEach(function (f) { f.needs_review = f.confidence < 0.8; });
    return { document_pages: doc.pages.length, fields: fields, warnings: warnings, lines: lines };
  }

  return { run: run, normalize: normalize, _internal: { field: field, table: table, findings: findings, rowsTable: rowsTable, vectorMarks: vectorMarks } };
})();
if (typeof module !== 'undefined') { module.exports = ProposalExtract; }
