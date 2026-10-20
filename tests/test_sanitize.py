"""Text that comes from the relay must never reach the terminal raw (audit F1, N4)."""

import unittest

from guptchar.app import captcha_rows


class Sanitize(unittest.TestCase):
    def test_captcha_from_a_hacked_relay_is_cleaned(self):
        evil = {
            "art": ["██\x1b]52;c;ZXZpbA==\x07▓▓", "ok ░▒", "\x9b31m█"],
            "tint": ["o\x1bo", "", "zzz"],
            "prompt": "type\x1b[2J this",
        }
        rows, tint = captcha_rows(evil)
        joined = "".join(rows)
        self.assertNotIn("\x1b", joined)
        self.assertNotIn("\x07", joined)
        self.assertNotIn("\x9b", joined)
        self.assertTrue(all(set(r) <= set(" █▓▒░#@.:-") for r in rows))
        self.assertEqual([len(r) for r in rows], [len(t) for t in tint])
        self.assertTrue(all(set(t) <= {"o", "."} for t in tint))

    def test_huge_art_is_cut(self):
        rows, _ = captcha_rows({"art": ["█" * 500] * 100, "tint": []})
        self.assertLessEqual(len(rows), 20)
        self.assertLessEqual(max(len(r) for r in rows), 80)


if __name__ == "__main__":
    unittest.main()
