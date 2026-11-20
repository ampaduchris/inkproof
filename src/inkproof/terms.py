"""The terms file (spec 5.2). Messages never contain a term: a term is identified by its line number."""

from __future__ import annotations

import re
from dataclasses import dataclass

from inkproof.normalise import count_units, normalise


class InputError(Exception):
    """Bad arguments or a bad input file. The message is safe to print: it holds no term and no document text."""


@dataclass(frozen=True)
class Term:
    line: int
    text: str
    norm: str


def parse_terms(data: bytes, allow_short: bool = False) -> list[Term]:
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise InputError("the terms file is not valid UTF-8") from None
    terms: list[Term] = []
    seen: set[str] = set()
    for number, raw in enumerate(re.split(r"\r\n|\n|\r", text), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        norm = " ".join(normalise(line).split())
        if not allow_short and count_units(norm) < 3:
            raise InputError(f"terms file line {number}: the term has fewer than three letters or digits "
                             f"(use --allow-short-terms to accept it)")
        if norm in seen:
            continue
        seen.add(norm)
        terms.append(Term(number, line, norm))
    if not terms:
        raise InputError("the terms file holds no terms")
    return terms
