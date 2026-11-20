"""Readers used only to prove that a fixture holds what it claims. Test support, not product code."""

from __future__ import annotations

import re
import unicodedata
import zlib
from io import BytesIO

import pymupdf

ZERO_WIDTH = dict.fromkeys(map(ord, "­​‌‍⁠﻿"))


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", s).translate(ZERO_WIDTH).casefold()


def contains(text: str, value: str) -> bool:
    """Loose containment: normalise, then ignore all white space and line-end hyphens."""
    squash = lambda s: re.sub(r"\s+", "", norm(s))  # noqa: E731
    t = squash(text)
    return squash(value) in t or squash(value) in t.replace("-", "")


def first_revision(data: bytes) -> bytes:
    i = data.index(b"%%EOF") + len(b"%%EOF")
    return data[i:i + 1] in (b"\n", b"\r") and data[: i + 1] or data[:i]


def _open(data: bytes, password: str | None = None) -> pymupdf.Document:
    d = pymupdf.open(stream=data, filetype="pdf")
    if d.needs_pass:
        assert password is not None and d.authenticate(password), "password needed"
    return d


def trace_text(data: bytes, password: str | None = None) -> str:
    d = _open(data, password)
    out = []
    for page in d:
        for span in page.get_texttrace():
            out.append("".join(chr(c[0]) for c in span["chars"]))
    return " ".join(out)


def pdfminer_text(data: bytes, password: str | None = None) -> str:
    from pdfminer.high_level import extract_text
    return extract_text(BytesIO(data), password=password or "")


def pypdf_text(data: bytes, password: str | None = None) -> str:
    from pypdf import PdfReader
    r = PdfReader(BytesIO(data))
    if r.is_encrypted:
        assert r.decrypt(password or "") != 0
    return " ".join(p.extract_text() or "" for p in r.pages)


def _strings(obj, seen=None) -> list[str]:
    """All strings and names inside a pypdf object, recursively."""
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, StreamObject
    seen = seen if seen is not None else set()
    out: list[str] = []
    if isinstance(obj, IndirectObject):
        if obj.idnum in seen:
            return out
        seen.add(obj.idnum)
        return _strings(obj.get_object(), seen)
    if isinstance(obj, StreamObject):
        out.append(obj.get_data().decode("utf-8", "replace"))
    if isinstance(obj, DictionaryObject):
        for k, v in obj.items():
            if k in ("/Parent", "/P", "/Pg"):
                continue
            out.append(str(k))
            out += _strings(v, seen)
    elif isinstance(obj, ArrayObject):
        for v in obj:
            out += _strings(v, seen)
    elif obj is not None:
        out.append(str(obj))
    return out


def struct_strings(data: bytes, check: str) -> str:
    """Enumerate a surface through the document structure (V3), by library and surface."""
    lib, _, surface = check[::-1].partition("-")[2][::-1], "-", check.rsplit("-", 1)[0]
    kind, engine = check.rsplit("-", 1)
    if engine == "pymupdf":
        d = pymupdf.open(stream=data, filetype="pdf")
        cat = d.pdf_catalog()
        if kind == "meta":
            return " ".join(str(v) for v in d.metadata.values())
        if kind == "xmp":
            return d.get_xml_metadata()
        if kind == "outline":
            return " ".join(t[1] for t in d.get_toc())
        if kind == "widgets":
            return " ".join(str(w.field_value) + str(w.field_name) for p in d for w in (p.widgets() or []))
        if kind == "embfile":
            return " ".join(d.embfile_get(n).decode("utf-8", "replace") + n for n in d.embfile_names())
        if kind == "annots":
            return " ".join(d.xref_object(x[0]) for p in d for x in p.annot_xrefs())
        if kind == "dests":
            return " ".join(str(k) for k in d.resolve_names())
        if kind == "labels":
            return " ".join(str(r) for r in d.get_page_labels())
        if kind == "ocg":
            return " ".join(str(v) for v in d.get_ocgs().values())
        if kind == "struct":
            root = d.xref_get_key(cat, "StructTreeRoot")[1].split()[0]
            out, todo = [], [int(root)]
            while todo:
                x = todo.pop()
                out.append(d.xref_object(x))
                k = d.xref_get_key(x, "K")[1]
                todo += [int(m) for m in re.findall(r"(\d+) 0 R", k)]
            return " ".join(out)
    else:
        from pypdf import PdfReader
        r = PdfReader(BytesIO(data))
        root = r.trailer["/Root"]
        if kind == "meta":
            return " ".join(str(v) for v in (r.metadata or {}).values())
        if kind == "xmp":
            return " ".join(_strings(root["/Metadata"]))
        if kind == "outline":
            def walk(o):
                return [x.title if hasattr(x, "title") else walk(x) for x in o]
            return str(walk(r.outline))
        if kind == "fields":
            return " ".join(f"{k} {v.get('/V')}" for k, v in (r.get_fields() or {}).items())
        if kind == "embfile":
            return " ".join(f"{n} " + " ".join(x.decode("utf-8", "replace") for x in c)
                            for n, c in r.attachments.items())
        if kind == "annots":
            return " ".join(" ".join(_strings(a)) for p in r.pages for a in p.get("/Annots", []))
        if kind == "dests":
            return " ".join(str(k) for k in r.named_destinations)
        if kind == "labels":
            return " ".join(r.page_labels)
        if kind == "ocg":
            return " ".join(_strings(root["/OCProperties"]))
        if kind == "struct":
            return " ".join(_strings(root["/StructTreeRoot"]))
    raise ValueError(check)


# ---- V4 style raw scan: every stream decoded, every string decoded, TJ elements joined

OBJ = re.compile(rb"(\d+) 0 obj(.*?)endobj", re.S)
LIT = re.compile(rb"\((?:\\.|[^\\()])*\)", re.S)
HEX = re.compile(rb"<([0-9A-Fa-f\s]*)>")
TJ = re.compile(rb"\[((?:\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|[-\d.\s])*)\]\s*TJ", re.S)


def _decode(b: bytes) -> list[str]:
    outs = []
    if b[:2] == b"\xfe\xff":
        outs.append(b[2:].decode("utf-16-be", "replace"))
    elif b[:2] == b"\xff\xfe":
        outs.append(b[2:].decode("utf-16-le", "replace"))
    outs += [b.decode("utf-8", "replace"), b.decode("latin-1")]
    return outs


def _lit(b: bytes) -> bytes:
    return re.sub(rb"\\(.)", rb"\1", b[1:-1])


def raw_strings(data: bytes) -> list[str]:
    streams = []
    for m in OBJ.finditer(data):
        body = m.group(2)
        streams.append(body)
        s = re.search(rb"stream\r?\n(.*)\r?\nendstream", body, re.S)
        if s:
            raw = s.group(1)
            try:
                raw = zlib.decompress(raw)
            except zlib.error:
                pass
            streams.append(raw)
    out: list[str] = []
    for chunk in streams:
        for m in TJ.finditer(chunk):
            parts = [_lit(x) if x.startswith(b"(") else bytes.fromhex(re.sub(rb"\s", b"", x[1:-1]).decode())
                     for x in re.findall(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>", m.group(1))]
            out += _decode(b"".join(parts))
        for m in LIT.finditer(chunk):
            out += _decode(_lit(m.group(0)))
        for m in HEX.finditer(chunk):
            h = re.sub(rb"\s", b"", m.group(1))
            if len(h) % 2 == 0:
                out += _decode(bytes.fromhex(h.decode()))
        out.append(chunk.decode("latin-1"))  # plain text, e.g. XMP
    return out


def check_text(data: bytes, check: str, password: str | None = None) -> str:
    """Return the text a named check sees. `rev1-` checks read the first revision only."""
    if check.startswith("auth:"):
        return check_text(data, check[5:], password)
    if check.startswith("rev1-"):
        return check_text(first_revision(data), check[5:], password)
    if check == "pymupdf-trace":
        return trace_text(data, password)
    if check == "pdfminer":
        return pdfminer_text(data, password)
    if check == "pypdf":
        return pypdf_text(data, password)
    if check == "raw":
        return "\n".join(raw_strings(data))
    return struct_strings(data, check)
