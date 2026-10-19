"""Lossless metadata removal before encryption — same rules as the web client.

  JPEG / PNG / WebP : drop EXIF/XMP/IPTC/comments/text chunks; keep pixels,
                      ICC colour profile and ONLY the EXIF orientation tag.
                      JPEG bytes after the end-of-image marker are kept.
  PDF   (pypdf)     : drop the Info dictionary, XMP stream and file ID.
  Office (zipfile)  : blank document properties, comment/revision authors,
                      and zip entry timestamps.
  Anything else     : returned unchanged with cleaned=False (caller asks the user).
"""

from __future__ import annotations

import io
import logging
import re
import struct
import zipfile
import zlib
from dataclasses import dataclass

# pypdf reports malformed files through logging; never print anything (zero logs, clean TUI).
logging.getLogger("pypdf").setLevel(logging.CRITICAL + 1)


@dataclass
class Stripped:
    data: bytes
    cleaned: bool
    kind: str


def strip_metadata(data: bytes) -> Stripped:
    kind = detect_kind(data)
    handlers = {"jpeg": _strip_jpeg, "png": _strip_png, "webp": _strip_webp, "pdf": _strip_pdf, "office": _strip_office}
    if kind in handlers:
        try:
            return Stripped(handlers[kind](data), True, kind)
        except Exception:
            pass  # malformed/encrypted: send as-is after the user confirms
    return Stripped(data, False, kind)


def detect_kind(b: bytes) -> str:
    if b[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if b[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if b[:4] == b"RIFF" and b[8:12] == b"WEBP":
        return "webp"
    if b[:5] == b"%PDF-":
        return "pdf"
    if b[:4] == b"PK\x03\x04":
        head = b[: 64 * 1024]
        if b"[Content_Types].xml" in head and re.search(rb"(word|xl|ppt)/", head):
            return "office"
    return "other"


# ---------------------------------------------------------------- orientation

def read_orientation(tiff: bytes) -> int:
    if len(tiff) < 8:
        return 1
    end = "<" if tiff[:2] == b"II" else ">"
    try:
        (ifd,) = struct.unpack_from(end + "I", tiff, 4)
        (count,) = struct.unpack_from(end + "H", tiff, ifd)
        for i in range(count):
            e = ifd + 2 + i * 12
            tag, _typ, _cnt = struct.unpack_from(end + "HHI", tiff, e)
            if tag == 0x0112:
                (value,) = struct.unpack_from(end + "H", tiff, e + 8)
                return value if 1 <= value <= 8 else 1
    except struct.error:
        pass
    return 1


def orientation_tiff(orientation: int) -> bytes:
    """Minimal little-endian TIFF block holding only the orientation tag."""
    return (
        b"II*\x00\x08\x00\x00\x00"
        + b"\x01\x00"
        + struct.pack("<HHIH2x", 0x0112, 3, 1, orientation)
        + b"\x00\x00\x00\x00"
    )


# ---------------------------------------------------------------- JPEG

EXIF_ID = b"Exif\x00\x00"


def _strip_jpeg(b: bytes) -> bytes:
    out = [b[:2]]
    orientation = 1
    exif_slot = -1
    pos = 2
    n = len(b)

    while pos < n:
        if b[pos] != 0xFF:
            raise ValueError("bad jpeg")
        while pos + 1 < n and b[pos + 1] == 0xFF:
            pos += 1
        marker = b[pos + 1]

        if marker == 0xD9:
            out.append(b[pos:])  # EOI + any trailing data (kept by design)
            break
        if marker == 0x01 or 0xD0 <= marker <= 0xD7:
            out.append(b[pos:pos + 2])
            pos += 2
            continue

        (length,) = struct.unpack_from(">H", b, pos + 2)
        end = pos + 2 + length
        if end > n:
            raise ValueError("bad jpeg")
        seg = b[pos:end]
        body = b[pos + 4:end]

        if marker == 0xDA:
            p = end
            while p < n - 1 and not (b[p] == 0xFF and b[p + 1] != 0x00 and not 0xD0 <= b[p + 1] <= 0xD7):
                p += 1
            if p >= n - 1:
                out.append(b[pos:])
                break
            out.append(b[pos:p])
            pos = p
            continue

        keep = True
        if marker == 0xE1:
            if body[:6] == EXIF_ID:
                orientation = read_orientation(body[6:])
                if exif_slot < 0:
                    exif_slot = len(out)
            keep = False
        elif marker == 0xE2:
            keep = body[:12] == b"ICC_PROFILE\x00" or body[:4] == b"MPF\x00"
        elif marker == 0xE0:
            keep = body[:5] in (b"JFIF\x00", b"JFXX\x00")
        elif marker == 0xEE:
            keep = body[:5] == b"Adobe"
        elif 0xE3 <= marker <= 0xEF or marker == 0xFE:
            keep = False

        if keep:
            out.append(seg)
        pos = end

    if orientation != 1:
        payload = EXIF_ID + orientation_tiff(orientation)
        app1 = b"\xff\xe1" + struct.pack(">H", len(payload) + 2) + payload
        out.insert(exif_slot if exif_slot > 0 else 1, app1)

    return b"".join(out)


# ---------------------------------------------------------------- PNG

PNG_KEEP = {
    b"IHDR", b"PLTE", b"IDAT", b"IEND",
    b"tRNS", b"gAMA", b"cHRM", b"sRGB", b"iCCP", b"sBIT", b"bKGD", b"pHYs", b"hIST", b"sPLT",
    b"cICP", b"mDCV", b"cLLI", b"acTL", b"fcTL", b"fdAT",
}


def _png_chunk(typ: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + typ + data + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF)


def _strip_png(b: bytes) -> bytes:
    out = [b[:8]]
    pos = 8
    while pos + 12 <= len(b):
        (length,) = struct.unpack_from(">I", b, pos)
        typ = b[pos + 4:pos + 8]
        end = pos + 12 + length
        if end > len(b):
            raise ValueError("bad png")
        if typ == b"eXIf":
            o = read_orientation(b[pos + 8:pos + 8 + length])
            if o != 1:
                out.append(_png_chunk(b"eXIf", orientation_tiff(o)))
        elif typ in PNG_KEEP:
            out.append(b[pos:end])
        pos = end
        if typ == b"IEND":
            break
    return b"".join(out)


# ---------------------------------------------------------------- WebP

WEBP_KEEP = {b"VP8 ", b"VP8L", b"VP8X", b"ALPH", b"ANIM", b"ANMF", b"ICCP"}


def _strip_webp(b: bytes) -> bytes:
    chunks: list[bytearray] = []
    vp8x = -1
    exif = None
    pos = 12
    while pos + 8 <= len(b):
        typ = b[pos:pos + 4]
        (length,) = struct.unpack_from("<I", b, pos + 4)
        end = pos + 8 + length + (length & 1)
        if pos + 8 + length > len(b):
            raise ValueError("bad webp")
        if typ == b"EXIF":
            tiff = b[pos + 8:pos + 8 + length]
            if tiff[:6] == EXIF_ID:
                tiff = tiff[6:]
            exif = read_orientation(tiff)
        elif typ in WEBP_KEEP:
            if typ == b"VP8X":
                vp8x = len(chunks)
            chunks.append(bytearray(b[pos:min(end, len(b))]))
        pos = end

    if vp8x >= 0:
        flags = chunks[vp8x]
        flags[8] &= ~(0x08 | 0x04) & 0xFF
        if exif and exif != 1:
            flags[8] |= 0x08
            tiff = orientation_tiff(exif)
            chunks.append(bytearray(b"EXIF" + struct.pack("<I", len(tiff)) + tiff))

    body = b"WEBP" + b"".join(bytes(c) for c in chunks)
    return b"RIFF" + struct.pack("<I", len(body)) + body


# ---------------------------------------------------------------- PDF

def _strip_pdf(b: bytes) -> bytes:
    from pypdf import PdfReader, PdfWriter
    from pypdf.generic import NameObject

    reader = PdfReader(io.BytesIO(b))
    if reader.is_encrypted:
        raise ValueError("encrypted pdf")
    writer = PdfWriter(clone_from=reader)
    writer.metadata = None
    writer.root_object.pop(NameObject("/Metadata"), None)
    writer._ID = None  # no file identifier in the trailer
    writer.compress_identical_objects(remove_duplicates=False, remove_unreferenced=True)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


# ---------------------------------------------------------------- Office (OOXML)

FIXED_DATE = (1980, 1, 1, 0, 0, 0)

EMPTY_PARTS = {
    "docProps/core.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"/>'
    ),
    "docProps/app.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
    ),
    "docProps/custom.xml": (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"/>'
    ),
}

SCRUB_PARTS = re.compile(
    r"^(word|xl|ppt)/(comments.*|people|persons/.*|commentAuthors|authors|document|header\d*|footer\d*"
    r"|footnotes|endnotes|threadedComments/.*|comments/.*)\.xml$"
)
_WORD_ATTRS = re.compile(r"\b(w|w15|w16cid|w16cex):(author|initials|userId|providerId)=\"[^\"]*\"")
_AUTHOR_TAGS = re.compile(r"<(p:cmAuthor|p\d*:author|person)\b[^>]*>")
_TAG_ATTRS = re.compile(r"\b(name|initials|userId|providerId|displayName)=\"[^\"]*\"")
_XL_AUTHOR = re.compile(r"<author>[^<]*</author>")


def scrub_office_xml(xml: str) -> str:
    xml = _WORD_ATTRS.sub(r'\1:\2=""', xml)
    xml = _AUTHOR_TAGS.sub(lambda m: _TAG_ATTRS.sub(r'\1=""', m.group(0)), xml)
    return _XL_AUTHOR.sub("<author></author>", xml)


def _strip_office(b: bytes) -> bytes:
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(b)) as src, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            data = src.read(info)
            if info.filename in EMPTY_PARTS:
                data = EMPTY_PARTS[info.filename].encode("utf-8")
            elif SCRUB_PARTS.match(info.filename):
                data = scrub_office_xml(data.decode("utf-8")).encode("utf-8")
            entry = zipfile.ZipInfo(info.filename, date_time=FIXED_DATE)
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = info.external_attr
            dst.writestr(entry, data)
    return out.getvalue()
