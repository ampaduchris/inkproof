"""The JSON report (spec section 8)."""

import json
from pathlib import Path
import re
import unicodedata
from importlib import resources

import pytest

from helpers import ALL_PATTERNS, FIXTURES, apply, fixture_bytes, sub, validate_report

READABLE = [fid for fid in FIXTURES if fid not in ("X03", "X04")]
LOCATION_KEYS = {"surface", "class", "page", "revision", "source", "match_kind", "count"}


def all_terms(fid: str) -> list[str]:
    return [c.value for c in FIXTURES[fid].canaries if c.kind == "term"] or ["Nomatchword"]


def forms(value: str) -> set[str]:
    norm = unicodedata.normalize("NFKC", value).casefold()
    return {value, norm, re.sub(r"\s+", "", norm)}


@pytest.fixture(scope="module")
def reports(tmp_path_factory):
    out = {}
    for fid in READABLE:
        d = tmp_path_factory.mktemp(fid)
        out[fid] = (d, apply(d, fid, terms=all_terms(fid), patterns=ALL_PATTERNS, report=True))
    return out


@pytest.mark.req("REQ-075")
def test_report_validates(reports):
    for fid, (_, r) in reports.items():
        assert r.exit_code in (0, 1), fid
        validate_report(r.report)                                          # also run inside helpers.apply for every test
    schema = json.loads((resources.files("inkproof") / "report.schema.json").read_text(encoding="utf-8"))
    assert schema["title"] == "inkproof report"


@pytest.mark.req("REQ-076")
def test_report_has_no_values(reports):
    for fid, (_, r) in reports.items():
        text = r.report_path.read_text(encoding="utf-8")
        squashed = re.sub(r"\s+", "", unicodedata.normalize("NFKC", text).casefold())
        for c in FIXTURES[fid].canaries:
            for f in forms(c.value):
                assert f not in text and re.sub(r"\s+", "", f.casefold()) not in squashed, (fid, c.kind)


@pytest.mark.req("REQ-076")
def test_report_has_no_paths(reports):
    for fid, (d, r) in reports.items():
        text = r.report_path.read_text(encoding="utf-8")
        assert str(d) not in text and "in.pdf" not in text and "out.pdf" not in text, fid
        assert re.fullmatch(r"[0-9a-f]{64}", r.report["input"]["sha256"])
        assert "/" not in text


@pytest.mark.req("REQ-077")
def test_report_location_fields(reports):
    for fid, (_, r) in reports.items():
        for m in r.report["removed"] + r.report["findings"]:
            assert set(m) <= LOCATION_KEYS, (fid, set(m) - LOCATION_KEYS)
            assert m["page"] is None or isinstance(m["page"], int)
            assert set(m["source"]) == {"type", "id"}
    assert {m["page"] for m in reports["R4"][1].report["removed"]} == {1, 2, 3}      # pages, not coordinates


@pytest.mark.req("REQ-078")
def test_report_deterministic(tmp_path):
    runs = [apply(sub(tmp_path, str(i)), "R4", terms=all_terms("R4"), patterns=ALL_PATTERNS, report=True)
            for i in range(2)]
    assert runs[0].report_path.read_bytes() == runs[1].report_path.read_bytes()
    rep = runs[0].report
    assert not re.search(r"20\d\d-\d\d-\d\d|timestamp|\"time", json.dumps(rep))   # no date or time field
    text = runs[0].report_path.read_text(encoding="utf-8")
    assert json.dumps(rep, sort_keys=True, indent=2) in (text, text.rstrip("\n"))   # keys sorted
    key = lambda m: (m["surface"], m["page"] or 0, m["revision"], str(m["source"]["id"]))  # noqa: E731
    assert rep["removed"] == sorted(rep["removed"], key=key)


@pytest.mark.req("REQ-079")
def test_schema_version(reports):
    schema = json.loads((resources.files("inkproof") / "report.schema.json").read_text(encoding="utf-8"))
    assert schema["properties"]["schema_version"] == {"const": "1.0"}
    for _, (_, r) in reports.items():
        assert r.report["schema_version"] == "1.0"


@pytest.mark.req("REQ-074")
def test_image_limits_reported(tmp_path):
    r = apply(tmp_path, "X06", terms=["Denlorlor"], report=True)
    assert r.exit_code == 0
    assert r.report["limits"]["pages_with_images"] == [1, 2]
    assert r.report["limits"]["image_only_pages"] == [1]
    assert "LIM-1" in r.report["limits"]["notes"]
    assert re.search(r"text layer only", r.stderr)                           # the one-line summary says so


@pytest.mark.req("REQ-079")
def test_shipped_schema_is_the_schema_of_the_spec():
    spec = (Path(__file__).parent.parent / "docs" / "spec.md").read_text(encoding="utf-8")
    block = re.search(r"### 8\.1 Schema\s+```json\n(.*?)\n```", spec, re.S).group(1)
    shipped = json.loads((resources.files("inkproof") / "report.schema.json").read_text(encoding="utf-8"))
    assert json.loads(block) == shipped


@pytest.mark.req("REQ-041")
def test_same_input_gives_the_same_output_bytes(tmp_path):
    runs = [apply(sub(tmp_path, str(i)), "R4", terms=all_terms("R4"), patterns=ALL_PATTERNS) for i in range(2)]
    assert runs[0].out.read_bytes() == runs[1].out.read_bytes()
