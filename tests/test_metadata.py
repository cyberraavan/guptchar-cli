"""Fixtures carry fake identifying data ("Secret…"); none of it may survive."""

import io
import re
import struct
import unittest
import zipfile
from pathlib import Path

from guptchar.metadata import detect_kind, read_orientation, strip_metadata

FIX = Path(__file__).parent / "fixtures"


def fixture(name: str) -> bytes:
    return (FIX / name).read_bytes()


def secrets(data: bytes) -> list[str]:
    return re.findall(r"Secret[A-Za-z]*", data.decode("latin1"))


def png_data(b: bytes) -> bytes:
    out, p = [], 8
    while p + 12 <= len(b):
        (n,) = struct.unpack_from(">I", b, p)
        if b[p + 4:p + 8] in (b"IHDR", b"IDAT", b"iCCP", b"PLTE"):
            out.append(b[p:p + 12 + n])
        p += 12 + n
    return b"".join(out)


def webp_chunks(b: bytes, kinds) -> bytes:
    out, p = [], 12
    while p + 8 <= len(b):
        (n,) = struct.unpack_from("<I", b, p + 4)
        if b[p:p + 4] in kinds:
            out.append(b[p:p + 8 + n])
        p += 8 + n + (n & 1)
    return b"".join(out)


class Metadata(unittest.TestCase):
    def test_detect(self):
        expected = {"photo.jpg": "jpeg", "photo.png": "png", "photo.webp": "webp", "doc.pdf": "pdf",
                    "doc.docx": "office", "sheet.xlsx": "office", "deck.pptx": "office"}
        for name, kind in expected.items():
            self.assertEqual(detect_kind(fixture(name)), kind, name)
        self.assertEqual(detect_kind(b"plain text"), "other")

    def test_jpeg(self):
        src = fixture("photo.jpg")
        out = strip_metadata(src)
        self.assertTrue(out.cleaned)
        self.assertEqual(secrets(out.data), [])
        exif = out.data.index(b"Exif\x00\x00")
        self.assertEqual(read_orientation(out.data[exif + 6:]), 6)
        self.assertIn(b"ICC_PROFILE", out.data)
        self.assertEqual(out.data[out.data.index(b"\xff\xda"):], src[src.index(b"\xff\xda"):])
        self.assertTrue(out.data.endswith(b"MOTIONPHOTO-TRAILER-BYTES"))

    def test_png(self):
        src = fixture("photo.png")
        out = strip_metadata(src).data
        self.assertEqual(secrets(out), [])
        for chunk in (b"tEXt", b"iTXt", b"tIME", b"prVt"):
            self.assertNotIn(chunk, out)
        self.assertEqual(read_orientation(out[out.index(b"eXIf") + 4:]), 6)
        self.assertEqual(png_data(out), png_data(src))

    def test_webp(self):
        src = fixture("photo.webp")
        out = strip_metadata(src).data
        self.assertEqual(secrets(out), [])
        self.assertEqual(struct.unpack_from("<I", out, 4)[0], len(out) - 8)
        self.assertNotIn(b"XMP ", out)
        kinds = (b"VP8L", b"VP8 ", b"ICCP")
        self.assertEqual(webp_chunks(out, kinds), webp_chunks(src, kinds))
        self.assertEqual(read_orientation(webp_chunks(out, (b"EXIF",))[8:]), 6)

    def test_pdf(self):
        out = strip_metadata(fixture("doc.pdf"))
        self.assertTrue(out.cleaned)
        text = out.data.decode("latin1")
        self.assertEqual(secrets(out.data), [])
        for marker in ("/Info", "/Metadata", "/ID", "5ec7e7"):
            self.assertNotIn(marker, text)
        self.assertIn("VisibleBodyText", text)

    def test_office(self):
        for name in ("doc.docx", "sheet.xlsx", "deck.pptx"):
            out = strip_metadata(fixture(name))
            self.assertTrue(out.cleaned, name)
            with zipfile.ZipFile(io.BytesIO(out.data)) as z:
                blob = b"".join(z.read(i) for i in z.infolist())
                self.assertEqual(secrets(blob), [], name)
                self.assertTrue(all(i.date_time[0] == 1980 for i in z.infolist()), name)

    def test_other_and_broken_pass_through(self):
        out = strip_metadata(b"just text")
        self.assertEqual((out.data, out.cleaned, out.kind), (b"just text", False, "other"))
        broken = fixture("doc.pdf")[:40]
        out = strip_metadata(broken)
        self.assertEqual((out.data, out.cleaned), (broken, False))


if __name__ == "__main__":
    unittest.main()
