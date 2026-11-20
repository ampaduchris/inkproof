"""Built-in patterns (spec 5.3 and 5.4). Each finder works on normalised text and returns (start, end, kind)."""

from __future__ import annotations

import json
import re
from importlib import resources
from typing import Callable, Iterator

from inkproof.normalise import is_unit

NAMES = ("iban", "de-tax-id", "uk-ni", "email")
Found = tuple[int, int, str]

_START = r"(?<![^\W_])"
_END = r"(?![^\W_])"
_EXACT_GAPS = re.compile(r"\S+(?: \S+)*")


def _kind(span: str) -> str:
    """Exact when every white space run is one plain space (or there is none); loose otherwise."""
    return "exact" if _EXACT_GAPS.fullmatch(span) else "loose"


def _length_table() -> dict[str, int]:
    raw = resources.files("inkproof").joinpath("data", "iban_lengths.json").read_text(encoding="utf-8")
    return json.loads(raw)["lengths"]


_LENGTHS: dict[str, int] | None = None


def iban_mod97(compact: str) -> bool:
    moved = compact[4:] + compact[:4]
    return int("".join(str(int(c, 36)) for c in moved)) % 97 == 1


_IBAN_HEAD = re.compile(_START + r"[a-z]{2}[0-9]{2}")


def find_iban(text: str) -> Iterator[Found]:
    global _LENGTHS
    if _LENGTHS is None:
        _LENGTHS = _length_table()
    pos = 0
    while True:
        head = _IBAN_HEAD.search(text, pos)
        if not head:
            return
        start = head.start()
        length = _LENGTHS.get(text[start:start + 2].upper())
        pos = start + 1
        if length is None:
            continue
        i, count = start, 0
        ok = True
        while count < length:
            if i >= len(text):
                ok = False
                break
            c = text[i]
            if c.isspace() and count % 4 == 0 and count > 0:
                while i < len(text) and text[i].isspace():
                    i += 1
                continue
            if not (c.isascii() and c.isalnum()):
                ok = False
                break
            count += 1
            i += 1
        if not ok or (i < len(text) and is_unit(text[i])):
            continue
        span = text[start:i]
        compact = re.sub(r"\s+", "", span).upper()
        if iban_mod97(compact):
            yield start, i, _kind(span)
            pos = i


def check_digit_de_tax_id(first_ten: str) -> int:
    """ISO 7064 MOD 11,10 check digit (spec 5.4)."""
    product = 10
    for ch in first_ten:
        total = (int(ch) + product) % 10
        if total == 0:
            total = 10
        product = (2 * total) % 11
    check = 11 - product
    return 0 if check == 10 else check


_TAX = re.compile(_START + r"(?:[0-9]{11}|[0-9]{2}\s+[0-9]{3}\s+[0-9]{3}\s+[0-9]{3})" + _END)


def find_de_tax_id(text: str) -> Iterator[Found]:
    for m in _TAX.finditer(text):
        digits = re.sub(r"\s+", "", m.group(0))
        if digits[0] != "0" and check_digit_de_tax_id(digits[:10]) == int(digits[10]):
            yield m.start(), m.end(), _kind(m.group(0))


_BAD_FIRST = set("dfiquv")
_BAD_SECOND = set("dfioquv")
_BAD_PREFIX = {"bg", "gb", "kn", "nk", "nt", "tn", "zz"}
_NI = re.compile(_START + r"(?:[a-z]{2}[0-9]{6}[a-d]|[a-z]{2}\s+[0-9]{2}\s+[0-9]{2}\s+[0-9]{2}\s+[a-d])" + _END)


def find_uk_ni(text: str) -> Iterator[Found]:
    for m in _NI.finditer(text):
        s = m.group(0)
        if s[0] in _BAD_FIRST or s[1] in _BAD_SECOND or s[:2] in _BAD_PREFIX:
            continue
        yield m.start(), m.end(), _kind(s)


_EMAIL = re.compile(
    r"(?<![a-z0-9._%+-])(?!\.)[a-z0-9._%+-]{1,64}(?<!\.)@"
    r"(?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,}" + _END
)


def find_email(text: str) -> Iterator[Found]:
    for m in _EMAIL.finditer(text):
        yield m.start(), m.end(), "exact"


FINDERS: dict[str, Callable[[str], Iterator[Found]]] = {
    "iban": find_iban, "de-tax-id": find_de_tax_id, "uk-ni": find_uk_ni, "email": find_email,
}
