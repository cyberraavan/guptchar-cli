"""One chat session — the Python twin of the web client's session.js.

UI-agnostic; talks to the interface only through callbacks:
    on_entry(Entry)            new log line
    on_update(Entry)           an entry changed (upload progress)
    on_status()                name / room / keys changed
    confirm(text) -> bool      awaitable yes/no question
    beep()                     new message / file arrived
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import itertools
import math
import mimetypes
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Awaitable, Callable

from . import texts as T
from .api import Api, ApiError
from .crypto import (
    AAD_FILE_HEADER, AAD_MESSAGE, MAX_LAYERS, CryptoError,
    aad_chunk, derive_key, open_envelope, seal,
)
from .metadata import strip_metadata
from .payload import (
    CHUNK_BYTES, MAX_FILE_BYTES, MAX_TEXT, NAME_RE, ROOM_RE,
    FileHeader, Message, PayloadError, decode_payload, encode_file_header, encode_message,
)

DOWNLOAD_DIR = Path.home() / "Downloads" / "guptchar"
_ids = itertools.count(1)


class UserError(Exception):
    """An error whose message is meant for the user."""


@dataclass
class Entry:
    kind: str  # msg | file | system | warn | error | echo | help
    text: str = ""
    name: str = ""
    own: bool = False
    file_name: str = ""
    size: int = 0
    id: int = field(default_factory=lambda: next(_ids))
    time: datetime = field(default_factory=datetime.now)


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text, validate=True)


def _user_error(exc: Exception, rate_text: str = T.RATE_MSG) -> UserError:
    if isinstance(exc, UserError):
        return exc
    if isinstance(exc, ApiError):
        if exc.code == "rate_limited":
            return UserError(rate_text)
        return UserError(T.API_ERRORS.get(exc.code, T.OFFLINE))
    return UserError(T.OFFLINE)


def unique_path(folder: Path, file_name: str) -> Path:
    """photo.jpg -> photo (1).jpg -> photo (2).jpg … (never overwrites)."""
    target = folder / file_name
    stem, suffix = os.path.splitext(file_name)
    n = 1
    while target.exists():
        target = folder / f"{stem} ({n}){suffix}"
        n += 1
    return target


class Session:
    def __init__(self, server_url: str, *, on_entry, on_update=None, on_status=None,
                 confirm: Callable[[str], Awaitable[bool]] | None = None, beep=None,
                 download_dir: Path = DOWNLOAD_DIR):
        self.api = Api(server_url)
        self.on_entry = on_entry
        self.on_update = on_update or (lambda e: None)
        self.on_status = on_status or (lambda: None)
        self.confirm = confirm
        self.beep = beep or (lambda: None)
        self.download_dir = download_dir

        self.name: str | None = None
        self.keys: list[dict] = []  # [{label, secret}] — memory only
        self.room: str | None = None
        self.joined = False
        self.crypto_keys: list[bytes] | None = None
        self.token: str | None = None
        self.cursor = 0
        self.poll_ms = 3000
        self.offline = False
        self._lock = asyncio.Lock()
        self._poll_task: asyncio.Task | None = None
        self._own_seqs: set[int] = set()
        self._own_files: set[str] = set()

    def log(self, kind: str, text: str) -> Entry:
        entry = Entry(kind, text)
        self.on_entry(entry)
        return entry

    # ------------------------------------------------------------ identity + keys

    def set_name(self, name: str) -> None:
        if not NAME_RE.match(name or ""):
            raise UserError(T.INVALID_NAME)
        self.name = name
        self.on_status()

    def add_key(self, label: str, secret: str) -> str:
        if self.joined:
            raise UserError(T.KEYS_LOCKED)
        if len(self.keys) >= MAX_LAYERS:
            raise UserError(T.MAX_LAYERS)
        if not secret:
            raise UserError(T.EMPTY_KEY)
        clean = (label or "").strip()[:32] or f"Key {len(self.keys) + 1}"
        self.keys.append({"label": clean, "secret": secret})
        self.on_status()
        return clean

    def remove_key(self, n: int) -> str:
        if self.joined:
            raise UserError(T.KEYS_LOCKED)
        if not 1 <= n <= len(self.keys):
            raise UserError(T.BAD_INDEX)
        removed = self.keys.pop(n - 1)
        self.on_status()
        return removed["label"]

    def move_key(self, n: int, delta: int) -> None:
        if self.joined:
            raise UserError(T.KEYS_LOCKED)
        a, b = n - 1, n - 1 + delta
        if not (0 <= a < len(self.keys) and 0 <= b < len(self.keys)):
            raise UserError(T.BAD_INDEX)
        self.keys[a], self.keys[b] = self.keys[b], self.keys[a]
        self.on_status()

    # ------------------------------------------------------------ room

    async def join(self, room: str) -> None:
        if self.joined:
            raise UserError(T.ALREADY_JOINED)
        if not room:
            raise UserError(T.NEED_ROOM)
        if not ROOM_RE.match(room):
            raise UserError(T.INVALID_ROOM)
        if not self.name:
            raise UserError(T.NEED_NAME)
        if not self.keys:
            raise UserError(T.NEED_KEY)

        self.log("system", T.DERIVING)
        keys = [await asyncio.to_thread(derive_key, k["secret"], room) for k in self.keys]
        try:
            async with self._lock:
                res = await self.api.call("join", {"room": room})
        except Exception as exc:
            raise _user_error(exc) from None

        self.room, self.crypto_keys = room, keys
        self.token, self.cursor = res["token"], res["cursor"]
        self.poll_ms = res.get("poll_ms") or 3000
        self.joined, self.offline = True, False
        self.on_status()
        self.log("system", T.connected(room, len(keys)))
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def leave(self, quiet: bool = False) -> None:
        if not self.joined:
            raise UserError(T.NOT_JOINED)
        room, token = self.room, self.token
        self._leave_local()
        try:
            await self.api.call("leave", {"room": room, "token": token})
        except ApiError:
            pass  # the token expires on its own within 60 s
        if not quiet:
            self.log("system", T.LEFT)

    def _leave_local(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            self._poll_task = None
        self.joined = False
        self.room = self.token = None
        self.crypto_keys = None
        self._own_seqs.clear()
        self._own_files.clear()
        self.on_status()

    async def close(self) -> None:
        if self.joined:
            await self.leave(quiet=True)
        await self.api.close()

    # ------------------------------------------------------------ polling

    async def _poll_loop(self) -> None:
        while self.joined:
            try:
                await self.poll_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(self.poll_ms / 1000)

    async def poll_once(self) -> None:
        if not self.joined:
            return
        async with self._lock:
            room = self.room
            try:
                res = await self.api.call("poll", {"room": room, "token": self.token, "cursor": self.cursor})
            except ApiError as exc:
                await self._on_poll_error(exc)
                return
            if room != self.room:
                return
            self._mark_online()
            self.cursor = res["cursor"]
            if res.get("missed"):
                self.log("warn", T.MISSED)
            for event in res["events"]:
                await self._handle_event(event)

    async def _on_poll_error(self, exc: ApiError) -> None:
        if exc.code == "token_expired":
            await self._rejoin()
        elif not self.offline:
            self.offline = True
            self.log("error", T.OFFLINE)

    def _mark_online(self) -> None:
        if self.offline:
            self.offline = False
            self.log("system", T.BACK)

    async def _rejoin(self) -> None:
        """Silent re-join with the same keys after the token expired."""
        try:
            res = await self.api.call("join", {"room": self.room})
            self.token, self.cursor = res["token"], res["cursor"]
            self._mark_online()
            self.log("warn", T.MISSED)
        except ApiError as exc:
            if exc.code == "room_full":
                self._leave_local()
                self.log("error", T.ROOM_FULL)
            elif not self.offline:
                self.offline = True
                self.log("error", T.OFFLINE)

    async def _with_token(self, endpoint: str, body: Callable[[], dict]) -> dict | None:
        """API call that re-joins once and retries if the token expired."""
        try:
            return await self.api.call(endpoint, body())
        except ApiError as exc:
            if exc.code == "token_expired" and self.joined:
                await self._rejoin()
                if self.joined:
                    return await self.api.call(endpoint, body())
            raise

    async def _handle_event(self, event: dict) -> None:
        if event.get("kind") == "msg":
            if event["seq"] in self._own_seqs:
                self._own_seqs.discard(event["seq"])
                return
            try:
                payload = decode_payload(open_envelope(self.crypto_keys, _unb64(event["envelope"]), AAD_MESSAGE))
            except (CryptoError, PayloadError, ValueError):
                return  # wrong key / not for us: ignored silently
            if isinstance(payload, Message):
                self.on_entry(Entry("msg", payload.text, name=payload.name))
                self.beep()
            return

        if event.get("kind") == "file":
            file_id = event["file_id"]
            if file_id in self._own_files:
                return
            try:
                header = decode_payload(open_envelope(self.crypto_keys, _unb64(event["header"]), AAD_FILE_HEADER))
            except (CryptoError, PayloadError, ValueError):
                return
            if not isinstance(header, FileHeader) or header.size != event["size"] or header.chunks != event["chunks"]:
                return
            entry = Entry("file", "", name=header.name, file_name=header.file_name, size=header.size)
            self.on_entry(entry)
            self.beep()
            # CLI auto-saves every received file (SPEC section 9).
            asyncio.create_task(self._auto_save(file_id, header))

    # ------------------------------------------------------------ sending

    async def send_text(self, text: str) -> None:
        if not self.joined:
            raise UserError(T.NOT_JOINED)
        if not text:
            return
        if len(text) > MAX_TEXT:
            raise UserError(T.TOO_LARGE)
        envelope = _b64(seal(self.crypto_keys, encode_message(self.name, text), AAD_MESSAGE))
        try:
            async with self._lock:
                res = await self._with_token("send", lambda: {"room": self.room, "token": self.token, "envelope": envelope})
                self._own_seqs.add(res["seq"])
        except Exception as exc:
            raise _user_error(exc) from None
        self.on_entry(Entry("msg", text, name=self.name, own=True))

    async def send_file(self, path: str) -> None:
        if not self.joined:
            raise UserError(T.NOT_JOINED)
        file = Path(os.path.expanduser(path.strip().strip('"').strip("'")))
        if not file.is_file():
            raise UserError(T.NO_FILE)
        size = file.stat().st_size
        if size == 0 or size > MAX_FILE_BYTES:
            raise UserError(T.TOO_LARGE)

        stripped = await asyncio.to_thread(strip_metadata, file.read_bytes())
        if not stripped.cleaned:
            ok = await self.confirm(T.UNSUPPORTED_CONFIRM) if self.confirm else False
            if not ok:
                self.log("system", T.CANCELLED)
                return
        data = stripped.data
        if len(data) > MAX_FILE_BYTES:
            raise UserError(T.TOO_LARGE)
        if not self.joined:
            raise UserError(T.NOT_JOINED)

        keys = self.crypto_keys
        chunks = math.ceil(len(data) / CHUNK_BYTES)
        mime = mimetypes.guess_type(file.name)[0] or "application/octet-stream"
        header_plain = encode_file_header(self.name, file.name, mime, len(data), chunks, hashlib.sha256(data).hexdigest())
        file_name = decode_payload(header_plain).file_name
        header = _b64(seal(keys, header_plain, AAD_FILE_HEADER))
        progress = Entry("system", T.sending(file_name, 0, chunks))

        try:
            async with self._lock:
                res = await self._with_token("file/start", lambda: {
                    "room": self.room, "token": self.token, "header": header, "size": len(data), "chunks": chunks,
                })
            file_id = res["file_id"]
            self._own_files.add(file_id)
            self.on_entry(progress)
            for i in range(chunks):
                piece = data[i * CHUNK_BYTES:(i + 1) * CHUNK_BYTES]
                body = {"room": self.room, "token": self.token, "file_id": file_id, "index": i,
                        "data": _b64(seal(keys, piece, aad_chunk(file_id, i)))}
                async with self._lock:
                    await self.api.call("file/chunk", body)
                progress.text = T.sending(file_name, i + 1, chunks)
                self.on_update(progress)
        except Exception as exc:
            raise _user_error(exc, T.RATE_FILE) from None

        progress.text = T.sent(file_name)
        self.on_update(progress)
        self.on_entry(Entry("file", "", name=self.name, own=True, file_name=file_name, size=len(data)))

    async def download(self, file_id: str, header: FileHeader) -> bytes:
        room, keys = self.room, self.crypto_keys
        parts = []
        for i in range(header.chunks):
            async with self._lock:
                if not self.joined or self.room != room:
                    raise UserError(T.FILE_EXPIRED)
                res = await self._with_token("file/get", lambda i=i: {
                    "room": self.room, "token": self.token, "file_id": file_id, "index": i,
                })
            try:
                parts.append(open_envelope(keys, _unb64(res["data"]), aad_chunk(file_id, i)))
            except (CryptoError, ValueError):
                raise UserError(T.INTEGRITY) from None
        data = b"".join(parts)
        if len(data) != header.size or hashlib.sha256(data).hexdigest() != header.sha256:
            raise UserError(T.INTEGRITY)
        return data

    async def _auto_save(self, file_id: str, header: FileHeader) -> None:
        try:
            data = await self.download(file_id, header)
            self.download_dir.mkdir(parents=True, exist_ok=True)
            target = unique_path(self.download_dir, header.file_name)
            target.write_bytes(data)
            self.log("system", T.saved(str(target)))
        except UserError as exc:
            self.log("error", str(exc))
        except ApiError as exc:
            self.log("error", str(_user_error(exc)))
        except OSError:
            self.log("error", T.FILE_EXPIRED)
