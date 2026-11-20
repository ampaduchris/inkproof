"""Canary values and seeded text. All values are synthetic or issuer-published examples (RA-3, RA-4)."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

IBANS = ["DE89370400440532013000", "GB29NWBK60161331926819"]
TAX_IDS = ["86095742719", "47036892816", "65929970489", "57549285017", "25768131411"]
TAX_ID_NEGATIVE = "02476291358"
NI_NUMBERS = ["AA123456A", "AB123456D", "AA111111A"]
NI_NEGATIVE = "QQ123456A"

SYLLABLES = ["bar", "den", "fen", "gar", "hol", "jun", "kel", "lor", "mar", "nor", "pel", "quin", "ros", "sel",
             "tav", "ulm", "vor", "wen", "yar", "zel"]
FILLER = ("the office keeps a plain record of supplies orders and visits each week and the clerk checks the list "
          "before the shelves are filled again with paper pens folders and tape while the meeting room is cleaned "
          "on quiet mornings and the notes are filed in the grey cabinet by the window near the long corridor").split()

# Engines and checks, named as the spec names them for a surface.
S1_ENGINES = ("pymupdf-trace", "pdfminer", "pypdf")  # V1, V2 and the third engine of REQ-030


@dataclass(frozen=True)
class Canary:
    kind: str  # iban, de-tax-id, uk-ni, email, term
    value: str  # normalised form: what a matcher must find
    surface: str  # S1 ... S11
    count: int  # expected number of occurrences on that surface
    checks: tuple[str, ...]  # engines or checks that must find it
    absent: bool = False  # True: the fixture claims this value is gone from every surface
    note: str = ""


@dataclass
class Fixture:
    id: str
    files: dict[str, bytes]
    canaries: list[Canary] = field(default_factory=list)
    password: str | None = None
    meta: dict = field(default_factory=dict)


def word(fid: str, tag: str, n: int = 3) -> str:
    """A unique synthetic word per fixture and tag. Not a real name."""
    rng = random.Random(f"inkproof-1.3-{fid}-{tag}")
    return "".join(rng.choice(SYLLABLES) for _ in range(n)).capitalize()


def terms(fid: str) -> tuple[str, str, str]:
    """Return (first word, second word, single-word term) for a fixture."""
    return word(fid, "a", 2), word(fid, "b", 2), word(fid, "c", 3)


def email(fid: str, tag: str = "e") -> str:
    return f"{word(fid, tag, 2).lower()}.{fid.lower()}@example.org"


def prose(fid: str, n_lines: int, per_line: int = 11) -> list[str]:
    rng = random.Random(f"inkproof-1.3-prose-{fid}")
    return [" ".join(rng.choice(FILLER) for _ in range(per_line)) for _ in range(n_lines)]
