/*
 * Port of liranapp backend/app/insurtix/mapping.py (to_insurtix): maps the
 * extracted fields onto the panel field paths ("insurtix-proposal" v1).
 * Constants (sections, question lists, insurers...) come from TEMPLATE.mapping.
 */
var ProposalMapping = (function () {
  'use strict';

  function fixParens(s) {
    var o = s.indexOf('(');
    var c = s.indexOf(')');
    if (c !== -1 && (o === -1 || c < o)) {
      return s.replace(/[()]/g, function (x) { return x === '(' ? ')' : '('; });
    }
    return s;
  }
  function norm(s) { return fixParens(String(s === null || s === undefined ? '' : s).replace(/\s+/g, ' ').trim()); }
  var DATE_RE = /(^|[^\d])(\d{1,2})[./-](\d{1,2})[./-](\d{4}|\d{2})(?!\d)/;
  function year(y, past) {
    if (y.length === 4) { return parseInt(y, 10); }
    var now = new Date().getFullYear();
    var full = 2000 + parseInt(y, 10);
    return full <= now + (past ? 0 : 10) ? full : full - 100;
  }
  function date(s, past) {
    var m = DATE_RE.exec(s || '');
    if (!m) { return null; }
    var d = parseInt(m[2], 10), mo = parseInt(m[3], 10), y = year(m[4], past);
    var dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) { return null; }
    return (d < 10 ? '0' : '') + d + '/' + (mo < 10 ? '0' : '') + mo + '/' + y;
  }
  function digits(s) { return String(s || '').replace(/\D/g, ''); }
  function yesNo(s) {
    var v = norm(s).replace(/\*/g, '');
    if (v === '\u05db\u05df') { return true; }
    if (v === '\u05dc\u05d0') { return false; }
    return null;
  }
  function number(s) {
    var v = String(s || '').replace(/,/g, '').replace(/[^\d.]/g, '');
    if (!v || (v.match(/\./g) || []).length > 1) { return null; }
    var n = parseFloat(v);
    if (isNaN(n)) { return null; }
    return n;
  }
  function gender(s) {
    var v = norm(s);
    if (v.indexOf('\u05d6') === 0) { return 'male'; }
    if (v.indexOf('\u05e0') === 0) { return 'female'; }
    return null;
  }
  function r3(x) { return Math.round(x * 1000) / 1000; }

  function toInsurtix(result, sourceFile, T) {
    var M = T.mapping;
    var C1 = M.C1;
    var byKey = new Map();
    var byName = new Map();
    result.fields.forEach(function (f) {
      var k = f.section + '\u0000' + f.field_name;
      if (!byKey.has(k)) { byKey.set(k, f); }
      if (!byName.has(f.field_name)) { byName.set(f.field_name, []); }
      byName.get(f.field_name).push(f);
    });
    var values = {};
    var warnings = result.warnings.slice();
    function get(sec, name) { return byKey.get(sec + '\u0000' + name) || null; }
    function any(name) { var l = byName.get(name); return l && l.length ? l[0] : null; }
    function put(path, value, src, review, note) {
      if (value === null || value === undefined || value === '') {
        if (src) { warnings.push('\u05dc\u05d0 \u05e0\u05d9\u05ea\u05df \u05dc\u05e4\u05e8\u05e9 \u05d0\u05ea \u05d4\u05e2\u05e8\u05da \x27' + src.value + '\x27 \u05d1\u05e9\u05d3\u05d4 ' + src.section + ' / ' + src.field_name); }
        return;
      }
      var conf = src ? src.confidence : 1;
      var o = { value: value, confidence: r3(conf), needs_review: !!(review || conf < M.REVIEW_BELOW),
        from: src ? src.section + ' / ' + src.field_name : '' };
      if (note) { o.note = note; }
      values[path] = o;
    }
    var HEALTH = M.HEALTH;
    var INS = M.INSURED_YES_NO;

    /* person */
    var OWNER = M.OWNER, CAND1 = M.CAND1, CAND2 = M.CAND2;
    var hasC1 = M.PERSON_FIELDS.some(function (p) { return get(CAND1, p[0]); }) || get(CAND1, M.ID_FIELD[CAND1]);
    var sec = OWNER;
    if (hasC1) {
      var oid = get(OWNER, M.ID_FIELD[OWNER]);
      var cid = get(CAND1, M.ID_FIELD[CAND1]);
      var nameOf = function (s) {
        return [get(s, '\u05e9\u05dd \u05e4\u05e8\u05d8\u05d9'), get(s, '\u05e9\u05dd \u05de\u05e9\u05e4\u05d7\u05d4')]
          .filter(Boolean).map(function (f) { return norm(f.value); }).join(' ');
      };
      var on = nameOf(OWNER);
      var cn = nameOf(CAND1);
      var differs = (oid && cid && digits(oid.value) !== digits(cid.value)) || (on && cn && on !== cn);
      if (differs) {
        warnings.push('\u05d1\u05e2\u05dc \u05d4\u05e4\u05d5\u05dc\u05d9\u05e1\u05d4 \u05d1\u05d8\u05d5\u05e4\u05e1 \u05e9\u05d5\u05e0\u05d4 \u05de\u05d4\u05de\u05d5\u05e2\u05de\u05d3 \u05d4\u05e8\u05d0\u05e9\u05d5\u05df. \u05d4\u05e4\u05d0\u05e0\u05dc \u05ea\u05d5\u05de\u05da \u05d1\u05d0\u05d3\u05dd \u05d0\u05d7\u05d3, \u05d5\u05dc\u05db\u05df \u05e0\u05dc\u05e7\u05d7\u05d5 \u05d4\u05e4\u05e8\u05d8\u05d9\u05dd \u05e9\u05dc \u05d4\u05de\u05d5\u05e2\u05de\u05d3 \u05d4\u05e8\u05d0\u05e9\u05d5\u05df \u05dc\u05d1\u05d9\u05d8\u05d5\u05d7.');
      }
      sec = CAND1;
    }
    M.PERSON_FIELDS.forEach(function (p) {
      var name = p[0], key = p[1], kind = p[2];
      var f = get(sec, name) || (sec === CAND1 && key === 'email' ? get(OWNER, name) : null);
      if (!f) { return; }
      var v = norm(f.value);
      if (kind === 'date') { put('p.owner.' + key, date(v, key === 'birthDate'), f); }
      else if (kind === 'gender') { put('p.owner.' + key, gender(v), f); }
      else if (kind === 'email') { put('p.owner.' + key, v.replace(/ /g, ''), f); }
      else if (key === 'city' || key === 'street') { put('p.owner.' + key, v, f, true, '\u05d9\u05e9 \u05dc\u05d5\u05d5\u05d3\u05d0 \u05e9\u05d4\u05e9\u05dd \u05ea\u05d5\u05d0\u05dd \u05dc\u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05de\u05e2\u05e8\u05db\u05ea'); }
      else { put('p.owner.' + key, v, f); }
    });
    var f = get(sec, M.ID_FIELD[sec]);
    if (f) {
      var d = digits(f.value);
      put('p.owner.idNumber', d.length >= 5 && d.length <= 9 ? ('000000000' + d).slice(-9) : null, f);
    }
    f = get(sec, M.PHONE_FIELD[sec]) || (sec === CAND1 ? get(OWNER, M.PHONE_FIELD[OWNER]) : null);
    if (f) {
      var ph = digits(f.value);
      if (ph.indexOf('972') === 0) { ph = '0' + ph.slice(3); }
      put('p.owner.phone', /^05\d{8}$/.test(ph) ? ph : null, f);
    }

    /* offer */
    f = any('\u05de\u05d5\u05e2\u05d3 \u05ea\u05d7\u05d9\u05dc\u05ea \u05d4\u05d1\u05d9\u05d8\u05d5\u05d7');
    if (f) { put('p.dates.requestedStartDate', date(f.value), f); }
    f = any(M.SIGN_TABLE + ' - \u05e9\u05d5\u05e8\u05d4 1 - \u05ea\u05d0\u05e8\u05d9\u05da \u05d7\u05ea\u05d9\u05de\u05d4');
    if (f) {
      put('p.dates.signatureDate', date(f.value), f, true, '\u05e0\u05dc\u05e7\u05d7 \u05de\u05d4\u05e9\u05d5\u05e8\u05d4 \u05d4\u05e8\u05d0\u05e9\u05d5\u05e0\u05d4 \u05d1\u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05d4\u05d7\u05ea\u05de\u05d5\u05ea');
    } else {
      f = any('\u05ea\u05d0\u05e8\u05d9\u05da \u05d1\u05d4\u05e6\u05d4\u05e8\u05d5\u05ea');
      if (f && date(f.value)) {
        put('p.dates.signatureDate', date(f.value), f, true, '\u05d0\u05d9\u05df \u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05d7\u05ea\u05de\u05d5\u05ea; \u05e0\u05dc\u05e7\u05d7 \u05de\u05ea\u05d0\u05e8\u05d9\u05da \u05d4\u05d4\u05e6\u05d4\u05e8\u05d5\u05ea');
      }
    }
    f = any('\u05de\u05e1\u05e4\u05e8 \u05e1\u05d5\u05db\u05df');
    if (f) { put('p.agent', digits(f.value) || null, f); }
    f = any('\u05e7\u05d5\u05d3 \u05d4\u05e0\u05d7\u05d4');
    if (f) {
      if (f.value.indexOf('%') >= 0) {
        warnings.push('\u05d1\u05e9\u05d3\u05d4 \x27\u05e7\u05d5\u05d3 \u05d4\u05e0\u05d7\u05d4\x27 \u05e8\u05e9\u05d5\u05dd \u05d0\u05d7\u05d5\u05d6 (' + norm(f.value) + ') \u05d5\u05dc\u05d0 \u05e7\u05d5\u05d3 \u05d4\u05e0\u05d7\u05d4. \u05d9\u05e9 \u05dc\u05d1\u05d7\u05d5\u05e8 \u05d0\u05ea \u05d4\u05d4\u05e0\u05d7\u05d4 \u05d9\u05d3\u05e0\u05d9\u05ea.');
      } else { put('p.discount', digits(f.value) || null, f); }
    }
    f = any('\u05e1\u05db\u05d5\u05dd \u05d4\u05d1\u05d9\u05d8\u05d5\u05d7 \u05d4\u05de\u05d1\u05d5\u05e7\u05e9' + C1);
    if (f) { put('p.cover.insuranceSum', number(f.value), f); }
    f = any('\u05d2\u05d9\u05dc \u05ea\u05d5\u05dd \u05d1\u05d9\u05d8\u05d5\u05d7' + C1);
    if (f) { var n = number(f.value); put('p.cover.untilAge', n ? Math.trunc(n) : null, f); }

    /* insured */
    f = get(CAND1, '\u05e2\u05d9\u05e1\u05d5\u05e7 \u05d1\u05e4\u05d5\u05e2\u05dc');
    if (f) { put('p.answers.InsuredDetailes.Occupation', norm(f.value), f, true, '\u05d9\u05e9 \u05dc\u05d5\u05d5\u05d3\u05d0 \u05e9\u05d4\u05e2\u05d9\u05e1\u05d5\u05e7 \u05ea\u05d5\u05d0\u05dd \u05dc\u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05de\u05e2\u05e8\u05db\u05ea'); }
    f = get(CAND1, '\u05e7\u05d5\u05e4\u05ea \u05d7\u05d5\u05dc\u05d9\u05dd');
    if (f) {
      var hv = norm(f.value);
      put('p.answers.InsuredDetailes.HMO', M.HMO_NAMES.filter(function (h) { return hv.indexOf(h) >= 0; })[0] || null, f);
    }
    INS.forEach(function (kv) {
      var g = any(kv[0] + C1);
      if (g) { put('p.answers.InsuredDetailes.' + kv[1], yesNo(g.value), g); }
    });

    /* health */
    HEALTH.forEach(function (kv) {
      var g = any(kv[0] + C1);
      if (g) { put('p.answers.HealthDeclaration.' + kv[1], yesNo(g.value), g); }
    });
    f = any('\u05d2\u05d5\u05d1\u05d4' + C1);
    if (f) {
      var hgt = number(f.value);
      if (hgt && hgt > 3) { hgt = Math.round(hgt) / 100; }
      put('p.answers.HealthDeclaration.Height', hgt, f);
    }
    f = any('\u05de\u05e9\u05e7\u05dc' + C1);
    if (f) { put('p.answers.HealthDeclaration.Weight', number(f.value), f); }
    f = any('\u05e7\u05d9\u05d9\u05de\u05ea \u05e4\u05d5\u05dc\u05d9\u05e1\u05ea \u05e8\u05d9\u05e1\u05e7 \u05d0\u05d7\u05e8\u05ea' + C1);
    if (f) { put('p.answers.ComparisonQuestionnaire.OtherPolicy', yesNo(f.value), f); }

    /* payment */
    var pays = byName.get('\u05d0\u05de\u05e6\u05e2\u05d9 \u05ea\u05e9\u05dc\u05d5\u05dd') || [];
    pays.forEach(function (p) {
      if (norm(p.value).indexOf('\u05db\u05e8\u05d8\u05d9\u05e1') >= 0) {
        warnings.push('\u05d1\u05d8\u05d5\u05e4\u05e1 \u05e0\u05d1\u05d7\u05e8 \u05ea\u05e9\u05dc\u05d5\u05dd \u05d1\u05db\u05e8\u05d8\u05d9\u05e1 \u05d0\u05e9\u05e8\u05d0\u05d9. \u05d4\u05e4\u05d0\u05e0\u05dc \u05ea\u05d5\u05de\u05da \u05e8\u05e7 \u05d1\u05d4\u05d5\u05e8\u05d0\u05ea \u05e7\u05d1\u05e2, \u05d5\u05dc\u05db\u05df \u05e0\u05e9\u05d0\u05e8\u05d4 \u05d4\u05d5\u05e8\u05d0\u05ea \u05e7\u05d1\u05e2.');
      }
    });
    var debit = pays.filter(function (p) { return norm(p.value).indexOf('\u05d4\u05d5\u05e8\u05d0\u05ea') >= 0; })[0] || null;
    f = any('\u05d9\u05d5\u05dd \u05d2\u05d1\u05d9\u05d4 \u05de\u05d1\u05d5\u05e7\u05e9');
    if (f) { put('p.payment.collectionDay', digits(f.value) || null, f); }
    else if (debit) {
      put('p.payment.collectionDay', '2', debit, true, '\u05dc\u05d0 \u05e1\u05d5\u05de\u05df \u05d9\u05d5\u05dd \u05d2\u05d1\u05d9\u05d9\u05d4; \u05dc\u05e4\u05d9 \u05d4\u05d8\u05d5\u05e4\u05e1 \u05d1\u05e8\u05d9\u05e8\u05ea \u05d4\u05de\u05d7\u05d3\u05dc \u05dc\u05d4\u05d5\u05e8\u05d0\u05ea \u05e7\u05d1\u05e2 \u05d4\u05d9\u05d0 2 \u05dc\u05d7\u05d5\u05d3\u05e9');
    }
    var PAY = '\u05d4\u05e8\u05e9\u05d0\u05d4 \u05dc\u05d7\u05d9\u05d5\u05d1 \u05d7\u05e9\u05d1\u05d5\u05df';
    var BANK = '\u05d1\u05e0\u05e7', BRANCH = '\u05de\u05e1\u05e4\u05e8 \u05e1\u05e0\u05d9\u05e3', ACC = '\u05de\u05e1\u05e4\u05e8 \u05d7\u05e9\u05d1\u05d5\u05df';
    if (![BANK, BRANCH, ACC].some(function (x) { return get(PAY, x); }) && debit) {
      warnings.push('\u05e0\u05d1\u05d7\u05e8\u05d4 \u05d4\u05d5\u05e8\u05d0\u05ea \u05e7\u05d1\u05e2, \u05d0\u05d1\u05dc \u05e4\u05e8\u05d8\u05d9 \u05d7\u05e9\u05d1\u05d5\u05df \u05d4\u05d1\u05e0\u05e7 (\u05d1\u05e0\u05e7, \u05e1\u05e0\u05d9\u05e3, \u05de\u05e1\u05e4\u05e8 \u05d7\u05e9\u05d1\u05d5\u05df) \u05e8\u05d9\u05e7\u05d9\u05dd \u05d1\u05d8\u05d5\u05e4\u05e1. \u05d9\u05e9 \u05dc\u05d4\u05e9\u05dc\u05d9\u05dd \u05d0\u05d5\u05ea\u05dd \u05d9\u05d3\u05e0\u05d9\u05ea.');
    }
    f = get(PAY, BANK);
    if (f) {
      var bv = norm(f.value);
      put('p.payment.bank', /^\d{1,3}$/.test(bv) ? digits(bv) : bv, f, true, '\u05d9\u05e9 \u05dc\u05d5\u05d5\u05d3\u05d0 \u05e9\u05d4\u05d1\u05e0\u05e7 \u05ea\u05d5\u05d0\u05dd \u05dc\u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05de\u05e2\u05e8\u05db\u05ea');
    }
    f = get(PAY, BRANCH);
    if (f) { put('p.payment.branch', digits(f.value) || null, f, true); }
    f = get(PAY, ACC);
    if (f) { put('p.payment.accountNumber', digits(f.value) || null, f); }

    /* beneficiaries */
    var rows = new Map();
    var bre = new RegExp('^' + M.BENEF_TABLE.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + ' - \u05e9\u05d5\u05e8\u05d4 (\\d+) - (.+)$');
    byName.forEach(function (lst, name) {
      var m = bre.exec(name);
      if (m) {
        var k = parseInt(m[1], 10);
        if (!rows.has(k)) { rows.set(k, {}); }
        rows.get(k)[m[2]] = lst[0];
      }
    });
    var bens = [];
    var review = false;
    var bconf = 1;
    Array.from(rows.keys()).sort(function (a, b) { return a - b; }).forEach(function (k) {
      var r = rows.get(k);
      var val = function (c) { return r[c] ? norm(r[c].value) : ''; };
      if (!(val('\u05e9\u05dd \u05e4\u05e8\u05d8\u05d9') || val('\u05de\u05e1\u05e4\u05e8 \u05d6\u05d4\u05d5\u05ea'))) { return; }
      var rel = relation(val('\u05e7\u05e8\u05d1\u05d4'), M);
      var pct = number(val('% \u05d7\u05dc\u05d5\u05e7\u05d4'));
      var item = { firstName: val('\u05e9\u05dd \u05e4\u05e8\u05d8\u05d9'), lastName: val('\u05e9\u05dd \u05de\u05e9\u05e4\u05d7\u05d4'),
        idNumber: digits(val('\u05de\u05e1\u05e4\u05e8 \u05d6\u05d4\u05d5\u05ea')), birthDate: date(val('\u05ea\u05d0\u05e8\u05d9\u05da \u05dc\u05d9\u05d3\u05d4'), true) || '',
        gender: gender(val('\u05de\u05d2\u05d3\u05e8')) || 'male', relation: rel[0], percent: pct !== null ? pct : 0 };
      bens.push(item);
      review = review || rel[1] || !item.birthDate || pct === null;
      Object.keys(r).forEach(function (c) { bconf = Math.min(bconf, r[c].confidence); });
    });
    if (bens.length) {
      var total = bens.reduce(function (s, x) { return s + x.percent; }, 0);
      if (Math.abs(total - 100) > 0.01) {
        warnings.push('\u05e1\u05db\u05d5\u05dd \u05d0\u05d7\u05d5\u05d6\u05d9 \u05d4\u05de\u05d5\u05d8\u05d1\u05d9\u05dd \u05d1\u05d8\u05d5\u05e4\u05e1 \u05d4\u05d5\u05d0 ' + total + ' \u05d5\u05dc\u05d0 100');
        review = true;
      }
      values['p.beneficiaries'] = { value: bens, confidence: r3(bconf), needs_review: !!(review || bconf < M.REVIEW_BELOW), from: M.BENEF_TABLE };
    } else {
      var heirs = any('\u05d9\u05d5\u05e8\u05e9\u05d9\u05dd \u05d7\u05d5\u05e7\u05d9\u05d9\u05dd' + C1);
      if (heirs) {
        var ticked = yesNo(heirs.value) === true;
        values['p.beneficiaries'] = { value: [], confidence: r3(heirs.confidence), needs_review: heirs.confidence < M.REVIEW_BELOW,
          from: heirs.section + ' / ' + heirs.field_name,
          note: ticked ? '\u05d9\u05d5\u05e8\u05e9\u05d9\u05dd \u05d7\u05d5\u05e7\u05d9\u05d9\u05dd' : '\u05dc\u05d0 \u05e8\u05e9\u05d5\u05de\u05d9\u05dd \u05de\u05d5\u05d8\u05d1\u05d9\u05dd, \u05d5\u05dc\u05db\u05df \u05dc\u05e4\u05d9 \u05d4\u05d8\u05d5\u05e4\u05e1 \u05d9\u05d5\u05e8\u05e9\u05d9\u05dd \u05d7\u05d5\u05e7\u05d9\u05d9\u05dd' };
      }
    }

    /* more: smoking follow-up, existing insurance, lien, consents */
    var smoke = (values['p.answers.InsuredDetailes.IsSmoking'] || {}).value;
    f = any('\u05db\u05de\u05d5\u05ea \u05e1\u05d9\u05d2\u05e8\u05d9\u05d5\u05ea \u05dc\u05d9\u05d5\u05dd' + C1);
    if (f && smoke === true) { put('p.answers.SmokeHelthComp.NumberSig', number(f.value), f); }
    var reduce = any('\u05dc\u05d4\u05e7\u05d8\u05d9\u05df \u05e1\u05db\u05d5\u05dd \u05d1\u05d9\u05d8\u05d5\u05d7 \u05d1\u05e4\u05d5\u05dc\u05d9\u05e1\u05d4 \u05d4\u05e7\u05d9\u05d9\u05de\u05ea' + C1);
    var cancel = any('\u05dc\u05d1\u05d8\u05dc \u05d0\u05ea \u05d4\u05e4\u05d5\u05dc\u05d9\u05e1\u05d4 \u05d4\u05e7\u05d9\u05d9\u05de\u05ea' + C1);
    var ans = [reduce, cancel].filter(Boolean);
    if (ans.length) {
      var required = ans.some(function (x) { return yesNo(x.value) === true; });
      var src = ans.filter(function (x) { return yesNo(x.value) === true; })[0] || ans[0];
      put('p.answers.ComparisonQuestionnaire.IsCancellationRequired', required, src, false, '\u05d1\u05d9\u05d8\u05d5\u05dc \u05d0\u05d5 \u05d4\u05e7\u05d8\u05e0\u05d4 \u05e9\u05dc \u05d4\u05e4\u05d5\u05dc\u05d9\u05e1\u05d4 \u05d4\u05e7\u05d9\u05d9\u05de\u05ea');
      if (required) {
        var via = any('\u05d4\u05d2\u05e9\u05ea \u05d1\u05d9\u05d8\u05d5\u05dc \u05d1\u05d0\u05de\u05e6\u05e2\u05d5\u05ea \u05e9\u05dc\u05de\u05d4' + C1);
        var other = any('\u05d4\u05d2\u05e9\u05ea \u05d1\u05d9\u05d8\u05d5\u05dc \u05d1\u05d0\u05de\u05e6\u05e2\u05d5\u05ea \u05e1\u05d5\u05db\u05df' + C1) || any('\u05d4\u05d2\u05e9\u05ea \u05d1\u05d9\u05d8\u05d5\u05dc \u05d1\u05d0\u05d5\u05e4\u05df \u05e2\u05e6\u05de\u05d9' + C1);
        if (via) { put('p.answers.ComparisonQuestionnaire.IsCancellationRequiredByShlomo', true, via); }
        else if (other) { put('p.answers.ComparisonQuestionnaire.IsCancellationRequiredByShlomo', false, other); }
      }
    }
    f = any('\u05d7\u05d1\u05e8\u05ea \u05d1\u05d9\u05d8\u05d5\u05d7 \u05dc\u05d1\u05d9\u05d8\u05d5\u05dc' + C1);
    if (f) {
      var ins = insurer(f.value, M);
      put('p.answers.ComparisonQuestionnaire.InsuranceCompany', ins || norm(f.value), f, ins === null, ins ? '' : '\u05dc\u05d0 \u05e0\u05de\u05e6\u05d0\u05d4 \u05d1\u05e8\u05e9\u05d9\u05de\u05ea \u05d4\u05d7\u05d1\u05e8\u05d5\u05ea');
    }
    var bankNo = any('\u05de\u05e1\u05e4\u05e8 \u05d1\u05e0\u05e7' + C1);
    var fin = any('\u05e9\u05dd \u05d4\u05de\u05d5\u05d8\u05d1 \u05d4\u05d1\u05dc\u05ea\u05d9 \u05d7\u05d5\u05d6\u05e8 (\u05de\u05d5\u05e1\u05d3 \u05e4\u05d9\u05e0\u05e0\u05e1\u05d9)' + C1);
    if (bankNo && digits(bankNo.value)) {
      var bname = any('\u05e9\u05dd \u05d4\u05de\u05d5\u05d8\u05d1 \u05d4\u05d1\u05dc\u05ea\u05d9 \u05d7\u05d5\u05d6\u05e8 (\u05d1\u05e0\u05e7)' + C1);
      var bnote = bname ? '\u05d1\u05e0\u05e7: ' + norm(bname.value) : '';
      put('p.lien.type', 'bank', bankNo, false, bnote);
      put('p.lien.bank', digits(bankNo.value), bankNo, false, bnote);
      var br = any('\u05de\u05e1\u05e4\u05e8 \u05e1\u05e0\u05d9\u05e3' + C1);
      if (br) { put('p.lien.branch', digits(br.value) || null, br); }
    } else if (fin && norm(fin.value)) {
      put('p.lien.type', 'financial', fin, true);
      put('p.lien.company', norm(fin.value), fin, true, '\u05d9\u05e9 \u05dc\u05d1\u05d7\u05d5\u05e8 \u05d0\u05ea \u05d4\u05d7\u05d1\u05e8\u05d4 \u05de\u05d4\u05e8\u05e9\u05d9\u05de\u05d4');
    }
    [['\u05d7\u05ea\u05d5\u05dd: \u05e4\u05e0\u05d9\u05d4 \u05e9\u05d9\u05d5\u05d5\u05e7\u05d9\u05ea - \u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df', ['p.owner.marketingApproval']],
      ['\u05d7\u05ea\u05d5\u05dd: \u05d4\u05d2\u05e0\u05ea \u05d4\u05e4\u05e8\u05d8\u05d9\u05d5\u05ea - \u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df', ['p.answers.PolicyOwnerAgreements.PrivacyProtection', 'p.answers.InshuredAgreemntAndDeclarration.PrivacyProtection']],
      ['\u05d7\u05ea\u05d5\u05dd: \u05d5\u05d9\u05ea\u05d5\u05e8 \u05e2\u05dc \u05e1\u05d5\u05d3\u05d9\u05d5\u05ea \u05e8\u05e4\u05d5\u05d0\u05d9\u05ea - \u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df', ['p.answers.InshuredAgreemntAndDeclarration.MedicalConfidentiality']],
      ['\u05d7\u05ea\u05d5\u05dd: \u05d4\u05e6\u05d4\u05e8\u05ea \u05d4\u05de\u05d5\u05e2\u05de\u05d3\u05d9\u05dd \u05dc\u05d1\u05d9\u05d8\u05d5\u05d7 \u05d7\u05d9\u05d9\u05dd - \u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df', ['p.answers.InshuredAgreemntAndDeclarration.ConsentJoinInsuarnce']],
      ['\u05d7\u05ea\u05d5\u05dd: \u05d4\u05e6\u05d4\u05e8\u05ea \u05d4\u05e1\u05d5\u05db\u05df', ['p.answers.MethodSale.AgentStatementCopy', 'p.answers.MethodSale.AgentStatementMaterialInfo']]
    ].forEach(function (x) {
      var g = any(x[0]);
      if (g) { x[1].forEach(function (path) { put(path, yesNo(g.value), g, false, M.SIGNED_NOTE); }); }
    });
    f = any('\u05de\u05d1\u05e7\u05e9 \u05de\u05e1\u05de\u05db\u05d9\u05dd \u05d1\u05d3\u05d5\u05d0\u05e8 \u05d9\u05e9\u05e8\u05d0\u05dc');
    if (f) {
      var post = yesNo(f.value);
      put('p.owner.digitalMailing', post === null ? null : !post, f, false,
        post === false ? '\u05dc\u05d0 \u05e1\u05d5\u05de\u05df \u05de\u05e9\u05dc\u05d5\u05d7 \u05d1\u05d3\u05d5\u05d0\u05e8 \u05d9\u05e9\u05e8\u05d0\u05dc' : '\u05e1\u05d5\u05de\u05df \u05de\u05e9\u05dc\u05d5\u05d7 \u05d1\u05d3\u05d5\u05d0\u05e8 \u05d9\u05e9\u05e8\u05d0\u05dc');
    }

    /* findings */
    var fout = [];
    [[1, '\u05de\u05d5\u05e2\u05de\u05d3 \u05e8\u05d0\u05e9\u05d5\u05df'], [2, '\u05de\u05d5\u05e2\u05de\u05d3 \u05e9\u05e0\u05d9']].forEach(function (c) {
      var prefix = M.FINDINGS_TABLE + ' - ' + c[1] + ' - ';
      var frows = new Map();
      byName.forEach(function (lst, name) {
        if (name.indexOf(prefix) !== 0) { return; }
        var m = /^\u05e9\u05d5\u05e8\u05d4 (\d+) - (.+)$/.exec(name.slice(prefix.length));
        if (!m) { return; }
        var k = parseInt(m[1], 10);
        if (!frows.has(k)) { frows.set(k, { question: '', details: '', conf: 1 }); }
        var rw = frows.get(k);
        var key = m[2].indexOf('\u05de\u05e1') === 0 ? 'question' : 'details';
        rw[key] = norm(lst[0].value);
        rw.conf = Math.min(rw.conf, lst[0].confidence);
      });
      Array.from(frows.keys()).sort(function (a, b) { return a - b; }).forEach(function (k) {
        var rw = frows.get(k);
        var title = questionTitle(rw.question, M);
        fout.push({ candidate: c[0], question: rw.question, question_title: title, details: rw.details,
          confidence: r3(rw.conf), needs_review: rw.conf < M.REVIEW_BELOW });
        if (c[0] !== 1) { return; }
        var q = title || rw.question || '(\u05dc\u05dc\u05d0 \u05de\u05e1\u05e4\u05e8 \u05e9\u05d0\u05dc\u05d4)';
        warnings.push('\u05de\u05de\u05e6\u05d0 \u05d7\u05d9\u05d5\u05d1\u05d9 \u05e9\u05dc \u05d4\u05de\u05d5\u05e2\u05de\u05d3 \u05d4\u05e8\u05d0\u05e9\u05d5\u05df, \u05e9\u05d0\u05dc\u05d4 ' + q + ': ' + (rw.details || '(\u05dc\u05dc\u05d0 \u05e4\u05d9\u05e8\u05d5\u05d8)') + '. \u05d9\u05e9 \u05dc\u05d4\u05e9\u05dc\u05d9\u05dd \u05d0\u05ea \u05d4\u05e4\u05e8\u05d8\u05d9\u05dd \u05d1\u05e9\u05d0\u05dc\u05d5\u05df \u05d4\u05d4\u05e9\u05dc\u05de\u05d4 \u05d1\u05de\u05e2\u05e8\u05db\u05ea.');
        var g = title ? any(title + C1) : null;
        if (g && yesNo(g.value) === false) {
          warnings.push('\u05d1\u05e9\u05d0\u05dc\u05d4 ' + title + ' \u05e1\u05d5\u05de\u05df \x27\u05dc\u05d0\x27, \u05d0\u05d1\u05dc \u05d9\u05e9 \u05dc\u05d4 \u05e4\u05d9\u05e8\u05d5\u05d8 \u05d1\u05d8\u05d1\u05dc\u05ea \u05d4\u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d4\u05d7\u05d9\u05d5\u05d1\u05d9\u05d9\u05dd. \u05db\u05d3\u05d0\u05d9 \u05dc\u05d1\u05d3\u05d5\u05e7.');
        }
      });
    });
    var second = fout.filter(function (x) { return x.candidate === 2; });
    if (second.length) {
      warnings.push('\u05dc\u05de\u05d5\u05e2\u05de\u05d3 \u05d4\u05e9\u05e0\u05d9 \u05d9\u05e9 ' + second.length + ' \u05de\u05de\u05e6\u05d0\u05d9\u05dd \u05d7\u05d9\u05d5\u05d1\u05d9\u05d9\u05dd (\u05e9\u05d0\u05dc\u05d5\u05ea: ' +
        second.map(function (x) { return x.question || '?'; }).join(', ') + '). \u05d4\u05dd \u05dc\u05d0 \u05e0\u05d8\u05e2\u05e0\u05d5 \u05db\u05d9 \u05d4\u05e4\u05d0\u05e0\u05dc \u05ea\u05d5\u05de\u05da \u05d1\u05de\u05d1\u05d5\u05d8\u05d7 \u05d0\u05d7\u05d3.');
    }
    if (result.fields.some(function (x) { return x.section === CAND2 && norm(x.value); })) {
      warnings.push('\u05d1\u05d8\u05d5\u05e4\u05e1 \u05d9\u05e9 \u05de\u05d5\u05e2\u05de\u05d3 \u05e9\u05e0\u05d9 \u05dc\u05d1\u05d9\u05d8\u05d5\u05d7. \u05d4\u05e4\u05d0\u05e0\u05dc \u05ea\u05d5\u05de\u05da \u05d1\u05de\u05d1\u05d5\u05d8\u05d7 \u05d0\u05d7\u05d3, \u05d5\u05dc\u05db\u05df \u05d4\u05e4\u05e8\u05d8\u05d9\u05dd \u05e9\u05dc\u05d5 \u05dc\u05d0 \u05e0\u05d8\u05e2\u05e0\u05d5.');
    }
    var prop = any('\u05de\u05e1\u05e4\u05e8 \u05d4\u05e6\u05e2\u05d4');
    var unreadable = !result.fields.length;
    if (unreadable && !warnings.length) { warnings.push('\u05dc\u05d0 \u05e0\u05d9\u05ea\u05df \u05dc\u05e7\u05e8\u05d5\u05d0 \u05d0\u05ea \u05e4\u05e8\u05d8\u05d9 \u05d4\u05de\u05e1\u05de\u05da.'); }
    return { format: M.FORMAT, unreadable: unreadable, version: M.VERSION,
      source: { file: sourceFile || '', extracted_at: new Date().toISOString().slice(0, 19) + '+00:00',
        proposal_number: prop ? norm(prop.value) : '', pages: result.document_pages, reader: 'panel' },
      values: values, findings: fout, warnings: warnings };
  }
  function relation(s, M) {
    var v = norm(s);
    var flat = v.replace(/ /g, '');
    for (var i = 0; i < M.PANEL_RELATIONS.length; i++) {
      if (flat === M.PANEL_RELATIONS[i].replace(/ /g, '')) { return [M.PANEL_RELATIONS[i], false]; }
    }
    for (var j = 0; j < M.RELATIONS.length; j++) {
      var words = M.RELATIONS[j][0];
      if (words.some(function (w) { return v === w || v.indexOf(w + ' ') === 0; })) { return [M.RELATIONS[j][1], false]; }
    }
    return ['\u05d0\u05d7\u05e8', true];
  }
  function insurer(name, M) {
    var v = norm(name);
    if (!v) { return null; }
    for (var i = 0; i < M.INSURERS.length; i++) {
      var ins = M.INSURERS[i];
      if (v === ins || ins.indexOf(v + ' ') === 0 || v.indexOf(ins.split(' ')[0]) === 0) { return ins; }
    }
    return null;
  }
  function questionTitle(num, M) {
    num = norm(num);
    if (!num) { return ''; }
    var all = M.HEALTH.concat(M.INSURED_YES_NO);
    for (var i = 0; i < all.length; i++) { if (all[i][0].split(' ')[0] === num) { return all[i][0]; } }
    return '';
  }
  return { toInsurtix: toInsurtix, _t: { date: date, number: number, norm: norm } };
})();
if (typeof module !== 'undefined') { module.exports = ProposalMapping; }
