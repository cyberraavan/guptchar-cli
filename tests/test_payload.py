import json
import unittest

from guptchar.payload import (
    FileHeader, Message, PayloadError, clean_file_name, decode_payload, encode_file_header, encode_message,
)


class Payloads(unittest.TestCase):
    def test_message_roundtrip_and_limits(self):
        self.assertEqual(decode_payload(encode_message("a_b-1", "hi")), Message("a_b-1", "hi"))
        for bad in ("bad name", "seventeen_chars_x", ""):
            with self.assertRaises(PayloadError):
                encode_message(bad, "x")
        encode_message("ok", "😀" * 1000)  # 1000 code points allowed
        with self.assertRaises(PayloadError):
            encode_message("ok", "😀" * 1001)

    def test_same_bytes_as_web_client(self):
        # JSON.stringify output of the web client for the same message
        self.assertEqual(encode_message("raavan", "hello 👋 duniya"),
                         '{"v":1,"t":"msg","n":"raavan","m":"hello 👋 duniya"}'.encode())

    def test_file_header(self):
        h = decode_payload(encode_file_header("neo", "../../etc/passwd", "text/plain", 262145, 2, "a" * 64))
        self.assertIsInstance(h, FileHeader)
        self.assertEqual(h.file_name, "passwd")
        with self.assertRaises(PayloadError):
            decode_payload(json.dumps({"v": 1, "t": "file", "n": "neo", "f": "x", "y": "", "s": 10, "c": 2, "h": "a" * 64}).encode())

    def test_rejects_garbage(self):
        for raw in (b"\xff\xfe", b"[]", b'{"v":2,"t":"msg","n":"a","m":"b"}', b'{"v":1,"t":"x","n":"a"}'):
            with self.assertRaises(PayloadError):
                decode_payload(raw)

    def test_clean_file_name(self):
        self.assertEqual(clean_file_name("C:\\a\\b\x07.txt"), "b.txt")
        self.assertEqual(clean_file_name(""), "file")
        self.assertEqual(clean_file_name("photo\u202egpj.exe"), "photogpj.exe")  # RLO extension spoof
        self.assertEqual(clean_file_name("a\x9b31mb.txt"), "a31mb.txt")  # C1 control
        self.assertEqual(clean_file_name("CON.txt"), "_CON.txt")
        self.assertEqual(clean_file_name("nul"), "_nul")
        self.assertEqual(clean_file_name("report.pdf. . "), "report.pdf")

    def test_safe_text_blocks_terminal_escapes(self):
        from guptchar.payload import safe_text
        evil = "hi\x1b]52;c;ZXZpbA==\x07 there\x9b31m \u202edlrow\nline2"
        self.assertEqual(safe_text(evil), "hi]52;c;ZXZpbA== there31m dlrow\nline2")


if __name__ == "__main__":
    unittest.main()
