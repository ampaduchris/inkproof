"""Record the demo as an asciicast v2 file (docs/demo.cast).

Runs the real commands on the files in examples/ and writes their real output,
with typing delays added. Usage: uv run python scripts/make_demo.py
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    "inkproof audit examples/statement.pdf --terms examples/terms.txt --patterns iban,email --report /dev/null",
    "inkproof apply examples/statement.pdf --terms examples/terms.txt --patterns iban,email -o out.pdf",
    "inkproof audit out.pdf --terms examples/terms.txt --patterns iban,email --report /dev/null",
]


def main() -> None:
    events: list[tuple[float, str, str]] = []
    t = 0.5
    with tempfile.TemporaryDirectory() as tmp:
        for cmd in STEPS:
            events.append((t, "o", "$ "))
            for ch in cmd:
                t += 0.03
                events.append((t, "o", ch))
            t += 0.4
            events.append((t, "o", "\r\n"))
            done = subprocess.run(
                cmd.replace("inkproof ", "uv run --project %s inkproof " % ROOT, 1)
                .replace("examples/", f"{ROOT}/examples/")
                .replace("out.pdf", "out.pdf"),
                shell=True, cwd=tmp, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            t += 0.8
            events.append((t, "o", done.stdout.replace("\n", "\r\n")))
            events.append((t, "o", f"exit {done.returncode}\r\n"))
            t += 1.5
    header = {"version": 2, "width": 100, "height": 14, "title": "inkproof: audit, apply, audit again"}
    lines = [json.dumps(header)] + [json.dumps([round(a, 3), b, c]) for a, b, c in events]
    (ROOT / "docs" / "demo.cast").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote docs/demo.cast, {round(t)} seconds")


if __name__ == "__main__":
    main()
