"""Test-only: reads a captcha answer with the relay's APP_KEY (DECISIONS D34).

Set GUPTCHAR_APP_KEY to the server's APP_KEY (e.g. "base64:...") to run the
live tests. Attackers don't have this key, so this is no way around the captcha.
"""

import base64
import hashlib
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

APP_KEY = os.environ.get("GUPTCHAR_APP_KEY")


def answer(challenge: str) -> str:
    expiry, b64 = challenge.split(".", 1)
    raw = base64.urlsafe_b64decode(b64 + "=" * (-len(b64) % 4))
    key = hashlib.sha256(("guptchar-captcha|" + APP_KEY).encode()).digest()
    plain = AESGCM(key).decrypt(raw[:12], raw[12:], expiry.encode())
    return json.loads(plain)["a"]
