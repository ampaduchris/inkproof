"""The IBAN length table is a data file that records its registry release (REQ-021)."""

import json
import re
from importlib import resources

import pytest


def load() -> dict:
    return json.loads((resources.files("inkproof") / "data" / "iban_lengths.json").read_text(encoding="utf-8"))


@pytest.mark.req("REQ-021")
def test_iban_length_table_has_source_and_fixed_rows():
    t = load()
    assert isinstance(t["release"], int) and t["release"] > 0
    assert t["source"].startswith("https://")
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", t["retrieved"])
    assert re.fullmatch(r"[0-9a-f]{64}", t["source_file_sha256"])
    assert t["lengths"]["DE"] == 22
    assert t["lengths"]["GB"] == 22


@pytest.mark.req("REQ-021")
def test_iban_length_table_rows_are_well_formed():
    lengths = load()["lengths"]
    assert len(lengths) >= 89
    for code, n in lengths.items():
        assert re.fullmatch(r"[A-Z]{2}", code)
        assert isinstance(n, int) and 15 <= n <= 34
