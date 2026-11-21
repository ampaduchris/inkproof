import subprocess
import sys

import inkproof


def test_version_importable():
    assert inkproof.__version__


def test_cli_version_runs():
    out = subprocess.run(
        [sys.executable, "-m", "inkproof.cli", "--version"], capture_output=True, text=True
    )
    assert out.returncode == 0
    assert inkproof.__version__ in out.stdout


def test_example_statement_is_fixture_r1():
    """The README, the demo and CI use examples/statement.pdf; it must stay the generated fixture R1."""
    from pathlib import Path

    from helpers import fixture_bytes

    assert (Path(__file__).parent.parent / "examples" / "statement.pdf").read_bytes() == fixture_bytes("R1")
