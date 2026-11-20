"""A small deterministic PDF writer for fixtures.

Everything is fixed: object order, the document id, no dates except literal ones.
PyMuPDF is not used to write fixtures because its output differs between runs.
"""

from __future__ import annotations

import hashlib
import zlib

DOC_ID = hashlib.md5(b"inkproof-fixture-id").digest()


def esc(s: str | bytes) -> bytes:
    b = s.encode("cp1252") if isinstance(s, str) else s
    return b"(" + b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)") + b")"


def hexs(b: bytes) -> bytes:
    return b"<" + b.hex().upper().encode() + b">"


def utf16(s: str) -> bytes:
    return hexs(b"\xfe\xff" + s.encode("utf-16-be"))


def rc4(key: bytes, data: bytes) -> bytes:
    s = list(range(256))
    j = 0
    for i in range(256):
        j = (j + s[i] + key[i % len(key)]) % 256
        s[i], s[j] = s[j], s[i]
    out = bytearray()
    i = j = 0
    for byte in data:
        i = (i + 1) % 256
        j = (j + s[i]) % 256
        s[i], s[j] = s[j], s[i]
        out.append(byte ^ s[(s[i] + s[j]) % 256])
    return bytes(out)


class Pdf:
    def __init__(self) -> None:
        self.objs: dict[int, bytes] = {}
        self.next = 1

    def reserve(self) -> int:
        n = self.next
        self.next += 1
        return n

    def add(self, body: bytes | str, num: int | None = None) -> int:
        n = num or self.reserve()
        self.objs[n] = body.encode("cp1252") if isinstance(body, str) else body
        return n

    def stream(self, d: str, data: bytes, compress: bool = True, num: int | None = None) -> int:
        if compress:
            data = zlib.compress(data, 9)
            d += " /Filter /FlateDecode"
        body = b"<< " + d.encode("cp1252") + b" /Length %d >>\nstream\n" % len(data) + data + b"\nendstream"
        return self.add(body, num)

    def _render_objs(self, out: bytearray, nums: list[int], offsets: dict[int, int], enc=None) -> None:
        for n in nums:
            offsets[n] = len(out)
            body = self.objs[n]
            if enc is not None and body.startswith(b"<<") and b"\nstream\n" in body:
                head, _, rest = body.partition(b"\nstream\n")
                data = rest[: -len(b"\nendstream")]
                data = rc4(enc(n), data)
                body = head + b"\nstream\n" + data + b"\nendstream"
            out += b"%d 0 obj\n" % n + body + b"\nendobj\n"

    def render(self, root: int, info: int | None = None, encrypt: tuple[int, bytes, bytes] | None = None,
               enc_key=None) -> tuple[bytes, int]:
        """Full file. Returns (bytes, offset of its xref table)."""
        out = bytearray(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets: dict[int, int] = {}
        self._render_objs(out, sorted(self.objs), offsets, enc_key)
        xref = len(out)
        size = max(self.objs) + 1
        out += b"xref\n0 %d\n0000000000 65535 f \n" % size
        for n in range(1, size):
            out += b"%010d 00000 n \n" % offsets[n]
        tr = b"<< /Size %d /Root %d 0 R" % (size, root)
        if info:
            tr += b" /Info %d 0 R" % info
        if encrypt:
            tr += b" /Encrypt %d 0 R" % encrypt[0]
        tr += b" /ID [" + hexs(DOC_ID) + hexs(DOC_ID) + b"] >>"
        out += b"trailer\n" + tr + b"\nstartxref\n%d\n%%%%EOF\n" % xref
        return bytes(out), xref

    def update(self, base: bytes, prev_xref: int, changed: list[int], root: int, size: int,
               info: int | None = None) -> bytes:
        """Append an incremental update holding the objects in `changed`."""
        out = bytearray(base)
        offsets: dict[int, int] = {}
        self._render_objs(out, changed, offsets)
        xref = len(out)
        out += b"xref\n"
        for n in changed:
            out += b"%d 1\n%010d 00000 n \n" % (n, offsets[n])
        tr = b"<< /Size %d /Root %d 0 R /Prev %d" % (size, root, prev_xref)
        if info:
            tr += b" /Info %d 0 R" % info
        tr += b" /ID [" + hexs(DOC_ID) + hexs(DOC_ID) + b"] >>"
        out += b"trailer\n" + tr + b"\nstartxref\n%d\n%%%%EOF\n" % xref
        return bytes(out)


PAD = bytes.fromhex("28BF4E5E4E758A4164004E56FFFA01082E2E00B6D0683E802F0CA9FE6453697A")


def standard_encryption(user_pw: bytes, owner_pw: bytes, perms: int = -4):
    """RC4 128-bit standard security handler (revision 3). Returns (dict body, key function)."""
    n = 16
    p = (perms & 0xFFFFFFFF).to_bytes(4, "little")
    h = hashlib.md5((owner_pw + PAD)[:32]).digest()
    for _ in range(50):
        h = hashlib.md5(h).digest()
    okey = h[:n]
    o = rc4(okey, (user_pw + PAD)[:32])
    for i in range(1, 20):
        o = rc4(bytes(b ^ i for b in okey), o)
    k = hashlib.md5((user_pw + PAD)[:32] + o + p + DOC_ID).digest()
    for _ in range(50):
        k = hashlib.md5(k[:n]).digest()
    key = k[:n]
    u = rc4(key, hashlib.md5(PAD + DOC_ID).digest())
    for i in range(1, 20):
        u = rc4(bytes(b ^ i for b in key), u)
    u = u + bytes(16)
    body = b"<< /Filter /Standard /V 2 /R 3 /Length 128 /P %d /O " % perms + hexs(o) + b" /U " + hexs(u) + b" >>"

    def objkey(num: int) -> bytes:
        return hashlib.md5(key + num.to_bytes(3, "little") + b"\x00\x00").digest()[: min(n + 5, 16)]

    return body, objkey
