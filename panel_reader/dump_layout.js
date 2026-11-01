/* Dump what the panel's JS reader sees in a PDF: fields, Insurtix values and
   the text lines with coordinates. Used by backend/app/formgen/build_profile.py
   and to check generated forms against the panel reader.
     node panel_reader/dump_layout.js form.pdf out.json */
const fs = require('fs');
const path = require('path');
const R = require('./pdfreader.js');
const L = require('./pdflayout.js');
const E = require('./extract.js');
const M = require('./mapping.js');
const T = JSON.parse(fs.readFileSync(path.join(__dirname, 'template.json')));
(async () => {
  const [inp, out] = process.argv.slice(2);
  const doc = await R.read(fs.readFileSync(inp).buffer.slice(0));
  const res = E.run(doc, L, T);
  const m = M.toInsurtix(res, path.basename(inp), T);
  const pages = doc.pages.map((p) => {
    const b = L.build(p, 0);
    const lines = b.lines || b;
    return { w: p.width, h: p.height, lines: lines.map((l) => ({
      t: l.words.map((w) => w.text).join(' '), x0: l.x0, y0: l.y0, x1: l.x1, y1: l.y1,
      words: l.words.map((w) => ({ t: w.text, x0: w.x0, y0: w.y0, x1: w.x1, y1: w.y1 })) })) };
  });
  fs.writeFileSync(out, JSON.stringify({ fields: res.fields, warnings: res.warnings, mapped: m, pages }));
})().catch((e) => { console.error(e); process.exit(1); });
