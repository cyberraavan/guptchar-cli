"""Argon2id key derivation + layered AES-256-GCM with hidden nesting.

Byte-for-byte identical to the web client (PROTOCOL.md section 4):

    c1 = IV1 || AES-GCM(k1, IV1, plaintext, aad)
    c2 = IV2 || AES-GCM(k2, IV2, c1, aad)
    envelope = 0x01 || c_last
"""

from __future__ import annotations

import os
import unicodedata

from argon2.low_level import Type, hash_secret_raw
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

VERSION = 1
MAX_LAYERS = 3
IV_BYTES = 12
TAG_BYTES = 16
SALT_PREFIX = b"guptchar"

ARGON2_MEMORY_KIB = 19456  # 19 MiB
ARGON2_TIME = 2
ARGON2_PARALLELISM = 1
KEY_BYTES = 32

AAD_MESSAGE = "guptchar/v1/msg"
AAD_FILE_HEADER = "guptchar/v1/fhdr"


def aad_chunk(file_id: str, index: int) -> str:
    return f"guptchar/v1/fchunk/{file_id}/{index}"


class CryptoError(Exception):
    """Wrong key, wrong layer order, tampering or a malformed envelope."""


def derive_key(passphrase: str, room: str) -> bytes:
    password = unicodedata.normalize("NFC", passphrase)
    if not password:
        raise ValueError("Empty key")
    return hash_secret_raw(
        secret=password.encode("utf-8"),
        salt=SALT_PREFIX + room.encode("utf-8"),
        time_cost=ARGON2_TIME,
        memory_cost=ARGON2_MEMORY_KIB,
        parallelism=ARGON2_PARALLELISM,
        hash_len=KEY_BYTES,
        type=Type.ID,
    )


def _check_keys(keys: list[bytes]) -> None:
    if not 1 <= len(keys) <= MAX_LAYERS:
        raise ValueError("Need 1 to 3 keys")


def seal(keys: list[bytes], plaintext: bytes, aad: str, ivs: list[bytes] | None = None) -> bytes:
    """Encrypts through every layer, keys[0] first. `ivs` is for test vectors only."""
    _check_keys(keys)
    data = plaintext
    for i, key in enumerate(keys):
        iv = ivs[i] if ivs else os.urandom(IV_BYTES)
        data = iv + AESGCM(key).encrypt(iv, data, aad.encode())
    return bytes([VERSION]) + data


def open_envelope(keys: list[bytes], envelope: bytes, aad: str) -> bytes:
    """Decrypts the outermost layer first. Raises CryptoError on any mismatch."""
    _check_keys(keys)
    if len(envelope) < 1 + IV_BYTES + TAG_BYTES or envelope[0] != VERSION:
        raise CryptoError("Bad envelope")
    data = envelope[1:]
    try:
        for key in reversed(keys):
            if len(data) < IV_BYTES + TAG_BYTES:
                raise CryptoError("Bad layer")
            data = AESGCM(key).decrypt(data[:IV_BYTES], data[IV_BYTES:], aad.encode())
    except CryptoError:
        raise
    except Exception as exc:  # cryptography raises InvalidTag
        raise CryptoError("Cannot decrypt") from exc
    return data
