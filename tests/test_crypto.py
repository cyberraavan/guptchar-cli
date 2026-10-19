"""Crypto must match the web client byte for byte (shared vectors.json)."""

import base64
import json
import unittest
from pathlib import Path

from guptchar.crypto import (
    AAD_FILE_HEADER, AAD_MESSAGE, CryptoError, derive_key, open_envelope, seal,
)
from guptchar.payload import PayloadError, decode_payload

VECTORS = json.loads((Path(__file__).parent / "vectors.json").read_text(encoding="utf-8"))


class CryptoVectors(unittest.TestCase):
    def test_argon2id_matches_web_client(self):
        for v in VECTORS["kdf"]:
            self.assertEqual(derive_key(v["passphrase"], v["room"]).hex(), v["key_hex"])

    def test_nfc_normalisation(self):
        self.assertEqual(derive_key("café third", "vector-room.01"), derive_key("café third", "vector-room.01"))

    def test_seal_matches_web_client_and_opens(self):
        for v in VECTORS["seal"]:
            keys = [bytes.fromhex(h) for h in v["keys_hex"]]
            ivs = [bytes.fromhex(h) for h in v["ivs_hex"]]
            plain = bytes.fromhex(v["plaintext_hex"])
            envelope = seal(keys, plain, v["aad"], ivs)
            self.assertEqual(base64.b64encode(envelope).decode(), v["envelope_b64"])
            self.assertEqual(open_envelope(keys, base64.b64decode(v["envelope_b64"]), v["aad"]), plain)

    def test_wrong_key_order_aad_tamper_fail(self):
        v = next(s for s in VECTORS["seal"] if len(s["keys_hex"]) == 2)
        keys = [bytes.fromhex(h) for h in v["keys_hex"]]
        env = base64.b64decode(v["envelope_b64"])
        with self.assertRaises(CryptoError):
            open_envelope([keys[0], bytes(32)], env, v["aad"])
        with self.assertRaises(CryptoError):
            open_envelope(list(reversed(keys)), env, v["aad"])
        with self.assertRaises(CryptoError):
            open_envelope(keys, env, AAD_FILE_HEADER)
        tampered = bytearray(env)
        tampered[20] ^= 1
        with self.assertRaises(CryptoError):
            open_envelope(keys, bytes(tampered), v["aad"])
        # fewer keys: only the outer layer opens -> still ciphertext -> payload rejected
        with self.assertRaises(PayloadError):
            decode_payload(open_envelope([keys[1]], env, v["aad"]))

    def test_random_ivs(self):
        key = derive_key("k", "room-random")
        self.assertNotEqual(seal([key], b"x", AAD_MESSAGE), seal([key], b"x", AAD_MESSAGE))


if __name__ == "__main__":
    unittest.main()
