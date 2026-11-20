"""Audit mode (spec 7 to 7.2): leaks on every surface, leak classes, earlier revisions, report and exit codes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import unicodedata
from pathlib import Path

import pytest

from fixturegen.build import VIS, Doc, T
from fixturegen.values import word
from helpers import ALL_PATTERNS, FIXTURES, audit, fixture_bytes, sub

HIDDEN = {"A01": "covered", "A02": "covered", "A03": "same-colour", "A04": "same-colour", "A05": "off-page",
          "A06": "off-page", "A09": "invisible"}


def term_values(fid: str) -> list[str]:
    seen: list[str] = []
    for c in FIXTURES[fid].canaries:
        if c.kind == "term" and not c.absent and c.value not in seen:
            seen.append(c.value)
    return seen


def source_id(fid: str, c) -> object:
    return term_values(fid).index(c.value) + 1 if c.kind == "term" else c.kind


def keyset(rep: dict) -> set[tuple]:
    return {(f["surface"], f.get("class"), f["page"], f["revision"], f["source"]["type"], f["source"]["id"])
            for f in rep["findings"]}


def total(rep: dict) -> int:
    return sum(f["count"] for f in rep["findings"])


# ---------------------------------------------------------------- two fixtures the spec's list does not hold (DEV-019)

def local_fixture(kind: str) -> tuple[bytes, str]:
    """S7: a document action holding a value. S11: an unreferenced object holding a value."""
    v = word(kind, "c", 3)
    d = Doc()
    d.page(T(72, 700, VIS))
    if kind == "S7":
        data = d.finish(f"/OpenAction << /S /JavaScript /JS ({v}) >>")
    else:
        d.p.add(f"<< /Note ({v}) >>")
        data = d.finish()
    return data, v


# ---------------------------------------------------------------- command line

@pytest.mark.req("REQ-002")
def test_cli_audit_happy_path(tmp_path):
    t = term_values("A01")[0]
    r = audit(tmp_path, "A01", terms=[t])
    assert r.exit_code == 1
    assert r.report["mode"] == "audit" and r.report["result"] == "leaks-found" and r.report["exit_code"] == 1
    assert len(r.report["findings"]) == 1
    f = r.report["findings"][0]
    assert (f["surface"], f["class"], f["page"], f["revision"], f["match_kind"], f["count"]) == \
        ("S1", "covered", 1, 1, "exact", 1)
    assert f["source"] == {"type": "term", "id": 1}


@pytest.mark.req("REQ-003")
def test_audit_requires_a_source(tmp_path):
    r = audit(tmp_path, "R1")
    assert r.exit_code == 2
    assert "--terms" in r.stderr and "--patterns" in r.stderr


@pytest.mark.req("REQ-004")
def test_audit_unknown_pattern(tmp_path):
    r = audit(tmp_path, "R1", patterns="iban,passport")
    assert r.exit_code == 2 and "passport" in r.stderr


@pytest.mark.req("REQ-005")
def test_audit_report_destinations(tmp_path):
    t = term_values("A01")[0]
    a = audit(sub(tmp_path, "a"), "A01", terms=[t])                    # no --report: standard output
    assert json.loads(a.stdout)["mode"] == "audit" and not a.report_path.exists()
    b = audit(sub(tmp_path, "b"), "A01", terms=[t], report=True)       # --report: the file, and nothing on standard output
    assert b.report_path.exists() and b.stdout.strip() == ""
    assert json.loads(b.report_path.read_text(encoding="utf-8")) == a.report


@pytest.mark.req("REQ-008")
def test_audit_help_documents_exit_codes():
    from inkproof.cli import app
    from typer.testing import CliRunner
    text = CliRunner().invoke(app, ["audit", "--help"]).stdout
    for code, word_ in enumerate(["clean", "leaks", "usage", "document", "internal"]):
        assert re.search(rf"\b{code}\s+{word_}", text), (code, word_)
    for opt in ("--terms", "--patterns", "--report", "--substring", "--allow-short-terms", "--debug"):
        assert opt in text


# ---------------------------------------------------------------- never changes the file

@pytest.mark.req("REQ-055")
def test_audit_does_not_modify(tmp_path):
    for name, mode in (("rw", 0o644), ("ro", 0o444)):
        d = sub(tmp_path, name)
        src = d / "in.pdf"
        src.write_bytes(fixture_bytes("A07"))
        os.utime(src, (1_700_000_000, 1_700_000_000))
        os.chmod(src, mode)
        before = (hashlib.sha256(src.read_bytes()).hexdigest(), src.stat().st_size, src.stat().st_mtime_ns,
                  stat.S_IMODE(src.stat().st_mode))
        from inkproof.cli import app
        from typer.testing import CliRunner
        t = term_values("A07")[0]
        (d / "terms.txt").write_text(t + "\n", encoding="utf-8")
        res = CliRunner().invoke(app, ["audit", str(src), "--terms", str(d / "terms.txt")])
        assert res.exit_code == 1
        after = (hashlib.sha256(src.read_bytes()).hexdigest(), src.stat().st_size, src.stat().st_mtime_ns,
                 stat.S_IMODE(src.stat().st_mode))
        assert after == before, name
        assert sorted(p.name for p in d.iterdir()) == ["in.pdf", "terms.txt"], name     # nothing written beside it


# ---------------------------------------------------------------- surfaces

@pytest.mark.req("REQ-056")
def test_audit_surfaces(tmp_path):
    """One planted canary per surface, found on the surface that holds it."""
    expected: dict[str, list[tuple]] = {}
    for fid in ("A01", "A08", "A10", "X07", "X08"):
        terms = term_values(fid)
        r = audit(sub(tmp_path, fid), fid, terms=terms)
        assert r.exit_code == 1, fid
        found = {(f["surface"], f["source"]["id"]) for f in r.report["findings"]}
        for c in FIXTURES[fid].canaries:
            if c.kind == "term" and not c.absent:
                assert (c.surface, source_id(fid, c)) in found, (fid, c.surface, c.note)
                expected.setdefault(c.surface, []).append(fid)
    for kind in ("S7", "S11"):
        data, v = local_fixture(kind)
        r = audit(sub(tmp_path, kind), kind, terms=[v], data=data)
        assert r.exit_code == 1
        assert {(f["surface"], f["source"]["id"]) for f in r.report["findings"]} == {(kind, 1)}, kind
        expected[kind] = [kind]
    r = audit(sub(tmp_path, "A07"), "A07", terms=term_values("A07"), patterns="iban")     # S8: an earlier revision
    assert r.exit_code == 1 and {f["class"] for f in r.report["findings"]} == {"earlier-revision"}
    expected["S8"] = ["A07"]
    assert set(expected) == {"S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9", "S10", "S11"}


@pytest.mark.req("REQ-056")
def test_audit_finds_both_match_kinds(tmp_path):
    r = audit(tmp_path, "X01", terms=term_values("X01"))              # fragments with a wide gap: a loose match
    assert r.exit_code == 1
    assert any(f["match_kind"] == "loose" for f in r.report["findings"])
    assert {f["source"]["id"] for f in r.report["findings"]} == {1, 2}


@pytest.mark.req("REQ-056")
def test_audit_finds_raw_encodings(tmp_path):
    r = audit(tmp_path, "X02", terms=term_values("X02"))              # hexadecimal, UTF-16, split across a TJ array
    assert r.exit_code == 1
    assert {f["source"]["id"] for f in r.report["findings"]} == {1, 2, 3}


@pytest.mark.req("REQ-057")
def test_audit_exit_codes(tmp_path):
    a01 = audit(sub(tmp_path, "a"), "A01", terms=term_values("A01"))
    c01 = audit(sub(tmp_path, "c"), "C01", terms=[c.value for c in FIXTURES["C01"].canaries if c.kind == "term"],
                patterns=ALL_PATTERNS)
    assert (a01.exit_code, c01.exit_code) == (1, 0)
    assert a01.report["result"] == "leaks-found" and c01.report["result"] == "clean"


@pytest.mark.req("REQ-058")
def test_audit_control_is_clean(tmp_path):
    terms = [c.value for c in FIXTURES["C01"].canaries if c.kind == "term"]
    assert terms
    r = audit(tmp_path, "C01", terms=terms, patterns=ALL_PATTERNS)
    assert r.exit_code == 0 and r.report["findings"] == [] and r.report["input"]["revisions"] == 1
    assert all(c["result"] == "pass" for c in r.report["checks"])


# ---------------------------------------------------------------- earlier revisions

@pytest.mark.req("REQ-060")
def test_revision_count(tmp_path):
    a07 = audit(sub(tmp_path, "a"), "A07", terms=term_values("A07"))
    r1 = audit(sub(tmp_path, "b"), "R1", terms=["Nomatchword"])
    assert a07.report["input"]["revisions"] == 2 and r1.report["input"]["revisions"] == 1
    assert r1.exit_code == 0


@pytest.mark.req("REQ-061")
def test_incremental_update_leak(tmp_path):
    r = audit(tmp_path, "A07", terms=term_values("A07"), patterns="iban")
    assert r.exit_code == 1
    assert keyset(r.report) == {("S1", "earlier-revision", 1, 1, "term", 1),
                                ("S1", "earlier-revision", 1, 1, "pattern", "iban")}
    assert all(f["revision"] == 1 for f in r.report["findings"])      # the current revision is clean
    assert [c["result"] for c in r.report["checks"] if c["id"] == "V5"] == ["fail"]


# ---------------------------------------------------------------- leak classes (spec 7.2)

def classes(tmp_path, fid: str) -> dict:
    r = audit(tmp_path, fid, terms=term_values(fid)[:1], patterns="email")
    assert r.exit_code == 1, fid
    assert {f["surface"] for f in r.report["findings"]} == {"S1"}
    assert total(r.report) == 2, fid                                  # the term and the address, once each
    return {f["class"] for f in r.report["findings"]}


@pytest.mark.req("REQ-065")
def test_class_covered_shape(tmp_path):
    assert classes(tmp_path, "A01") == {"covered"}


@pytest.mark.req("REQ-066")
def test_class_covered_image(tmp_path):
    assert classes(tmp_path, "A02") == {"covered"}


@pytest.mark.req("REQ-067")
def test_class_white_on_white(tmp_path):
    assert classes(tmp_path, "A03") == {"same-colour"}


@pytest.mark.req("REQ-068")
def test_class_same_colour_panel(tmp_path):
    assert classes(tmp_path, "A04") == {"same-colour"}


@pytest.mark.req("REQ-069")
def test_class_off_page(tmp_path):
    assert classes(sub(tmp_path, "a"), "A05") == {"off-page"}           # outside the media box
    assert classes(sub(tmp_path, "b"), "A06") == {"off-page"}           # inside the media box, outside the crop box


@pytest.mark.req("REQ-070")
def test_class_invisible(tmp_path):
    assert classes(tmp_path, "A09") == {"invisible"}


@pytest.mark.req("REQ-065")
def test_class_visible_and_order(tmp_path):
    """Plain text is `visible`; a visible match is not mistaken for a hidden one, and the order of 7.2 decides ties."""
    r = audit(sub(tmp_path, "r1"), "R1", terms=term_values("R1")[:1])
    assert r.exit_code == 1 and {f["class"] for f in r.report["findings"]} == {"visible"}
    # off-page beats invisible; invisible beats covered (first in the order wins)
    d = Doc()
    d.page(T(72, 700, VIS) + T(700, 600, "Held Zelvorkel", pre="3 Tr") + "q 1 0 0 rg 66 590 40 30 re f Q\n" +
           T(72, 500, "Held Pelnorgar", pre="3 Tr") + "0 g 66 490 300 30 re f\n")
    data = d.finish()
    r = audit(sub(tmp_path, "mix"), "mix", terms=["Zelvorkel", "Pelnorgar"], data=data)
    assert {(f["source"]["id"], f["class"]) for f in r.report["findings"]} == {(1, "off-page"), (2, "invisible")}


@pytest.mark.req("REQ-065")
def test_partial_cover_is_not_covered(tmp_path):
    """A shape over the first 60% of a match leaves it readable: `visible`. Over all of it: `covered`."""
    def klass(width: int) -> set:
        d = Doc()
        d.page(T(72, 700, VIS) + T(72, 600, "Held Zelvorkel") + f"0 g 66 590 {width} 30 re f\n")
        r = audit(sub(tmp_path, f"w{width}"), "part", terms=["Zelvorkel"], data=d.finish())
        return {f["class"] for f in r.report["findings"]}
    assert klass(58) == {"visible"} and klass(120) == {"covered"}


@pytest.mark.req("REQ-069")
def test_match_partly_on_the_page_is_not_off_page(tmp_path):
    d = Doc()
    d.page(T(72, 700, VIS) + T(-30, 600, "Zelvorkel"))                   # starts outside the page, ends inside it
    r = audit(tmp_path, "edge", terms=["Zelvorkel"], data=d.finish())
    assert {f["class"] for f in r.report["findings"]} == {"visible"}


@pytest.mark.req("REQ-065")
def test_transparent_shape_does_not_cover(tmp_path):
    d = Doc()
    d.page(T(72, 700, VIS) + T(72, 600, "Held Zelvorkel") + "/G1 gs 0 g 66 590 300 30 re f\n",
           resources="/ExtGState << /G1 << /ca 0.5 >> >>")
    r = audit(tmp_path, "alpha", terms=["Zelvorkel"], data=d.finish())
    assert {f["class"] for f in r.report["findings"]} == {"visible"}


@pytest.mark.req("REQ-068")
def test_text_on_a_dark_panel_is_visible(tmp_path):
    d = Doc()
    d.page(T(72, 700, VIS) + "0 g 66 590 300 30 re f\n1 g\n" + T(72, 600, "Held Zelvorkel"))
    r = audit(tmp_path, "panel", terms=["Zelvorkel"], data=d.finish())
    assert {f["class"] for f in r.report["findings"]} == {"visible"}                # white on black can be read


# ---------------------------------------------------------------- annotations and the other surfaces

@pytest.mark.req("REQ-071")
def test_annotation_leaks(tmp_path):
    r = audit(tmp_path, "A08", terms=term_values("A08"), patterns="email")
    assert r.exit_code == 1
    assert {(f["surface"], f["source"]["id"], f["count"]) for f in r.report["findings"]} == \
        {("S2", 1, 1), ("S2", "email", 1)}                              # free text, and the pop-up note


@pytest.mark.req("REQ-072")
def test_non_page_surface_leaks(tmp_path):
    r = audit(tmp_path, "A10", terms=term_values("A10"))
    assert r.exit_code == 1
    by_surface: dict[str, set] = {}
    for f in r.report["findings"]:
        by_surface.setdefault(f["surface"], set()).add(f["source"]["id"])
    got = {s: len(ids) for s, ids in by_surface.items()}
    assert got == {"S4": 2, "S5": 1, "S3": 1, "S6": 1}                  # information dictionary and XMP, outline, field, file
    assert {f["surface"]: f["page"] for f in r.report["findings"]} == {"S4": None, "S5": None, "S3": 1, "S6": None}


@pytest.mark.req("REQ-074")
def test_image_limits_reported(tmp_path):
    r = audit(tmp_path, "X06", terms=term_values("X06"))
    assert r.report["limits"]["pages_with_images"] == [1, 2] and r.report["limits"]["image_only_pages"] == [1]
    assert re.search(r"text layer only", r.stderr)


# ---------------------------------------------------------------- the report of an audit

READABLE = [fid for fid in FIXTURES if fid not in ("X03", "X04")]


@pytest.fixture(scope="module")
def audit_reports(tmp_path_factory):
    out = {}
    for fid in READABLE:
        d = tmp_path_factory.mktemp("a" + fid)
        terms = [c.value for c in FIXTURES[fid].canaries if c.kind == "term"] or ["Nomatchword"]
        out[fid] = (d, audit(d, fid, terms=terms, patterns=ALL_PATTERNS))
    return out


def forms(value: str) -> set[str]:
    norm = unicodedata.normalize("NFKC", value).casefold()
    return {value, norm, re.sub(r"\s+", "", norm)}


@pytest.mark.req("REQ-075")
def test_audit_report_validates(audit_reports):
    for fid, (_, r) in audit_reports.items():
        assert r.exit_code in (0, 1) and r.report is not None, fid          # helpers.audit validates every report
        assert r.report["output"] is None and r.report["removed"] == [], fid
        assert r.report["actions"]["structure_tree_removed"] is False and r.report["actions"]["metadata_removed"] is False


@pytest.mark.req("REQ-076")
def test_audit_report_has_no_values_or_paths(audit_reports):
    for fid, (d, r) in audit_reports.items():
        text = r.stdout + r.stderr
        squashed = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())
        for c in FIXTURES[fid].canaries:
            for f in forms(c.value):
                assert f not in text and re.sub(r"\s+", "", f.casefold()) not in squashed, (fid, c.kind)
        assert str(d) not in text and "in.pdf" not in text and "terms.txt" not in text, fid
        assert re.fullmatch(r"[0-9a-f]{64}", r.report["input"]["sha256"])


@pytest.mark.req("REQ-077")
def test_audit_report_location_fields(audit_reports):
    keys = {"surface", "class", "page", "revision", "source", "match_kind", "count"}
    for fid, (_, r) in audit_reports.items():
        for f in r.report["findings"]:
            assert set(f) <= keys and {"surface", "page", "revision", "source", "match_kind", "count"} <= set(f), fid
            assert f["page"] is None or f["page"] >= 1


@pytest.mark.req("REQ-078")
def test_audit_report_deterministic(tmp_path):
    runs = [audit(sub(tmp_path, "r" + fid), fid, terms=term_values(fid), patterns=ALL_PATTERNS).stdout
            for fid in ("A07", "A10", "A01")]
    again = [audit(sub(tmp_path, "s" + fid), fid, terms=term_values(fid), patterns=ALL_PATTERNS).stdout
             for fid in ("A07", "A10", "A01")]
    assert runs == again
    rep = json.loads(runs[0])
    assert list(rep) == sorted(rep) and "time" not in runs[0].lower()
    keys = [(f["surface"], f["page"] or 0, f["revision"], str(f["source"]["id"])) for f in rep["findings"]]
    assert keys == sorted(keys)


@pytest.mark.req("REQ-051")
def test_audit_report_checks_section(tmp_path):
    r = audit(tmp_path, "A01", terms=term_values("A01"))
    checks = {c["id"]: c for c in r.report["checks"]}
    assert set(checks) == {"V1", "V2", "V3", "V4", "V5"}
    assert checks["V1"]["engine"] == "pymupdf" and checks["V2"]["engine"] == "pdfminer.six"
    assert all(c["engine_version"] for c in checks.values())


# ---------------------------------------------------------------- hygiene, errors, exit codes (audit column)

SECRET = "Rosselgar"


def boom(monkeypatch):
    import inkproof.audit as au

    def fail(*a, **k):
        raise RuntimeError(f"failed on {SECRET}")
    monkeypatch.setattr(au, "audit_document", fail)


def leaked(text: str, vals: list[str]) -> list[str]:
    norm = unicodedata.normalize("NFKC", text).casefold()
    squashed = re.sub(r"\s+", "", norm)
    return [v for v in vals if v in text or unicodedata.normalize("NFKC", v).casefold() in norm
            or re.sub(r"\s+", "", unicodedata.normalize("NFKC", v).casefold()) in squashed]


@pytest.mark.req("REQ-080")
def test_no_value_in_any_output_audit(tmp_path, monkeypatch):
    vals = [c.value for c in FIXTURES["A10"].canaries] + [c.value for c in FIXTURES["A07"].canaries]
    cases = {
        "leaks, report on standard output": audit(sub(tmp_path, "a"), "A10", terms=term_values("A10"), patterns=ALL_PATTERNS),
        "leaks, report file": audit(sub(tmp_path, "b"), "A07", terms=term_values("A07"), patterns=ALL_PATTERNS, report=True),
        "bad terms file": audit(sub(tmp_path, "c"), "A10", terms=term_values("A10") + ["q7"]),
        "corrupt input": audit(sub(tmp_path, "d"), "X04", terms=["Zelfen"], data=FIXTURES["X04"].files["X04-truncated.pdf"]),
    }
    assert [r.exit_code for r in cases.values()] == [1, 1, 2, 3]
    for name, r in cases.items():
        text = r.stdout + r.stderr + (r.report_path.read_text(encoding="utf-8") if r.report_path.exists() else "")
        assert leaked(text, vals + ["q7"]) == [], name
    boom(monkeypatch)
    r = audit(sub(tmp_path, "e"), "A10", terms=term_values("A10"))
    assert r.exit_code == 4
    assert leaked(r.stdout + r.stderr, vals + [SECRET]) == []


@pytest.mark.req("REQ-081")
def test_audit_internal_error_is_masked(tmp_path, monkeypatch):
    boom(monkeypatch)
    plain = audit(sub(tmp_path, "a"), "R1", terms=[SECRET])
    assert plain.exit_code == 4
    msg = plain.stdout + plain.stderr
    assert re.search(r"internal error.*\bE4\b|\bE4\b.*internal error", msg, re.I | re.S)
    assert "Traceback" not in msg and SECRET not in msg and "failed on" not in msg
    dbg = audit(sub(tmp_path, "b"), "R1", terms=[SECRET], extra=["--debug"])
    assert dbg.exit_code == 4
    text = dbg.stdout + dbg.stderr
    assert "Traceback" in text and "RuntimeError" in text and SECRET not in text and "failed on" not in text


@pytest.mark.req("REQ-082")
def test_audit_leaves_no_temporary_files(tmp_path, monkeypatch):
    import tempfile
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(systmp))
    monkeypatch.setattr(tempfile, "tempdir", None)
    for code, fid, terms in ((0, "R1", ["Nomatchword"]), (1, "A01", term_values("A01")), (3, "X03", ["Tavnorzel"])):
        d = sub(tmp_path, f"w{code}")
        assert audit(d, fid, terms=terms).exit_code == code
        assert sorted(p.name for p in d.iterdir()) == ["in.pdf", "terms.txt"] and list(systmp.iterdir()) == []
    boom(monkeypatch)
    d = sub(tmp_path, "w4")
    assert audit(d, "R1", terms=[SECRET]).exit_code == 4
    assert sorted(p.name for p in d.iterdir()) == ["in.pdf", "terms.txt"] and list(systmp.iterdir()) == []


@pytest.mark.req("REQ-085")
def test_exit_codes_audit(tmp_path, monkeypatch):
    seen = {
        0: audit(sub(tmp_path, "0"), "C01", terms=["Nomatchword"]).exit_code,
        1: audit(sub(tmp_path, "1"), "A01", terms=term_values("A01")).exit_code,
        2: audit(sub(tmp_path, "2"), "R1").exit_code,
        3: audit(sub(tmp_path, "3"), "X03", terms=["Tavnorzel"]).exit_code,
    }
    boom(monkeypatch)
    seen[4] = audit(sub(tmp_path, "4"), "R1", terms=["Nomatchword"]).exit_code
    assert seen == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


@pytest.mark.req("REQ-088")
def test_audit_unreadable_documents(tmp_path):
    for i, (fid, name) in enumerate((("X03", "X03.pdf"), ("X04", "X04-truncated.pdf"), ("X04", "X04-not-a-pdf.bin"))):
        r = audit(sub(tmp_path, str(i)), fid, terms=["Tavnorzel"], data=FIXTURES[fid].files[name])
        assert r.exit_code == 3, name


@pytest.mark.req("REQ-056")
def test_audit_each_engine_catches_alone(tmp_path, monkeypatch):
    """Page text is read by two engines. Each, with the other returning nothing, still finds the planted leak."""
    import inkproof.audit as au
    t = term_values("A01")[0]
    monkeypatch.setattr(au, "v2_text", lambda data: [])
    a = audit(sub(tmp_path, "a"), "A01", terms=[t])
    assert a.exit_code == 1 and {f["class"] for f in a.report["findings"]} == {"covered"}
    monkeypatch.undo()
    real = au.page_matches
    monkeypatch.setattr(au, "page_matches", lambda doc, m, rev, classify: [] if classify else real(doc, m, rev, classify))
    b = audit(sub(tmp_path, "b"), "A01", terms=[t])
    assert b.exit_code == 1 and [(f["surface"], f.get("class"), f["count"]) for f in b.report["findings"]] == [("S1", None, 1)]
