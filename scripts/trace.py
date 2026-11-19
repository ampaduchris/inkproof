"""Requirement traceability: print the matrix, exit 1 if a MUST has no test.

Stub for session 1.1. It reads the table rows in docs/spec.md that begin
`| REQ-` and the `@pytest.mark.req("REQ-###")` tags in tests/. Until docs/spec.md
is adopted (session 1.2) there are no requirements, so it prints an empty matrix
and exits 0.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = ROOT / "docs" / "spec.md"
ROW = re.compile(r"^\|\s*(REQ-\d{3})\s*\|\s*(MUST NOT|MUST|SHOULD|MAY)\s*\|")
TAG = re.compile(r"""mark\.req\(\s*["'](REQ-\d{3})["']""")


def main() -> int:
    reqs: dict[str, str] = {}
    if SPEC.exists():
        for line in SPEC.read_text(encoding="utf-8").splitlines():
            m = ROW.match(line)
            if m:
                reqs[m.group(1)] = m.group(2)
    tested: set[str] = set()
    for path in (ROOT / "tests").rglob("*.py"):
        tested.update(TAG.findall(path.read_text(encoding="utf-8")))
    missing = []
    for rid in sorted(reqs):
        ok = rid in tested
        print(f"{rid}  {reqs[rid]:<8} {'tested' if ok else 'NO TEST'}")
        if not ok and reqs[rid].startswith("MUST"):
            missing.append(rid)
    print(f"{len(reqs)} requirements, {len(missing)} untested MUST")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
