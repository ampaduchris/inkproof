"""The fixed synthetic corpus for REQ-026: 10,000 words of plain prose, no planted identifiers.

Generated from a seed. The committed copy is tests/data/corpus.txt; a test checks they agree.
Run `python tests/corpusgen.py` to write it.
"""

from __future__ import annotations

import random
from pathlib import Path

from fixturegen.values import FILLER

EXTRA = ["2026", "12.50", "A4", "9001", "3rd", "page", "14", "by", "e-mail", "post", "no.", "(see", "list)", "1,200",
         "40%", "Room", "B12", "ref", "of", "the", "day", "month", "ISO", "Monday", "Tuesday", "at", "10:30",
         "12/03", "co-op", "x-ray", "plan,", "update;", "order.", "team's"]


def generate() -> str:
    rng = random.Random("inkproof-1.4-corpus")
    pool = FILLER * 3 + EXTRA
    words = [rng.choice(pool) for _ in range(10_000)]
    lines = [" ".join(words[i:i + 12]) for i in range(0, len(words), 12)]
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    Path(__file__).parent.joinpath("data", "corpus.txt").write_text(generate(), encoding="utf-8")
