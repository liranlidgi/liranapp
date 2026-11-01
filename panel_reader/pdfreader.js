/*
 * Minimal PDF text-layer reader for the proposal forms.
 * Pure browser code: Web Crypto (AES / SHA) and DecompressionStream.
 * Output per page: glyphs with unicode and position (top-left origin,
 * points, like pdftotext -bbox), filled / stroked shapes and images.
 * Only the parts of PDF these forms use are implemented: classic and
 * stream xref (objects are found by scanning, so broken xref tables do not
 * matter), object streams, AES-256 (R5/R6) with the empty user password,
 * Flate + PNG predictors, ASCIIHex, ASCII85, Type1 / TrueType / Type0 fonts
 * with ToUnicode, Form XObjects, paths and images.
 */
var PdfReader = (function () {
  'use strict';

  /* ------------------------------------------------------------ objects */
  function Name(n) { this.n = n; }
  function Ref(num, gen) { this.num = num; this.gen = gen; }
  function PStr(bytes) { this.b = bytes; }
  function Kw(k) { this.k = k; }
  function Stream(dict, start, file) { this.dict = dict; this.start = start; this.file = file; this.data = null; }

  var WS = [];
  var DELIM = [];
  (function () {
    var i;
    for (i = 0; i < 256; i++) { WS[i] = false; DELIM[i] = false; }
    [0, 9, 10, 12, 13, 32].forEach(function (c) { WS[c] = true; });
    '()<>[]{}/%'.split('').forEach(function (c) { DELIM[c.charCodeAt(0)] = true; });
  })();

  function latin1(u8, s, e) {
    var out = '';
    var CH = 8192;
    for (var i = s; i < e; i += CH) {
      out += String.fromCharCode.apply(null, u8.subarray(i, Math.min(e, i + CH)));
    }
    return out;
  }

  /* ------------------------------------------------------------- lexer */
  function Lexer(b, pos) { this.b = b; this.p = pos || 0; this.n = b.length; }
  Lexer.prototype.skip = function () {
    var b = this.b;
    for (;;) {
      while (this.p < this.n && WS[b[this.p]]) { this.p++; }
      if (this.p < this.n && b[this.p] === 37) {          /* % comment */
        while (this.p < this.n && b[this.p] !== 10 && b[this.p] !== 13) { this.p++; }
        continue;
      }
      return;
    }
  };
  Lexer.prototype.token = function () {
    this.skip();
    var b = this.b;
    if (this.p >= this.n) { return null; }
    var c = b[this.p];
    if (c === 47) {                                        /* /Name */
      var s = ++this.p;
      while (this.p < this.n && !WS[b[this.p]] && !DELIM[b[this.p]]) { this.p++; }
      var raw = latin1(b, s, this.p);
      if (raw.indexOf('#') >= 0) {
        raw = raw.replace(/#([0-9A-Fa-f]{2})/g, function (m, h) { return String.fromCharCode(parseInt(h, 16)); });
      }
      return new Name(raw);
    }
    if (c === 40) { return this.litString(); }
    if (c === 60) {
      if (b[this.p + 1] === 60) { this.p += 2; return '<<'; }
      return this.hexString();
    }
    if (c === 62 && b[this.p + 1] === 62) { this.p += 2; return '>>'; }
    if (c === 91) { this.p++; return '['; }
    if (c === 93) { this.p++; return ']'; }
    if (c === 123) { this.p++; return '{'; }
    if (c === 125) { this.p++; return '}'; }
    if (c === 41 || c === 62) { this.p++; return this.token(); }
    var st = this.p;
    while (this.p < this.n && !WS[b[this.p]] && !DELIM[b[this.p]]) { this.p++; }
    var w = latin1(b, st, this.p);
    if (/^[+-]?(\d+\.?\d*|\.\d+)$/.test(w)) { return parseFloat(w); }
    if (/^[+-]?\d*\.\d*[eE]?/.test(w) && !isNaN(parseFloat(w))) { return parseFloat(w); }
    if (w === 'true') { return true; }
    if (w === 'false') { return false; }
    if (w === 'null') { return null; }
    return new Kw(w);
  };
  Lexer.prototype.litString = function () {
    var b = this.b;
    this.p++;
    var out = [];
    var depth = 1;
    while (this.p < this.n) {
      var c = b[this.p++];
      if (c === 92) {
        var d = b[this.p++];
        if (d === 110) { out.push(10); } else if (d === 114) { out.push(13); }
        else if (d === 116) { out.push(9); } else if (d === 98) { out.push(8); }
        else if (d === 102) { out.push(12); }
        else if (d === 13) { if (b[this.p] === 10) { this.p++; } }
        else if (d === 10) { /* line continuation */ }
        else if (d >= 48 && d <= 55) {
          var v = d - 48;
          for (var k = 0; k < 2 && b[this.p] >= 48 && b[this.p] <= 55; k++) { v = v * 8 + (b[this.p++] - 48); }
          out.push(v & 255);
        } else { out.push(d); }
        continue;
      }
      if (c === 40) { depth++; } else if (c === 41) { if (--depth === 0) { break; } }
      out.push(c);
    }
    return new PStr(Uint8Array.from(out));
  };
  Lexer.prototype.hexString = function () {
    var b = this.b;
    this.p++;
    var hex = [];
    while (this.p < this.n && b[this.p] !== 62) {
      var c = b[this.p++];
      if (!WS[c]) { hex.push(c); }
    }
    this.p++;
    if (hex.length % 2) { hex.push(48); }
    var out = new Uint8Array(hex.length / 2);
    for (var i = 0; i < out.length; i++) {
      out[i] = parseInt(String.fromCharCode(hex[2 * i], hex[2 * i + 1]), 16) || 0;
    }
    return new PStr(out);
  };

  /* parser on top of the lexer, with a small look-ahead for "n g R" */
  function Parser(lexer) { this.lx = lexer; this.buf = []; }
  Parser.prototype.peek = function (i) {
    while (this.buf.length <= (i || 0)) { this.buf.push(this.lx.token()); }
    return this.buf[i || 0];
  };
  Parser.prototype.next = function () { return this.buf.length ? this.buf.shift() : this.lx.token(); };
  Parser.prototype.object = function () {
    var t = this.next();
    if (t === '[') {
      var arr = [];
      while (this.peek() !== ']' && this.peek() !== null) { arr.push(this.object()); }
      this.next();
      return arr;
    }
    if (t === '<<') {
      var d = {};
      while (this.peek() !== '>>' && this.peek() !== null) {
        var k = this.next();
        if (!(k instanceof Name)) { continue; }
        d[k.n] = this.object();
      }
      this.next();
      return d;
    }
    if (typeof t === 'number' && Number.isInteger(t)) {
      var a = this.peek(0);
      var r = this.peek(1);
      if (typeof a === 'number' && Number.isInteger(a) && r instanceof Kw && r.k === 'R') {
        this.next();
        this.next();
        return new Ref(t, a);
      }
    }
    return t;
  };

  /* ------------------------------------------------------------ crypto */
  function concat(list) {
    var n = 0;
    list.forEach(function (a) { n += a.length; });
    var out = new Uint8Array(n);
    var o = 0;
    list.forEach(function (a) { out.set(a, o); o += a.length; });
    return out;
  }
  async function sha(alg, data) { return new Uint8Array(await crypto.subtle.digest(alg, data)); }
  async function aesKey(raw, use) { return crypto.subtle.importKey('raw', raw, { name: 'AES-CBC' }, false, use); }
  async function aesEncryptNoPad(raw, iv, data) {
    var k = await aesKey(raw, ['encrypt']);
    var out = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-CBC', iv: iv }, k, data));
    return out.subarray(0, data.length);
  }
  async function aesDecrypt(raw, iv, data, noPad) {
    var k = await aesKey(raw, ['encrypt', 'decrypt']);
    if (noPad) {
      /* Web Crypto always checks PKCS7 padding: append a block that
         decrypts to a full padding block, then drop it */
      var last = data.subarray(data.length - 16);
      var pad = new Uint8Array(16).fill(16);
      var extra = new Uint8Array(await crypto.subtle.encrypt({ name: 'AES-CBC', iv: last }, k, pad)).subarray(0, 16);
      data = concat([data, extra]);
    }
    return new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-CBC', iv: iv }, k, data));
  }
  async function hash2B(pw, salt, udata) {
    var k = await sha('SHA-256', concat([pw, salt, udata]));
    for (var round = 0; ; round++) {
      var one = concat([pw, k, udata]);
      var k1 = new Uint8Array(one.length * 64);
      for (var i = 0; i < 64; i++) { k1.set(one, i * one.length); }
      var e = await aesEncryptNoPad(k.subarray(0, 16), k.subarray(16, 32), k1);
      var sum = 0;
      for (var j = 0; j < 16; j++) { sum += e[j]; }
      var m = sum % 3;
      k = await sha(m === 0 ? 'SHA-256' : m === 1 ? 'SHA-384' : 'SHA-512', e);
      if (round >= 63 && e[e.length - 1] <= round - 31) { break; }
    }
    return k.subarray(0, 32);
  }

  /* ----------------------------------------------------------- filters */
  async function pump(u8, format) {
    var ds = new DecompressionStream(format);
    var w = ds.writable.getWriter();
    w.write(u8).catch(function () {});
    w.close().catch(function () {});
    var r = ds.readable.getReader();
    var out = [];
    try {
      for (;;) {
        var x = await r.read();
        if (x.done) { break; }
        out.push(x.value);
      }
    } catch (e) { /* truncated or trailing garbage: keep what was read */ }
    return concat(out);
  }
  async function inflate(u8) {
    var out = await pump(u8, 'deflate');
    if (!out.length && u8.length) { out = await pump(u8, 'deflate-raw'); }
    return out;
  }
  function pngPredict(data, parms) {
    var pred = parms.Predictor || 1;
    if (pred < 10) { return data; }
    var colors = parms.Colors || 1;
    var bpc = parms.BitsPerComponent || 8;
    var cols = parms.Columns || 1;
    var bpp = Math.max(1, Math.ceil(colors * bpc / 8));
    var row = Math.ceil(colors * bpc * cols / 8);
    var out = new Uint8Array(Math.floor(data.length / (row + 1)) * row);
    var prev = new Uint8Array(row);
    var o = 0;
    for (var p = 0; p + row < data.length + 1 && o < out.length; p += row + 1) {
      var t = data[p];
      var cur = data.subarray(p + 1, p + 1 + row);
      var line = new Uint8Array(row);
      for (var i = 0; i < row; i++) {
        var a = i >= bpp ? line[i - bpp] : 0;
        var up = prev[i];
        var c = i >= bpp ? prev[i - bpp] : 0;
        var x = cur[i] || 0;
        if (t === 1) { x += a; } else if (t === 2) { x += up; }
        else if (t === 3) { x += (a + up) >> 1; }
        else if (t === 4) {
          var pa = Math.abs(up - c);
          var pb = Math.abs(a - c);
          var pc = Math.abs(a + up - 2 * c);
          x += (pa <= pb && pa <= pc) ? a : (pb <= pc ? up : c);
        }
        line[i] = x & 255;
      }
      out.set(line, o);
      o += row;
      prev = line;
    }
    return out;
  }
  function asciiHex(u8) {
    var s = latin1(u8, 0, u8.length).replace(/[^0-9A-Fa-f]/g, '');
    if (s.length % 2) { s += '0'; }
    var out = new Uint8Array(s.length / 2);
    for (var i = 0; i < out.length; i++) { out[i] = parseInt(s.substr(2 * i, 2), 16); }
    return out;
  }
  function ascii85(u8) {
    var s = latin1(u8, 0, u8.length).replace(/\s/g, '');
    var end = s.indexOf('~>');
    if (end >= 0) { s = s.slice(0, end); }
    if (s.slice(0, 2) === '<~') { s = s.slice(2); }
    var out = [];
    var tup = [];
    for (var i = 0; i < s.length; i++) {
      var c = s.charCodeAt(i);
      if (c === 122 && !tup.length) { out.push(0, 0, 0, 0); continue; }
      tup.push(c - 33);
      if (tup.length === 5) {
        var v = (((tup[0] * 85 + tup[1]) * 85 + tup[2]) * 85 + tup[3]) * 85 + tup[4];
        out.push((v >>> 24) & 255, (v >>> 16) & 255, (v >>> 8) & 255, v & 255);
        tup = [];
      }
    }
    if (tup.length) {
      var n = tup.length;
      while (tup.length < 5) { tup.push(84); }
      var w = (((tup[0] * 85 + tup[1]) * 85 + tup[2]) * 85 + tup[3]) * 85 + tup[4];
      var bytes = [(w >>> 24) & 255, (w >>> 16) & 255, (w >>> 8) & 255, w & 255];
      for (var k = 0; k < n - 1; k++) { out.push(bytes[k]); }
    }
    return Uint8Array.from(out);
  }

  /* ---------------------------------------------------------- document */
  function Doc(bytes) {
    this.b = bytes;
    this.objs = {};       /* num -> {off, obj} or {stm, idx} */
    this.cache = {};
    this.key = null;
    this.trailer = null;
  }
  Doc.prototype.scan = function () {
    var s = latin1(this.b, 0, this.b.length);
    this.s = s;
    var re = /(\d+)\s+(\d+)\s+obj\b/g;
    var m;
    var self = this;
    while ((m = re.exec(s))) {
      var num = parseInt(m[1], 10);
      self.objs[num] = { off: m.index, body: m.index + m[0].length };
    }
    /* trailer: the last classic trailer, or the last xref stream */
    var trailers = [];
    var tr = /trailer\s*<</g;
    while ((m = tr.exec(s))) {
      var p = new Parser(new Lexer(this.b, m.index + 7));
      try { trailers.push({ off: m.index, d: p.object() }); } catch (e) { /* skip */ }
    }
    this.trailers = trailers;
  };
  Doc.prototype.rawObject = function (num) {
    var e = this.objs[num];
    if (!e) { return null; }
    if (e.val !== undefined) { return e.val; }
    if (e.stm !== undefined) { return null; }
    var lx = new Lexer(this.b, e.body);
    var p = new Parser(lx);
    var v = p.object();
    var nx = p.peek();
    if (nx instanceof Kw && nx.k === 'stream') {
      /* data starts after the EOL that follows the keyword */
      var st = lx.p;
      if (this.b[st] === 13) { st++; }
      if (this.b[st] === 10) { st++; }
      v = new Stream(v, st, this);
    }
    e.val = v;
    return v;
  };
  Doc.prototype.get = function (v) {
    var guard = 0;
    while (v instanceof Ref && guard++ < 32) { v = this.resolve(v.num); }
    return v;
  };
  Doc.prototype.resolve = function (num) {
    var e = this.objs[num];
    if (!e) { return null; }
    if (e.stm !== undefined) { return e.val; }
    return this.rawObject(num);
  };
  Doc.prototype.streamRaw = function (stm) {
    var len = this.get(stm.dict.Length);
    var b = this.b;
    var end;
    if (typeof len === 'number' && stm.start + len <= b.length) {
      var tail = latin1(b, stm.start + len, Math.min(b.length, stm.start + len + 20));
      if (/^\s*endstream/.test(tail)) { end = stm.start + len; }
    }
    if (end === undefined) {
      var i = this.s.indexOf('endstream', stm.start);
      end = i < 0 ? b.length : i;
      while (end > stm.start && (b[end - 1] === 10 || b[end - 1] === 13)) { end--; }
    }
    return b.subarray(stm.start, end);
  };
  Doc.prototype.decode = async function (stm, isXref) {
    if (stm.data) { return stm.data; }
    var d = stm.dict;
    var data = this.streamRaw(stm);
    var type = this.get(d.Type);
    if (this.key && !isXref && !(type instanceof Name && type.n === 'XRef') && data.length >= 32) {
      try {
        data = await aesDecrypt(this.key, data.subarray(0, 16), data.subarray(16));
      } catch (e) {
        try { data = await aesDecrypt(this.key, data.subarray(0, 16), data.subarray(16, 16 + ((data.length - 16) >> 4 << 4)), true); }
        catch (e2) { data = new Uint8Array(0); }
      }
    }
    var f = this.get(d.Filter);
    var parms = this.get(d.DecodeParms);
    var filters = Array.isArray(f) ? f : (f ? [f] : []);
    var plist = Array.isArray(parms) ? parms : [parms];
    for (var i = 0; i < filters.length; i++) {
      var name = this.get(filters[i]);
      name = name && name.n;
      var pm = this.get(plist[i]) || {};
      if (name === 'FlateDecode' || name === 'Fl') {
        data = await inflate(data);
        if (pm && this.get(pm.Predictor) >= 10) {
          data = pngPredict(data, { Predictor: this.get(pm.Predictor), Colors: this.get(pm.Colors), BitsPerComponent: this.get(pm.BitsPerComponent), Columns: this.get(pm.Columns) });
        }
      } else if (name === 'ASCIIHexDecode' || name === 'AHx') {
        data = asciiHex(data);
      } else if (name === 'ASCII85Decode' || name === 'A85') {
        data = ascii85(data);
      } else {
        stm.unsupported = name;
        break;                                       /* images: not needed */
      }
    }
    stm.data = data;
    return data;
  };
  Doc.prototype.load = async function () {
    this.scan();
    var self = this;
    /* xref streams can also be trailers */
    var nums = Object.keys(this.objs).map(Number);
    var stmObjs = [];
    nums.forEach(function (n) {
      var v;
      try { v = self.rawObject(n); } catch (e) { v = null; }
      if (v instanceof Stream) {
        var t = self.get(v.dict.Type);
        if (t instanceof Name && t.n === 'XRef') { self.trailers.push({ off: self.objs[n].off, d: v.dict }); }
        if (t instanceof Name && t.n === 'ObjStm') { stmObjs.push({ n: n, s: v }); }
      }
    });
    this.trailers.sort(function (a, b) { return a.off - b.off; });
    var tr = {};
    this.trailers.forEach(function (t) { Object.keys(t.d).forEach(function (k) { tr[k] = t.d[k]; }); });
    this.trailer = tr;
    if (tr.Encrypt) { await this.setupCrypto(this.get(tr.Encrypt)); }
    for (var i = 0; i < stmObjs.length; i++) {
      var so = stmObjs[i];
      var off = this.objs[so.n].off;
      var data;
      try { data = await this.decode(so.s); } catch (e) { continue; }
      var first = this.get(so.s.dict.First);
      var count = this.get(so.s.dict.N);
      var p = new Parser(new Lexer(data, 0));
      var pairs = [];
      for (var k = 0; k < count; k++) { pairs.push([p.next(), p.next()]); }
      for (var j = 0; j < pairs.length; j++) {
        var num = pairs[j][0];
        var cur = this.objs[num];
        if (cur && cur.stm === undefined && cur.off > off) { continue; }   /* newer direct object */
        if (cur && cur.stm !== undefined && cur.off > off) { continue; }
        var pp = new Parser(new Lexer(data, first + pairs[j][1]));
        var val;
        try { val = pp.object(); } catch (e) { val = null; }
        this.objs[num] = { off: off, stm: so.n, val: val };
      }
    }
  };
  Doc.prototype.setupCrypto = async function (enc) {
    var V = this.get(enc.V);
    var R = this.get(enc.R);
    if (!(V === 5 && (R === 5 || R === 6))) {
      throw new Error('unsupported-encryption');
    }
    var U = this.get(enc.U).b;
    var UE = this.get(enc.UE).b;
    var pw = new Uint8Array(0);
    var keySalt = U.subarray(40, 48);
    var h = R === 6 ? await hash2B(pw, keySalt, new Uint8Array(0)) : await sha('SHA-256', concat([pw, keySalt]));
    this.key = await aesDecrypt(h, new Uint8Array(16), UE.subarray(0, 32), true);
  };

  /* -------------------------------------------------------------- fonts */
  var HEB = ['alef', 'bet', 'gimel', 'dalet', 'he', 'vav', 'zayin', 'het', 'tet', 'yod', 'finalkaf',
    'kaf', 'lamed', 'finalmem', 'mem', 'finalnun', 'nun', 'samekh', 'ayin', 'finalpe', 'pe',
    'finaltsadi', 'tsadi', 'qof', 'resh', 'shin', 'tav'];
  var GLYPHS = {
    space: ' ', exclam: '!', quotedbl: '"', numbersign: '#', dollar: '$', percent: '%',
    ampersand: '&', quotesingle: '\x27', quoteright: '\x27', parenleft: '(', parenright: ')',
    asterisk: '*', plus: '+', comma: ',', hyphen: '-', minus: '-', period: '.', slash: '/',
    zero: '0', one: '1', two: '2', three: '3', four: '4', five: '5', six: '6', seven: '7',
    eight: '8', nine: '9', colon: ':', semicolon: ';', less: '<', equal: '=', greater: '>',
    question: '?', at: '@', bracketleft: '[', backslash: '\\', bracketright: ']',
    underscore: '_', quoteleft: '\x27', braceleft: '{', bar: '|', braceright: '}',
    endash: '-', emdash: '-', bullet: '\u2022', quotedblleft: '"', quotedblright: '"',
    geresh: '\u05f3', gershayim: '\u05f4', maqaf: '\u05be', maqafhebrew: '\u05be', sheqel: '\u20aa'
  };
  function glyphUnicode(name) {
    if (!name) { return ''; }
    if (GLYPHS[name] !== undefined) { return GLYPHS[name]; }
    if (/^[A-Za-z]$/.test(name)) { return name; }
    var m = /^afii(5766[4-9]|576[7-8]\d|5769[0])$/.exec(name);
    if (m) { return String.fromCharCode(0x5D0 + parseInt(m[1], 10) - 57664); }
    m = /^uni([0-9A-Fa-f]{4})/.exec(name);
    if (m) { return String.fromCharCode(parseInt(m[1], 16)); }
    var best = -1;
    var bestLen = 0;
    for (var i = 0; i < HEB.length; i++) {
      if (name.indexOf(HEB[i]) === 0 && HEB[i].length > bestLen) { best = i; bestLen = HEB[i].length; }
    }
    if (best >= 0) { return String.fromCharCode(0x5D0 + best); }
    return '';
  }
  var DINGBATS = { 0x33: '\u2713', 0x34: '\u2714', 0x35: '\u2715', 0x36: '\u2716', 0x37: '\u2717',
    0x38: '\u2718', 0x6C: '\u25cf', 0x6E: '\u25a0', 0x6F: '\u274f', 0x70: '\u2750', 0x71: '\u2751',
    0x72: '\u2752', 0x75: '\u25c6' };
  var DINGBAT_W = { 0x33: 0.755, 0x34: 0.846, 0x35: 0.762, 0x36: 0.759, 0x37: 0.509, 0x38: 0.410 };

  function parseCMap(data) {
    var s = latin1(data, 0, data.length);
    var map = {};
    var codeLen = 0;
    function hexs(t) { return t.replace(/[<>\s]/g, ''); }
    function u16(h) {
      var out = '';
      for (var i = 0; i + 4 <= h.length; i += 4) { out += String.fromCharCode(parseInt(h.substr(i, 4), 16)); }
      if (h.length === 2) { out = String.fromCharCode(parseInt(h, 16)); }
      return out;
    }
    var m;
    var cs = /begincodespacerange([\s\S]*?)endcodespacerange/g;
    while ((m = cs.exec(s))) {
      var r = /<([0-9A-Fa-f]+)>/.exec(m[1]);
      if (r) { codeLen = Math.max(codeLen, r[1].length / 2); }
    }
    var bc = /beginbfchar([\s\S]*?)endbfchar/g;
    while ((m = bc.exec(s))) {
      var re = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]*)>/g;
      var x;
      while ((x = re.exec(m[1]))) {
        map[parseInt(x[1], 16)] = u16(x[2]);
        if (!codeLen) { codeLen = x[1].length / 2; }
      }
    }
    var br = /beginbfrange([\s\S]*?)endbfrange/g;
    while ((m = br.exec(s))) {
      var re2 = /<([0-9A-Fa-f]+)>\s*<([0-9A-Fa-f]+)>\s*(<[0-9A-Fa-f]*>|\[[^\]]*\])/g;
      var y;
      while ((y = re2.exec(m[1]))) {
        var lo = parseInt(y[1], 16);
        var hi = parseInt(y[2], 16);
        if (!codeLen) { codeLen = y[1].length / 2; }
        if (y[3][0] === '[') {
          var items = y[3].match(/<[0-9A-Fa-f]*>/g) || [];
          for (var k = 0; k < items.length && lo + k <= hi; k++) { map[lo + k] = u16(hexs(items[k])); }
        } else {
          var base = hexs(y[3]);
          var last = parseInt(base.slice(-4) || base, 16);
          var prefix = base.length > 4 ? u16(base.slice(0, -4)) : '';
          for (var c = lo; c <= hi && c - lo < 65536; c++) {
            map[c] = prefix + String.fromCharCode(last + (c - lo));
          }
        }
      }
    }
    return { map: map, codeLen: codeLen };
  }

  Doc.prototype.font = async function (ref) {
    var key = ref instanceof Ref ? 'r' + ref.num : null;
    if (key && this.cache[key]) { return this.cache[key]; }
    var d = this.get(ref) || {};
    var self = this;
    var sub = (this.get(d.Subtype) || {}).n;
    var base = ((this.get(d.BaseFont) || {}).n || '').replace(/^[A-Z]{6}\+/, '');
    var f = { sub: sub, base: base, two: false, widths: {}, dw: 0, toU: null, enc: {}, asc: 0.95, desc: -0.35, scale: 0.001, dingbats: /Dingbat/i.test(base) };
    var fd = this.get(d.FontDescriptor);
    if (sub === 'Type0') {
      f.two = true;
      var df = this.get((this.get(d.DescendantFonts) || [])[0]) || {};
      fd = this.get(df.FontDescriptor);
      f.dw = (this.get(df.DW) || 1000) / 1000;
      var W = this.get(df.W) || [];
      for (var i = 0; i < W.length;) {
        var c0 = this.get(W[i]);
        var nx = this.get(W[i + 1]);
        if (Array.isArray(nx)) {
          for (var j = 0; j < nx.length; j++) { f.widths[c0 + j] = this.get(nx[j]) / 1000; }
          i += 2;
        } else {
          var c1 = nx;
          var w = this.get(W[i + 2]) / 1000;
          for (var c = c0; c <= c1; c++) { f.widths[c] = w; }
          i += 3;
        }
      }
    } else {
      var fc = this.get(d.FirstChar) || 0;
      var ws = this.get(d.Widths) || [];
      for (var k = 0; k < ws.length; k++) { f.widths[fc + k] = this.get(ws[k]) / 1000; }
      if (sub === 'Type3') {
        var fm = this.get(d.FontMatrix) || [0.001];
        f.scale = this.get(fm[0]) || 0.001;
        for (var kk = 0; kk < ws.length; kk++) { f.widths[fc + kk] = this.get(ws[kk]) * f.scale; }
      }
      var enc = this.get(d.Encoding);
      if (enc && !(enc instanceof Name)) {
        var diffs = this.get(enc.Differences) || [];
        var code = 0;
        diffs.forEach(function (x) {
          x = self.get(x);
          if (typeof x === 'number') { code = x; } else if (x instanceof Name) { f.enc[code++] = x.n; }
        });
      }
      if (fd) { f.dw = (this.get(fd.MissingWidth) || 0) / 1000; }
    }
    if (fd) {
      var a = this.get(fd.Ascent);
      var de = this.get(fd.Descent);
      if (typeof a === 'number' && a > 0 && a < 3000) { f.asc = a / 1000; }
      if (typeof de === 'number' && de < 0 && de > -3000) { f.desc = de / 1000; }
    }
    var tu = this.get(d.ToUnicode);
    if (tu instanceof Stream) {
      try {
        var cm = parseCMap(await this.decode(tu));
        f.toU = cm.map;
      } catch (e) { f.toU = null; }
    }
    if (key) { this.cache[key] = f; }
    return f;
  };
  function glyphText(f, code) {
    if (f.dingbats) { return DINGBATS[code] || ''; }
    if (f.toU && f.toU[code] !== undefined) { return f.toU[code]; }
    if (f.enc[code]) { return glyphUnicode(f.enc[code]); }
    if (f.two) { return ''; }
    if (code >= 32 && code < 127) { return String.fromCharCode(code); }
    if (code === 0xA0) { return ' '; }
    return '';
  }
  function glyphWidth(f, code) {
    if (f.widths[code] !== undefined) { return f.widths[code]; }
    if (f.dingbats) { return DINGBAT_W[code] || 0.75; }
    if (f.two) { return f.dw || 1; }
    return f.dw || 0.5;
  }

  /* -------------------------------------------------------- interpreter */
  function mul(a, b) {
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
      a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
      a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]];
  }
  function apply(m, x, y) { return [m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5]]; }

  Doc.prototype.runContent = async function (data, res, ctm, page, depth) {
    var self = this;
    var lx = new Lexer(data, 0);
    var ops = [];
    var gs = { ctm: ctm, fill: [0], fillCs: 'G', strokeCs: 'G' };
    var stack = [];
    var ts = { font: null, size: 0, tc: 0, tw: 0, tz: 1, tl: 0, rise: 0 };
    var tm = [1, 0, 0, 1, 0, 0];
    var tlm = [1, 0, 0, 1, 0, 0];
    var path = [];
    var sub = null;
    var fonts = this.get(res && res.Font) || {};
    var xobjs = this.get(res && res.XObject) || {};
    var colorSpaces = this.get(res && res.ColorSpace) || {};
    function csComps(nm) {
      if (nm === 'DeviceGray' || nm === 'G' || nm === 'CalGray') { return 1; }
      if (nm === 'DeviceRGB' || nm === 'RGB' || nm === 'CalRGB') { return 3; }
      if (nm === 'DeviceCMYK' || nm === 'CMYK') { return 4; }
      var cs = self.get(colorSpaces[nm]);
      if (Array.isArray(cs)) {
        var kind = (self.get(cs[0]) || {}).n;
        if (kind === 'ICCBased') { return self.get((self.get(cs[1]) || {}).dict ? self.get(cs[1]).dict.N : 3) || 3; }
        if (kind === 'Separation') { return 1; }
        if (kind === 'DeviceN') { return (self.get(cs[1]) || []).length || 1; }
        if (kind === 'CalRGB' || kind === 'Lab') { return 3; }
        if (kind === 'CalGray') { return 1; }
        if (kind === 'Indexed') { return 1; }
      }
      return 1;
    }
    function point(x, y) { return apply(gs.ctm, x, y); }
    function flushPath(fill, stroke) {
      if (!path.length) { return; }
      path.forEach(function (sp) {
        if (!sp.pts.length) { return; }
        var xs = sp.pts.map(function (p) { return p[0]; });
        var ys = sp.pts.map(function (p) { return p[1]; });
        var x0 = Math.min.apply(null, xs);
        var x1 = Math.max.apply(null, xs);
        var y0 = Math.min.apply(null, ys);
        var y1 = Math.max.apply(null, ys);
        page.shapes.push({ x0: x0 - page.ox, x1: x1 - page.ox, top: page.h - (y1 - page.oy), bottom: page.h - (y0 - page.oy),
          fill: fill, stroke: stroke, curve: sp.curve, rect: sp.rect, color: gs.fill.slice() });
      });
      path = [];
      sub = null;
    }
    async function showText(bytes) {
      var f = ts.font;
      if (!f) { return; }
      var i = 0;
      while (i < bytes.length) {
        var code;
        var n = f.two ? 2 : 1;
        if (f.two) { code = (bytes[i] << 8) | (bytes[i + 1] || 0); } else { code = bytes[i]; }
        i += n;
        var w0 = glyphWidth(f, code);
        var trm = mul([ts.size * ts.tz, 0, 0, ts.size, 0, ts.rise], mul(tm, gs.ctm));
        var u = glyphText(f, code);
        var adv = w0 * ts.size;
        var p0 = apply(trm, 0, 0);
        var p1 = apply(trm, w0, 0);
        var size = Math.sqrt(trm[2] * trm[2] + trm[3] * trm[3]);
        if (u !== '') {
          var gx0 = Math.min(p0[0], p1[0]) - page.ox;
          var gx1 = Math.max(p0[0], p1[0]) - page.ox;
          var base = page.h - (p0[1] - page.oy);
          page.glyphs.push({ u: u, x0: gx0, x1: gx1, base: base, size: size, asc: f.asc, desc: f.desc, upright: Math.abs(trm[1]) < 1e-3 && Math.abs(trm[2]) < 1e-3 });
        }
        var tx = (adv + ts.tc + (n === 1 && code === 32 ? ts.tw : 0)) * ts.tz;
        tm = mul([1, 0, 0, 1, tx, 0], tm);
      }
    }
    for (;;) {
      var t = lx.token();
      if (t === null) { break; }
      if (t === '[') {
        var arr = [];
        var tt;
        while ((tt = lx.token()) !== ']' && tt !== null) { arr.push(tt); }
        ops.push(arr);
        continue;
      }
      if (t === '<<') {
        var depthD = 1;
        var dd = {};
        var lastName = null;
        while (depthD > 0) {
          var q = lx.token();
          if (q === null) { break; }
          if (q === '<<') { depthD++; } else if (q === '>>') { depthD--; }
          else if (depthD === 1 && q instanceof Name && lastName === null) { lastName = q.n; }
          else if (depthD === 1 && lastName !== null) { dd[lastName] = q; lastName = null; }
        }
        ops.push(dd);
        continue;
      }
      if (!(t instanceof Kw)) { ops.push(t); continue; }
      var op = t.k;
      var a = ops;
      ops = [];
      switch (op) {
        case 'q': stack.push({ ctm: gs.ctm, fill: gs.fill, fillCs: gs.fillCs }); break;
        case 'Q': if (stack.length) { var g = stack.pop(); gs.ctm = g.ctm; gs.fill = g.fill; gs.fillCs = g.fillCs; } break;
        case 'cm': gs.ctm = mul(a.slice(-6), gs.ctm); break;
        case 'BT': tm = [1, 0, 0, 1, 0, 0]; tlm = tm; break;
        case 'ET': break;
        case 'Tf': {
          var fr = fonts[(a[0] || {}).n];
          ts.font = fr ? await self.font(fr) : null;
          ts.size = a[1] || 0;
          break;
        }
        case 'Tc': ts.tc = a[0] || 0; break;
        case 'Tw': ts.tw = a[0] || 0; break;
        case 'Tz': ts.tz = (a[0] || 100) / 100; break;
        case 'TL': ts.tl = a[0] || 0; break;
        case 'Ts': ts.rise = a[0] || 0; break;
        case 'Td': tlm = mul([1, 0, 0, 1, a[0] || 0, a[1] || 0], tlm); tm = tlm; break;
        case 'TD': ts.tl = -(a[1] || 0); tlm = mul([1, 0, 0, 1, a[0] || 0, a[1] || 0], tlm); tm = tlm; break;
        case 'Tm': tlm = a.slice(-6); tm = tlm; break;
        case 'T*': tlm = mul([1, 0, 0, 1, 0, -ts.tl], tlm); tm = tlm; break;
        case 'Tj': if (a[0] instanceof PStr) { await showText(a[0].b); } break;
        case '\x27':
          tlm = mul([1, 0, 0, 1, 0, -ts.tl], tlm); tm = tlm;
          if (a[0] instanceof PStr) { await showText(a[0].b); }
          break;
        case '"':
          ts.tw = a[0] || 0; ts.tc = a[1] || 0;
          tlm = mul([1, 0, 0, 1, 0, -ts.tl], tlm); tm = tlm;
          if (a[2] instanceof PStr) { await showText(a[2].b); }
          break;
        case 'TJ': {
          var list = Array.isArray(a[0]) ? a[0] : [];
          for (var li = 0; li < list.length; li++) {
            var it = list[li];
            if (it instanceof PStr) { await showText(it.b); }
            else if (typeof it === 'number') {
              tm = mul([1, 0, 0, 1, -it / 1000 * ts.size * ts.tz, 0], tm);
            }
          }
          break;
        }
        case 'g': gs.fill = [a[0] || 0]; gs.fillCs = 'G'; break;
        case 'rg': gs.fill = a.slice(-3); gs.fillCs = 'RGB'; break;
        case 'k': gs.fill = a.slice(-4); gs.fillCs = 'CMYK'; break;
        case 'cs': {
          var nm = (a[0] || {}).n;
          gs.fillCs = nm;
          var nc = csComps(nm);
          gs.fill = nc === 4 ? [0, 0, 0, 1] : (nc === 3 ? [0, 0, 0] : [0]);
          break;
        }
        case 'sc': case 'scn': {
          var nums = a.filter(function (x) { return typeof x === 'number'; });
          if (nums.length) { gs.fill = nums; }
          break;
        }
        case 'm': sub = { pts: [point(a[0], a[1])], curve: false, rect: false }; path.push(sub); break;
        case 'l': if (!sub) { sub = { pts: [], curve: false, rect: false }; path.push(sub); } sub.pts.push(point(a[0], a[1])); break;
        case 'c': if (!sub) { sub = { pts: [], curve: false, rect: false }; path.push(sub); } sub.curve = true; sub.pts.push(point(a[0], a[1]), point(a[2], a[3]), point(a[4], a[5])); break;
        case 'v': case 'y': if (!sub) { sub = { pts: [], curve: false, rect: false }; path.push(sub); } sub.curve = true; sub.pts.push(point(a[0], a[1]), point(a[2], a[3])); break;
        case 'h': break;
        case 're': {
          var x = a[0], y = a[1], w = a[2], hh = a[3];
          path.push({ pts: [point(x, y), point(x + w, y), point(x + w, y + hh), point(x, y + hh)], curve: false, rect: true });
          sub = null;
          break;
        }
        case 'f': case 'F': case 'f*': flushPath(true, false); break;
        case 'S': case 's': flushPath(false, true); break;
        case 'B': case 'B*': case 'b': case 'b*': flushPath(true, true); break;
        case 'n': path = []; sub = null; break;
        case 'W': case 'W*': break;
        case 'Do': {
          var xr = xobjs[(a[0] || {}).n];
          var xo = self.get(xr);
          if (!(xo instanceof Stream)) { break; }
          var st = (self.get(xo.dict.Subtype) || {}).n;
          if (st === 'Image') {
            var c0 = point(0, 0), c1 = point(1, 1), c2 = point(0, 1), c3 = point(1, 0);
            var ixs = [c0[0], c1[0], c2[0], c3[0]];
            var iys = [c0[1], c1[1], c2[1], c3[1]];
            page.images.push({ x0: Math.min.apply(null, ixs) - page.ox, x1: Math.max.apply(null, ixs) - page.ox,
              top: page.h - (Math.max.apply(null, iys) - page.oy), bottom: page.h - (Math.min.apply(null, iys) - page.oy) });
          } else if (st === 'Form' && depth < 12) {
            var fm = self.get(xo.dict.Matrix);
            var mtx = Array.isArray(fm) ? fm.map(function (v) { return self.get(v); }) : [1, 0, 0, 1, 0, 0];
            var fres = self.get(xo.dict.Resources) || res;
            var fdata = await self.decode(xo);
            await self.runContent(fdata, fres, mul(mtx, gs.ctm), page, depth + 1);
          }
          break;
        }
        case 'BI': {
          /* inline image: skip to EI */
          var b = data;
          var pos = lx.p;
          var idAt = -1;
          for (var z = pos; z < b.length - 1; z++) {
            if (b[z] === 73 && b[z + 1] === 68 && WS[b[z - 1]] && WS[b[z + 2]]) { idAt = z; break; }
          }
          var ei = -1;
          for (var zz = idAt + 3; idAt >= 0 && zz < b.length - 1; zz++) {
            if (b[zz] === 69 && b[zz + 1] === 73 && WS[b[zz - 1]] && (zz + 2 >= b.length || WS[b[zz + 2]])) { ei = zz; break; }
          }
          lx.p = ei >= 0 ? ei + 2 : b.length;
          var i0 = point(0, 0), i1 = point(1, 1);
          page.images.push({ x0: Math.min(i0[0], i1[0]) - page.ox, x1: Math.max(i0[0], i1[0]) - page.ox,
            top: page.h - (Math.max(i0[1], i1[1]) - page.oy), bottom: page.h - (Math.min(i0[1], i1[1]) - page.oy) });
          break;
        }
        default: break;
      }
    }
  };

  /* -------------------------------------------------------------- pages */
  Doc.prototype.pages = function () {
    var self = this;
    var out = [];
    var root = this.get(this.trailer.Root);
    var seen = {};
    function walk(node, inherit) {
      var d = self.get(node);
      if (!d || typeof d !== 'object') { return; }
      if (node instanceof Ref) { if (seen[node.num]) { return; } seen[node.num] = true; }
      var inh = {
        Resources: d.Resources !== undefined ? d.Resources : inherit.Resources,
        MediaBox: d.MediaBox !== undefined ? d.MediaBox : inherit.MediaBox,
        CropBox: d.CropBox !== undefined ? d.CropBox : inherit.CropBox,
        Rotate: d.Rotate !== undefined ? d.Rotate : inherit.Rotate
      };
      var type = (self.get(d.Type) || {}).n;
      var kids = self.get(d.Kids);
      if (type === 'Pages' || (Array.isArray(kids) && type !== 'Page')) {
        (kids || []).forEach(function (k) { walk(k, inh); });
      } else {
        out.push({ d: d, inh: inh });
      }
    }
    walk(root.Pages, {});
    return out;
  };

  async function read(arrayBuffer) {
    var doc = new Doc(new Uint8Array(arrayBuffer));
    await doc.load();
    var result = { pages: [] };
    var list = doc.pages();
    for (var i = 0; i < list.length; i++) {
      var pg = list[i];
      var box = doc.get(pg.inh.CropBox) || doc.get(pg.inh.MediaBox) || [0, 0, 612, 792];
      box = box.map(function (v) { return doc.get(v); });
      var mb = (doc.get(pg.inh.MediaBox) || box).map(function (v) { return doc.get(v); });
      /* pdftotext measures against the media box */
      var bx = mb;
      var page = { number: i + 1, width: bx[2] - bx[0], height: bx[3] - bx[1], ox: bx[0], oy: bx[1], h: bx[3] - bx[1],
        glyphs: [], shapes: [], images: [] };
      var cont = doc.get(pg.d.Contents);
      var parts = Array.isArray(cont) ? cont : (cont ? [pg.d.Contents] : []);
      var chunks = [];
      for (var k = 0; k < parts.length; k++) {
        var s = doc.get(parts[k]);
        if (s instanceof Stream) { chunks.push(await doc.decode(s)); chunks.push(new Uint8Array([10])); }
      }
      var res = doc.get(pg.inh.Resources) || {};
      try { await doc.runContent(concat(chunks), res, [1, 0, 0, 1, 0, 0], page, 0); }
      catch (e) { page.error = String(e && e.message || e); }
      result.pages.push(page);
    }
    return result;
  }

  return { read: read, _test: { Lexer: Lexer, Parser: Parser, parseCMap: parseCMap, glyphUnicode: glyphUnicode, pngPredict: pngPredict } };
})();
if (typeof module !== 'undefined') { module.exports = PdfReader; }
