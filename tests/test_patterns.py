"""Built-in patterns (spec 5.3 and 5.4), by example. Properties P2 to P5 arrive in session 1.6."""

import random
from pathlib import Path

import pytest

from helpers import apply
from inkproof.matcher import Matcher
from inkproof.patterns import check_digit_de_tax_id

CORPUS = Path(__file__).parent / "data" / "corpus.txt"


def find(pattern: str, text: str, **kw):
    return Matcher(terms=[], patterns=[pattern], **kw).find(text)


def spans(ms, text):
    return [text[m.start:m.end] for m in ms]


def make_iban(country: str, body: str) -> str:
    """A string with valid ISO 13616 check digits for any length."""
    def mod(s: str) -> int:
        return int("".join(str(int(c, 36)) for c in s)) % 97
    return f"{country}{98 - mod(body + country + '00'):02d}{body}"


GROUPED = lambda s: " ".join(s[i:i + 4] for i in range(0, len(s), 4))  # noqa: E731
IBANS = ["DE89370400440532013000", "GB29NWBK60161331926819"]


@pytest.mark.req("REQ-020")
def test_iban_pattern():
    for v in IBANS:
        for form in (v, GROUPED(v)):
            text = f"account {form} checked"
            assert spans(find("iban", text), text) == [form], form
        assert [m.kind for m in find("iban", f"x {v} y")] == ["exact"]
        assert [m.kind for m in find("iban", f"x {GROUPED(v)} y")] == ["exact"]
        loose = "x " + GROUPED(v).replace(" ", "\n", 2) + " y"          # a line break between groups
        assert [m.kind for m in find("iban", loose)] == ["loose"]
        changed = v[:10] + ("1" if v[10] != "1" else "2") + v[11:]
        assert find("iban", f"x {changed} y") == []                      # one changed digit
        assert find("iban", f"x {v.lower()} y") != []                    # case is folded
    wrong = make_iban("DE", "370400440532013")                           # valid check digits, 19 characters
    assert len(wrong) == 19 and find("iban", f"x {wrong} y") == []
    unknown = make_iban("QQ", "370400440532013000")
    assert find("iban", f"x {unknown} y") == []                          # country not in the table
    assert find("iban", f"x {IBANS[0]}1 y") == []                        # touches a unit
    assert find("iban", f"xDE89370400440532013000") == []


@pytest.mark.req("REQ-022")
def test_de_tax_id_pattern():
    good = ["86095742719", "47036892816", "65929970489", "57549285017", "25768131411"]
    for v in good:
        for form in (v, f"{v[:2]} {v[2:5]} {v[5:8]} {v[8:]}"):
            text = f"number {form} on file"
            assert spans(find("de-tax-id", text), text) == [form]
    assert find("de-tax-id", "x 02476291358 y") == []                    # starts with 0
    bad = "86095742718"
    assert find("de-tax-id", f"x {bad} y") == []                         # changed check digit
    assert find("de-tax-id", "x 860957427190 y") == []                   # a 12-digit run
    assert find("de-tax-id", "x 186095742719 y") == []
    assert [check_digit_de_tax_id(v[:10]) for v in good] == [int(v[10]) for v in good]


@pytest.mark.req("REQ-024")
def test_uk_ni_pattern():
    for v in ("AA123456A", "AB123456D", "AA111111A"):
        for form in (v, f"{v[:2]} {v[2:4]} {v[4:6]} {v[6:8]} {v[8]}"):
            text = f"ni {form} end"
            assert spans(find("uk-ni", text), text) == [form]
    for first in "DFIQUV":
        assert find("uk-ni", f"x {first}A123456A y") == [], first
    for second in "DFIOQUV":
        assert find("uk-ni", f"x A{second}123456A y") == [], second
    for prefix in ("BG", "GB", "KN", "NK", "NT", "TN", "ZZ"):
        assert find("uk-ni", f"x {prefix}123456A y") == [], prefix
    assert find("uk-ni", "x AA123456E y") == []                          # suffix E
    assert find("uk-ni", "x QQ123456A y") == []


@pytest.mark.req("REQ-025")
def test_email_pattern():
    ok = ["anna.lee@example.org", "a@example.com", "x_y%z+tag@sub.example.net", "A-B@EXAMPLE.ORG",
          "n1@a-b.example.co.uk"]
    for v in ok:
        text = f"mail {v} now"
        ms = find("email", text)
        assert [text[m.start:m.end] for m in ms] == [v], v
    for v in [".anna@example.org", "anna.@example.org", "anna@example", "anna@example.c", "anna@-example.org",
              "@example.org", f"{'a' * 65}@example.org"]:
        text = f"mail {v} now"
        assert not [m for m in find("email", text) if text[m.start:m.end] == v], v
    assert find("email", "mail a@example.org1 now") == []
    text = "a.b@example.org."
    assert spans(find("email", text), text) == ["a.b@example.org"]       # a full stop ends the sentence


@pytest.mark.req("REQ-026")
def test_patterns_no_false_positives_on_corpus():
    from corpusgen import generate
    committed = CORPUS.read_text(encoding="utf-8")
    assert committed == generate()                                       # committed and generated from a seed
    assert len(committed.split()) == 10_000
    assert Matcher(terms=[], patterns=["iban", "de-tax-id", "uk-ni", "email"]).find(committed) == []


@pytest.mark.req("REQ-027")
def test_overlapping_matches(tmp_path):
    from inkproof.matcher import merge_extents
    from inkproof.terms import parse_terms
    text = "mail tavhol.r1@example.org now"
    ms = Matcher(terms=parse_terms(b"Tavhol\n"), patterns=["email"]).find(text)
    assert sorted(m.source for m in ms) == [("pattern", "email"), ("term", 1)]
    assert merge_extents(ms) == [(5, 26)]                                # one removal area
    r = apply(tmp_path, "R1", terms=["Tavhol"], patterns="email", report=True)
    assert r.exit_code == 0
    found = sorted((m["source"]["type"], m["count"]) for m in r.report["removed"])
    assert found == [("pattern", 1), ("term", 1)]                        # each source counted once
