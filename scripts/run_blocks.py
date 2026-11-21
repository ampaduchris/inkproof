"""Run the ```bash run blocks of a Markdown file and check each expected last line.

A block tagged `bash run` is followed by a line `Expected last line: `TEXT``.
The block passes when it exits 0 and the last line of its output (standard
output and standard error together) contains TEXT. Lines that start with `sys:1:` (an interpreter warning from PyMuPDF at exit) are ignored.
Prints one line per block.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

BLOCK = re.compile(r"```bash run\n(.*?)\n```\n\s*Expected last line: `([^`]*)`", re.S)


def main(path: str) -> int:
    blocks = BLOCK.findall(Path(path).read_text(encoding="utf-8"))
    if len(blocks) != 3:
        print(f"expected 3 runnable blocks, found {len(blocks)}")
        return 1
    failed = 0
    for command, expected in blocks:
        done = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        lines = [x for x in done.stdout.strip().splitlines() if not x.startswith("sys:1:")]
        last = lines[-1] if lines else ""
        ok = done.returncode == 0 and expected in last
        print(("PASS " if ok else "FAIL ") + command.splitlines()[0])
        failed += not ok
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "README.md"))
