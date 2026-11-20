"""Builds the 24 synthetic fixtures of spec section 10. Same output every run."""

from __future__ import annotations

import random
from io import BytesIO

from reportlab.pdfbase import pdfmetrics

from .pdfw import Pdf, esc, hexs, standard_encryption, utf16
from .values import (IBANS, NI_NUMBERS, S1_ENGINES, TAX_IDS, Canary, Fixture, email, prose, terms, word)

HELV = "Helvetica"
PASSWORD = "fixture-password"
INFO = b"<< /Producer (inkproof fixture generator) /CreationDate (D:20260101000000Z) >>"


class Doc:
    def __init__(self) -> None:
        self.p = Pdf()
        self.catalog = self.p.reserve()
        self.pages_obj = self.p.reserve()
        self.font = self.p.add("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
        self.pages: list[int] = []
        self.contents: dict[int, int] = {}

    def page(self, ops: bytes | str, resources: str = "", extra: str = "", media="0 0 612 792",
             num: int | None = None) -> int:
        if isinstance(ops, str):
            ops = ops.encode("cp1252")
        c = self.p.stream("", ops)
        res = f"<< /Font << /F1 {self.font} 0 R >> {resources} >>"
        n = self.p.add(f"<< /Type /Page /Parent {self.pages_obj} 0 R /MediaBox [{media}] /Resources {res} "
                       f"/Contents {c} 0 R {extra} >>", num)
        self.pages.append(n)
        self.contents[n] = c
        return n

    def finish(self, catalog_extra: str = "", info: bool = True, **kw) -> bytes:
        kids = " ".join(f"{n} 0 R" for n in self.pages)
        self.p.add(f"<< /Type /Pages /Kids [{kids}] /Count {len(self.pages)} >>", self.pages_obj)
        self.p.add(f"<< /Type /Catalog /Pages {self.pages_obj} 0 R {catalog_extra} >>", self.catalog)
        inf = self.p.add(INFO) if info else None
        self.info = inf
        data, self.xref = self.p.render(self.catalog, inf, **kw)
        return data


def T(x: float, y: float, s: str, size: int = 11, pre: str = "") -> str:
    return f"BT {pre} /F1 {size} Tf {x} {y} Td {esc(s).decode('cp1252')} Tj ET\n"


def lines_ops(lines: list[str], x: float, y: float, lead: int = 14, size: int = 11) -> str:
    return "".join(T(x, y - i * lead, s, size) for i, s in enumerate(lines))


def block(fid: str, split: bool, a: int) -> tuple[list[str], dict[str, str]]:
    """The standard lines that carry the six canaries of a removal layout."""
    w1, w2, w3 = terms(fid)
    vals = {"iban": IBANS[a % 2], "de-tax-id": TAX_IDS[a % 5], "uk-ni": NI_NUMBERS[a % 3],
            "email": email(fid), "term1": f"{w1} {w2}", "term2": w3}
    ls = [f"Account {vals['iban']} was checked.", f"Tax identifier {vals['de-tax-id']} on file.",
          f"Insurance number {vals['uk-ni']} on file.", f"Contact {vals['email']} for questions."]
    ls += [f"Please also record the visit by {w1}", f"{w2} in the register."] if split else \
        [f"Please also record the visit by {w1} {w2} in the register."]
    ls += [f"Further notes mention {w3} once."]
    return ls, vals


def canaries_for(vals: dict[str, str], count: dict[str, int] | None = None) -> list[Canary]:
    count = count or {}
    return [Canary("term" if k.startswith("term") else k, v, "S1", count.get(k, 1), S1_ENGINES)
            for k, v in vals.items()]


def r1() -> Fixture:
    ls, vals = block("R1", True, 0)
    pr = prose("R1", 6)
    data = Doc_single(lines_ops(pr + [""] + ls + [""] + prose("R1b", 3), 72, 720))
    return Fixture("R1", {"R1.pdf": data}, canaries_for(vals))


def Doc_single(ops: str, **kw) -> bytes:
    d = Doc()
    d.page(ops, **kw)
    return d.finish()


def r2() -> Fixture:
    ls, vals = block("R2", False, 1)
    left = prose("R2l", 5, 6) + [""] + ls[:3] + prose("R2m", 3, 6)
    right = prose("R2r", 5, 6) + [""] + ls[3:] + prose("R2n", 3, 6)
    data = Doc_single(lines_ops(left, 72, 720) + lines_ops(right, 320, 720))
    return Fixture("R2", {"R2.pdf": data}, canaries_for(vals))


def r3() -> Fixture:
    ls, vals = block("R3", False, 2)
    rows = [("Account", vals["iban"]), ("Tax identifier", vals["de-tax-id"]), ("Insurance number", vals["uk-ni"]),
            ("Contact", vals["email"]), ("Counterparty", vals["term1"]), ("Project", vals["term2"])]
    ops = ""
    y = 700
    for label, v in rows:
        ops += f"72 {y - 6} 400 22 re S\n" + f"72 {y - 6} 140 22 re S\n" + T(78, y, label) + T(220, y, v)
        y -= 22
    return Fixture("R3", {"R3.pdf": Doc_single(ops)}, canaries_for(vals))


def r4() -> Fixture:
    ls, vals = block("R4", False, 3)
    d = Doc()
    for i in range(3):
        ops = T(72, 760, f"{vals['iban']} {vals['de-tax-id']} {vals['uk-ni']}", 9)
        ops += T(72, 30, f"{vals['email']} {vals['term1']} {vals['term2']}", 9)
        body = prose(f"R4p{i}", 6)
        if i == 0:
            body += [""] + ls
        ops += lines_ops(body, 72, 700)
        d.page(ops)
    # header and footer on three pages, the block on page one: each value occurs 3 + 1 times
    return Fixture("R4", {"R4.pdf": d.finish()}, canaries_for(vals, {k: 4 for k in vals}))


def r5() -> Fixture:
    from reportlab.lib.pagesizes import letter
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas
    import reportlab, os
    pdfmetrics.registerFont(TTFont("Vera", os.path.join(os.path.dirname(reportlab.__file__), "fonts", "Vera.ttf")))
    fid = "R5"
    w1, w2, w3 = terms(fid)
    vals = {"iban": IBANS[0], "de-tax-id": TAX_IDS[4], "uk-ni": NI_NUMBERS[1], "email": email(fid),
            "term1": f"{w1} {w2}", "term2": w3}
    cut = 4
    lines = prose("R5a", 3, 10) + [f"Account {vals['iban']} and tax number {vals['de-tax-id']} were checked by {w1}",
            f"{w2} with insurance number {vals['uk-ni']} and mail to {vals['email']} before the visit",
            f"of {w3[:cut]}-", f"{w3[cut:]} was noted in the long register of the office"] + prose("R5b", 3, 10)
    buf = BytesIO()
    c = Canvas(buf, pagesize=letter, invariant=1, pageCompression=1)
    y = 720
    for line in lines:
        t = c.beginText(72, y)
        t.setFont("Vera", 11)
        spaces = line.count(" ")
        t.setWordSpace((468 - pdfmetrics.stringWidth(line, "Vera", 11)) / spaces if spaces else 0)
        t.textOut(line)
        c.drawText(t)
        y -= 14
    c.showPage()
    c.save()
    cs = canaries_for(vals)
    # pdfminer.six splits justified lines at wide word gaps and returns the hyphenated word apart (DEV-009)
    cs[-1] = Canary("term", w3, "S1", 1, ("pymupdf-trace", "pypdf"), note="hyphenated at a line end")
    return Fixture("R5", {"R5.pdf": buf.getvalue()}, cs)


# ---------------------------------------------------------------- audit fixtures

VIS = "Quarterly summary of supplies and visits."


def hidden(fid: str):
    w1, w2, w3 = terms(fid)
    return w3, email(fid)


def hid_canaries(term: str, mail: str, surface: str = "S1") -> list[Canary]:
    return [Canary("term", term, surface, 1, S1_ENGINES), Canary("email", mail, surface, 1, S1_ENGINES)]


def a01() -> Fixture:
    t, e = hidden("A01")
    ops = T(72, 700, VIS) + T(72, 680, f"Held {t}") + T(72, 666, f"Held {e}") + "0 g 66 660 300 36 re f\n"
    return Fixture("A01", {"A01.pdf": Doc_single(ops)}, hid_canaries(f"{t}", e))


def a02() -> Fixture:
    t, e = hidden("A02")
    d = Doc()
    rng = random.Random("inkproof-1.3-A02-img")
    img = d.p.stream("/Type /XObject /Subtype /Image /Width 4 /Height 4 /ColorSpace /DeviceRGB /BitsPerComponent 8",
                     bytes(rng.randrange(90, 140) for _ in range(48)))
    ops = T(72, 700, VIS) + T(72, 680, f"Held {t}") + T(72, 666, f"Held {e}") + \
        "q 300 0 0 36 66 660 cm /Im1 Do Q\n"
    d.page(ops, resources=f"/XObject << /Im1 {img} 0 R >>")
    return Fixture("A02", {"A02.pdf": d.finish()}, hid_canaries(t, e))


def a03() -> Fixture:
    t, e = hidden("A03")
    ops = T(72, 700, VIS) + "1 g\n" + T(72, 680, f"Held {t}") + T(72, 666, f"Held {e}")
    return Fixture("A03", {"A03.pdf": Doc_single(ops)}, hid_canaries(t, e))


def a04() -> Fixture:
    t, e = hidden("A04")
    panel = "0.2 0.4 0.8"
    ops = T(72, 700, VIS) + f"{panel} rg 66 660 300 36 re f\n" + f"{panel} rg\n" + T(72, 680, f"Held {t}") + \
        T(72, 666, f"Held {e}")
    return Fixture("A04", {"A04.pdf": Doc_single(ops)}, hid_canaries(t, e))


def a05() -> Fixture:
    t, e = hidden("A05")
    ops = T(72, 700, VIS) + T(700, 680, f"Held {t}") + T(700, 666, f"Held {e}")
    return Fixture("A05", {"A05.pdf": Doc_single(ops)}, hid_canaries(t, e))


def a06() -> Fixture:
    t, e = hidden("A06")
    ops = T(320, 650, VIS) + T(20, 400, f"Held {t}") + T(20, 386, f"Held {e}")
    d = Doc()
    d.page(ops, extra="/CropBox [300 100 500 700]")
    return Fixture("A06", {"A06.pdf": d.finish()}, hid_canaries(t, e))


def a07() -> Fixture:
    fid = "A07"
    t = word(fid, "c", 3)
    iban = IBANS[0]
    d = Doc()
    # strings are hexadecimal so that a plain byte search of the old revision finds nothing (E3, E4)
    h = lambda s: "<" + s.encode("cp1252").hex().upper() + ">"  # noqa: E731
    ops1 = f"BT /F1 11 Tf 72 700 Td {h(VIS)} Tj 0 -16 Td {h('Held ' + t)} Tj 0 -16 Td {h('Held ' + iban)} Tj ET\n"
    pg = d.page(ops1)
    first = d.finish()
    ops2 = f"BT /F1 11 Tf 72 700 Td {h(VIS)} Tj ET\n"
    d.p.stream("", ops2.encode(), num=d.contents[pg])
    size = max(d.p.objs) + 1
    second = d.p.update(first, d.xref, [d.contents[pg]], d.catalog, size, d.info)
    cs = [Canary("term", t, "S8", 1, ("rev1-pymupdf-trace", "rev1-pdfminer", "rev1-pypdf")),
          Canary("iban", iban, "S8", 1, ("rev1-pymupdf-trace", "rev1-pdfminer", "rev1-pypdf")),
          Canary("term", t, "S1", 0, S1_ENGINES, absent=True, note="absent from the current revision"),
          Canary("iban", iban, "S1", 0, S1_ENGINES, absent=True, note="absent from the current revision")]
    return Fixture("A07", {"A07.pdf": second}, cs, meta={"revisions": 2})


def a08() -> Fixture:
    fid = "A08"
    v1, v2 = word(fid, "c", 3), email(fid)
    d = Doc()
    pg, ft, tx, pop, ap = (d.p.reserve() for _ in range(5))
    d.p.stream("/Type /XObject /Subtype /Form /BBox [0 0 228 40] /Resources << /Font << /F1 %d 0 R >> >>" % d.font,
               T(4, 14, v1, 12).encode(), num=ap)
    d.p.add(f"<< /Type /Annot /Subtype /FreeText /Rect [72 600 300 640] /Contents {esc(v1).decode()} "
            f"/DA (/F1 12 Tf 0 g) /F 4 /T (Reviewer) /AP << /N {ap} 0 R >> >>", ft)
    d.p.add(f"<< /Type /Annot /Subtype /Text /Rect [72 500 92 520] /Contents (See note) /T (Reviewer) "
            f"/Popup {pop} 0 R /F 4 >>", tx)
    d.p.add(f"<< /Type /Annot /Subtype /Popup /Rect [100 450 300 520] /Parent {tx} 0 R "
            f"/Contents {esc(v2).decode()} /Open false >>", pop)
    d.page(T(72, 700, VIS), extra=f"/Annots [{ft} 0 R {tx} 0 R {pop} 0 R]", num=pg)
    cs = [Canary("term", v1, "S2", 1, ("annots-pymupdf", "annots-pypdf", "raw")),
          Canary("email", v2, "S2", 1, ("annots-pymupdf", "annots-pypdf", "raw"), note="pop-up note")]
    return Fixture("A08", {"A08.pdf": d.finish()}, cs)


def a09() -> Fixture:
    t, e = hidden("A09")
    ops = T(72, 700, VIS) + T(72, 680, f"Held {t}", pre="3 Tr") + T(72, 666, f"Held {e}", pre="3 Tr")
    return Fixture("A09", {"A09.pdf": Doc_single(ops)}, hid_canaries(t, e))


def a10() -> Fixture:
    fid = "A10"
    c = {k: word(fid, k, 3) for k in "infoxmpoutlinefieldfile".split() if False}
    vals = {k: word(fid, k, 3) for k in ("info", "xmp", "outline", "field", "file")}
    d = Doc()
    pg, wd, ol, oi, xm, fs, ef = (d.p.reserve() for _ in range(7))
    d.page(T(72, 700, VIS), extra=f"/Annots [{wd} 0 R]", num=pg)
    d.p.add(f"<< /Type /Annot /Subtype /Widget /FT /Tx /T (field1) /V {esc(vals['field']).decode()} "
            f"/Rect [72 400 300 420] /F 4 /P {pg} 0 R >>", wd)
    d.p.add(f"<< /Type /Outlines /First {oi} 0 R /Last {oi} 0 R /Count 1 >>", ol)
    d.p.add(f"<< /Title {esc(vals['outline']).decode()} /Parent {ol} 0 R /Dest [{pg} 0 R /Fit] >>", oi)
    xmp = ('<?xpacket begin="" id="W5M0MpCehiHzreSzNTczkc9d"?><x:xmpmeta xmlns:x="adobe:ns:meta/">'
           '<rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"><rdf:Description rdf:about="" '
           'xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:subject><rdf:Bag><rdf:li>' + vals["xmp"] +
           '</rdf:li></rdf:Bag></dc:subject></rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="w"?>')
    d.p.stream("/Type /Metadata /Subtype /XML", xmp.encode(), compress=False, num=xm)
    d.p.stream("/Type /EmbeddedFile /Subtype /text#2Fplain", f"Held {vals['file']}\n".encode(), num=ef)
    d.p.add(f"<< /Type /Filespec /F (note.txt) /UF (note.txt) /EF << /F {ef} 0 R >> >>", fs)
    extra = (f"/Outlines {ol} 0 R /PageMode /UseOutlines /Metadata {xm} 0 R "
             f"/AcroForm << /Fields [{wd} 0 R] /DA (/F1 0 Tf 0 g) /DR << /Font << /F1 {d.font} 0 R >> >> >> "
             f"/Names << /EmbeddedFiles << /Names [(note.txt) {fs} 0 R] >> >>")
    # the information dictionary carries the first canary
    d.p.add(f"<< /Title {esc(vals['info']).decode()} /Producer (inkproof fixture generator) "
            f"/CreationDate (D:20260101000000Z) >>", d.p.reserve())
    info_num = d.p.next - 1
    kids = f"{pg} 0 R"
    d.p.add(f"<< /Type /Pages /Kids [{kids}] /Count 1 >>", d.pages_obj)
    d.p.add(f"<< /Type /Catalog /Pages {d.pages_obj} 0 R {extra} >>", d.catalog)
    data, _ = d.p.render(d.catalog, info_num)
    cs = [Canary("term", vals["info"], "S4", 1, ("meta-pymupdf", "meta-pypdf", "raw")),
          Canary("term", vals["xmp"], "S4", 1, ("xmp-pymupdf", "xmp-pypdf", "raw")),
          Canary("term", vals["outline"], "S5", 1, ("outline-pymupdf", "outline-pypdf", "raw")),
          Canary("term", vals["field"], "S3", 1, ("widgets-pymupdf", "fields-pypdf", "raw")),
          Canary("term", vals["file"], "S6", 1, ("embfile-pymupdf", "embfile-pypdf", "raw"))]
    return Fixture("A10", {"A10.pdf": data}, cs)


# ---------------------------------------------------------------- control and edge fixtures

def c01() -> Fixture:
    ls, vals = block("C01", False, 0)
    ops = lines_ops(prose("C01", 6), 72, 720)
    y = 600
    for _ in ls:
        ops += f"0 g 66 {y - 4} 360 16 re f\n"  # black marks where text used to be; no text remains
        y -= 14
    cs = [Canary(("term" if k.startswith("term") else k), v, s, 0, ch, absent=True)
          for k, v in vals.items() for s, ch in (("S1", S1_ENGINES),)]
    return Fixture("C01", {"C01.pdf": Doc_single(ops)}, cs, meta={"revisions": 1})


FONT2 = ("<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding << /Type /Encoding /BaseEncoding "
         "/WinAnsiEncoding /Differences [1 /uni00AD 2 /uni200D] >> /ToUnicode %d 0 R >>")
CMAP = (b"/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CMapName /Adobe-Identity-UCS def "
        b"/CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfrange <20> <7E> <0020> "
        b"endbfrange 2 beginbfchar <01> <00AD> <02> <200D> endbfchar endcmap CMapName currentdict /CMap "
        b"defineresource pop end end")


def x01() -> Fixture:
    fid = "X01"
    w = word(fid, "c", 3)
    v = word(fid, "d", 3)
    d = Doc()
    cm = d.p.stream("", CMAP)
    f2 = d.p.add(FONT2 % cm)
    f1, f2w, f3 = w[:2], w[2:-4], w[-4:]
    sw = lambda s: pdfmetrics.stringWidth(s, HELV, 12)  # noqa: E731
    ops = (f"BT /F1 12 Tf 72 700 Td ({f1}) Tj {sw(f1) + 30:.2f} 0 Td ({f2w}) Tj {sw(f2w):.2f} 0 Td ({f3}) Tj ET\n")
    mixed = v[:3] + "\x01" + v[3:6] + "\x02" + v[6:]
    ops += f"BT /F2 12 Tf 72 660 Td ({mixed}) Tj ET\n"
    d.page(ops, resources="", extra="")
    # add the second font to the page resources
    pg = d.pages[0]
    d.p.objs[pg] = d.p.objs[pg].replace(b"/F1 %d 0 R" % d.font, b"/F1 %d 0 R /F2 %d 0 R" % (d.font, f2))
    cs = [Canary("term", w, "S1", 1, S1_ENGINES, note="fragments with a wide gap"),
          Canary("term", v, "S1", 1, S1_ENGINES, note="soft hyphen and zero-width joiner inside")]
    return Fixture("X01", {"X01.pdf": d.finish()}, cs)


def x02() -> Fixture:
    fid = "X02"
    a, b, c = word(fid, "a", 3), word(fid, "b", 3), word(fid, "c", 3)
    h = lambda s: "<" + s.encode("cp1252").hex().upper() + ">"  # noqa: E731
    p1, p2, p3 = c[:3], c[3:6], c[6:]
    ops = (f"BT /F1 12 Tf 72 700 Td {h('Held ' + a)} Tj 0 -16 Td [({'Held ' + p1}) -15 ({p2}) 20 ({p3})] TJ ET\n")
    d = Doc()
    d.page(ops)
    d.p.add(f"<< /Title (fixture) /Subject ".encode() + utf16(b) + b" /Producer (inkproof fixture generator) "
            b"/CreationDate (D:20260101000000Z) >>", d.p.reserve())
    info = d.p.next - 1
    kids = " ".join(f"{n} 0 R" for n in d.pages)
    d.p.add(f"<< /Type /Pages /Kids [{kids}] /Count 1 >>", d.pages_obj)
    d.p.add(f"<< /Type /Catalog /Pages {d.pages_obj} 0 R >>", d.catalog)
    data, _ = d.p.render(d.catalog, info)
    cs = [Canary("term", a, "S11", 1, ("raw",), note="hexadecimal string"),
          Canary("term", b, "S11", 1, ("raw",), note="UTF-16 string"),
          Canary("term", c, "S11", 1, ("raw",), note="split across the elements of one TJ operator")]
    return Fixture("X02", {"X02.pdf": data}, cs)


def x03() -> Fixture:
    fid = "X03"
    t = word(fid, "c", 3)
    d = Doc()
    d.page(T(72, 700, VIS) + T(72, 680, f"Held {t}"))
    body, key = standard_encryption(PASSWORD.encode(), b"fixture-owner-password")
    enc = d.p.add(body)
    kids = " ".join(f"{n} 0 R" for n in d.pages)
    d.p.add(f"<< /Type /Pages /Kids [{kids}] /Count 1 >>", d.pages_obj)
    d.p.add(f"<< /Type /Catalog /Pages {d.pages_obj} 0 R >>", d.catalog)
    data, _ = d.p.render(d.catalog, None, encrypt=(enc, b"", b""), enc_key=key)
    return Fixture("X03", {"X03.pdf": data}, [Canary("term", t, "S1", 1, ("auth:pymupdf-trace", "auth:pdfminer", "auth:pypdf"))],
                   password=PASSWORD)


def x04() -> Fixture:
    r = r1().files["R1.pdf"]
    return Fixture("X04", {"X04-truncated.pdf": r[: int(len(r) * 0.55)],
                           "X04-not-a-pdf.bin": b"This file is not a PDF. It is a plain text stand-in.\n"})


def x05() -> Fixture:
    fid = "X05"
    t, e = word(fid, "c", 3), email(fid)
    d = Doc()
    fm2 = d.p.stream("/Type /XObject /Subtype /Form /BBox [0 0 400 100] /Resources << /Font << /F1 %d 0 R >> >>"
                     % d.font, (T(10, 60, f"Held {t}") + T(10, 40, f"Held {e}")).encode())
    fm1 = d.p.stream("/Type /XObject /Subtype /Form /BBox [0 0 400 100] /Resources << /XObject << /Fm2 %d 0 R >> >>"
                     % fm2, b"/Fm2 Do\n")
    d.page("q 1 0 0 1 72 600 cm /Fm1 Do Q\n" + T(72, 700, VIS), resources=f"/XObject << /Fm1 {fm1} 0 R >>")
    return Fixture("X05", {"X05.pdf": d.finish()}, hid_canaries(t, e))


def x06() -> Fixture:
    fid = "X06"
    t = word(fid, "c", 3)
    d = Doc()
    rng = random.Random("inkproof-1.3-X06-img")
    img = d.p.stream("/Type /XObject /Subtype /Image /Width 8 /Height 8 /ColorSpace /DeviceRGB /BitsPerComponent 8",
                     bytes(rng.randrange(256) for _ in range(192)))
    res = f"/XObject << /Im1 {img} 0 R >>"
    d.page("q 200 0 0 200 100 500 cm /Im1 Do Q\n", resources=res)
    d.page("q 200 0 0 200 100 500 cm /Im1 Do Q\n" + T(72, 700, f"Held {t}"), resources=res)
    return Fixture("X06", {"X06.pdf": d.finish()}, [Canary("term", t, "S1", 1, S1_ENGINES)],
                   meta={"image_pages": [1, 2], "image_only_pages": [1]})


def x07() -> Fixture:
    fid = "X07"
    alt, act = word(fid, "c", 3), word(fid, "d", 3)
    d = Doc()
    pg = d.page(T(72, 700, VIS))
    root, el = d.p.reserve(), d.p.reserve()
    d.p.add(f"<< /Type /StructTreeRoot /K {el} 0 R >>", root)
    d.p.add(f"<< /Type /StructElem /S /Figure /P {root} 0 R /Pg {pg} 0 R /Alt {esc(alt).decode()} "
            f"/ActualText {esc(act).decode()} >>", el)
    data = d.finish(f"/MarkInfo << /Marked true >> /StructTreeRoot {root} 0 R")
    ch = ("raw", "struct-pymupdf", "struct-pypdf")
    return Fixture("X07", {"X07.pdf": data}, [Canary("term", alt, "S9", 1, ch, note="alternative text"),
                                              Canary("term", act, "S9", 1, ch, note="actual text")])


def x08() -> Fixture:
    fid = "X08"
    dn, nt, pl, lay = (word(fid, k, 3) for k in "cdef")
    d = Doc()
    pg = d.page(T(72, 700, VIS))
    ocg = d.p.add(f"<< /Type /OCG /Name (Layer {lay}) >>")
    extra = (f"/Dests << /{dn} [{pg} 0 R /Fit] >> /Names << /Dests << /Names [({nt}) [{pg} 0 R /Fit]] >> >> "
             f"/PageLabels << /Nums [0 << /S /D /P ({pl}-) >>] >> "
             f"/OCProperties << /OCGs [{ocg} 0 R] /D << /Order [{ocg} 0 R] /ON [{ocg} 0 R] >> >>")
    data = d.finish(extra)
    both = ("dests-pymupdf", "dests-pypdf", "raw")
    tree = ("dests-pymupdf", "raw")  # pypdf returns only the /Dests dictionary when both forms are present
    cs = [Canary("term", dn, "S5", 1, both, note="/Dests dictionary"),
          Canary("term", nt, "S5", 1, tree, note="name tree (/Names)"),
          Canary("term", pl, "S5", 1, ("labels-pymupdf", "labels-pypdf", "raw"), note="page label prefix"),
          Canary("term", lay, "S10", 1, ("ocg-pymupdf", "ocg-pypdf", "raw"))]
    return Fixture("X08", {"X08.pdf": data}, cs)


ORDER = [r1, r2, r3, r4, r5, c01, x01, x02, x03, x04, x05, x06, x07, x08,
         a01, a02, a03, a04, a05, a06, a07, a08, a09, a10]


def build_all() -> dict[str, Fixture]:
    out = {}
    for f in ORDER:
        fx = f()
        out[fx.id] = fx
    return out


def write_all(directory) -> dict[str, Fixture]:
    from pathlib import Path
    out = build_all()
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    for fx in out.values():
        for name, data in fx.files.items():
            (d / name).write_bytes(data)
    return out
