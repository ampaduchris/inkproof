"""Normalisation of terms and document text (spec section 3)."""

from __future__ import annotations

import unicodedata

_DROP = {0xAD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}


def normalise(s: str) -> str:
    """NFKC, then remove the soft hyphen and zero-width characters, then full case folding."""
    s = unicodedata.normalize("NFKC", s)
    s = "".join(c for c in s if ord(c) not in _DROP)
    return s.casefold()


def is_unit(c: str) -> bool:
    """A unit is a letter or a digit (Unicode general categories L and N)."""
    return unicodedata.category(c)[0] in "LN"


def count_units(s: str) -> int:
    return sum(1 for c in s if is_unit(c))


def normalise_with_map(text: str) -> tuple[str, list[int], list[int]]:
    """Normalise `text` and keep, for each normalised character, the span of original characters it came from.

    A base character and the combining marks after it are normalised together, so that a decomposed accent
    composes as NFKC requires. Returns (normalised text, start index, end index exclusive) per character.
    """
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    i, n = 0, len(text)
    while i < n:
        j = i + 1
        while j < n and unicodedata.category(text[j]).startswith("M"):
            j += 1
        piece = normalise(text[i:j])
        for ch in piece:
            out.append(ch)
            starts.append(i)
            ends.append(j)
        i = j
    return "".join(out), starts, ends
