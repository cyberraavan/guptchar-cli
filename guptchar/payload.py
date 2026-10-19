"""Plaintext payloads that travel inside the encryption (PROTOCOL.md section 5)."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass

ROOM_RE = re.compile(r"^[A-Za-z0-9._-]{8,64}$")
NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")
SHA_RE = re.compile(r"^[0-9a-f]{64}$")
MAX_TEXT = 1000
MAX_FILE_BYTES = 10 * 1024 * 1024
CHUNK_BYTES = 256 * 1024
MAX_FILE_NAME = 255
MAX_MIME = 127


class PayloadError(ValueError):
    pass


@dataclass
class Message:
    name: str
    text: str


@dataclass
class FileHeader:
    name: str
    file_name: str
    mime: str
    size: int
    chunks: int
    sha256: str


def _dumps(obj: dict) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def encode_message(name: str, text: str) -> bytes:
    if not NAME_RE.match(name):
        raise PayloadError("Bad name")
    if not text or len(text) > MAX_TEXT:
        raise PayloadError("Bad text")
    return _dumps({"v": 1, "t": "msg", "n": name, "m": text})


def encode_file_header(name: str, file_name: str, mime: str, size: int, chunks: int, sha256: str) -> bytes:
    if not NAME_RE.match(name):
        raise PayloadError("Bad name")
    return _dumps({
        "v": 1, "t": "file", "n": name, "f": clean_file_name(file_name),
        "y": (mime or "application/octet-stream")[:MAX_MIME], "s": size, "c": chunks, "h": sha256,
    })


def decode_payload(data: bytes) -> Message | FileHeader:
    try:
        p = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise PayloadError("Bad payload") from exc
    if not isinstance(p, dict) or p.get("v") != 1 or not isinstance(p.get("n"), str) or not NAME_RE.match(p["n"]):
        raise PayloadError("Bad payload")

    if p.get("t") == "msg":
        text = p.get("m")
        if not isinstance(text, str) or not text or len(text) > MAX_TEXT:
            raise PayloadError("Bad payload")
        return Message(p["n"], text)

    if p.get("t") == "file":
        size, chunks = p.get("s"), p.get("c")
        ok = (
            isinstance(p.get("f"), str) and isinstance(p.get("y"), str)
            and type(size) is int and 0 < size <= MAX_FILE_BYTES
            and type(chunks) is int and chunks == math.ceil(size / CHUNK_BYTES)
            and isinstance(p.get("h"), str) and SHA_RE.match(p["h"])
        )
        if not ok:
            raise PayloadError("Bad payload")
        return FileHeader(p["n"], clean_file_name(p["f"]), p["y"][:MAX_MIME], size, chunks, p["h"])

    raise PayloadError("Bad payload")


# C0/C1 control characters and Unicode direction marks/overrides. The overrides
# can disguise an extension: "photo" + U+202E + "gpj.exe" displays like a .jpg.
UNSAFE_CHARS = re.compile("[\u0000-\u001f\u007f-\u009f‎‏‪-‮⁦-⁩]")
WINDOWS_RESERVED = re.compile(r"^(con|prn|aux|nul|com[0-9]|lpt[0-9])$", re.IGNORECASE)


def safe_text(text: str) -> str:
    """Text from other people, made safe to print in a terminal (no escapes, no bidi tricks)."""
    return UNSAFE_CHARS.sub(lambda m: "\n" if m.group(0) == "\n" else "", text)


def clean_file_name(file_name: str) -> str:
    """Strips path parts, control and direction characters; safe on every OS (same as web)."""
    base = re.split(r"[\\/]", str(file_name))[-1] or "file"
    clean = UNSAFE_CHARS.sub("", base).strip().rstrip(". ")
    if WINDOWS_RESERVED.match(clean.split(".")[0]):
        clean = "_" + clean
    return (clean or "file")[:MAX_FILE_NAME]
