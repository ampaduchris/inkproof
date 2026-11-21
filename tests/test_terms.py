"""Terms file and term matching (spec 5.2, section 3 definitions)."""

import pytest

from helpers import apply, invoke, write_terms
from inkproof.matcher import Matcher
from inkproof.normalise import normalise
from inkproof.terms import InputError, parse_terms


def matches(term_lines: list[str], text: str, **kw):
    terms = parse_terms("\n".join(term_lines).encode(), allow_short=kw.pop("allow_short", False))
    return Matcher(terms=terms, patterns=[], **kw).find(text)


def spans(ms, text):
    return [text[m.start:m.end] for m in ms]


@pytest.mark.req("REQ-010")
@pytest.mark.parametrize("raw,expected", [
    (b"\xef\xbb\xbfZelfen\nBarvor\n", [(1, "zelfen"), (2, "barvor")]),            # byte order mark ignored
    (b"Zelfen\n\n\nBarvor\n", [(1, "zelfen"), (4, "barvor")]),                      # blank lines ignored
    (b"# a comment\nZelfen\n   # another\nBarvor\n", [(2, "zelfen"), (4, "barvor")]),  # comment lines ignored
    (b"   Zelfen \t\n\tBarvor  \n", [(1, "zelfen"), (2, "barvor")]),               # white space trimmed
    (b"Zelfen\r\nBarvor\r\n", [(1, "zelfen"), (2, "barvor")]),                      # CRLF line ends
    (b"Zelfen #1\n", [(1, "zelfen #1")]),                                           # a hash inside a line is text
])
def test_terms_parsing(raw, expected):
    got = [(t.line, t.norm) for t in parse_terms(raw)]
    assert got == expected


@pytest.mark.req("REQ-011")
def test_terms_file_errors(tmp_path):
    src = tmp_path / "in.pdf"
    from helpers import fixture_bytes
    src.write_bytes(fixture_bytes("R1"))
    out = tmp_path / "out.pdf"
    cases = {
        "missing": tmp_path / "no-such-file.txt",
        "not-utf8": tmp_path / "bad.txt",
        "no-terms": tmp_path / "empty.txt",
    }
    cases["not-utf8"].write_bytes(b"Zelfen\n\xff\xfe\xfa\n")
    cases["no-terms"].write_text("# only a comment\n\n   \n", encoding="utf-8")
    for name, path in cases.items():
        res = invoke(["apply", str(src), "--terms", str(path), "-o", str(out)])
        assert res.exit_code == 2, name
        assert not out.exists(), name


@pytest.mark.req("REQ-012")
def test_short_term_rejected(tmp_path):
    secret = "q7"
    r = apply(tmp_path, "R1", terms=["Zelhol Selwen", secret])
    assert r.exit_code == 2
    assert "line 2" in r.stdout + r.stderr                                # the line number
    assert secret not in r.stdout + r.stderr                              # never the term
    (tmp_path / "ok").mkdir()
    ok = apply(tmp_path / "ok", "R1", terms=[secret], extra=["--allow-short-terms"])
    assert ok.exit_code == 0
    with pytest.raises(InputError):
        parse_terms(b"ab\n")
    assert [t.line for t in parse_terms(b"ab\n", allow_short=True)] == [1]
    with pytest.raises(InputError):
        parse_terms("a­b\n".encode())                                # soft hyphen is not a unit


@pytest.mark.req("REQ-013")
def test_term_normalisation():
    t = "Zelfinn"
    assert spans(matches([t], "x ZELFINN y"), "x ZELFINN y") == ["ZELFINN"]       # upper case
    assert len(matches(["ZELFINN"], "a zelfinn b")) == 1                             # lower case in text
    lig = "a Zelﬁnn b"                                                           # ligature form
    assert spans(matches([t], lig), lig) == ["Zelﬁnn"]
    soft = "a Zel­finn b"                                                        # soft hyphen inside
    assert spans(matches([t], soft), soft) == ["Zel­finn"]
    zw = "a Zel‍finn b"                                                          # zero-width joiner inside
    assert spans(matches([t], zw), zw) == ["Zel‍finn"]
    assert normalise("Zel­​ﬁnn") == "zelfinn"


@pytest.mark.req("REQ-014")
def test_term_across_line_break():
    text = "visit by Zelhol\nSelwen in the register"
    ms = matches(["Zelhol Selwen"], text)
    assert [m.kind for m in ms] == ["exact"]
    assert spans(ms, text) == ["Zelhol\nSelwen"]
    text2 = "visit by Zelhol   \t Selwen in"
    assert [m.kind for m in matches(["Zelhol Selwen"], text2)] == ["exact"]


@pytest.mark.req("REQ-015")
def test_term_loose_match():
    text = "see Ze l fen now"                                   # stray white space inside a word
    ms = matches(["Zelfen"], text)
    assert [m.kind for m in ms] == ["loose"] and spans(ms, text) == ["Ze l fen"]
    text = "of Selz-\neljun was noted"                           # a word hyphenated at a line end
    ms = matches(["Selzeljun"], text)
    assert [m.kind for m in ms] == ["loose"] and spans(ms, text) == ["Selz-\neljun"]
    assert [m.kind for m in matches(["Zelfen"], "a Zelfen b")] == ["exact"]   # exact wins when both apply


@pytest.mark.req("REQ-016")
def test_term_boundaries():
    assert matches(["ann"], "the annual report") == []
    assert matches(["ann"], "a plann") == []
    assert matches(["ann"], "ann2") == []
    for text in ("the ann.", "(ann)", "ann"):
        assert len(matches(["ann"], text)) == 1, text
    assert len(matches(["ann"], "annual", substring=True)) == 1


@pytest.mark.req("REQ-017")
def test_duplicate_terms():
    terms = parse_terms(b"Zelfen\nBarvor\nZELFEN\n  zelfen \n")
    assert [t.line for t in terms] == [1, 2]
    ms = Matcher(terms=terms, patterns=[]).find("a Zelfen b")
    assert [m.source for m in ms] == [("term", 1)]


@pytest.mark.req("REQ-013")
@pytest.mark.parametrize("dropped", ["​", "‍", "­", "⁠", "﻿", "‌"])
def test_dropped_character_between_base_and_accent_still_matches(dropped):
    """Review 1.7 F-01: a dropped character between a letter and its combining accent must not split them."""
    term = "José Zqvara"
    text = "to Jose" + dropped + "́ Zqvara."
    found = matches([term], text)
    assert len(found) == 1
    assert spans(found, text) == ["Jose" + dropped + "́ Zqvara"]
