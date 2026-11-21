# Changelog

All notable changes are listed here. The format follows Keep a Changelog.

## 1.0.0 - 2026-11-21

- `inkproof apply`: removes terms and the four built-in patterns (`iban`, `de-tax-id`, `uk-ni`, `email`) from the text layer, strips annotations, form fields, metadata, embedded files and actions, writes one new file, and re-reads the serialised bytes with two extraction engines (PyMuPDF, pdfminer.six), a structure walk, a raw scan of decoded streams and strings, and a revision count. It writes nothing if one match survives.
- `inkproof audit`: reports leaks in someone else's redaction without changing the file: text under shapes, in the background colour, off the page, invisible, in earlier revisions, and in annotations, fields, metadata, bookmarks and embedded files.
- JSON report that never holds a matched value, a term or text from the document.
- Exit codes 0 to 4, defined in the specification.
- Examples in `examples/`, a recording script (`scripts/make_demo.py`) and a README runner (`scripts/run_blocks.py`) that CI runs.
- Release workflow: builds the wheel and source archive and attaches them to the GitHub release. Not published to PyPI (DEV-028).
- Known limits are listed in the README and in `docs/spec.md` section 1.2. Text drawn in a clipping render mode is not removed and makes `apply` exit 1 (DEV-027).
