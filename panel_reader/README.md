# Proposal PDF reader for the Insurtix panel

The same extraction as the backend, in plain browser JavaScript, so the
Insurtix policy panel can read a proposal PDF by itself ("טעינת טופס הצעה (PDF)")
on a computer that has only Chrome. Nothing leaves the browser.

| file | what it does |
|---|---|
| `pdfreader.js` | PDF structure, AES-256 (R5/R6) decryption, Flate, fonts / ToUnicode, text positions, shapes, images |
| `pdflayout.js` | glyphs to words and lines, like `pdftotext -bbox-layout` (+ `fix_word`) |
| `extract.js` | port of `app/extraction` (patterns, tables, findings, beneficiary rows, vector marks, engine) |
| `mapping.js` | port of `app/insurtix/mapping.py` (`to_insurtix`) |
| `template.json` | generated: `python backend/tools/export_template.py panel_reader/template.json` |

The field definitions and mapping constants are never written by hand here:
they are exported from the Python template, so a change in
`shlomo_life_insurance.py` or `mapping.py` constants reaches the panel on the
next export. A change in the Python *logic* must be ported to `extract.js` /
`mapping.js`; `parity.js` proves both readers agree:

    python backend/tools/export_template.py panel_reader/template.json
    python backend/tools/dump_extraction.py /path/to/pdfs
    node panel_reader/parity.js /path/to/pdfs

The PDFs hold personal data (IDs, health declarations): keep them outside
the repository.
