"""Properties P1 to P8 (spec 11.3), written with Hypothesis.

Each test names the property it proves and carries the requirement ids it supports. Examples are derandomised
so that CI is stable: the same inputs run every time. Test data holds no real value; every canary is generated.
"""

import json
import re
from importlib import resources

import pytest
from hypothesis import example, given, settings, strategies as st

from inkproof.matcher import Matcher, merge_extents
from inkproof.normalise import is_unit, normalise
from inkproof.terms import parse_terms

settings.register_profile("inkproof", derandomize=True, max_examples=200, deadline=None)
settings.load_profile("inkproof")

ALNUM_UPPER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
LENGTHS = json.loads(resources.files("inkproof").joinpath("data", "iban_lengths.json").read_text("utf-8"))["lengths"]


def find(pattern: str, text: str):
    return Matcher(terms=[], patterns=[pattern]).find(text)


def find_term(term: str, text: str, **kw):
    return Matcher(terms=parse_terms(term.encode("utf-8"), allow_short=True), patterns=[], **kw).find(text)


def groups(s: str, sizes: list[int]) -> str:
    out, i = [], 0
    for n in sizes:
        out.append(s[i:i + n])
        i += n
    return " ".join(out)


# --- P1 ----------------------------------------------------------------------------------------------------

words = st.text(alphabet=st.sampled_from("abcdefghijklmnopqrstuvwxyzABCXYZ0123456789"), min_size=3, max_size=12)
units = st.text(alphabet=st.sampled_from("abcxyzABC019éß"), min_size=1, max_size=4)
non_units = st.text(alphabet=st.sampled_from(" \n\t.,;:!?()-_/\"'"), min_size=1, max_size=3)


@pytest.mark.req("REQ-016")
@given(term=words, left=units, right=units, nl=non_units, nr=non_units, side=st.sampled_from(["both", "left", "right"]))
def test_p1_term_boundaries(term, left, right, nl, nr, side):
    """P1: units on either side of a term mean no match; non-units on both sides mean exactly one."""
    glued_left = left if side in ("both", "left") else nl
    glued_right = right if side in ("both", "right") else nr
    assert find_term(term, f"{glued_left}{term}{glued_right}") == []
    ms = find_term(term, f"{nl}{term}{nr}")
    assert len(ms) == 1 and (ms[0].start, ms[0].end) == (len(nl), len(nl) + len(term))


# --- P2 ----------------------------------------------------------------------------------------------------

def iban_check(country: str, body: str) -> str:
    """Check digits by the ISO 13616 rule, written here from the spec and not taken from the matcher."""
    n = int("".join(str(int(c, 36)) for c in body + country + "00"))
    return f"{country}{98 - n % 97:02d}{body}"


@st.composite
def valid_ibans(draw):
    country = draw(st.sampled_from(sorted(LENGTHS)))
    body = draw(st.text(alphabet=ALNUM_UPPER, min_size=LENGTHS[country] - 4, max_size=LENGTHS[country] - 4))
    return iban_check(country, body)


@pytest.mark.req("REQ-020")
@given(v=valid_ibans(), grouped=st.booleans(), lower=st.booleans())
def test_p2_valid_iban_matches(v, grouped, lower):
    """P2 (first half): any generated valid IBAN matches, compact or in groups of four, in either case."""
    form = groups(v, [4] * ((len(v) + 3) // 4)).strip() if grouped else v
    form = form.lower() if lower else form
    text = f"account {form} end"
    ms = find("iban", text)
    assert [text[m.start:m.end] for m in ms] == [form]


@pytest.mark.req("REQ-020")
@settings(max_examples=1500)
@given(v=valid_ibans(), data=st.data())
def test_p2_changed_character_does_not_match(v, data):
    """P2 (second half, narrowed, DEV-026): changing any single character to another of the same class (digit for
    digit, letter for letter) makes it not match. The mod 97 check guarantees this. A digit swapped for a letter
    can keep a valid check; see test_p2_digit_for_letter_can_still_match."""
    i = data.draw(st.integers(0, len(v) - 1))
    same_class = "0123456789" if v[i].isdigit() else "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    new = data.draw(st.sampled_from([c for c in same_class if c != v[i]]))
    changed = v[:i] + new + v[i + 1:]
    assert find("iban", f"account {changed} end") == []


@pytest.mark.req("REQ-020")
def test_p2_digit_for_letter_can_still_match():
    """DEV-026: the spec's P2 says any single change breaks a match. This value, a valid IBAN with one 0 changed to
    O, still passes ISO 13616 (checked below by the spec's own rule), so the matcher is right and P2 is too strong."""
    valid, changed = "FI26YE0T2000000000", "FI26YE0TO000000000"
    for v in (valid, changed):
        assert int("".join(str(int(c, 36)) for c in v[4:] + v[:4])) % 97 == 1 and len(v) == LENGTHS["FI"]
        assert len(find("iban", f"x {v} y")) == 1


# --- P3 ----------------------------------------------------------------------------------------------------

def mod_11_10(first_ten: str) -> int:
    """ISO 7064 MOD 11,10 as spec 5.4 states it, written here and not taken from the matcher."""
    product = 10
    for ch in first_ten:
        s = (int(ch) + product) % 10 or 10
        product = (s * 2) % 11
    c = 11 - product
    return 0 if c == 10 else c


ten_digits = st.text(alphabet="0123456789", min_size=9, max_size=9).flatmap(
    lambda tail: st.integers(1, 9).map(lambda d: f"{d}{tail}"))


@pytest.mark.req("REQ-022")
@given(ten=ten_digits, grouped=st.booleans(), wrong=st.integers(1, 9))
def test_p3_de_tax_id(ten, grouped, wrong):
    """P3: ten digits (first non-zero) plus the computed check digit match; any other eleventh digit does not."""
    check = mod_11_10(ten)

    def form(d: int) -> str:
        v = f"{ten}{d}"
        return f"{v[:2]} {v[2:5]} {v[5:8]} {v[8:]}" if grouped else v

    good = f"id {form(check)} end"
    assert [good[m.start:m.end] for m in find("de-tax-id", good)] == [form(check)]
    other = (check + wrong) % 10
    assert find("de-tax-id", f"id {form(other)} end") == []
    zero = "0" + ten[1:]
    v0 = f"{zero}{mod_11_10(zero)}"
    assert find("de-tax-id", f"id {v0} end") == []                       # a leading zero never matches


# --- P4 ----------------------------------------------------------------------------------------------------

BAD_PREFIXES = ["BG", "GB", "KN", "NK", "NT", "TN", "ZZ"]
FIRST_OK = "ABCEGHJKLMNOPRSTWXYZ"          # not D F I Q U V
SECOND_OK = "ABCEGHJKLMNPRSTWXYZ"          # not D F I O Q U V


@st.composite
def ni_numbers(draw):
    prefix = draw(st.tuples(st.sampled_from(FIRST_OK), st.sampled_from(SECOND_OK)).map("".join)
                  .filter(lambda p: p not in BAD_PREFIXES))
    digits = draw(st.text(alphabet="0123456789", min_size=6, max_size=6))
    return prefix, digits, draw(st.sampled_from("ABCD"))


def ni_form(prefix: str, digits: str, suffix: str, spaced: bool) -> str:
    return f"{prefix} {digits[:2]} {digits[2:4]} {digits[4:]} {suffix}" if spaced else f"{prefix}{digits}{suffix}"


@pytest.mark.req("REQ-024")
@given(parts=ni_numbers(), spaced=st.booleans(), data=st.data())
def test_p4_uk_ni(parts, spaced, data):
    """P4: the allowed alphabet matches; any excluded prefix, or a suffix beyond D, does not."""
    prefix, digits, suffix = parts
    text = f"ni {ni_form(prefix, digits, suffix, spaced)} end"
    assert [text[m.start:m.end] for m in find("uk-ni", text)] == [ni_form(prefix, digits, suffix, spaced)]
    excluded = data.draw(st.one_of(
        st.sampled_from(BAD_PREFIXES),
        st.tuples(st.sampled_from("DFIQUV"), st.sampled_from(string_letters())).map("".join),
        st.tuples(st.sampled_from(string_letters()), st.sampled_from("DFIOQUV")).map("".join)))
    assert find("uk-ni", f"ni {ni_form(excluded, digits, suffix, spaced)} end") == []
    late = data.draw(st.sampled_from([c for c in "EFGHIJKLMNOPQRSTUVWXYZ"]))
    assert find("uk-ni", f"ni {ni_form(prefix, digits, late, spaced)} end") == []


def string_letters() -> str:
    return "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


# --- P5 ----------------------------------------------------------------------------------------------------

LOCAL_CHARS = "abcxyzABC019._%+-"
label_inner = st.text(alphabet="abcxyz019-", min_size=0, max_size=8)
label = st.tuples(st.sampled_from("abcxyz019"), label_inner, st.sampled_from("abcxyz019")).map("".join) | \
    st.sampled_from("abcxyz019")
local = st.text(alphabet=LOCAL_CHARS, min_size=1, max_size=64).filter(lambda s: not s.startswith(".") and not s.endswith("."))
tld = st.text(alphabet="abcxyzABC", min_size=2, max_size=6)
domains = st.tuples(st.lists(label, min_size=1, max_size=3), tld).map(lambda t: ".".join(t[0] + [t[1]]))


@pytest.mark.req("REQ-025")
@given(loc=local, dom=domains)
def test_p5_email_grammar(loc, dom):
    """P5: any address built from the spec grammar matches as one whole match."""
    addr = f"{loc}@{dom}"
    text = f"mail {addr} now"
    ms = find("email", text)
    assert [text[m.start:m.end] for m in ms] == [addr]
    assert [m for m in find("email", f"mail {loc}@{dom[:-len(dom.rsplit('.', 1)[1])]}x now")
            if m.end - m.start == len(loc) + 1 + len(dom) - len(dom.rsplit(".", 1)[1]) + 1] == []  # one-letter ending


# --- P6 ----------------------------------------------------------------------------------------------------

NORMALISE_STRESS = st.text(alphabet=st.sampled_from(["a", "e", "\u200d", "\u00ad", "\u0301", "\ufb01", "\u0130", " "]),
                           max_size=8)


@pytest.mark.req("REQ-013")
@given(s=st.one_of(st.text(), NORMALISE_STRESS))
@example("a\u200d\u0301")
def test_p6_normalise_idempotent(s):
    """P6: normalising twice equals normalising once (holds since session 1.8; see DEV-024)."""
    once = normalise(s)
    assert normalise(once) == once


@pytest.mark.req("REQ-013")
def test_p6_normalise_idempotent_without_dropped_characters():
    """P6 narrowed: idempotent on text with no soft hyphen or zero-width character. Passes."""
    @given(s=st.text().filter(lambda t: not any(c in t for c in "\u00ad\u200b\u200c\u200d\u2060\ufeff")))
    def inner(s):
        assert normalise(normalise(s)) == normalise(s)
    inner()


# --- P7 ----------------------------------------------------------------------------------------------------

term_words = st.lists(st.text(alphabet="abcxyz019", min_size=2, max_size=6), min_size=1, max_size=3)
ws_runs = st.text(alphabet=st.sampled_from(" \t\n\r"), min_size=1, max_size=4)


@pytest.mark.req("REQ-014")
@given(ws=term_words, data=st.data())
def test_p7_white_space_between_words_keeps_exact_match(ws, data):
    """P7 (first half): any white space runs between the words of a term still give an exact match."""
    term = " ".join(ws)
    runs = [data.draw(ws_runs) for _ in ws[1:]]
    text = " " + ws[0] + "".join(r + w for r, w in zip(runs, ws[1:])) + " "
    ms = find_term(term, text)
    assert [m.kind for m in ms] == ["exact"]
    assert (ms[0].start, ms[0].end) == (1, len(text) - 1)


@pytest.mark.req("REQ-015")
@given(ws=term_words, data=st.data())
def test_p7_white_space_inside_a_word_gives_loose_match(ws, data):
    """P7 (second half): white space inside a word gives a loose match and no exact one."""
    k = data.draw(st.integers(0, len(ws) - 1))
    at = data.draw(st.integers(1, len(ws[k]) - 1))
    broken = ws[:k] + [ws[k][:at] + data.draw(ws_runs) + ws[k][at:]] + ws[k + 1:]
    ms = find_term(" ".join(ws), " " + " ".join(broken) + " ")
    assert [m.kind for m in ms] == ["loose"]


# --- P8 ----------------------------------------------------------------------------------------------------

PLANTED = ["DE89370400440532013000", "DE89 3704 0044 0532 0130 00", "86095742719", "AA123456A", "a.b@example.org",
           "tavhol", "tav hol", "tav-\nhol"]
pieces = st.sampled_from(PLANTED + ["abc", "a", "b", "c", " ", "\n", "-", ".", "@", "1", "ﬁ", "­", "é"])
sources = st.fixed_dictionaries({
    "terms": st.lists(st.sampled_from(["tavhol", "tav hol", "abc", "ab c", "example"]), max_size=3, unique=True),
    "patterns": st.lists(st.sampled_from(["iban", "de-tax-id", "uk-ni", "email"]), max_size=4, unique=True),
})


@pytest.mark.req("REQ-027")
@given(parts=st.lists(pieces, max_size=14), src=sources)
def test_p8_extents_are_inside_the_text_and_agree_with_the_matcher(parts, src):
    """P8 (first half): every extent lies inside the text, is non-empty, and merging keeps them inside."""
    text = "".join(parts)
    matcher = Matcher(terms=parse_terms("\n".join(src["terms"]).encode(), allow_short=True) if src["terms"] else [],
                      patterns=src["patterns"])
    ms = matcher.find(text)
    for m in ms:
        assert 0 <= m.start < m.end <= len(text)
    for a, b in merge_extents(ms):
        assert 0 <= a < b <= len(text)
        assert any(m.start >= a and m.end <= b for m in ms)


@pytest.mark.req("REQ-027")
@pytest.mark.xfail(strict=True, reason="DEV-025: removing a loose-matchable word can join its neighbours into a new "
                                       "loose match; spec P8 does not hold")
@given(parts=st.lists(pieces, max_size=14), src=sources)
@example(parts=["ab", " ", "abc", " ", "c"], src={"terms": ["abc"], "patterns": []})
def test_p8_removing_all_extents_leaves_no_match(parts, src):
    """P8 (second half): after every merged extent is removed, the matcher finds nothing in what is left.

    Fails today: see DEV-025. `ab abc c` loses `abc` and becomes `ab  c`, which the loose rule matches."""
    text = "".join(parts)
    matcher = Matcher(terms=parse_terms("\n".join(src["terms"]).encode(), allow_short=True) if src["terms"] else [],
                      patterns=src["patterns"])
    extents = merge_extents(matcher.find(text))
    left, pos = [], 0
    for a, b in extents:
        left.append(text[pos:a])
        pos = b
    left.append(text[pos:])
    assert matcher.find("".join(left)) == []
