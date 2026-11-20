"""Verification of the serialised output (spec 6.1, REQ-045 to REQ-051)."""

import pymupdf
import pytest
import typer

from helpers import FIXTURES, apply, fixture_bytes, sub
from inkproof.cli import app
from inkproof.matcher import Matcher
from inkproof.terms import parse_terms

ALL_CHECKS = ("V1", "V2", "V3", "V4", "V5")


def matcher(*terms: str, patterns=()):
    return Matcher(terms=parse_terms("\n".join(terms).encode()), patterns=list(patterns))


def checks(report):
    return {c["id"]: c["result"] for c in report["checks"]}


@pytest.mark.req("REQ-045")
def test_no_skip_verify_option():
    opts = {o for p in typer.main.get_command(app).commands["apply"].params for o in p.opts}
    assert not [o for o in opts if any(w in o for w in ("skip", "no-verify", "unsafe", "fast", "trust"))]


@pytest.mark.req("REQ-045")
def test_verify_always_runs(tmp_path, monkeypatch):
    import inkproof.apply as ap
    calls = []
    real = ap.verify
    monkeypatch.setattr(ap, "verify", lambda *a, **k: calls.append(1) or real(*a, **k))
    assert apply(sub(tmp_path, "ok"), "R1", terms=["Rosselgar"]).exit_code == 0
    assert len(calls) == 1
    assert apply(sub(tmp_path, "bad"), "X08", terms=["Denkelhol"]).exit_code == 1
    assert len(calls) == 2


@pytest.mark.req("REQ-046")
def test_verify_uses_serialised_bytes(tmp_path, monkeypatch):
    import inkproof.apply as ap
    real = ap.serialise

    def poisoned(doc, *a, **k):
        data = real(doc, *a, **k)
        doc.close()                                                       # the edited in-memory document is gone
        return data
    monkeypatch.setattr(ap, "serialise", poisoned)
    r = apply(tmp_path, "R1", terms=["Rosselgar"], patterns="iban,email", report=True)
    assert r.exit_code == 0 and set(checks(r.report)) == set(ALL_CHECKS)
    assert set(checks(r.report).values()) == {"pass"}


@pytest.mark.req("REQ-047")
def test_two_engines_listed_in_report(tmp_path):
    r = apply(tmp_path, "R1", terms=["Rosselgar"], report=True)
    by_id = {c["id"]: c for c in r.report["checks"]}
    assert by_id["V1"]["engine"] != by_id["V2"]["engine"]
    assert {by_id["V1"]["engine"], by_id["V2"]["engine"]} == {"pymupdf", "pdfminer.six"}
    from importlib import metadata
    assert by_id["V2"]["engine_version"] == metadata.version("pdfminer.six")


@pytest.mark.req("REQ-047")
def test_each_engine_catches_alone(tmp_path, monkeypatch):
    import inkproof.apply as ap
    import inkproof.verify as vf
    monkeypatch.setattr(ap, "remove_s1", lambda *a, **k: [])               # leave the canary in place
    monkeypatch.setattr(vf, "v2_text", lambda data: "")                    # engine B returns nothing
    a = apply(sub(tmp_path, "a"), "R1", terms=["Rosselgar"], report=True)
    assert a.exit_code == 1 and checks(a.report)["V1"] == "fail"
    monkeypatch.undo()
    monkeypatch.setattr(ap, "remove_s1", lambda *a, **k: [])
    monkeypatch.setattr(vf, "v1_text", lambda data, *x: "")                # engine A returns nothing
    b = apply(sub(tmp_path, "b"), "R1", terms=["Rosselgar"], report=True)
    assert b.exit_code == 1 and checks(b.report)["V2"] == "fail"


@pytest.mark.req("REQ-048")
def test_raw_scan_encodings():
    from inkproof.verify import verify
    terms = [c.value for c in FIXTURES["X02"].canaries]
    res = verify(fixture_bytes("X02"), matcher(*terms))
    found = {(f["source"]["id"], f["surface"]) for f in res.findings if f["surface"] == "S11"}
    assert found == {(i + 1, "S11") for i in range(3)}                     # hex string, UTF-16, split TJ elements
    assert dict((c.id, c.result) for c in res.checks)["V4"] == "fail"


def _stub_survivor(monkeypatch, check: str):
    """Leave one canary in place and silence every other check, so that only `check` can fail."""
    import inkproof.apply as ap
    import inkproof.verify as vf
    monkeypatch.setattr(ap, "remove_s1", lambda *a, **k: [])
    monkeypatch.setattr(ap, "strip_surfaces", lambda *a, **k: ap.empty_actions())
    silent = {"V1": ("v1_text", lambda *a: ""), "V2": ("v2_text", lambda *a: ""),
              "V3": ("v3_strings", lambda *a: []), "V4": ("v4_strings", lambda *a: [])}
    for k, (name, fn) in silent.items():
        if k != check and k in silent:
            monkeypatch.setattr(vf, name, fn)


@pytest.mark.req("REQ-049")
@pytest.mark.parametrize("check,fid,term,surface", [
    ("V1", "R1", "Rosselgar", "S1"), ("V2", "R1", "Rosselgar", "S1"),
    ("V3", "A10", "Wenwenyar", "S4"), ("V4", "X02", "Quinulmmar", "S11")])
def test_survivor_fails_closed(tmp_path, monkeypatch, check, fid, term, surface):
    _stub_survivor(monkeypatch, check)
    d = sub(tmp_path, "run")
    (d / "out.pdf").write_bytes(b"previous")
    r = apply(d, fid, terms=[term], report=True, extra=["--force"])
    assert r.exit_code == 1
    assert (d / "out.pdf").read_bytes() == b"previous"                    # nothing was written
    assert checks(r.report)[check] == "fail"
    f = [x for x in r.report["findings"] if x["surface"] == surface]
    assert f and f[0]["source"] == {"type": "term", "id": 1} and f[0]["count"] >= 1
    assert r.report["result"] == "leaks-found" and r.report["output"] is None


@pytest.mark.req("REQ-049")
def test_survivor_fails_closed_v5(tmp_path, monkeypatch):
    import inkproof.apply as ap
    monkeypatch.setattr(ap, "serialise", lambda doc, *a, **k: fixture_bytes("A07"))   # two revisions
    r = apply(tmp_path, "A07", terms=["Denvorfen"], report=True)
    assert r.exit_code == 1 and not r.out.exists()
    assert checks(r.report)["V5"] == "fail"
    f = r.report["findings"][0]
    assert (f["surface"], f["revision"], f["class"], f["count"]) == ("S1", 1, "earlier-revision", 1)


@pytest.mark.req("REQ-050")
def test_verify_only_surfaces_fail_closed(tmp_path):
    terms = [c.value for c in FIXTURES["X08"].canaries]
    r = apply(tmp_path, "X08", terms=terms, report=True)
    assert r.exit_code == 1 and not r.out.exists()
    hits = {(f["surface"], f["source"]["id"]) for f in r.report["findings"] if f["surface"] in ("S5", "S10")}
    assert {s for s, _ in hits} == {"S5", "S10"}
    assert {i for s, i in hits if s == "S5"} == {1, 2, 3}                 # named destinations (both forms), page label
    assert {i for s, i in hits if s == "S10"} == {4}                      # layer name


@pytest.mark.req("REQ-051")
def test_report_checks_section(tmp_path):
    r = apply(tmp_path, "R1", terms=["Rosselgar"], report=True)
    assert [c["id"] for c in r.report["checks"]] == list(ALL_CHECKS)
    for c in r.report["checks"]:
        assert c["engine"] and c["engine_version"] and c["result"] == "pass"
    assert pymupdf.__version__ in {c["engine_version"] for c in r.report["checks"]}
