"""Conservative key-strength estimate (audit H3). Mirrors the web client's
keystrength.js exactly — both clients must accept and reject the same keys.

bits < 40 -> "too weak" (blocked) · < 60 "fair" · < 80 "good" · else "strong"
"""

from __future__ import annotations

import math
import re
import unicodedata

MIN_BITS = 40

COMMON = {
    "password", "password1", "passw0rd", "123456", "1234567", "12345678", "123456789", "1234567890",
    "qwerty", "qwerty123", "qwertyuiop", "abc123", "letmein", "welcome", "admin", "iloveyou",
    "monkey", "dragon", "football", "baseball", "sunshine", "princess", "master", "shadow",
    "superman", "trustno1", "whatever", "freedom", "secret", "guptchar", "hello", "helloworld",
    "friend", "hellofriend", "fsociety", "mrrobot", "elliot", "india", "bharat", "pakistan",
    "cricket", "chatroom", "mykey", "roomkey", "changeme", "test", "test123", "testing",
}

SEQUENCES = ["abcdefghijklmnopqrstuvwxyz", "01234567890", "qwertyuiop", "asdfghjkl", "zxcvbnm"]
SEPARATORS = re.compile(r"[\s._-]+")
PUNCT = re.compile(r"[\x20-\x2f\x3a-\x40\x5b-\x60\x7b-\x7e]")


def _is_sequence(s: str) -> bool:
    if len(s) < 3:
        return False
    return any(s in seq or s in seq[::-1] for seq in SEQUENCES)


def estimate_bits(key: str) -> float:
    k = unicodedata.normalize("NFC", key)
    if not k:
        return 0.0

    lower = k.lower()
    squashed = SEPARATORS.sub("", lower)
    if lower in COMMON or squashed in COMMON:
        return 10.0
    if len(set(k)) == 1:
        return 4.0
    if _is_sequence(lower) or _is_sequence(squashed):
        return 10.0

    pool = 0
    if re.search(r"[a-z]", k):
        pool += 26
    if re.search(r"[A-Z]", k):
        pool += 26
    if re.search(r"[0-9]", k):
        pool += 10
    if PUNCT.search(k):
        pool += 33
    if re.search(r"[^\x00-\x7f]", k):
        pool += 100

    effective = min(len(k), 2 * len(set(k)))
    bits = effective * math.log2(pool)

    words = [w for w in SEPARATORS.split(lower) if w]
    if words and all(re.fullmatch(r"[a-z]+", w) for w in words):
        bits = min(bits, 20 if len(words) == 1 else len(words) * 11)
    return bits


def strength_label(bits: float) -> str:
    if bits < MIN_BITS:
        return "too weak"
    if bits < 60:
        return "fair"
    if bits < 80:
        return "good"
    return "strong"
