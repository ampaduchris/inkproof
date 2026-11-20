"""The 24 synthetic fixtures of spec section 10: determinism, the requirement map, and canaries.

A fixture that does not hold what it claims fails here. No requirement of the product is proved by
these tests, so they carry no requirement tags.
"""

import os
import re
import subprocess
import sys
import warnings
from io import BytesIO
from pathlib import Path

import pymupdf
import pytest

from fixturegen import build_all
from fixturegen.engines import check_text, contains, norm, pdfminer_text, trace_text
from fixturegen.values import S1_ENGINES

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parent.parent
SPEC = (ROOT / "docs" / "spec.md").read_text(encoding="utf-8")
FIXTURES = build_all()


def section(title_start: str) -> str:
    m = re.search(rf"^###? {re.escape(title_start)}.*?(?=^##)", SPEC, re.S | re.M)
    assert m, title_start
    return m.group(0)


def whole_section(start: str, end: str) -> str:
    m = re.search(rf"^## {re.escape(start)}.*?(?=^## {re.escape(end)})", SPEC, re.S | re.M)
    assert m, start
    return m.group(0)


def fid_of(letter: str, number: str) -> str:
    return f"R{int(number)}" if letter == "R" else f"{letter}{int(number):02d}"


def fixture_tokens(text: str) -> set[str]:
    ids = {fid_of(m[0], m[1:]) for m in re.findall(r"\b([RAXC]\d{1,2})\b", text)}
    for a, b in re.findall(r"\b([RAXC]\d{1,2}) to ([RAXC]\d{1,2})\b", text):
        la, na, nb = a[0], int(a[1:]), int(b[1:])
        ids |= {fid_of(la, str(n)) for n in range(na, nb + 1)}
    return {i for i in ids if i in FIXTURES}


# ---------------------------------------------------------------- determinism and inventory

def test_all_fixtures_regenerate_byte_identically_in_process():
    second = build_all()
    assert list(second) == list(FIXTURES)
    for fid, fx in FIXTURES.items():
        assert second[fid].files == fx.files, fid


def test_all_fixtures_regenerate_byte_identically_across_processes(tmp_path):
    outs = []
    for i in range(2):
        out = tmp_path / f"run{i}"
        env = {**os.environ, "PYTHONPATH": str(ROOT / "tests"), "PYTHONHASHSEED": str(i + 7), "PYTHONWARNINGS": "ignore"}
        subprocess.run([sys.executable, "-m", "fixturegen", str(out)], check=True, env=env, capture_output=True)
        outs.append({p.name: p.read_bytes() for p in sorted(out.iterdir())})
    assert outs[0] == outs[1]
    expected = {n for fx in FIXTURES.values() for n in fx.files}
    assert set(outs[0]) == expected
    for fx in FIXTURES.values():
        for n, data in fx.files.items():
            assert outs[0][n] == data


def test_there_are_24_fixtures_named_as_in_the_spec():
    sec10 = whole_section("10. Fixtures", "11.")
    named = set(re.findall(r"^\| ([RAXC]\d{1,2}) \|", sec10, re.M))
    assert len(FIXTURES) == 24
    assert named == set(FIXTURES)


# ---------------------------------------------------------------- the requirement map (spec 10.4)

def spec_requirements() -> dict[str, str]:
    return {m[0]: m[1] for m in re.findall(r"^\| (REQ-\d{3}) \| (?:MUST NOT|MUST|SHOULD|MAY) \|(.*)$", SPEC, re.M)}


def map_rows() -> dict[str, set[str]]:
    sec = section("10.4 Fixture to requirement map")
    return {m[0]: set(re.findall(r"REQ-\d{3}", m[1]))
            for m in re.findall(r"^\| ([RAXC]\d{1,2}) \| (.*?) \|$", sec, re.M)}


def test_map_lists_every_fixture_once():
    rows = re.findall(r"^\| ([RAXC]\d{1,2}) \|", section("10.4 Fixture to requirement map"), re.M)
    assert sorted(rows) == sorted(FIXTURES)


def test_every_fixture_serves_at_least_one_existing_requirement():
    reqs = spec_requirements()
    for fid, used in map_rows().items():
        assert used, fid
        assert used <= set(reqs), (fid, used - set(reqs))


def test_map_agrees_with_the_proof_columns_of_the_spec():
    """Every fixture a requirement's proof names is in the map for that requirement, and the reverse."""
    mapped = map_rows()
    named: dict[str, set[str]] = {f: set() for f in FIXTURES}
    for req, rest in spec_requirements().items():
        proof = rest.rsplit("|", 2)[-2] if rest.count("|") >= 2 else rest
        for f in fixture_tokens(proof):
            named[f].add(req)
    # the proof column of REQ-030 names R1 to R5; REQ-001 and REQ-060 name R1 in other columns
    missing = {f: sorted(named[f] - mapped[f]) for f in FIXTURES if named[f] - mapped[f]}
    assert not missing, f"named in a proof column but not in the map: {missing}"
    extra = {}
    reqs = spec_requirements()
    for f, used in mapped.items():
        for r in used:
            if f not in fixture_tokens(reqs[r]):
                extra[f] = extra.get(f, []) + [r]
    assert not extra, f"in the map but the requirement row never names the fixture: {extra}"


# ---------------------------------------------------------------- canaries

CASES = [(fid, i, ch) for fid, fx in FIXTURES.items() for i, c in enumerate(fx.canaries) for ch in c.checks]


@pytest.mark.parametrize("fid,i,check", CASES, ids=[f"{f}-{i}-{c}" for f, i, c in CASES])
def test_planted_canary_is_found_by_the_engines_the_spec_names(fid, i, check):
    fx = FIXTURES[fid]
    c = fx.canaries[i]
    data = next(iter(fx.files.values()))
    seen = contains(check_text(data, check, fx.password), c.value)
    assert seen is not c.absent, f"{fid} {c.surface} {c.kind} {check}: {'found' if seen else 'not found'}"


def test_absent_canaries_are_gone_from_every_surface_of_the_current_revision():
    for fid in ("C01", "A07"):
        fx = FIXTURES[fid]
        data = fx.files[f"{fid}.pdf"]
        for c in fx.canaries:
            if not c.absent:
                continue
            assert c.value.encode() not in data or fid == "A07"  # A07 keeps the old revision, as hex
            current = data
            assert not contains(check_text(current, "raw"), c.value) or fid == "A07"
            for ch in ("pymupdf-trace", "pdfminer", "pypdf"):
                assert not contains(check_text(current, ch), c.value)


def test_planted_counts_match_on_page_text():
    for fid, fx in FIXTURES.items():
        data = next(iter(fx.files.values()))
        for c in fx.canaries:
            if c.surface != "S1" or c.absent or fx.password or c.count == 0:
                continue
            squashed = re.sub(r"\s+", "", norm(trace_text(data))).replace("-", "")
            n = squashed.count(re.sub(r"\s+", "", norm(c.value)))
            assert n == c.count, (fid, c.kind, n, c.count)


# ---------------------------------------------------------------- each fixture holds what it claims

def doc(fid: str, name: str | None = None) -> pymupdf.Document:
    fx = FIXTURES[fid]
    return pymupdf.open(stream=fx.files[name or f"{fid}.pdf"], filetype="pdf")


def term(fid: str, idx: int = 0) -> str:
    return [c for c in FIXTURES[fid].canaries if not c.absent][idx].value


def test_layouts_are_what_they_say():
    assert doc("R1").page_count == 1 and doc("R2").page_count == 1 and doc("R3").page_count == 1
    assert doc("R4").page_count == 3
    # R1: the two-word term is split by a line break, so the words sit on different lines
    w1, w2 = term("R1", 4).split()
    page = doc("R1")[0]
    ys = {w[1]: w[4] for w in page.get_text("words")}
    y1 = [w[3] for w in page.get_text("words") if w[4] == w1]
    y2 = [w[3] for w in page.get_text("words") if w[4] == w2]
    assert y1 and y2 and y1[0] != y2[0]
    # R2: two text columns
    xs = {round(w[0]) for w in doc("R2")[0].get_text("words")}
    assert any(x < 100 for x in xs) and any(x > 300 for x in xs)
    # R3: a table, drawn as rectangles
    assert len(doc("R3")[0].get_drawings()) >= 6
    # R5: an embedded subset font, justified by word spacing
    fonts = doc("R5").get_page_fonts(0)
    assert any("+" in f[3] and f[1] == "ttf" for f in fonts), fonts
    assert b" Tw" in b"".join(doc("R5").xref_stream(x) for x in range(1, doc("R5").xref_length())
                              if doc("R5").xref_is_stream(x) and b"Tw" in (doc("R5").xref_stream(x) or b""))


def test_audit_fixtures_plant_the_failure_they_name():
    t = lambda fid: [s for s in doc(fid)[0].get_texttrace() if "Held" in "".join(chr(c[0]) for c in s["chars"])]  # noqa: E731
    a01 = doc("A01")[0]
    assert t("A01") and any(d.get("fill") == (0.0, 0.0, 0.0) for d in a01.get_drawings())
    assert doc("A02")[0].get_images()
    assert all(s["color"] == (1.0, 1.0, 1.0) for s in t("A03"))
    pane = [d for d in doc("A04")[0].get_drawings() if d.get("fill")]
    assert pane and all(s["color"] == pane[0]["fill"] for s in t("A04"))
    assert doc("A05")[0].rect.width == 612
    assert all(s["bbox"][0] >= 612 for s in t("A05"))
    assert term("A05") not in doc("A05")[0].get_text()  # E1: the plain text call misses off-page text
    a06 = doc("A06")[0]
    assert a06.cropbox != a06.mediabox and all(s["bbox"][2] < a06.cropbox.x0 + 400 for s in t("A06"))
    assert all(s["type"] == 3 for s in t("A09"))


def test_a07_has_two_revisions_and_the_old_text_is_hidden_from_a_byte_search():
    data = FIXTURES["A07"].files["A07.pdf"]
    assert data.count(b"%%EOF") == 2 and doc("A07").version_count == 2
    assert FIXTURES["R1"].files["R1.pdf"].count(b"%%EOF") == 1 and doc("R1").version_count == 1
    for c in FIXTURES["A07"].canaries:
        assert c.value.encode() not in data


def test_c01_is_a_single_clean_revision():
    d = doc("C01")
    data = FIXTURES["C01"].files["C01.pdf"]
    assert data.count(b"%%EOF") == 1 and d.version_count == 1
    assert not list(d[0].annot_xrefs()) and not d.embfile_names() and not d.get_toc()
    assert not d.xref_get_key(d.pdf_catalog(), "Names")[1] != "null"
    assert all(d.metadata[k] in ("", None) for k in ("title", "author", "subject", "keywords"))
    assert len(d[0].get_drawings()) >= 6


def test_x01_text_is_fragmented_and_carries_invisible_characters():
    data = FIXTURES["X01"].files["X01.pdf"]
    a, b = term("X01", 0), term("X01", 1)
    from fixturegen.engines import pypdf_text
    plain = "".join(p.get_text() for p in doc("X01"))
    for text in (pdfminer_text(data), pypdf_text(data), plain):
        assert a not in text  # E6, E11: the unbroken word is not returned
        assert contains(text, a)
    raw = trace_text(data)
    assert "­" in raw and "‍" in raw and b not in raw


def test_x02_values_are_hidden_from_a_plain_byte_search():
    data = FIXTURES["X02"].files["X02.pdf"]
    for c in FIXTURES["X02"].canaries:
        assert c.value.encode() not in data
        assert c.value.encode("utf-16-be") not in data
        assert contains(check_text(data, "raw"), c.value)


def test_x03_needs_a_password_and_x04_files_are_broken():
    fx = FIXTURES["X03"]
    d = pymupdf.open(stream=fx.files["X03.pdf"], filetype="pdf")
    assert d.needs_pass and not d.authenticate("wrong-password") and d.authenticate(fx.password)
    assert fx.canaries[0].value.encode() not in fx.files["X03.pdf"]
    trunc = FIXTURES["X04"].files["X04-truncated.pdf"]
    assert trunc.startswith(b"%PDF-") and b"%%EOF" not in trunc and b"startxref" not in trunc
    notpdf = FIXTURES["X04"].files["X04-not-a-pdf.bin"]
    assert not notpdf.startswith(b"%PDF-")
    with pytest.raises(Exception):
        pymupdf.open(stream=notpdf, filetype="pdf")


def test_x05_value_sits_in_a_form_nested_two_levels_deep():
    d = doc("X05")
    page = d[0]
    content = b"".join(d.xref_stream(x) for x in page.get_contents())
    assert b"Held" not in content and b"/Fm1 Do" in content
    fm1 = int(re.search(r"/Fm1 (\d+) 0 R", d.xref_object(page.xref)).group(1))
    assert d.xref_stream(fm1).strip() == b"/Fm2 Do"
    assert b"Held" in d.xref_stream(int(re.search(r"/Fm2 (\d+) 0 R", d.xref_object(fm1)).group(1)))


def test_x06_has_an_image_only_page_and_a_page_with_both():
    d = doc("X06")
    assert [bool(p.get_images()) for p in d] == [True, True]
    assert [bool(p.get_text().strip()) for p in d] == [False, True]


def test_x07_is_tagged_and_the_text_engines_do_not_return_the_alternative_text():
    d = doc("X07")
    assert "true" in d.xref_get_key(d.pdf_catalog(), "MarkInfo")[1]
    data = FIXTURES["X07"].files["X07.pdf"]
    for c in FIXTURES["X07"].canaries:
        for engine in S1_ENGINES:
            assert not contains(check_text(data, engine), c.value)


def test_x08_surfaces_are_not_in_any_text_engine():
    data = FIXTURES["X08"].files["X08.pdf"]
    for c in FIXTURES["X08"].canaries:
        for engine in S1_ENGINES:
            assert not contains(check_text(data, engine), c.value)


def test_x08_name_tree_destinations_n5(tmp_path):
    """N5, remaining part: each library on a /Dests dictionary alone, a name tree alone, and both together."""
    from fixturegen.build import VIS, Doc, T
    from pypdf import PdfReader

    def make(fn):
        d = Doc()
        pg = d.page(T(72, 700, VIS))
        return d.finish(fn(pg))

    forms = {"dict": lambda pg: f"/Dests << /DictForm [{pg} 0 R /Fit] >>",
             "tree": lambda pg: f"/Names << /Dests << /Names [(TreeForm) [{pg} 0 R /Fit]] >> >>"}
    both = make(lambda pg: forms["dict"](pg) + " " + forms["tree"](pg))
    got = {}
    for k, fn in forms.items():
        b = make(fn)
        got[k] = (sorted(pymupdf.open(stream=b, filetype="pdf").resolve_names()),
                  sorted(n.lstrip("/") for n in PdfReader(BytesIO(b)).named_destinations))
    assert got["dict"] == (["DictForm"], ["DictForm"])
    assert got["tree"] == (["TreeForm"], ["TreeForm"])
    both_got = (sorted(pymupdf.open(stream=both, filetype="pdf").resolve_names()),
                sorted(n.lstrip("/") for n in PdfReader(BytesIO(both)).named_destinations))
    assert both_got == (["DictForm", "TreeForm"], ["DictForm"])  # pypdf drops the name tree when both exist
