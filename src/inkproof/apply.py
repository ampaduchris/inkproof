"""The apply procedure (spec section 6): find, remove, serialise, verify. The file reaches OUT only if verification passes."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import traceback
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import pymupdf
import typer

from inkproof import __version__
from inkproof.matcher import Matcher, merge_extents
from inkproof.patterns import NAMES
from inkproof.terms import InputError, parse_terms
from inkproof.verify import (page_text_with_map, strings_in, structure_strings, verify, make_finding)

FIXED_TITLE = "[REDACTED]"
LIMIT_NOTES = ["LIM-1", "LIM-2", "LIM-3", "LIM-4", "LIM-5", "LIM-6"]


class DocumentError(Exception):
    """The input is not a PDF, is damaged, or needs a password (exit 3)."""


@dataclass
class Request:
    input: Path
    output: Path
    terms: Path | None
    patterns: list[str]
    report: Path | None
    force: bool = False
    substring: bool = False
    allow_short_terms: bool = False
    no_mark: bool = False
    debug: bool = False


def empty_actions() -> dict:
    return {"annotations_removed": {}, "form_fields_removed": 0, "metadata_removed": False,
            "embedded_files_removed": 0, "actions_removed": 0, "outline_titles_redacted": 0,
            "structure_tree_removed": False}


def open_document(data: bytes) -> pymupdf.Document:
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        raise DocumentError("not a PDF file or cannot be parsed") from None
    if not doc.is_pdf or doc.needs_pass or doc.is_encrypted:
        doc.close()
        raise DocumentError("the document needs a password or is not a PDF")
    if doc.is_repaired:
        doc.close()
        raise DocumentError("the document is damaged")
    return doc


# ---------------------------------------------------------------- removal from page text (S1)


def _inset(r: pymupdf.Rect) -> pymupdf.Rect:
    w, h = r.width, r.height
    return pymupdf.Rect(r.x0 + w * 0.2, r.y0 + h * 0.3, r.x1 - w * 0.2, r.y1 - h * 0.3)


def _line_boxes(boxes: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    """Union the glyph boxes of one removal area into one box per line."""
    lines: list[pymupdf.Rect] = []
    for b in boxes:
        if lines and abs((b.y0 + b.y1) / 2 - (lines[-1].y0 + lines[-1].y1) / 2) <= 0.4 * max(b.height, 1):
            lines[-1] = pymupdf.Rect(lines[-1]).include_rect(b)
        else:
            lines.append(pymupdf.Rect(b))
    return lines


def remove_s1(doc, matcher: Matcher, mark: bool = True, revision: int = 1) -> list[dict]:
    """Delete the glyphs of every match from the page content, wherever the text sits. Returns the removed matches."""
    records: list[tuple] = []
    for pno, page in enumerate(doc, start=1):
        text, index, chars = page_text_with_map(page)
        matches = matcher.find(text)
        if not matches:
            continue
        records += [("S1", pno, revision, m.source, m.kind) for m in matches]
        areas = []
        for start, end in merge_extents(matches):
            boxes = [chars[index[p]][1] for p in range(start, end) if index[p] >= 0]
            areas.append(boxes)
            for box in boxes:
                page.add_redact_annot(_inset(box), fill=False)
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
        if mark:
            for boxes in areas:
                for line in _line_boxes(boxes):
                    page.draw_rect(line, color=None, fill=(0, 0, 0), overlay=True)
    return [make_finding(*rec, n) for rec, n in Counter(records).items()]


# ---------------------------------------------------------------- the other surfaces


def _ref(value: str) -> int | None:
    m = re.match(r"\s*(\d+) 0 R", value)
    return int(m.group(1)) if m else None


def _top_level_keys(text: str) -> list[str]:
    depth, keys, i = 0, [], 0
    while i < len(text):
        if text.startswith("<<", i):
            depth += 1
            i += 2
        elif text.startswith(">>", i):
            depth -= 1
            i += 2
        elif text[i] == "/" and depth == 1:
            m = re.match(r"/([^\s/<>\[\]()]+)", text[i:])
            keys.append(m.group(1))
            i += len(m.group(0))
            # skip the value of this key when it is a nested dictionary
            rest = text[i:].lstrip()
            if rest.startswith("<<"):
                j, d = i + (len(text[i:]) - len(rest)), 0
                while j < len(text):
                    if text.startswith("<<", j):
                        d += 1
                        j += 2
                    elif text.startswith(">>", j):
                        d -= 1
                        j += 2
                        if d == 0:
                            break
                    else:
                        j += 1
                i = j
        else:
            i += 1
    return keys


def _dict_text(doc, kind: str, value: str) -> str:
    if kind == "xref":
        return doc.xref_object(int(value.split()[0]), compressed=False)
    return value


def _remove_actions(doc) -> int:
    """Remove document and page actions and scripts (S7). Returns how many actions were removed."""
    count = 0
    cat = doc.pdf_catalog()
    kind, val = doc.xref_get_key(cat, "OpenAction")
    if kind != "null":
        count += 1
        doc.xref_set_key(cat, "OpenAction", "null")
    kind, val = doc.xref_get_key(cat, "AA")
    if kind != "null":
        count += len(_top_level_keys(_dict_text(doc, kind, val)))
        doc.xref_set_key(cat, "AA", "null")
    kind, val = doc.xref_get_key(cat, "Names/JavaScript")
    if kind != "null":
        count += len(re.findall(r"\)\s*(?:<<|\d+ 0 R)|>\s*(?:<<|\d+ 0 R)", _dict_text(doc, kind, val)))
        doc.xref_set_key(cat, "Names/JavaScript", "null")
    for page in doc:
        kind, val = doc.xref_get_key(page.xref, "AA")
        if kind != "null":
            count += len(_top_level_keys(_dict_text(doc, kind, val)))
            doc.xref_set_key(page.xref, "AA", "null")
    return count


def _redact_outline(doc, matcher: Matcher) -> int:
    cat = doc.pdf_catalog()
    kind, val = doc.xref_get_key(cat, "Outlines")
    root = _ref(val) if kind == "xref" else None
    if root is None:
        return 0
    count, todo, seen = 0, [], set()
    first = doc.xref_get_key(root, "First")
    if first[0] == "xref":
        todo.append(_ref(first[1]))
    while todo:
        node = todo.pop()
        if node in seen or node is None:
            continue
        seen.add(node)
        title = doc.xref_get_key(node, "Title")[1]
        texts = [title] + strings_in(doc.xref_object(node, compressed=False).encode("latin-1", "replace"))
        if any(matcher.find(t) for t in texts):
            doc.xref_set_key(node, "Title", f"({FIXED_TITLE})")
            count += 1
        for key in ("First", "Next"):
            k, v = doc.xref_get_key(node, key)
            if k == "xref":
                todo.append(_ref(v))
    return count


def strip_surfaces(doc, matcher: Matcher) -> dict:
    """Strip annotations, fields, metadata, embedded files and actions; redact outline titles; drop the structure tree on a match."""
    actions = empty_actions()
    cat = doc.pdf_catalog()
    types: Counter = Counter()
    fields = 0
    for page in doc:
        for xref, _, _ in page.annot_xrefs():
            subtype = doc.xref_get_key(xref, "Subtype")[1].lstrip("/")
            if subtype == "Widget":
                fields += 1
            else:
                types[subtype] += 1
        doc.xref_set_key(page.xref, "Annots", "null")
    doc.xref_set_key(cat, "AcroForm", "null")
    actions["annotations_removed"] = dict(sorted(types.items()))
    actions["form_fields_removed"] = fields
    doc.set_metadata({})
    doc.del_xml_metadata()
    doc.xref_set_key(cat, "Metadata", "null")
    actions["metadata_removed"] = True
    names = list(doc.embfile_names())
    for name in names:
        doc.embfile_del(name)
    doc.xref_set_key(cat, "Names/EmbeddedFiles", "null")
    actions["embedded_files_removed"] = len(names)
    actions["actions_removed"] = _remove_actions(doc)
    actions["outline_titles_redacted"] = _redact_outline(doc, matcher)
    if any(matcher.find(t) for t in structure_strings(doc)):
        doc.xref_set_key(cat, "StructTreeRoot", "null")
        doc.xref_set_key(cat, "MarkInfo", "null")
        actions["structure_tree_removed"] = True
    return actions


_TRAILER_ID = re.compile(rb"/ID\s*\[\s*<([0-9A-Fa-f]{32})>\s*<([0-9A-Fa-f]{32})>\s*\]")


def stable_trailer_id(data: bytes) -> bytes:
    """Replace the random file identifier by one derived from the file itself, so the same input gives the same bytes.

    The new identifier has the same length, so no offset in the file moves. It carries nothing from the input file.
    """
    matches = list(_TRAILER_ID.finditer(data))
    if not matches:
        return data
    m = matches[-1]
    zeroed = data[:m.start(1)] + b"0" * 32 + data[m.end(1):m.start(2)] + b"0" * 32 + data[m.end(2):]
    ident = hashlib.sha256(zeroed).hexdigest()[:32].upper().encode()
    return data[:m.start(1)] + ident + data[m.end(1):m.start(2)] + ident + data[m.end(2):]


def serialise(doc) -> bytes:
    """A complete new file: one revision, no unreferenced objects, the same bytes for the same input."""
    return stable_trailer_id(doc.tobytes(garbage=4, deflate=True))


# ---------------------------------------------------------------- limits and report


def limits_of(doc) -> dict:
    with_images, image_only = [], []
    for pno, page in enumerate(doc, start=1):
        if page.get_images(full=True):
            with_images.append(pno)
            if not page.get_texttrace():
                image_only.append(pno)
    return {"pages_with_images": with_images, "image_only_pages": image_only, "notes": list(LIMIT_NOTES)}


def _close(doc) -> None:
    if doc is not None and not doc.is_closed:
        doc.close()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sorted_matches(items: list[dict]) -> list[dict]:
    return sorted(items, key=lambda m: (m["surface"], m["page"] or 0, m["revision"], str(m["source"]["id"]),
                                         m["match_kind"], m.get("class", "")))


def build_report(*, mode: str, input_info: dict, output_info: dict | None, terms_count: int, patterns: list[str],
                 options: list[str], removed: list[dict], actions: dict, findings: list[dict], checks: list[dict],
                 limits: dict, result: str, exit_code: int) -> dict:
    return {
        "schema_version": "1.0",
        "tool": {"name": "inkproof", "version": __version__},
        "mode": mode, "input": input_info, "output": output_info,
        "request": {"terms_count": terms_count, "patterns": sorted(set(patterns)), "options": sorted(options)},
        "removed": _sorted_matches(removed), "actions": actions, "findings": _sorted_matches(findings),
        "checks": checks, "limits": limits, "result": result, "exit_code": exit_code,
    }


def dump_report(report: dict) -> str:
    return json.dumps(report, sort_keys=True, indent=2) + "\n"


def _err(message: str) -> None:
    typer.echo(f"inkproof: {message}", err=True)


def masked_traceback(exc: BaseException) -> str:
    """Frames only: file name, line and function. No message, no source line, no local value."""
    lines = ["Traceback (most recent call last):"]
    for frame in traceback.extract_tb(exc.__traceback__):
        lines.append(f'  File "{os.path.basename(frame.filename)}", line {frame.lineno}, in {frame.name}')
    lines.append(f"{type(exc).__name__}: <message masked>")
    return "\n".join(lines)


# ---------------------------------------------------------------- the procedure


def read_sources(terms_path: Path | None, patterns: list[str], allow_short: bool) -> list:
    """Check the pattern names and read the terms file. Raises InputError for exit 2. Shared by apply and audit."""
    unknown = [p for p in patterns if p not in NAMES]
    if unknown:
        raise InputError("unknown pattern: " + ", ".join(unknown) + " (known: " + ", ".join(NAMES) + ")")
    if terms_path is None and not patterns:
        raise InputError("give at least one of --terms and --patterns")
    if terms_path is None:
        return []
    try:
        raw = terms_path.read_bytes()
    except OSError:
        raise InputError("the terms file cannot be read") from None
    return parse_terms(raw, allow_short=allow_short)


def run_apply(req: Request) -> int:
    """Run apply. Returns the exit code. Raises InputError for exit 2."""
    terms = read_sources(req.terms, req.patterns, req.allow_short_terms)
    if req.input.resolve() == req.output.resolve():
        raise InputError("the output file must differ from the input file")
    if req.output.exists() and not req.force:
        raise InputError("the output file exists (use --force to replace it)")
    try:
        data = req.input.read_bytes()
    except OSError:
        raise InputError("the input file cannot be read") from None

    options = [name for name, on in (("substring", req.substring), ("allow-short-terms", req.allow_short_terms),
                                     ("no-mark", req.no_mark), ("force", req.force)) if on]
    report_path = req.report or Path(str(req.output) + ".report.json")
    matcher = Matcher(terms, req.patterns, substring=req.substring)
    base = dict(mode="apply", terms_count=len(terms), patterns=req.patterns, options=options)
    input_info = {"sha256": _sha(data), "pages": 0, "revisions": 1}

    def write(code: int, result: str, **kw) -> None:
        fields = dict(output_info=None, removed=[], actions=empty_actions(), findings=[], checks=[],
                      limits={"pages_with_images": [], "image_only_pages": [], "notes": list(LIMIT_NOTES)})
        fields.update(kw)
        rep = build_report(input_info=input_info, result=result, exit_code=code, **base, **fields)
        report_path.write_text(dump_report(rep), encoding="utf-8")

    doc = None
    try:
        try:
            doc = open_document(data)
        except DocumentError as exc:
            _err(f"{exc}. No output was written.")
            write(3, "error")
            return 3
        input_info = {"sha256": _sha(data), "pages": doc.page_count, "revisions": max(doc.version_count, 1)}
        limits = limits_of(doc)
        actions = strip_surfaces(doc, matcher)       # first: annotation text is not page text
        removed = remove_s1(doc, matcher, mark=not req.no_mark, revision=input_info["revisions"])
        candidate = serialise(doc)
        _close(doc)
        doc = None
        outcome = verify(candidate, matcher, revision=1)
        checks = [{"id": c.id, "engine": c.engine, "engine_version": c.version, "result": c.result}
                  for c in outcome.checks]
        if not outcome.ok:
            survivors = sum(f["count"] for f in outcome.findings)
            write(1, "leaks-found", removed=removed, actions=actions, findings=outcome.findings, checks=checks,
                  limits=limits)
            _err(f"leaks found: {survivors} survivor(s) in the output, which was not written. "
                 f"The check covers the text layer only; text in images is not examined.")
            return 1
        parent = req.output.resolve().parent
        private = Path(tempfile.mkdtemp(dir=parent, prefix=".inkproof-"))
        try:
            staged = private / "candidate.pdf"
            staged.write_bytes(candidate)
            os.replace(staged, req.output)
        finally:
            shutil.rmtree(private, ignore_errors=True)
        write(0, "clean", output_info={"sha256": _sha(candidate), "pages": input_info["pages"], "revisions": 1},
              removed=removed, actions=actions, checks=checks, limits=limits)
        total = sum(m["count"] for m in removed)
        _err(f"clean: {total} match(es) removed and not found again by any check. "
             f"The check covers the text layer only; text in images is not examined.")
        return 0
    except typer.Exit:
        raise
    except Exception as exc:
        _err("internal error (E4). No output was written. Run again with --debug for a masked traceback.")
        if req.debug:
            typer.echo(masked_traceback(exc), err=True)
        try:
            write(4, "error")
        except Exception:
            pass
        return 4
    finally:
        _close(doc)
