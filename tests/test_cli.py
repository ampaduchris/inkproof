"""Command line, exit codes and output safety for `apply` (spec 5.1 and 9.2). Audit arrives in session 1.5."""

import os
import re
from pathlib import Path

import pymupdf
import pytest
import typer

from helpers import ALL_PATTERNS, FIXTURES, apply, fixture_bytes, invoke, sha256, sub, write_terms

import inkproof
from inkproof.cli import app

R1_TERM = "Rosselgar"
OPTIONS = {"--terms", "--patterns", "--output", "--report", "--force", "--substring", "--allow-short-terms",
           "--no-mark", "--debug", "--help"}


@pytest.mark.req("REQ-001")
def test_cli_apply_happy_path(tmp_path):
    r = apply(tmp_path, "R1", terms=["Zelhol Selwen", R1_TERM], patterns=ALL_PATTERNS)
    assert r.exit_code == 0
    assert r.out.exists()
    assert r.report["result"] == "clean"
    assert r.report["mode"] == "apply" and r.report["exit_code"] == 0


@pytest.mark.req("REQ-003")
def test_cli_requires_a_source(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(fixture_bytes("R1"))
    out = tmp_path / "out.pdf"
    res = invoke(["apply", str(src), "-o", str(out)])
    assert res.exit_code == 2
    assert not out.exists() and not Path(str(out) + ".report.json").exists()
    assert sha256(src) == __import__("hashlib").sha256(fixture_bytes("R1")).hexdigest()


@pytest.mark.req("REQ-004")
def test_cli_unknown_pattern(tmp_path):
    r = apply(tmp_path, "R1", patterns="iban,passport-no")
    assert r.exit_code == 2
    assert "passport-no" in r.stdout + r.stderr
    assert not r.out.exists()


@pytest.mark.req("REQ-005")
def test_report_destinations(tmp_path):
    a = apply(sub(tmp_path, "a"), "R1", patterns="email", report=True)                 # --report PATH
    assert a.exit_code == 0 and a.report_path.name == "report.json" and a.report["result"] == "clean"
    assert not Path(str(a.out) + ".report.json").exists()
    b = apply(sub(tmp_path, "b"), "R1", patterns="email")                              # default: beside OUT
    assert b.report_path == Path(str(b.out) + ".report.json") and b.report["result"] == "clean"
    assert b.stdout.strip() == ""                                                  # report not on stdout


@pytest.mark.req("REQ-006")
def test_apply_refuses_in_place(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(fixture_bytes("R1"))
    before = sha256(src)
    terms = write_terms(tmp_path / "t.txt", [R1_TERM])
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(src), "--force"])
    assert res.exit_code == 2 and sha256(src) == before
    link = tmp_path / "link.pdf"
    link.symlink_to(src)
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(link), "--force"])
    assert res.exit_code == 2 and sha256(src) == before
    assert link.is_symlink()


@pytest.mark.req("REQ-007")
def test_apply_no_overwrite_without_force(tmp_path):
    src = tmp_path / "in.pdf"
    src.write_bytes(fixture_bytes("R1"))
    out = tmp_path / "out.pdf"
    out.write_bytes(b"earlier output")
    terms = write_terms(tmp_path / "t.txt", [R1_TERM])
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(out)])
    assert res.exit_code == 2 and out.read_bytes() == b"earlier output"
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(out), "--force"])
    assert res.exit_code == 0 and out.read_bytes() != b"earlier output"


@pytest.mark.req("REQ-008")
@pytest.mark.req("REQ-090")
def test_cli_version_and_help():
    res = invoke(["--version"])
    assert res.exit_code == 0 and res.stdout.strip() == inkproof.__version__
    assert invoke(["--help"]).exit_code == 0 and invoke(["apply", "--help"]).exit_code == 0
    text = invoke(["apply", "--help"]).stdout
    for opt in OPTIONS:
        assert opt in text, opt
    for code, word in enumerate(["clean", "leaks", "usage", "document", "internal"]):
        assert re.search(rf"\b{code}\s+{word}", text), (code, word)
    names = {o for p in typer.main.get_command(app).commands["apply"].params for o in p.opts if o.startswith("-")}
    assert OPTIONS | {"-o"} >= names


# ---- exit codes: one case per cell of the table that this session builds (the audit column is session 1.5)

def _internal_error(monkeypatch, canary="Rosselgar"):
    import inkproof.apply as ap

    def boom(*a, **k):
        raise RuntimeError(f"boom {canary}")
    monkeypatch.setattr(ap, "serialise", boom)


@pytest.mark.req("REQ-085")
def test_exit_codes(tmp_path, monkeypatch):
    seen = {
        0: apply(sub(tmp_path, "0"), "R1", terms=[R1_TERM]).exit_code,
        1: apply(sub(tmp_path, "1"), "X08", terms=["Denkelhol"]).exit_code,   # survivor on a verify-only surface
        2: apply(sub(tmp_path, "2"), "R1").exit_code,                          # neither terms nor patterns
        3: apply(sub(tmp_path, "3"), "X03", terms=["Tavnorzel"]).exit_code,   # needs a password
    }
    _internal_error(monkeypatch)
    seen[4] = apply(sub(tmp_path, "4"), "R1", terms=[R1_TERM]).exit_code
    assert seen == {0: 0, 1: 1, 2: 2, 3: 3, 4: 4}


@pytest.mark.req("REQ-086")
def test_no_output_on_failure(tmp_path, monkeypatch):
    def attempt(name, fid, terms, data=None):
        d = tmp_path / name
        d.mkdir()
        (d / "out.pdf").write_bytes(b"previous")
        r = apply(d, fid, terms=terms, extra=["--force"] if name != "none" else [], data=data)
        return r, d / "out.pdf"
    r, out = attempt("c1", "X08", ["Denkelhol"])
    assert r.exit_code == 1 and out.read_bytes() == b"previous"
    r, out = attempt("c2", "R1", ["q7"])                                         # short term, exit 2
    assert r.exit_code == 2 and out.read_bytes() == b"previous"
    r, out = attempt("c3", "X03", ["Tavnorzel"])
    assert r.exit_code == 3 and out.read_bytes() == b"previous"
    _internal_error(monkeypatch)
    r, out = attempt("c4", "R1", [R1_TERM])
    assert r.exit_code == 4 and out.read_bytes() == b"previous"
    for name, fid, terms, code in (("n1", "X08", ["Denkelhol"], 1), ("n3", "X03", ["Tavnorzel"], 3)):
        monkeypatch.undo()
        d = tmp_path / name
        d.mkdir()
        r = apply(d, fid, terms=terms)
        assert r.exit_code == code and not r.out.exists()                         # nothing at OUT without --force


@pytest.mark.req("REQ-087")
def test_atomic_write(tmp_path, monkeypatch):
    import inkproof.apply as ap
    seen = {}
    real = os.replace

    def spy(src, dst, *a, **k):
        seen["tmp_mode"] = os.stat(os.path.dirname(src)).st_mode & 0o777
        seen["same_dir"] = Path(os.path.dirname(os.path.dirname(src))) == Path(os.path.dirname(dst))
        assert Path(dst).exists() is False                                        # nothing is at OUT before the rename
        return real(src, dst, *a, **k)
    monkeypatch.setattr(ap.os, "replace", spy)
    (tmp_path / "ok").mkdir()
    r = apply(tmp_path / "ok", "R1", terms=[R1_TERM])
    assert r.exit_code == 0 and seen["same_dir"] and seen["tmp_mode"] & 0o077 == 0

    def fail(*a, **k):
        raise OSError("injected failure before the rename")
    monkeypatch.setattr(ap.os, "replace", fail)
    (tmp_path / "bad").mkdir()
    r = apply(tmp_path / "bad", "R1", terms=[R1_TERM])
    assert r.exit_code == 4 and not r.out.exists()
    assert sorted(p.name for p in (tmp_path / "bad").iterdir() if p.name not in ("terms.txt", "in.pdf", "out.pdf.report.json")) == []


@pytest.mark.req("REQ-088")
def test_unreadable_documents(tmp_path):
    for i, (fid, name, terms) in enumerate((("X03", "X03.pdf", ["Tavnorzel"]), ("X04", "X04-truncated.pdf", ["Zelfen"]),
                                            ("X04", "X04-not-a-pdf.bin", ["Zelfen"]))):
        d = tmp_path / str(i)
        d.mkdir()
        r = apply(d, fid, terms=terms, data=FIXTURES[fid].files[name])
        assert r.exit_code == 3, name
        assert not r.out.exists()


@pytest.mark.req("REQ-089")
def test_apply_does_not_modify_input(tmp_path):
    for code, fid, terms in ((0, "R1", [R1_TERM]), (1, "X08", ["Denkelhol"])):
        d = tmp_path / str(code)
        d.mkdir()
        src = d / "in.pdf"
        src.write_bytes(fixture_bytes(fid))
        before = (sha256(src), src.stat().st_size)
        r = apply(d, fid, terms=terms)
        assert r.exit_code == code
        assert (sha256(src), src.stat().st_size) == before


@pytest.mark.req("REQ-006")
@pytest.mark.req("REQ-089")
def test_apply_refuses_report_path_equal_to_input_or_output(tmp_path):
    """Review 1.7 F-02: --report equal to IN or OUT exits 2 and writes nothing."""
    d = sub(tmp_path, "a")
    src = d / "in.pdf"
    src.write_bytes(fixture_bytes("R1"))
    before = sha256(src)
    out = d / "out.pdf"
    terms = write_terms(d / "t.txt", [R1_TERM])
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(out), "--report", str(src)])
    assert res.exit_code == 2 and sha256(src) == before and not out.exists()
    link = d / "link.json"
    link.symlink_to(src)
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(out), "--report", str(link)])
    assert res.exit_code == 2 and sha256(src) == before and not out.exists()
    res = invoke(["apply", str(src), "--terms", str(terms), "-o", str(out), "--report", str(out)])
    assert res.exit_code == 2 and not out.exists()


@pytest.mark.req("REQ-086")
@pytest.mark.req("REQ-087")
@pytest.mark.parametrize("force", [False, True])
def test_report_write_failure_leaves_no_output(tmp_path, force):
    """Review 1.7 F-03: a report that cannot be written (after verification passes) exits 4 with OUT untouched."""
    d = sub(tmp_path, "f" if force else "n")
    src = d / "in.pdf"
    src.write_bytes(fixture_bytes("R1"))
    out = d / "out.pdf"
    if force:
        out.write_bytes(b"previous")
    terms = write_terms(d / "t.txt", [R1_TERM])
    args = ["apply", str(src), "--terms", str(terms), "-o", str(out), "--report", str(d / "missing" / "r.json")]
    res = invoke(args + (["--force"] if force else []))
    assert res.exit_code == 4
    if force:
        assert out.read_bytes() == b"previous"
    else:
        assert not out.exists()
    assert not [p for p in d.iterdir() if p.name.startswith(".inkproof-")]


@pytest.mark.req("REQ-055")
def test_audit_refuses_report_path_equal_to_audited_file(tmp_path):
    """Review 1.7 F-02: audit --report FILE exits 2 and leaves FILE unchanged."""
    d = sub(tmp_path, "au")
    src = d / "aud.pdf"
    src.write_bytes(fixture_bytes("A07"))
    before = sha256(src)
    res = invoke(["audit", str(src), "--patterns", "email", "--report", str(src)])
    assert res.exit_code == 2 and sha256(src) == before
