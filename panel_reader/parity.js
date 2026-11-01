/*
 * Parity test: the in-browser reader must give exactly what liranapp gives.
 *   python backend/tools/export_template.py panel_reader/template.json
 *   python backend/tools/dump_extraction.py <folder with PDFs>
 *   node panel_reader/parity.js <folder with PDFs>
 * Compares every extracted field, every panel value, review flag and warning.
 * The PDFs contain personal data: keep them outside the repository.
 */
const fs = require('fs');
const path = require('path');
const R = require('./pdfreader.js');
const L = require('./pdflayout.js');
const E = require('./extract.js');
const Mp = require('./mapping.js');
const T = JSON.parse(fs.readFileSync(path.join(__dirname, 'template.json')));
const dir = process.argv[2];
(async () => {
  let allOk = true;
  for (const name of fs.readdirSync(dir).filter((n) => n.toLowerCase().endsWith('.pdf')).sort()) {
    const doc = await R.read(fs.readFileSync(path.join(dir, name)).buffer.slice(0));
    const res = E.run(doc, L, T);
    const out = Mp.toInsurtix(res, name, T);
    const py = JSON.parse(fs.readFileSync(path.join(dir, name.replace(/\.pdf$/i, '.py.json'))));
    const key = (f) => f.section + ' | ' + f.field_name;
    const pf = new Map(py.r.fields.map((f) => [key(f), f]));
    const jf = new Map(res.fields.map((f) => [key(f), f]));
    const diffs = [];
    for (const [k, f] of pf) {
      const j = jf.get(k);
      if (!j) diffs.push('missing field ' + k);
      else if (j.value !== f.value) diffs.push('field value ' + k);
      else if (Math.abs(j.confidence - f.confidence) > 0.02) diffs.push('confidence ' + k);
    }
    for (const k of jf.keys()) if (!pf.has(k)) diffs.push('extra field ' + k);
    for (const k of new Set([...Object.keys(py.m.values), ...Object.keys(out.values)])) {
      const a = py.m.values[k], b = out.values[k];
      if (!a || !b) diffs.push((a ? 'missing' : 'extra') + ' value ' + k);
      else if (JSON.stringify(a.value) !== JSON.stringify(b.value)) diffs.push('value ' + k);
      else if (a.needs_review !== b.needs_review) diffs.push('review flag ' + k);
    }
    const pw = new Set(py.m.warnings), jw = new Set(out.warnings);
    if ([...pw].some((w) => !jw.has(w)) || [...jw].some((w) => !pw.has(w))) diffs.push('warnings differ');
    allOk = allOk && !diffs.length;
    console.log(name + ': ' + (diffs.length ? diffs.length + ' differences' : 'identical'));
    diffs.slice(0, 20).forEach((d) => console.log('   ' + d));
  }
  console.log(allOk ? 'ALL IDENTICAL' : 'DIFFERENCES FOUND');
  process.exit(allOk ? 0 : 1);
})();
