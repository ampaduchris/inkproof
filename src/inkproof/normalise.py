"""Normalisation of terms and document text (spec section 3)."""

from __future__ import annotations

import unicodedata

_DROP = {0xAD, 0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF}


def normalise(s: str) -> str:
    """Remove the soft hyphen and zero-width characters, then NFKC, then full case folding.

    The characters are removed first so that a base letter and a combining mark that they separate still compose
    (REQ-013). Removing them again after NFKC keeps the result stable if a compatibility mapping produces one."""
    s = "".join(c for c in s if ord(c) not in _DROP)
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
    composes as NFKC requires. Dropped characters are skipped when the groups are formed, so a zero-width
    character between a base and its mark does not split them; it lies inside the group's span.
    Returns (normalised text, start index, end index exclusive) per character.
    """
    out: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    kept = [k for k, c in enumerate(text) if ord(c) not in _DROP]
    a, m = 0, len(kept)
    while a < m:
        b = a + 1
        while b < m and unicodedata.category(text[kept[b]]).startswith("M"):
            b += 1
        piece = normalise("".join(text[k] for k in kept[a:b]))
        for ch in piece:
            out.append(ch)
            starts.append(kept[a])
            ends.append(kept[b - 1] + 1)
        a = b
    return "".join(out), starts, ends
