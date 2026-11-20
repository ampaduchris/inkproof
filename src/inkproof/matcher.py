"""Finds matches of terms and patterns in text (spec section 3 and 5)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from inkproof.normalise import is_unit, normalise_with_map
from inkproof.patterns import FINDERS
from inkproof.terms import Term

_START = r"(?<![^\W_])"
_END = r"(?![^\W_])"
_GAP_PLAIN = r"\s*"
_GAP_HYPHEN = r"(?:\s*-\s*\n\s*|\s+)?"


@dataclass(frozen=True)
class Match:
    source: tuple[str, int | str]   # ("term", line number) or ("pattern", name)
    kind: str                        # "exact" or "loose"
    start: int                       # index in the text given to find()
    end: int                         # exclusive


def _exact_regex(norm: str, substring: bool) -> re.Pattern:
    body = r"\s+".join(re.escape(tok) for tok in norm.split(" "))
    return re.compile(body if substring else _START + body + _END)


def _loose_regex(norm: str, substring: bool) -> re.Pattern:
    chars = [c for c in norm if not c.isspace()]
    parts = []
    for i, c in enumerate(chars):
        parts.append(re.escape(c))
        if i + 1 < len(chars):
            both_units = is_unit(c) and is_unit(chars[i + 1])
            parts.append(_GAP_HYPHEN if both_units else r"\s*")
    body = "".join(parts)
    return re.compile(body if substring else _START + body + _END)


class Matcher:
    def __init__(self, terms: Iterable[Term], patterns: Iterable[str], substring: bool = False) -> None:
        self.terms = list(terms)
        self.patterns = list(patterns)
        self.substring = substring
        self._term_res = [(t, _exact_regex(t.norm, substring), _loose_regex(t.norm, substring)) for t in self.terms]

    def find(self, text: str) -> list[Match]:
        norm, starts, ends = normalise_with_map(text)
        found: list[Match] = []

        def add(source, kind: str, s: int, e: int) -> None:
            found.append(Match(source, kind, starts[s], ends[e - 1]))

        for term, exact, loose in self._term_res:
            for m in loose.finditer(norm):
                if m.end() > m.start():
                    kind = "exact" if exact.fullmatch(m.group(0)) else "loose"
                    add(("term", term.line), kind, m.start(), m.end())
        for name in self.patterns:
            for s, e, kind in FINDERS[name](norm):
                add(("pattern", name), kind, s, e)
        found.sort(key=lambda m: (m.start, m.end, str(m.source)))
        return found


def merge_extents(matches: Iterable[Match]) -> list[tuple[int, int]]:
    """The union of the extents of overlapping matches: one removal area each (REQ-027)."""
    areas: list[list[int]] = []
    for m in sorted(matches, key=lambda m: (m.start, m.end)):
        if areas and m.start < areas[-1][1]:
            areas[-1][1] = max(areas[-1][1], m.end)
        else:
            areas.append([m.start, m.end])
    return [(a, b) for a, b in areas]
