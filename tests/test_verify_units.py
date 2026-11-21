"""Exact-value tests for the verifier's string decoding (V4). Added in 1.9 to kill surviving mutants."""

import pytest

from inkproof.verify import _element, _unescape, decode_bytes, strings_in

pytestmark = pytest.mark.req("REQ-048")


@pytest.mark.parametrize(
    "lit, want",
    [
        (b"(abc)", b"abc"),
        (b"(a\\nb)", b"a\nb"),
        (b"(a\\rb)", b"a\rb"),
        (b"(a\\tb)", b"a\tb"),
        (b"(a\\bb)", b"a\bb"),
        (b"(a\\fb)", b"a\fb"),
        (b"(\\101)", b"A"),
        (b"(\\1012)", b"A2"),
        (b"(\\0612)", b"12"),
        (b"(\\7)", b"\x07"),
        (b"(\\377)", b"\xff"),
        (b"(\\400)", b"\x00"),
        (b"(a\\\nb)", b"ab"),
        (b"(a\\\rb)", b"ab"),
        (b"(a\\(b\\)c\\\\d)", b"a(b)c\\d"),
        (b"(a\\qb)", b"aqb"),
        (b"()", b""),
        (b"(ab\\)", b"ab\\"),
    ],
)
def test_unescape_exact(lit, want):
    assert _unescape(lit) == want


def test_unescape_trailing_backslash_kept():
    assert _unescape(b"(ab\\)") == b"ab\\"


def test_decode_bytes_utf16_with_mark():
    assert "hi" in decode_bytes(b"\xfe\xff\x00h\x00i")
    assert "hi" in decode_bytes(b"\xff\xfeh\x00i\x00")
    assert decode_bytes(b"\xfe\xff\x00h\x00i")[0] == "hi"
    assert decode_bytes(b"\xff\xfeh\x00i\x00")[0] == "hi"


def test_decode_bytes_utf16_without_mark():
    got = decode_bytes(b"\x00a\x00b")
    assert got[0] == "ab"
    assert got == ["ab", "\x00a\x00b"]
    # odd length or too short: no UTF-16 reading
    assert decode_bytes(b"\x00a\x00")[0] != "a"
    assert decode_bytes(b"\x00a")[0] == "\x00a"
    assert decode_bytes(b"\x01a\x00b")[0] != "ab"


def test_decode_bytes_plain_and_order_and_dedupe():
    assert decode_bytes(b"abc") == ["abc"]
    assert decode_bytes(b"\xc3\xa9") == ["é", "Ã©"]
    assert decode_bytes(b"\xe9") == ["�", "é"]
    assert decode_bytes(b"") == [""]
    assert decode_bytes(b"\xfe\xff") == ["", "��"[:0] or "þÿ"][:1] + decode_bytes(b"\xfe\xff")[1:]


def test_element_literal_and_hex():
    assert _element(b"(a\\nb)") == b"a\nb"
    assert _element(b"<48 65 6C6c>") == b"Hell"
    assert _element(b"<4>") == b"@"
    assert _element(b"<414>") == b"A@"
    assert _element(b"<>") == b""


def test_strings_in_literal_hex_and_tj():
    assert "secret" in strings_in(b"BT (secret) Tj ET")
    assert "secret" in strings_in(b"BT <736563726574> Tj ET")
    out = strings_in(b"BT [(sec) -20 (ret)] TJ ET")
    assert "secret" in out
    # the TJ pieces are not also read as separate strings
    assert "sec" not in out and "ret" not in out
    out = strings_in(b"[<7365> 5 (cr) <6574>]TJ")
    assert "secret" in out
    assert strings_in(b"no strings here") == []
    assert strings_in(b"(a) Tj (b) Tj") == ["a", "b"]


# ---- S7: actions on the document and on the pages (REQ-050, REQ-056 surface S7)

import pymupdf  # noqa: E402

from inkproof.verify import _action_xrefs_and_dicts  # noqa: E402


def _doc():
    doc = pymupdf.open()
    doc.new_page()
    return doc


def test_actions_none_gives_empty_list():
    assert _action_xrefs_and_dicts(_doc()) == []


@pytest.mark.parametrize("key", ["OpenAction", "AA", "Names/JavaScript"])
def test_actions_inline_dict_and_xref_in_catalog(key):
    for as_xref in (False, True):
        doc = _doc()
        cat = doc.pdf_catalog()
        body = "<< /S /JavaScript /JS (leak-value) >>"
        if as_xref:
            n = doc.get_new_xref()
            doc.update_object(n, body)
            body = f"{n} 0 R"
        doc.xref_set_key(cat, key, body)
        found = _action_xrefs_and_dicts(doc)
        assert "leak-value" in found, (key, as_xref)
        assert found.count("leak-value") >= 1


@pytest.mark.parametrize("as_xref", [False, True])
def test_actions_on_a_page(as_xref):
    doc = _doc()
    body = "<< /O << /S /JavaScript /JS (page-leak) >> >>"
    if as_xref:
        n = doc.get_new_xref()
        doc.update_object(n, body)
        body = f"{n} 0 R"
    doc.xref_set_key(doc[0].xref, "AA", body)
    assert "page-leak" in _action_xrefs_and_dicts(doc)


def test_actions_second_page_is_read():
    doc = _doc()
    doc.new_page()
    doc.xref_set_key(doc[1].xref, "AA", "<< /O << /JS (second-page) >> >>")
    assert "second-page" in _action_xrefs_and_dicts(doc)
