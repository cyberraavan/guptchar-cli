"""Command line handling (SPEC section 12) — same commands as the web client."""

from __future__ import annotations

from typing import Protocol

from . import texts as T
from .keystrength import estimate_bits, strength_label
from .session import Session, UserError


class Ui(Protocol):
    session: Session

    def log(self, kind: str, text: str) -> None: ...
    def clear(self) -> None: ...
    async def ask(self, label: str, password: bool = False) -> str | None: ...
    async def quit(self) -> None: ...


async def run_line(line: str, ui: Ui) -> None:
    session = ui.session
    raw = line.replace("\r", " ").replace("\n", " ")
    if not raw.strip():
        return

    try:
        if not raw.startswith("/") or raw.startswith("//"):
            await session.send_text(raw[1:] if raw.startswith("//") else raw)
            return

        ui.log("echo", raw)
        cmd, _, rest = raw.strip().partition(" ")
        args = rest.split()
        cmd = cmd.lower()

        if cmd == "/nick":
            session.set_name(rest.strip())
            ui.log("system", T.name_set(session.name))
        elif cmd == "/key":
            await _key(args, ui)
        elif cmd == "/join":
            await session.join(args[0] if args else "")
        elif cmd == "/send":
            if not rest.strip():
                raise UserError(T.NEED_PATH)
            await session.send_file(rest)
        elif cmd == "/leave":
            await session.leave()
        elif cmd == "/clear":
            ui.clear()
        elif cmd == "/help":
            for text in T.HELP:
                ui.log("help", text)
        elif cmd == "/exit":
            await ui.quit()
        elif cmd in ("/mode", "/theme"):
            raise UserError(T.WEB_ONLY)
        else:
            raise UserError(T.UNKNOWN)
    except UserError as exc:
        ui.log("error", str(exc))


async def _key(args: list[str], ui: Ui) -> None:
    session = ui.session
    sub = args[0].lower() if args else ""
    try:
        n = int(args[1]) if len(args) > 1 else 0
    except ValueError:
        n = 0

    if sub == "add":
        if session.joined:
            raise UserError(T.KEYS_LOCKED)
        ui.log("warn", T.KEY_WARNING)
        label = await ui.ask(T.LABEL_PROMPT)
        if label is None:
            return
        secret = await ui.ask(T.KEY_PROMPT, password=True)
        if secret is None:
            return
        ui.log("system", T.strength(strength_label(estimate_bits(secret))))
        added = session.add_key(label, secret)
        ui.log("system", T.key_added(added, len(session.keys)))
    elif sub == "list":
        if not session.keys:
            ui.log("system", T.NO_KEYS)
        for i, key in enumerate(session.keys, 1):
            ui.log("help", f"{i}. {key['label']}")
    elif sub == "remove":
        ui.log("system", T.key_removed(session.remove_key(n)))
    elif sub in ("up", "down"):
        session.move_key(n, -1 if sub == "up" else 1)
        ui.log("system", T.KEY_MOVED)
    else:
        raise UserError(T.UNKNOWN)
