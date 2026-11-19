"""Tests for scripts/trace.py (requirement traceability), run as a subprocess."""

import subprocess
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "trace.py"

SPEC = """\
# spec

| Id | Level | Requirement | Proof |
| --- | --- | --- | --- |
| REQ-001 | MUST | First. | t |
| REQ-002 | SHOULD | Second. | none |
| REQ-003 | MUST | Third. | t |
| REQ-004 | MUST | Withdrawn: gone. | none |

### 11.1 Scope bullets

| Scope bullet | MUST requirements |
| --- | --- |
| first thing | REQ-001, 003 |
| second thing | REQ-002 |

## 12. Evidence
"""

SPEC_FIXED = SPEC.replace("| second thing | REQ-002 |", "| second thing | REQ-003 |")


def run(tmp_path: Path, spec: str, tagged: list[str], *flags: str):
    (tmp_path / "spec.md").write_text(spec, encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir(exist_ok=True)
    body = "import pytest\n" + "".join(
        f'@pytest.mark.req("{rid}")\ndef test_{i}():\n    pass\n' for i, rid in enumerate(tagged)
    )
    (tests / "test_x.py").write_text(body, encoding="utf-8")
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--spec", str(tmp_path / "spec.md"), "--tests", str(tests), *flags],
        capture_output=True,
        text=True,
    )


def test_all_musts_tested_passes(tmp_path):
    r = run(tmp_path, SPEC_FIXED, ["REQ-001", "REQ-003"])
    assert r.returncode == 0, r.stdout
    assert "2 untested" not in r.stdout and "0 untested MUST" in r.stdout


def test_untested_must_fails(tmp_path):
    r = run(tmp_path, SPEC_FIXED, ["REQ-001"])
    assert r.returncode == 1
    assert "REQ-003  MUST     NO TEST" in r.stdout


def test_report_only_does_not_fail_on_untested_must(tmp_path):
    r = run(tmp_path, SPEC_FIXED, [], "--report-only")
    assert r.returncode == 0
    assert "2 untested MUST" in r.stdout


def test_untested_should_and_withdrawn_are_ignored(tmp_path):
    r = run(tmp_path, SPEC_FIXED, ["REQ-001", "REQ-003"])
    assert "REQ-004" not in r.stdout
    assert "REQ-002  SHOULD   NO TEST" in r.stdout and r.returncode == 0


def test_unknown_tag_fails_even_report_only(tmp_path):
    r = run(tmp_path, SPEC_FIXED, ["REQ-001", "REQ-003", "REQ-099"], "--report-only")
    assert r.returncode == 1
    assert "unknown requirement REQ-099" in r.stdout


def test_scope_row_without_must_fails(tmp_path):
    r = run(tmp_path, SPEC, ["REQ-001", "REQ-003"])
    assert r.returncode == 1
    assert "scope row maps to no MUST: second thing" in r.stdout


def test_real_spec_scope_rows_all_map_to_a_must():
    spec = Path(__file__).resolve().parent.parent / "docs" / "spec.md"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "--report-only", "--spec", str(spec)],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0, r.stdout[-500:]
    assert " 0 errors" in r.stdout
