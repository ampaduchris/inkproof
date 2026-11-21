"""The audit procedure (spec section 7): report the leaks in a PDF without changing it.

Audit reads the bytes of the file and never writes to it. It examines every surface S1 to S11 with both match kinds,
reconstructs each earlier revision, and gives every page-text match one leak class (spec 7.2).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

import pymupdf
import typer

from inkproof import __version__
from inkproof.apply import (DocumentError, LIMIT_NOTES, _close, _err, _sha, build_report, dump_report, empty_actions,
                            limits_of, masked_traceback, open_document, read_sources)
from inkproof.matcher import Matcher
from inkproof.terms import InputError
from inkproof.verify import (Glyph, Check, earlier_revisions, engine_versions, make_finding, page_text_with_glyphs,
                             revision_count, v2_text, v3_groups, v4_by_object)

COVER_SHARE = 0.9          # a later shape or image must cover this share of the match area (class `covered`)
SAME_COLOUR = 0.02         # the largest difference per channel that still counts as the same colour
EARLIER_SURFACES = {"S2", "S3", "S4", "S5", "S6", "S7"}   # spec 7.1: S1 to S7 of each earlier revision


@dataclass
class Request:
    input: Path
    terms: Path | None
    patterns: list[str]
    report: Path | None = None
    substring: bool = False
    allow_short_terms: bool = False
    debug: bool = False


@dataclass
class Outcome:
    findings: list[dict] = field(default_factory=list)
    checks: list[Check] = field(default_factory=list)
    limits: dict = field(default_factory=dict)
    pages: int = 0
    revisions: int = 1


# ---------------------------------------------------------------- geometry and colour


def _rgb(color) -> tuple[float, float, float] | None:
    if not color:
        return None
    if len(color) == 1:
        return (color[0],) * 3
    if len(color) == 3:
        return tuple(color)
    if len(color) == 4:
        c, m, y, k = color
        return ((1 - c) * (1 - k), (1 - m) * (1 - k), (1 - y) * (1 - k))
    return None


def _covered_area(box: pymupdf.Rect, rects: list[pymupdf.Rect]) -> float:
    """The area of `box` that lies under the union of `rects`."""
    clipped = [pymupdf.Rect(r) & box for r in rects]
    clipped = [r for r in clipped if not r.is_empty]
    if not clipped:
        return 0.0
    xs = sorted({box.x0, box.x1, *(v for r in clipped for v in (r.x0, r.x1))})
    ys = sorted({box.y0, box.y1, *(v for r in clipped for v in (r.y0, r.y1))})
    area = 0.0
    for x0, x1 in zip(xs, xs[1:]):
        for y0, y1 in zip(ys, ys[1:]):
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            if any(r.x0 <= cx <= r.x1 and r.y0 <= cy <= r.y1 for r in clipped):
                area += (x1 - x0) * (y1 - y0)
    return area


@dataclass(frozen=True)
class Cover:
    seqno: int
    rect: pymupdf.Rect
    color: tuple[float, float, float] | None   # None for an image


def page_covers(page) -> list[Cover]:
    """Filled shapes with full opacity and images, in drawing order."""
    out = [Cover(d["seqno"], pymupdf.Rect(d["rect"]), _rgb(d.get("fill")))
           for d in page.get_drawings()
           if d.get("fill") is not None and (d.get("fill_opacity") is None or d["fill_opacity"] >= 0.999)]
    out += [Cover(i, pymupdf.Rect(rect), None) for i, (kind, rect) in enumerate(page.get_bboxlog())
            if kind == "fill-image"]
    return sorted(out, key=lambda c: c.seqno)


def _outside(box: pymupdf.Rect, page: pymupdf.Rect) -> bool:
    return box.x1 <= page.x0 or box.x0 >= page.x1 or box.y1 <= page.y0 or box.y0 >= page.y1


def _solid(glyphs: list[Glyph]) -> list[Glyph]:
    return [g for g in glyphs if not g.ch.isspace() and g.box.width > 0 and g.box.height > 0] or glyphs


def leak_class(glyphs: list[Glyph], page_rect: pymupdf.Rect, covers: list[Cover]) -> str:
    """The class of one page-text match. The first rule in the order of spec 7.2 that holds wins."""
    glyphs = _solid(glyphs)
    if all(_outside(g.box, page_rect) for g in glyphs):
        return "off-page"
    if all(g.kind == 3 or g.opacity <= 0 for g in glyphs):
        return "invisible"
    area = sum(g.box.width * g.box.height for g in glyphs)
    if area > 0:
        got = sum(_covered_area(g.box, [c.rect for c in covers if c.seqno > g.seqno]) for g in glyphs)
        if got / area >= COVER_SHARE:
            return "covered"
    if all(_same_colour_as_beneath(g, covers) for g in glyphs):
        return "same-colour"
    return "visible"


def _same_colour_as_beneath(g: Glyph, covers: list[Cover]) -> bool:
    text = _rgb(g.color)
    if text is None:
        return False
    beneath: tuple[float, float, float] | None = (1.0, 1.0, 1.0)         # the page itself, where nothing is drawn
    area = g.box.width * g.box.height
    for c in reversed(covers):
        if c.seqno < g.seqno and area > 0 and _covered_area(g.box, [c.rect]) / area >= COVER_SHARE:
            beneath = c.color                                               # the nearest earlier covering shape
            break
    return beneath is not None and all(abs(a - b) <= SAME_COLOUR for a, b in zip(text, beneath))


# ---------------------------------------------------------------- the surfaces


def _drop_annotations(doc) -> None:
    """In memory only: annotation appearances are part of the page trace, and audit reports them as S2 or S3."""
    for page in doc:
        doc.xref_set_key(page.xref, "Annots", "null")


def page_matches(doc, matcher: Matcher, revision: int, classify: bool) -> list[tuple]:
    """S1: (surface, page, revision, source, kind, class) for each match of the page text."""
    records: list[tuple] = []
    for pno, page in enumerate(doc, start=1):
        text, index, glyphs = page_text_with_glyphs(page)
        matches = matcher.find(text)
        if not matches:
            continue
        covers = page_covers(page) if classify else []
        for m in matches:
            hit = [glyphs[index[p]] for p in range(m.start, m.end) if index[p] >= 0]
            cls = leak_class(hit, page.rect, covers) if classify else "earlier-revision"
            records.append(("S1", pno, revision, m.source, m.kind, cls))
    return records


def group_matches(groups, matcher: Matcher, revision: int, cls: str | None, only: set[str] | None = None) -> list[tuple]:
    """One count per item (annotation, entry, file, action ...) and source."""
    records: list[tuple] = []
    for surface, page, texts in groups:
        if only is not None and surface not in only:
            continue
        kinds: dict = {}
        for text in texts:
            for m in matcher.find(text):
                if kinds.get(m.source) != "exact":
                    kinds[m.source] = m.kind
        records += [(surface, page, revision, source, kind, cls) for source, kind in kinds.items()]
    return records


def raw_matches(data: bytes, matcher: Matcher, revision: int) -> list[tuple]:
    """S11: one count per object of the file and source."""
    records: list[tuple] = []
    for texts in v4_by_object(data):
        kinds: set = set()
        for text in texts:
            kinds |= {(m.source, m.kind) for m in matcher.find(text)}
        records += [("S11", None, revision, source, kind, None) for source, kind in kinds]
    return records


def _findings(records: list[tuple]) -> list[dict]:
    return [make_finding(*rec[:5], n, rec[5]) for rec, n in Counter(records).items()]


def audit_document(data: bytes, doc, matcher: Matcher) -> Outcome:
    """Examine S1 to S11 of the current revision and S1 to S7 of every earlier revision."""
    versions = engine_versions()
    revisions = revision_count(data)
    out = Outcome(pages=doc.page_count, revisions=revisions, limits=limits_of(doc))
    _drop_annotations(doc)
    v1 = page_matches(doc, matcher, revisions, classify=True)
    # engine B (pdfminer.six) can read what the trace cannot; its extra matches carry no class
    per_page = Counter((r[1], r[3]) for r in v1)
    extra: list[tuple] = []
    for pno, text in enumerate(v2_text(data), start=1):
        found = Counter()
        kinds: dict = {}
        for m in matcher.find(text):
            found[m.source] += 1
            kinds[m.source] = m.kind
        extra += [("S1", pno, revisions, source, kinds[source], None)
                  for source, n in found.items() for _ in range(n - per_page.get((pno, source), 0))]
    v3 = group_matches(v3_groups(data), matcher, revisions, None)
    earlier: list[tuple] = []
    for n, blob in enumerate(earlier_revisions(data), start=1):
        try:
            old = pymupdf.open(stream=blob, filetype="pdf")
        except Exception:
            continue
        try:
            _drop_annotations(old)
            earlier += page_matches(old, matcher, n, classify=False)
        finally:
            old.close()
        earlier += group_matches(v3_groups(blob), matcher, n, "earlier-revision", only=EARLIER_SURFACES)
    explained = {r[3] for r in v1 + extra + v3 + earlier}
    v4 = [r for r in raw_matches(data, matcher, revisions) if r[3] not in explained]
    out.findings = sorted(_findings(v1 + extra + v3 + earlier + v4),
                          key=lambda f: (f["surface"], f["page"] or 0, f["revision"], str(f["source"]["id"]),
                                         f["match_kind"], f.get("class", "")))
    failed = {"V1": bool(v1), "V2": bool(extra) or bool(v1), "V3": bool(v3), "V4": bool(v4), "V5": bool(earlier)}
    engines = {"V1": ("pymupdf", versions["pymupdf"]), "V2": ("pdfminer.six", versions["pdfminer.six"]),
               "V3": ("pymupdf", versions["pymupdf"]), "V4": ("inkproof-raw-scan", __version__),
               "V5": ("inkproof-revisions", __version__)}
    out.checks = [Check(i, *engines[i], "fail" if failed[i] else "pass") for i in ("V1", "V2", "V3", "V4", "V5")]
    return out


# ---------------------------------------------------------------- the procedure


def run_audit(req: Request) -> int:
    """Run audit. Returns the exit code. Raises InputError for exit 2."""
    terms = read_sources(req.terms, req.patterns, req.allow_short_terms)
    if req.report is not None and req.report.resolve() == req.input.resolve():
        raise InputError("the report path must differ from the audited file")
    try:
        data = req.input.read_bytes()
    except OSError:
        raise InputError("the input file cannot be read") from None
    options = [name for name, on in (("substring", req.substring), ("allow-short-terms", req.allow_short_terms)) if on]
    matcher = Matcher(terms, req.patterns, substring=req.substring)
    base = dict(mode="audit", terms_count=len(terms), patterns=req.patterns, options=options)
    input_info = {"sha256": _sha(data), "pages": 0, "revisions": 1}

    def emit(code: int, result: str, **kw) -> None:
        fields = dict(output_info=None, removed=[], actions=empty_actions(), findings=[], checks=[],
                      limits={"pages_with_images": [], "image_only_pages": [], "notes": list(LIMIT_NOTES)})
        fields.update(kw)
        text = dump_report(build_report(input_info=input_info, result=result, exit_code=code, **base, **fields))
        if req.report is not None:
            req.report.write_text(text, encoding="utf-8")
        else:
            typer.echo(text, nl=False)

    doc = None
    try:
        try:
            doc = open_document(data)
        except DocumentError as exc:
            _err(f"{exc}.")
            emit(3, "error")
            return 3
        outcome = audit_document(data, doc, matcher)
        input_info = {"sha256": input_info["sha256"], "pages": outcome.pages, "revisions": outcome.revisions}
        checks = [{"id": c.id, "engine": c.engine, "engine_version": c.version, "result": c.result}
                  for c in outcome.checks]
        leaks = sum(f["count"] for f in outcome.findings)
        code, result = (1, "leaks-found") if outcome.findings else (0, "clean")
        emit(code, result, findings=outcome.findings, checks=checks, limits=outcome.limits)
        _err((f"leaks found: {leaks} in {len(outcome.findings)} place(s). " if leaks else "clean: no leak found. ")
             + "The check covers the text layer only; text in images is not examined.")
        return code
    except typer.Exit:
        raise
    except Exception as exc:
        _err("internal error (E4). Run again with --debug for a masked traceback.")
        if req.debug:
            typer.echo(masked_traceback(exc), err=True)
        try:
            emit(4, "error")
        except Exception:
            pass
        return 4
    finally:
        _close(doc)
