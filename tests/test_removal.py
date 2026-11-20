"""Removal from the text layer and the other surfaces (spec section 6, REQ-030 to REQ-039)."""

from collections import Counter

import pymupdf
import pytest

from helpers import ALL_PATTERNS, FIXTURES, apply, canaries, fixture_bytes, present, source_for, sub
from fixturegen.engines import check_text, contains, trace_text

LAYOUTS = ["R1", "R2", "R3", "R4", "R5"]
HIDDEN = ["A01", "A03", "A05", "A06", "A09", "X05"]
KINDS = ["iban", "de-tax-id", "uk-ni", "email", "term1", "term2"]


def case_params():
    for fid in LAYOUTS:
        for i, c in enumerate(canaries(fid)):
            yield pytest.param(fid, i, id=f"{fid}-{c.kind}-{i}")


@pytest.mark.req("REQ-030")
@pytest.mark.parametrize("fid,idx", list(case_params()))
def test_removal_matrix(tmp_path, fid, idx):
    cs = canaries(fid)
    c = cs[idx]
    terms, pattern = source_for(fid, c)
    r = apply(tmp_path, fid, terms=terms, patterns=pattern, report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = r.out.read_bytes()
    for engine in c.checks:                                              # both engines and pypdf: the canary is gone
        assert not contains(check_text(out, engine), c.value), engine
    assert sum(m["count"] for m in r.report["removed"]) == c.count       # counts, never values
    for other in cs:                                                     # and nothing else was removed with it
        if other is not c:
            assert present(out, other), f"collateral damage: {other.kind}"


@pytest.mark.req("REQ-031")
def test_whole_glyph_removal(tmp_path):
    fid = "R5"                                                           # embedded subset font, justified text
    r = apply(tmp_path, fid, terms=[c.value for c in canaries(fid, "term")], patterns=ALL_PATTERNS)
    assert r.exit_code == 0
    before, after = trace_text(fixture_bytes(fid)).casefold(), trace_text(r.out.read_bytes()).casefold()
    for c in canaries(fid):
        v = c.value.casefold().replace(" ", "")
        rest = before.replace(c.value.casefold(), "")
        for i in range(len(v) - 2):
            run = v[i:i + 3]
            if run not in rest:                                          # a run only the canary holds
                assert run not in after.replace(" ", ""), f"remnant of {c.kind}"


@pytest.mark.req("REQ-032")
@pytest.mark.parametrize("fid", HIDDEN)
def test_removal_of_hidden_text(tmp_path, fid):
    cs = canaries(fid)
    r = apply(tmp_path, fid, terms=[c.value for c in cs if c.kind == "term"], patterns="email")
    assert r.exit_code == 0, (fid, r.stdout, r.stderr)
    out = r.out.read_bytes()
    for c in cs:
        for engine in (*c.checks, "raw"):
            assert not contains(check_text(out, engine), c.value), (fid, c.kind, engine)


@pytest.mark.req("REQ-033")
def test_mark_drawn_and_no_mark(tmp_path):
    def black_boxes(data: bytes) -> list[pymupdf.Rect]:
        d = pymupdf.open(stream=data, filetype="pdf")
        return [it["rect"] for p in d for it in p.get_drawings()
                if it.get("fill") == (0.0, 0.0, 0.0) and it["rect"].width > 5]
    assert black_boxes(fixture_bytes("R1")) == []
    c = canaries("R1", "iban")[0]
    r = apply(sub(tmp_path, "m"), "R1", patterns="iban")
    boxes = black_boxes(r.out.read_bytes())
    assert len(boxes) == 1
    page = pymupdf.open(stream=fixture_bytes("R1"), filetype="pdf")[0]
    glyphs = [pymupdf.Rect(ch[3]) for s in page.get_texttrace() for ch in s["chars"]]
    text = "".join(chr(ch[0]) for s in page.get_texttrace() for ch in s["chars"])
    i = text.index(c.value)
    area = pymupdf.Rect(glyphs[i]).include_rect(glyphs[i + len(c.value) - 1])
    assert boxes[0].contains(area + (1, 1, -1, -1))                       # covers the removal area
    n = apply(sub(tmp_path, "n"), "R1", patterns="iban", extra=["--no-mark"])
    assert n.exit_code == 0 and black_boxes(n.out.read_bytes()) == []
    assert not contains(trace_text(n.out.read_bytes()), c.value)          # removed, not covered


def _subtypes(data: bytes) -> Counter:
    d = pymupdf.open(stream=data, filetype="pdf")
    names = Counter()
    for p in d:
        for xref, _, _ in p.annot_xrefs():
            names[d.xref_get_key(xref, "Subtype")[1].lstrip("/")] += 1
    return names


@pytest.mark.req("REQ-034")
def test_annotations_and_fields_stripped(tmp_path):
    a08 = _subtypes(fixture_bytes("A08"))
    assert a08 and sum(a08.values()) >= 2
    r = apply(sub(tmp_path, "a"), "A08", terms=[c.value for c in FIXTURES["A08"].canaries if c.kind == "term"],
              patterns="email", report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    assert all(p.annot_xrefs() == [] for p in out)
    assert r.report["actions"]["annotations_removed"] == dict(a08)
    a10 = _subtypes(fixture_bytes("A10"))
    r = apply(sub(tmp_path, "b"), "A10", terms=["Vortavmar"], report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    assert all(p.annot_xrefs() == [] and not list(p.widgets() or []) for p in out)
    assert out.xref_get_key(out.pdf_catalog(), "AcroForm")[0] == "null"
    assert r.report["actions"]["form_fields_removed"] == 1
    assert a10["Widget"] == 1 and "Widget" not in r.report["actions"]["annotations_removed"]   # fields count apart


@pytest.mark.req("REQ-035")
def test_metadata_stripped(tmp_path):
    cs = [c.value for c in FIXTURES["A10"].canaries if c.kind == "term"]
    r = apply(tmp_path, "A10", terms=cs, report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    info = {k: v for k, v in out.metadata.items() if k not in ("format", "encryption")}
    assert all(not v for v in info.values()), info
    assert out.xref_get_key(out.pdf_catalog(), "Metadata")[0] == "null"
    assert not any(out.xref_get_key(x, "Subtype")[1] == "/XML" for x in range(1, out.xref_length()))
    assert r.report["actions"]["metadata_removed"] is True


@pytest.mark.req("REQ-036")
def test_embedded_files_and_actions_stripped(tmp_path):
    d = pymupdf.open(stream=fixture_bytes("A10"), filetype="pdf")
    cat = d.pdf_catalog()
    d.xref_set_key(cat, "OpenAction", "<< /S /JavaScript /JS (app.alert\\(0\\)) >>")
    d.xref_set_key(d[0].xref, "AA", "<< /O << /S /JavaScript /JS (this.print\\(\\)) >> >>")
    d.xref_set_key(cat, "Names/JavaScript", "<< /Names [(go) << /S /JavaScript /JS (x) >>] >>")
    data = d.tobytes()
    cs = [c.value for c in FIXTURES["A10"].canaries if c.kind == "term"]
    r = apply(tmp_path, "A10", terms=cs, data=data, report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    assert out.embfile_count() == 0
    assert out.xref_get_key(out.pdf_catalog(), "OpenAction")[0] == "null"
    assert out.xref_get_key(out.pdf_catalog(), "AA")[0] == "null"
    raw = check_text(r.out.read_bytes(), "raw")
    assert "app.alert" not in raw and "this.print" not in raw and "/JS" not in raw   # no script source is left
    assert r.report["actions"]["embedded_files_removed"] == 1
    assert r.report["actions"]["actions_removed"] == 3                     # OpenAction, page action, script name tree


@pytest.mark.req("REQ-037")
def test_outline_titles_redacted(tmp_path):
    d = pymupdf.open(stream=fixture_bytes("A10"), filetype="pdf")
    d.set_toc([[1, "Kelwenden", 1], [1, "Plain chapter", 1]])
    r = apply(tmp_path, "A10", terms=["Kelwenden"], data=d.tobytes(), report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    assert [t[1] for t in out.get_toc()] == ["[REDACTED]", "Plain chapter"]
    assert r.report["actions"]["outline_titles_redacted"] == 1


@pytest.mark.req("REQ-038")
def test_structure_tree_dropped_on_match(tmp_path):
    r = apply(sub(tmp_path, "hit"), "X07", terms=["Ulmulmulm", "Garselsel"], report=True)
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = pymupdf.open(stream=r.out.read_bytes(), filetype="pdf")
    assert out.xref_get_key(out.pdf_catalog(), "StructTreeRoot")[0] == "null"
    assert r.report["actions"]["structure_tree_removed"] is True
    assert not contains(check_text(r.out.read_bytes(), "raw"), "Ulmulmulm")
    miss = apply(sub(tmp_path, "miss"), "X07", terms=["Nomatchhere"], report=True)
    assert miss.exit_code == 0
    kept = pymupdf.open(stream=miss.out.read_bytes(), filetype="pdf")
    assert kept.xref_get_key(kept.pdf_catalog(), "StructTreeRoot")[0] != "null"
    assert miss.report["actions"]["structure_tree_removed"] is False


@pytest.mark.req("REQ-039")
@pytest.mark.parametrize("fid,terms", [("R1", ["Rosselgar"]), ("A07", ["Denvorfen"])])
def test_output_single_revision(tmp_path, fid, terms):
    r = apply(tmp_path, fid, terms=terms, patterns="iban")
    assert r.exit_code == 0, (r.stdout, r.stderr)
    out = r.out.read_bytes()
    d = pymupdf.open(stream=out, filetype="pdf")
    assert d.version_count == 1
    assert out.count(b"%%EOF") == 1
    tidy = pymupdf.open(stream=d.tobytes(garbage=4, deflate=True), filetype="pdf")
    assert tidy.xref_length() == d.xref_length()                          # no unreferenced objects
