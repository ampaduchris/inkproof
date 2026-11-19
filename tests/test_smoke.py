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
