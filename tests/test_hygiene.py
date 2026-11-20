"""Output hygiene, error masking, temporary files and network (spec 9.1, REQ-080 to REQ-083).

The audit case of REQ-080 arrives with audit mode in session 1.5.
"""

import os
import re
import tempfile
import unicodedata
from pathlib import Path

import pytest

from helpers import ALL_PATTERNS, FIXTURES, apply, fixture_bytes, sub

SECRET = "Rosselgar"          # R1 term canary
MESSAGE_TEXT = "Zelhol Selwen"  # R1 term canary, stands for text taken from the document


def values(fid: str) -> list[str]:
    return [c.value for c in FIXTURES[fid].canaries]


def leaks(blob: str, vals: list[str]) -> list[str]:
    """Canaries found in raw, normalised or space-stripped form."""
    norm = unicodedata.normalize("NFKC", blob).casefold()
    squashed = re.sub(r"\s+", "", norm)
    out = []
    for v in vals:
        n = unicodedata.normalize("NFKC", v).casefold()
        if v in blob or n in norm or re.sub(r"\s+", "", n) in squashed:
            out.append(v)
    return out


def everything(r, extra_text: str = "") -> str:
    parts = [r.stdout, r.stderr, extra_text]
    if r.report_path.exists():
        parts.append(r.report_path.read_text(encoding="utf-8"))
    return "\n".join(parts)


def force_internal_error(monkeypatch):
    import inkproof.apply as ap

    def boom(*a, **k):
        raise RuntimeError(f"failed on {SECRET} and {MESSAGE_TEXT}")
    monkeypatch.setattr(ap, "serialise", boom)


@pytest.mark.req("REQ-080")
def test_no_value_in_any_output(tmp_path, monkeypatch):
    vals = values("R1")
    terms = [c.value for c in FIXTURES["R1"].canaries if c.kind == "term"]
    cases = {}
    cases["apply success"] = apply(sub(tmp_path, "c1"), "R1", terms=terms, patterns=ALL_PATTERNS, report=True)
    cases["apply survivor"] = apply(sub(tmp_path, "c2"), "X08", terms=values("X08"), report=True)
    cases["bad terms file"] = apply(sub(tmp_path, "c3"), "R1", terms=terms + ["q7"])
    cases["corrupt input"] = apply(sub(tmp_path, "c4"), "X04", terms=terms,
                                   data=FIXTURES["X04"].files["X04-truncated.pdf"])
    expect = {"apply success": 0, "apply survivor": 1, "bad terms file": 2, "corrupt input": 3}
    for name, r in cases.items():
        assert r.exit_code == expect[name], name
        vs = values("X08") if name == "apply survivor" else vals + ["q7"]
        assert leaks(everything(r), vs) == [], name
    force_internal_error(monkeypatch)
    r = apply(sub(tmp_path, "c5"), "R1", terms=terms, patterns=ALL_PATTERNS, report=True)
    assert r.exit_code == 4
    assert leaks(everything(r), vals + [SECRET, MESSAGE_TEXT]) == []


@pytest.mark.req("REQ-081")
def test_internal_error_is_masked(tmp_path, monkeypatch):
    force_internal_error(monkeypatch)
    plain = apply(sub(tmp_path, "a"), "R1", terms=[SECRET])
    assert plain.exit_code == 4
    msg = (plain.stdout + plain.stderr)
    assert re.search(r"internal error.*\bE4\b|\bE4\b.*internal error", msg, re.I | re.S)
    assert "Traceback" not in msg and SECRET not in msg and MESSAGE_TEXT not in msg
    dbg = apply(sub(tmp_path, "b"), "R1", terms=[SECRET], extra=["--debug"])
    assert dbg.exit_code == 4
    text = dbg.stdout + dbg.stderr
    assert "Traceback" in text and "RuntimeError" in text and "boom" in text      # frames are shown
    assert SECRET not in text and MESSAGE_TEXT not in text                        # the message and locals are masked
    assert "failed on" not in text


@pytest.mark.req("REQ-082")
def test_temp_files_cleaned(tmp_path, monkeypatch):
    systmp = tmp_path / "systmp"
    systmp.mkdir()
    monkeypatch.setenv("TMPDIR", str(systmp))
    monkeypatch.setattr(tempfile, "tempdir", None)

    def listing(d: Path) -> list[str]:
        return sorted(str(p.relative_to(d)) for p in d.rglob("*"))
    runs = [(0, "R1", [SECRET], None), (1, "X08", ["Denkelhol"], None),
            (3, "X03", ["Tavnorzel"], None)]
    for code, fid, terms, _ in runs:
        d = sub(tmp_path, f"w{code}")
        r = apply(d, fid, terms=terms)
        assert r.exit_code == code
        left = [n for n in listing(d) if n not in ("in.pdf", "terms.txt", "out.pdf", "out.pdf.report.json")]
        assert left == [] and listing(systmp) == [], (code, left, listing(systmp))
    force_internal_error(monkeypatch)
    d = sub(tmp_path, "w4")
    r = apply(d, "R1", terms=[SECRET])
    assert r.exit_code == 4
    assert [n for n in listing(d) if n not in ("in.pdf", "terms.txt", "out.pdf.report.json")] == []
    assert listing(systmp) == []


@pytest.mark.req("REQ-083")
def test_no_network(tmp_path):
    import socket
    from conftest import NetworkBlocked
    with pytest.raises(NetworkBlocked):
        socket.socket().connect(("127.0.0.1", 9))                              # the block is active
    r = apply(tmp_path, "R1", terms=[SECRET], patterns=ALL_PATTERNS)
    assert r.exit_code == 0                                                   # the tool works with no network at all
    src = Path(__file__).parent.parent / "src" / "inkproof"
    code = "\n".join(p.read_text(encoding="utf-8") for p in src.rglob("*.py"))
    assert not re.search(r"^\s*(import|from)\s+(socket|urllib|http|requests|httpx|ssl|ftplib|smtplib)\b", code, re.M)
