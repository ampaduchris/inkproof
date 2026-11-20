"""Verification of the serialised output (spec 6.1). Runs on bytes, never on an in-memory document.

V1  Engine A, the PyMuPDF text trace (not clipped to the page), extracts S1.
V2  Engine B, pdfminer.six, extracts S1.
V3  Surfaces S2 to S7, S9 and S10 are enumerated through the document structure.
V4  S11: every decoded stream and every string object, joined per text-showing operator.
V5  The file has exactly one revision.
"""

from __future__ import annotations

import re
import zlib
from collections import Counter
from dataclasses import dataclass, field
from importlib import metadata
from io import BytesIO, StringIO

import pymupdf

from inkproof import __version__
from inkproof.matcher import Matcher

PAGE_SURFACES = {"S1"}


@dataclass
class Check:
    id: str
    engine: str
    version: str
    result: str = "pass"


@dataclass
class VerifyResult:
    checks: list[Check] = field(default_factory=list)
    findings: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.result == "pass" for c in self.checks)


# ---------------------------------------------------------------- page text engines


def trace_chars(page) -> list[tuple[str, pymupdf.Rect]]:
    return [(chr(c[0]), pymupdf.Rect(c[3])) for span in page.get_texttrace() for c in span["chars"]]


def page_text_with_map(page) -> tuple[str, list[int], list[tuple[str, pymupdf.Rect]]]:
    """The text of one page in content order, with a separator where the layout implies one.

    Returns the text, for each text position the index of the real character (or -1 for a separator),
    and the real characters with their boxes.
    """
    chars = []
    for span in page.get_texttrace():
        size = span.get("size") or 10
        for c in span["chars"]:
            chars.append((chr(c[0]), pymupdf.Rect(c[3]), size))
    text: list[str] = []
    index: list[int] = []
    prev = None
    for i, (ch, box, size) in enumerate(chars):
        if prev is not None:
            pch, pbox, psize = prev
            sep = ""
            if abs((box.y0 + box.y1) / 2 - (pbox.y0 + pbox.y1) / 2) > 0.4 * max(size, 1):
                sep = "\n"
            elif box.x0 - pbox.x1 > 0.25 * max(size, 1) and not (pch.isspace() or ch.isspace()):
                sep = " "
            if sep and not (pch.isspace() and sep == " "):
                text.append(sep)
                index.append(-1)
        text.append(ch)
        index.append(i)
        prev = (ch, box, size)
    return "".join(text), index, [(c, b) for c, b, _ in chars]


def v1_text(data: bytes) -> list[str]:
    """Engine A: the text of each page, from the text trace."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        return [page_text_with_map(p)[0] for p in doc]
    finally:
        doc.close()


def v2_text(data: bytes) -> list[str]:
    """Engine B: the text of each page, from pdfminer.six."""
    from pdfminer.converter import TextConverter
    from pdfminer.layout import LAParams
    from pdfminer.pdfinterp import PDFPageInterpreter, PDFResourceManager
    from pdfminer.pdfpage import PDFPage

    out = []
    manager = PDFResourceManager()
    for page in PDFPage.get_pages(BytesIO(data), check_extractable=False):
        buf = StringIO()
        device = TextConverter(manager, buf, laparams=LAParams())
        PDFPageInterpreter(manager, device).process_page(page)
        device.close()
        out.append(buf.getvalue())
    return out


# ---------------------------------------------------------------- string decoding (shared by V3 and V4)

_LIT = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
_HEX = re.compile(rb"<([0-9A-Fa-f\s]*)>")
_ELEM = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>")
_TJ = re.compile(rb"\[((?:\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|[-\d.\s])*)\]\s*TJ", re.S)
_ESC = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _unescape(lit: bytes) -> bytes:
    body = lit[1:-1]
    out = bytearray()
    i = 0
    while i < len(body):
        c = body[i:i + 1]
        if c == b"\\" and i + 1 < len(body):
            nxt = body[i + 1:i + 2]
            if nxt in _ESC:
                out += _ESC[nxt]
                i += 2
            elif nxt.isdigit():
                j = i + 1
                while j < len(body) and j < i + 4 and body[j:j + 1].isdigit():
                    j += 1
                out.append(int(body[i + 1:j], 8) & 0xFF)
                i = j
            elif nxt in (b"\n", b"\r"):
                i += 2
            else:
                out += nxt
                i += 2
        else:
            out += c
            i += 1
    return bytes(out)


def _element(raw: bytes) -> bytes:
    if raw.startswith(b"("):
        return _unescape(raw)
    hexa = re.sub(rb"\s", b"", raw[1:-1])
    if len(hexa) % 2:
        hexa += b"0"
    return bytes.fromhex(hexa.decode())


def decode_bytes(b: bytes) -> list[str]:
    """A string object read as UTF-16 (with or without a mark), UTF-8 and the one-byte PDFDocEncoding family."""
    out = []
    if b[:2] == b"\xfe\xff":
        out.append(b[2:].decode("utf-16-be", "replace"))
    elif b[:2] == b"\xff\xfe":
        out.append(b[2:].decode("utf-16-le", "replace"))
    elif len(b) >= 4 and b[0] == 0 and len(b) % 2 == 0:
        out.append(b.decode("utf-16-be", "replace"))
    out.append(b.decode("utf-8", "replace"))
    out.append(b.decode("latin-1"))
    return out


def strings_in(chunk: bytes) -> list[str]:
    """Every string object in a chunk of PDF syntax or of a content stream, and every TJ array joined."""
    out: list[str] = []
    for m in _TJ.finditer(chunk):
        joined = b"".join(_element(e) for e in _ELEM.findall(m.group(1)))
        out += decode_bytes(joined)
    for m in _LIT.finditer(chunk):
        out += decode_bytes(_unescape(m.group(0)))
    for m in _HEX.finditer(chunk):
        out += decode_bytes(_element(m.group(0)))
    return out


# ---------------------------------------------------------------- V3 and V4


def _annot_subtype(doc, xref: int) -> str:
    return doc.xref_get_key(xref, "Subtype")[1].lstrip("/")


def _object_strings(doc, xref: int) -> list[str]:
    try:
        src = doc.xref_object(xref, compressed=False)
    except Exception:
        return []
    return strings_in(src.encode("latin-1", "replace"))


def _stream_text(doc, xref: int) -> list[str]:
    try:
        raw = doc.xref_stream(xref)
    except Exception:
        return []
    return [] if raw is None else strings_in(raw) + [raw.decode("latin-1")]


def _struct_xrefs(doc) -> list[int]:
    cat = doc.pdf_catalog()
    kind, val = doc.xref_get_key(cat, "StructTreeRoot")
    if kind != "xref":
        return []
    todo, seen = [int(val.split()[0])], set()
    while todo:
        x = todo.pop()
        if x in seen:
            continue
        seen.add(x)
        k = doc.xref_get_key(x, "K")[1]
        todo += [int(m) for m in re.findall(r"(\d+) 0 R", k)]
    return sorted(seen)


def structure_strings(doc) -> list[str]:
    out = []
    for x in _struct_xrefs(doc):
        out += _object_strings(doc, x)
    return out


def _action_xrefs_and_dicts(doc) -> list[str]:
    """Text of the actions on the document and on the pages (S7)."""
    out = []
    cat = doc.pdf_catalog()
    for key in ("OpenAction", "AA"):
        kind, val = doc.xref_get_key(cat, key)
        if kind == "xref":
            out += _object_strings(doc, int(val.split()[0]))
        elif kind != "null":
            out += strings_in(val.encode("latin-1", "replace"))
    kind, val = doc.xref_get_key(cat, "Names/JavaScript")
    if kind == "xref":
        out += _object_strings(doc, int(val.split()[0]))
    elif kind != "null":
        out += strings_in(val.encode("latin-1", "replace"))
    for page in doc:
        kind, val = doc.xref_get_key(page.xref, "AA")
        if kind == "xref":
            out += _object_strings(doc, int(val.split()[0]))
        elif kind != "null":
            out += strings_in(val.encode("latin-1", "replace"))
    return out


def v3_strings(data: bytes) -> list[tuple[str, int | None, str]]:
    """Surfaces S2 to S7, S9 and S10 as (surface, page, string) triples."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    out: list[tuple[str, int | None, str]] = []
    try:
        for pno, page in enumerate(doc, start=1):
            for xref, _, _ in page.annot_xrefs():
                surface = "S3" if _annot_subtype(doc, xref) == "Widget" else "S2"
                texts = _object_strings(doc, xref)
                for key in ("AP/N", "Popup", "AA", "A"):
                    kind, val = doc.xref_get_key(xref, key)
                    if kind == "xref":
                        sub = int(val.split()[0])
                        texts += _object_strings(doc, sub) + _stream_text(doc, sub)
                out += [(surface, pno, t) for t in texts]
        out += [("S4", None, str(v)) for v in doc.metadata.values() if v]
        out += [("S4", None, doc.get_xml_metadata() or "")]
        out += [("S5", None, t[1]) for t in doc.get_toc()]
        try:
            out += [("S5", None, str(k)) for k in doc.resolve_names()]
        except Exception:
            pass
        out += [("S5", None, str(r.get("prefix", ""))) for r in (doc.get_page_labels() or [])]
        for name in doc.embfile_names():
            info = doc.embfile_info(name)
            out += [("S6", None, str(v)) for v in info.values() if isinstance(v, str)]
            out += [("S6", None, name)]
            for dec in decode_bytes(doc.embfile_get(name)):
                out.append(("S6", None, dec))
        out += [("S7", None, t) for t in _action_xrefs_and_dicts(doc)]
        out += [("S9", None, t) for t in structure_strings(doc)]
        for ocg in (doc.get_ocgs() or {}).values():
            out.append(("S10", None, str(ocg.get("name", ""))))
        return out
    finally:
        doc.close()


def v4_strings(data: bytes) -> list[str]:
    """Surface S11: every string object and every decoded stream of the whole file."""
    doc = pymupdf.open(stream=data, filetype="pdf")
    out: list[str] = []
    try:
        for xref in range(1, doc.xref_length()):
            try:
                src = doc.xref_object(xref, compressed=False)
            except Exception:
                continue
            out += strings_in(src.encode("latin-1", "replace"))
            out += _stream_text(doc, xref)
        out += strings_in(doc.xref_object(-1).encode("latin-1", "replace"))
        return out
    finally:
        doc.close()


# ---------------------------------------------------------------- V5


def revision_count(data: bytes) -> int:
    doc = pymupdf.open(stream=data, filetype="pdf")
    try:
        engine = doc.version_count
    finally:
        doc.close()
    return max(engine, len(re.findall(rb"(?m)^%%EOF[ \t\r]*$", data)), 1)


def earlier_revisions(data: bytes) -> list[bytes]:
    cuts = [m.end() for m in re.finditer(rb"(?m)^%%EOF[ \t\r]*\n?", data)]
    return [data[:c] for c in cuts[:-1]]


# ---------------------------------------------------------------- findings


def make_finding(surface: str, page: int | None, revision: int, source, kind: str, count: int,
                 cls: str | None = None) -> dict:
    f = {"surface": surface, "page": page, "revision": revision,
         "source": {"type": source[0], "id": source[1]}, "match_kind": kind, "count": count}
    if cls:
        f["class"] = cls
    return f


def _tally(records: list[tuple]) -> list[dict]:
    counts = Counter(records)
    return [make_finding(*key, count) for key, count in counts.items()]


def engine_versions() -> dict[str, str]:
    return {"pymupdf": pymupdf.__version__, "pdfminer.six": metadata.version("pdfminer.six")}


def verify(data: bytes, matcher: Matcher, revision: int = 1) -> VerifyResult:
    """Run V1 to V5 on `data`. `revision` is the number reported for page text of the current revision."""
    versions = engine_versions()
    result = VerifyResult()
    s1: dict[tuple, int] = {}

    def run(check_id: str, engine: str, version: str, records: list[tuple]) -> None:
        check = Check(check_id, engine, version, "fail" if records else "pass")
        result.checks.append(check)
        if check_id in ("V1", "V2"):
            for rec, n in Counter(records).items():
                s1[rec] = max(s1.get(rec, 0), n)
        else:
            result.findings.extend(_tally(records))

    def page_records(pages) -> list[tuple]:
        return [("S1", pno, revision, m.source, m.kind) for pno, text in enumerate(pages, start=1)
                for m in matcher.find(text)]

    run("V1", "pymupdf", versions["pymupdf"], page_records(v1_text(data)))
    run("V2", "pdfminer.six", versions["pdfminer.six"], page_records(v2_text(data)))
    result.findings.extend(make_finding(*rec, n) for rec, n in s1.items())

    v3 = [(surface, page, revision, m.source, m.kind)
          for surface, page, text in v3_strings(data) for m in matcher.find(text)]
    run("V3", "pymupdf", versions["pymupdf"], v3)
    v4 = [("S11", None, revision, m.source, m.kind) for text in v4_strings(data) for m in matcher.find(text)]
    run("V4", "inkproof-raw-scan", __version__, v4)

    revisions = revision_count(data)
    result.checks.append(Check("V5", "inkproof-revisions", __version__, "pass" if revisions == 1 else "fail"))
    if revisions != 1:
        for n, blob in enumerate(earlier_revisions(data), start=1):
            try:
                pages = v1_text(blob)
            except Exception:
                continue
            recs = [("S1", pno, n, m.source, m.kind, "earlier-revision")
                    for pno, text in enumerate(pages, start=1) for m in matcher.find(text)]
            result.findings.extend(make_finding(*rec[:5], c, rec[5]) for rec, c in Counter(recs).items())
    result.findings.sort(key=lambda f: (f["surface"], f["page"] or 0, f["revision"], str(f["source"]["id"]),
                                        f["match_kind"], f.get("class", "")))
    return result
