"""Same cases as the web client (keystrength-cases.json) — both must agree."""

import json
import unittest
from pathlib import Path

from guptchar.keystrength import estimate_bits, strength_label
from guptchar.payload import is_executable
from guptchar.session import Session, UserError

CASES = json.loads((Path(__file__).parent / "keystrength-cases.json").read_text(encoding="utf-8"))


class KeyStrength(unittest.TestCase):
    def test_shared_cases(self):
        for key, expected in CASES:
            self.assertEqual(strength_label(estimate_bits(key)), expected, key)

    def test_weak_keys_are_blocked(self):
        s = Session("http://127.0.0.1:9", on_entry=lambda e: None)
        with self.assertRaisesRegex(UserError, "too weak"):
            s.add_key("", "123456")
        self.assertEqual(s.add_key("", "Orbit-Kite-42#Lamp"), "Key 1")

    def test_executable_detection(self):
        self.assertTrue(is_executable("setup.EXE"))
        self.assertTrue(is_executable("run.sh"))
        self.assertFalse(is_executable("photo.jpg"))


if __name__ == "__main__":
    unittest.main()
