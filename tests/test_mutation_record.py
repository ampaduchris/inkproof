"""REQ-092: the mutation score of the matcher and the verifier is recorded with its date and meets the floor.

The mutation run itself is local and slow (about ten minutes); it is not run in CI (STANDARD.md R2, gate: release).
This test reads the record in docs/MUTATION.md and checks that the figures agree and meet the spec's floor.
"""

import re
from pathlib import Path

import pytest

RECORD = Path(__file__).resolve().parent.parent / "docs" / "MUTATION.md"
FLOOR = 80.0


@pytest.mark.req("REQ-092")
def test_mutation_score_recorded_and_meets_floor():
    text = RECORD.read_text(encoding="utf-8")
    date = re.search(r"^Date: (\d{4}-\d{2}-\d{2})$", text, re.M)
    total = re.search(r"^Total mutants: (\d+)$", text, re.M)
    killed = re.search(r"^Killed \(including timeouts\): (\d+)$", text, re.M)
    score = re.search(r"^Score: ([\d.]+)%$", text, re.M)
    assert date and total and killed and score, "record is missing a field"
    computed = 100 * int(killed.group(1)) / int(total.group(1))
    assert abs(computed - float(score.group(1))) < 0.05
    assert float(score.group(1)) >= FLOOR
