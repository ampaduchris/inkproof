"""N5 probe (spec section 12.3): nested form object, tagged file, layer name, named
destination, page label. Synthetic one-page files built with PyMuPDF low-level calls.
No real documents. Run: uv run --locked python docs/probes/n5_probe.py"""
import io
import sys

import pymupdf
import pypdf
from pdfminer.high_level import extract_text as miner_text

print("python", sys.version.split()[0], "pymupdf", pymupdf.__version__, "mupdf", pymupdf.mupdf_version, "pypdf", pypdf.__version__)

FONT = "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"


def new_doc():
    d = pymupdf.open()
    d.new_page()
    return d


def add_obj(d, text, stream=None):
    x = d.get_new_xref()
    d.update_object(x, text)
    if stream is not None:
        d.update_stream(x, stream)
    return x


def engines(data: bytes, needle: str):
    out = {}
    out["pypdf"] = needle in "".join((p.extract_text() or "") for p in pypdf.PdfReader(io.BytesIO(data)).pages)
    out["pdfminer"] = needle in miner_text(io.BytesIO(data))
    doc = pymupdf.open(stream=data, filetype="pdf")
    out["mu_text"] = any(needle in pg.get_text() for pg in doc)
    out["mu_trace"] = any(needle in "".join(s["chars"] and "".join(c[0] if isinstance(c[0], str) else chr(c[0]) for c in s["chars"]) or "" for s in pg.get_texttrace()) for pg in doc)
    out["mu_search"] = any(pg.search_for(needle) for pg in doc)
    out["raw_bytes"] = needle.encode() in data
    return out


def fmt(r):
    return " ".join(f"{k}={'Y' if v else '-'}" for k, v in r.items())


# ---- X05: text inside a form object nested two levels deep
d = new_doc()
f = add_obj(d, FONT)
inner = add_obj(d, f"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << /Font << /F1 {f} 0 R >> >> >>",
                b"BT /F1 14 Tf 72 700 Td (CANARY-X05) Tj ET")
outer = add_obj(d, f"<< /Type /XObject /Subtype /Form /BBox [0 0 612 792] /Resources << /XObject << /Fm2 {inner} 0 R >> >> >>",
                b"/Fm2 Do")
d[0].set_contents(add_obj(d, "<< >>", b"/Fm1 Do"))
res = d.xref_get_key(d[0].xref, "Resources")
d.xref_set_key(d[0].xref, "Resources", f"<< /XObject << /Fm1 {outer} 0 R >> >>")
x05 = d.tobytes(garbage=0)
print("\nX05 nested form text:")
print(" ", fmt(engines(x05, "CANARY-X05")))

# Does the redaction call remove it? Locate by trace, as the spec requires.
doc = pymupdf.open(stream=x05, filetype="pdf")
pg = doc[0]
tr = pg.get_texttrace()
print("  trace spans:", len(tr), "bbox", [tuple(round(v) for v in s["bbox"]) for s in tr][:2])
for s in tr:
    pg.add_redact_annot(pymupdf.Rect(s["bbox"]))
pg.apply_redactions(images=0)
after = doc.tobytes(garbage=4, deflate=True)
print("  after apply_redactions + full save:", fmt(engines(after, "CANARY-X05")))
# Stream scan: does any decoded stream still hold the string?
doc2 = pymupdf.open(stream=after, filetype="pdf")
hit = [x for x in range(1, doc2.xref_length()) if (doc2.xref_is_stream(x) and b"CANARY-X05" in (doc2.xref_stream(x) or b""))]
print("  decoded streams still holding it:", hit)

# ---- X07: tagged file, value in alternative text
d = new_doc()
d[0].insert_text((72, 100), "visible body text")
elem = add_obj(d, "<< /Type /StructElem /S /Figure /Alt (CANARY-X07) /ActualText (CANARY-X07B) /P 0 0 R >>")
root = add_obj(d, f"<< /Type /StructTreeRoot /K {elem} 0 R >>")
d.xref_set_key(elem, "P", f"{root} 0 R")
cat = d.pdf_catalog()
d.xref_set_key(cat, "StructTreeRoot", f"{root} 0 R")
d.xref_set_key(cat, "MarkInfo", "<< /Marked true >>")
x07 = d.tobytes(garbage=0)
print("\nX07 alt text in structure tree:")
print("  alt  :", fmt(engines(x07, "CANARY-X07")))
print("  actual:", fmt(engines(x07, "CANARY-X07B")))
doc = pymupdf.open(stream=x07, filetype="pdf")
c = doc.pdf_catalog()
print("  reach via catalog key:", doc.xref_get_key(c, "StructTreeRoot"))
r = pypdf.PdfReader(io.BytesIO(x07))
print("  reach via pypdf:", "/StructTreeRoot" in r.trailer["/Root"])
# Removal: drop the key, full save with garbage collection
doc.xref_set_key(c, "StructTreeRoot", "null")
doc.xref_set_key(c, "MarkInfo", "null")
gone = doc.tobytes(garbage=4, deflate=True)
print("  after dropping StructTreeRoot + gc4:", "alt bytes present:", b"CANARY-X07" in gone)

# ---- X08: named destination, page label, layer name
d = new_doc()
d[0].insert_text((72, 100), "body")
pgx = d[0].xref
dest = f"[{pgx} 0 R /Fit]"
ocg = add_obj(d, "<< /Type /OCG /Name (CANARY-X08-LAYER) >>")
cat = d.pdf_catalog()
d.xref_set_key(cat, "Dests", f"<< /CANARY-X08-DEST {dest} >>")
d.xref_set_key(cat, "PageLabels", "<< /Nums [0 << /P (CANARY-X08-LABEL) /S /D >>] >>")
d.xref_set_key(cat, "OCProperties", f"<< /OCGs [{ocg} 0 R] /D << /Order [{ocg} 0 R] /ON [{ocg} 0 R] >> >>")
x08 = d.tobytes(garbage=0)
print("\nX08 named destination, page label, layer name:")
for n in ("CANARY-X08-DEST", "CANARY-X08-LABEL", "CANARY-X08-LAYER"):
    print(f"  {n:18}", fmt(engines(x08, n)))
doc = pymupdf.open(stream=x08, filetype="pdf")
print("  mupdf: labels:", doc.get_page_labels())
print("  mupdf: layers:", [o.get("name") if isinstance(o, dict) else o for o in (doc.get_ocgs() or {}).values()] if hasattr(doc, "get_ocgs") else "no api")
try:
    print("  mupdf: named dests:", list(doc.resolve_names().keys()))
except Exception as e:  # noqa: BLE001
    print("  mupdf: resolve_names error", type(e).__name__)
r = pypdf.PdfReader(io.BytesIO(x08))
print("  pypdf: named_destinations:", list(r.named_destinations.keys()), "page_labels:", r.page_labels, "layers:", [str(x.get_object().get("/Name")) for x in r.trailer["/Root"]["/OCProperties"]["/OCGs"]])
# decode through a full save: do the strings survive gc and compression (are they in decoded objects)?
saved = pymupdf.open(stream=x08, filetype="pdf").tobytes(garbage=4, deflate=True)
print("  after gc4+deflate raw bytes hold:", {n: n.encode() in saved for n in ("CANARY-X08-DEST", "CANARY-X08-LABEL", "CANARY-X08-LAYER")})
doc = pymupdf.open(stream=saved, filetype="pdf")
cat = doc.pdf_catalog()
print("  catalog keys after gc:", [k for k in doc.xref_get_keys(cat) if k in ("Dests", "PageLabels", "OCProperties", "Names")])
# Are strings visible in object bodies when objects are inside object streams?
inside = [x for x in range(1, doc.xref_length()) if "CANARY-X08" in (doc.xref_object(x, compressed=False) or "")]
print("  xref objects whose body holds a canary:", len(inside))
