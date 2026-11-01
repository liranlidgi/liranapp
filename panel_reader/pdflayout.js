/*
 * Glyphs -> words -> lines, close to pdftotext -bbox-layout:
 * same-baseline glyphs closer than a word space form a word; words on one
 * baseline closer than LINE_GAP font sizes form a line. Hebrew words come
 * out in visual order and are reversed to logical order, the same way
 * liranapp fixes pdftotext output (fix_word).
 */
var PdfLayout = (function () {
  'use strict';
  var WORD_GAP = 0.15;
  var LINE_GAP = 1.0;

  function isHeb(ch) { return ch >= '\u0590' && ch <= '\u05ff'; }
  function stripNiqqud(s) {
    return s.normalize('NFD').replace(/[\u0591-\u05c7]/g, function (c) {
      return (c >= '\u05be' && c <= '\u05c6' && c !== '\u05bf' && c !== '\u05c1' && c !== '\u05c2' && c !== '\u05c4' && c !== '\u05c5') ? c : '';
    }).replace(/\p{Mn}/gu, '').normalize('NFC');
  }
  function mostlyHeb(s) {
    var letters = s.replace(/\s/g, '').split('');
    if (!letters.length) { return false; }
    var h = letters.filter(isHeb).length;
    return h >= Math.max(1, letters.length * 0.5);
  }
  function fixWord(raw) {
    var c = stripNiqqud(raw);
    if (mostlyHeb(c)) {
      var w = c.split('').reverse().join('');
      if (w.length > 1 && (w[0] === '\x27' || w[0] === '\u05f3') && isHeb(w[1])) { w = w.slice(1) + w[0]; }
      return w;
    }
    return c;
  }

  /* like pdftotext: punctuation at the edges of a Latin word becomes its
     own word (",(COPD)" -> ",(" "COPD" ")"); inner punctuation stays */
  function splitLatinEdges(words) {
    var out = [];
    words.forEach(function (w) {
      var gl = w.gl || [];
      var first = -1, last = -1;
      gl.forEach(function (g, i) { if (/[A-Za-z]/.test(g.u)) { if (first < 0) { first = i; } last = i; } });
      if (first < 0 || (first === 0 && last === gl.length - 1)) { out.push(w); return; }
      [[0, first], [first, last + 1], [last + 1, gl.length]].forEach(function (r) {
        if (r[1] <= r[0]) { return; }
        var part = gl.slice(r[0], r[1]);
        out.push({ raw: part.map(function (g) { return g.u; }).join(''),
          x0: Math.min.apply(null, part.map(function (g) { return g.x0; })), x1: Math.max.apply(null, part.map(function (g) { return g.x1; })),
          y0: Math.min.apply(null, part.map(function (g) { return g.y0; })), y1: Math.max.apply(null, part.map(function (g) { return g.y1; })),
          size: w.size, gl: part });
      });
    });
    return out;
  }

  function build(page, startId) {
    var gl = page.glyphs.filter(function (g) { return g.upright !== false; });
    gl.forEach(function (g) {
      g.y0 = g.base - g.asc * g.size;
      g.y1 = g.base - g.desc * g.size;
    });
    gl.sort(function (a, b) { return a.base - b.base || a.x0 - b.x0; });
    /* baseline groups */
    var groups = [];
    gl.forEach(function (g) {
      var cur = groups[groups.length - 1];
      if (cur && Math.abs(g.base - cur.base) <= 0.3 * Math.min(g.size, cur.size)) { cur.items.push(g); }
      else { groups.push({ base: g.base, size: g.size, items: [g] }); }
    });
    var lines = [];
    var id = startId || 0;
    groups.forEach(function (grp) {
      var items = grp.items.sort(function (a, b) { return a.x0 - b.x0; });
      /* split the baseline into words */
      var words = [];
      var cur = null;
      items.forEach(function (g) {
        var space = g.u.trim() === '';
        if (space) { if (cur) { cur.closed = true; } return; }
        var gap = cur ? g.x0 - cur.x1 : 0;
        if (!cur || cur.closed || gap > WORD_GAP * g.size || gap < -0.5 * g.size || Math.abs(g.size - cur.size) > 0.35 * g.size) {
          cur = { raw: '', x0: g.x0, x1: g.x1, y0: g.y0, y1: g.y1, size: g.size };
          words.push(cur);
        }
        cur.raw += g.u;
        cur.gl = (cur.gl || []).concat([g]);
        cur.x1 = Math.max(cur.x1, g.x1);
        cur.y0 = Math.min(cur.y0, g.y0);
        cur.y1 = Math.max(cur.y1, g.y1);
      });
      words = splitLatinEdges(words);
      /* words -> lines by horizontal gap */
      var line = null;
      words.forEach(function (w) {
        if (!line || w.x0 - line.x1 > LINE_GAP * Math.max(w.size, line.size)) {
          line = { words: [], x0: w.x0, x1: w.x1, size: w.size };
          lines.push(line);
        }
        line.words.push(w);
        line.x1 = Math.max(line.x1, w.x1);
      });
    });
    var out = [];
    lines.forEach(function (l) {
      var ws = l.words.map(function (w) {
        return { text: fixWord(w.raw), raw: w.raw, x0: w.x0, y0: w.y0, x1: w.x1, y1: w.y1, page: page.number, line_id: id };
      }).filter(function (w) { return w.text.trim() !== ''; });
      if (!ws.length) { return; }
      ws.sort(function (a, b) { return b.x0 - a.x0; });
      out.push({ line_id: id, page: page.number,
        x0: Math.min.apply(null, ws.map(function (w) { return w.x0; })),
        y0: Math.min.apply(null, ws.map(function (w) { return w.y0; })),
        x1: Math.max.apply(null, ws.map(function (w) { return w.x1; })),
        y1: Math.max.apply(null, ws.map(function (w) { return w.y1; })),
        words: ws });
      id++;
    });
    return out;
  }
  return { build: build, fixWord: fixWord, params: function (wg, lg) { WORD_GAP = wg; LINE_GAP = lg; } };
})();
if (typeof module !== 'undefined') { module.exports = PdfLayout; }
