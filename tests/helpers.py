"""Shared helpers for the product tests. Fixtures come from the generator, never from outside the repo."""

from __future__ import annotations

import hashlib
import json
import warnings
from dataclasses import dataclass
from pathlib import Path

from typer.testing import CliRunner

from fixturegen import build_all
from fixturegen.engines import check_text, contains

warnings.filterwarnings("ignore")
FIXTURES = build_all()
PATTERN_KINDS = ("iban", "de-tax-id", "uk-ni", "email")
ALL_PATTERNS = ",".join(PATTERN_KINDS)


def validate_report(rep: dict) -> None:
    """Every report produced by any test must validate against the shipped schema (REQ-075)."""
    import jsonschema
    from importlib import resources
    schema = json.loads((resources.files("inkproof") / "report.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(rep)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def fixture_bytes(fid: str, name: str | None = None) -> bytes:
    fx = FIXTURES[fid]
    return fx.files[name or next(iter(fx.files))]


@dataclass
class Run:
    exit_code: int
    stdout: str
    stderr: str
    out: Path
    report: dict | None
    report_path: Path


def runner() -> CliRunner:
    return CliRunner()


def invoke(args: list[str], *, input_bytes: bytes | None = None):
    from inkproof.cli import app
    return runner().invoke(app, args, catch_exceptions=False)


def sub(tmp: Path, name: str) -> Path:
    d = tmp / name
    d.mkdir()
    return d


def write_terms(path: Path, lines: list[str]) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def apply(tmp: Path, fid: str, *, terms: list[str] | None = None, patterns: str | None = None,
          extra: list[str] | None = None, data: bytes | None = None, name: str = "in.pdf",
          report: bool = False, catch: bool = False) -> Run:
    """Run `inkproof apply` on a fixture. Returns the exit code, both streams and the parsed report."""
    from inkproof.cli import app
    src = tmp / name
    src.write_bytes(data if data is not None else fixture_bytes(fid))
    out = tmp / "out.pdf"
    args = ["apply", str(src), "-o", str(out)]
    if terms is not None:
        args += ["--terms", str(write_terms(tmp / "terms.txt", terms))]
    if patterns:
        args += ["--patterns", patterns]
    rep_path = tmp / "report.json" if report else Path(str(out) + ".report.json")
    if report:
        args += ["--report", str(rep_path)]
    args += extra or []
    res = runner().invoke(app, args, catch_exceptions=catch)
    rep = json.loads(rep_path.read_text(encoding="utf-8")) if rep_path.exists() else None
    if rep is not None:
        validate_report(rep)
    return Run(res.exit_code, res.stdout, res.stderr, out, rep, rep_path)


def canaries(fid: str, kind: str | None = None, *, absent: bool = False):
    return [c for c in FIXTURES[fid].canaries if c.surface == "S1" and c.absent == absent
            and (kind is None or c.kind == kind)]


def source_for(fid: str, canary) -> tuple[list[str] | None, str | None]:
    """The terms and patterns that find one canary."""
    if canary.kind == "term":
        return [canary.value], None
    return None, canary.kind


def present(data: bytes, canary, engines=None) -> bool:
    return any(contains(check_text(data, e), canary.value) for e in (engines or canary.checks))
