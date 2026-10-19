"""Textual full-screen interface: 5-second boot, then the chat terminal."""

from __future__ import annotations

import asyncio
import json
import random
import time
from importlib import resources

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Input, Static

from . import __version__
from . import texts as T
from .commands import run_line
from .config import MIN_COLS, MIN_ROWS, SERVER_URL
from .session import Entry, Session

WHITE, RED, ORANGE, DIM, GREY = "#ffffff", "#ff2b3f", "#ff8a1f", "#6e6e6e", "#bdbdbd"
MASK_WIDTHS = (40, 60, 80, 100, 120, 140, 160)
QUOTES = ("Hello, friend.", "Control is an illusion.", "Is any of it real?", "People are the best exploits.")
BOOT_LINES = (
    ("0.00", "GUPTCHAR v2.0 — booting", ""),
    ("0.12", "argon2id", "ok"),
    ("0.31", "aes-256-gcm", "ok"),
    ("0.44", "metadata scrubber", "ok"),
    ("0.58", "logs", "none"),
    ("0.73", "cookies", "none"),
)
GLITCH = "█▓▒░"

CSS = f"""
Screen {{ background: #000000; color: #e8e8e8; }}
#boot-log {{ height: auto; padding: 1 2 0 2; }}
#boot-mask {{ width: 100%; height: 1fr; content-align: center middle; text-align: center; }}
#boot-quote {{ height: 1; text-align: center; color: {RED}; margin-bottom: 1; }}
#status {{ height: 1; padding: 0 1; background: #0b0b0b; color: {DIM}; }}
#log {{ height: 1fr; padding: 0 1; scrollbar-size-vertical: 1; }}
#log Static {{ width: 100%; }}
#prompt {{ height: 1; padding: 0 1; color: {DIM}; }}
Input {{ border: none; height: 1; padding: 0 1; background: #000000; color: {WHITE}; }}
Input:focus {{ border: none; }}
Input > .input--placeholder {{ color: #3a3a3a; }}
Input > .input--cursor {{ background: {RED}; color: #000000; }}
#too-small {{ width: 100%; height: 100%; content-align: center middle; color: {ORANGE}; }}
"""


def load_mask(cols: int) -> dict | None:
    try:
        raw = resources.files("guptchar").joinpath(f"assets/mask-{cols}.json").read_text(encoding="utf-8")
        return json.loads(raw)
    except (OSError, ValueError):
        return None


def mask_text(rows: list[str], tints: list[str]) -> Text:
    text = Text()
    for row, tint in zip(rows, tints):
        for ch, code in zip(row, tint):
            text.append(ch, style=f"bold {ORANGE}" if code == "o" else "#d9d9d9")
        text.append("\n")
    return text


def boot_line(t: str, label: str, result: str) -> Text:
    line = Text(f"[ {t}] ", style=DIM)
    line.append(label, style=WHITE)
    if result:
        line.append(" " + "." * max(3, 30 - len(label)) + " ", style=DIM)
        line.append(result, style=WHITE if result == "ok" else RED)
    return line


def render_entry(e: Entry) -> Text:
    time_part = Text(f"[{e.time:%H:%M}] ", style=DIM)
    if e.kind == "msg":
        t = time_part
        t.append(e.name, style=ORANGE if e.own else RED)
        t.append(": ", style=DIM)
        t.append(e.text, style=GREY if e.own else WHITE)
        return t
    if e.kind == "file":
        t = time_part
        t.append(e.name, style=ORANGE if e.own else RED)
        t.append(" » file: ", style=DIM)
        t.append(e.file_name, style=WHITE)
        t.append(f" ({_size(e.size)})", style=DIM)
        return t
    if e.kind == "echo":
        return Text(f"> {e.text}", style=DIM)
    if e.kind == "help":
        return Text(f"  {e.text}", style=GREY)
    styles = {"warn": (ORANGE, "!! "), "error": (RED, "xx "), "system": ("#9a9a9a", "-- ")}
    style, prefix = styles.get(e.kind, styles["system"])
    t = time_part
    t.append(prefix + e.text, style=style)
    return t


def _size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / 1024 / 1024:.1f} MB"


class SizedScreen(Screen):
    """Resize events reach the active screen, not the App — forward them."""

    def on_resize(self) -> None:
        self.app._check_size()  # type: ignore[attr-defined]


class TooSmallScreen(SizedScreen):
    def compose(self) -> ComposeResult:
        yield Static(T.TOO_SMALL, id="too-small")


class BootScreen(SizedScreen):
    """Exactly 5 seconds, cannot be skipped (SPEC section 10)."""

    BINDINGS = []

    def compose(self) -> ComposeResult:
        yield Static(id="boot-log")
        yield Static(id="boot-mask")
        yield Static(id="boot-quote")

    def on_mount(self) -> None:
        self.run_worker(self.play(), exclusive=True)

    async def play(self) -> None:
        start = time.monotonic()

        async def until(ms: float) -> None:
            await asyncio.sleep(max(0.0, start + ms / 1000 - time.monotonic()))

        log, mask, quote = (self.query_one(f"#boot-{n}", Static) for n in ("log", "mask", "quote"))
        lines = Text()
        for i, line in enumerate(BOOT_LINES):
            if i:
                lines.append("\n")
            lines.append_text(boot_line(*line))
            log.update(lines)
            await until((i + 1) * 150)

        await until(1000)
        width, height = self.app.size
        fits = [c for c in MASK_WIDTHS if c <= width - 4 and round(c * 0.4) <= height - 3]
        art = load_mask(fits[-1]) if fits else None
        if art and round(art["cols"] * 0.4) > height - 10:
            log.display = False  # small terminal: give the mask the room

        if art:
            rows = art["rows"]
            for y in range(len(rows)):
                shown = list(rows[: y + 1])
                shown[y] = "".join(
                    random.choice(GLITCH) if c != " " and random.random() < 0.35 else c for c in shown[y]
                )
                mask.update(mask_text(shown, art["tint"]))
                await until(1000 + (y + 1) * 2600 / len(rows))
            mask.update(mask_text(rows, art["tint"]))

        await until(3700)
        text = "> " + random.choice(QUOTES)
        for i in range(len(text)):
            quote.update(text[: i + 1])
            await until(3700 + (i + 1) * 800 / len(text))

        await until(5000)
        while getattr(self.app, "_too_small", False):
            await asyncio.sleep(0.2)
        self.app.switch_screen(ChatScreen())


class ChatScreen(SizedScreen):
    def compose(self) -> ComposeResult:
        yield Static(id="status")
        yield VerticalScroll(id="log")
        yield Static(id="prompt")
        yield Input(id="input", placeholder="message or /command — /help")

    def on_mount(self) -> None:
        app: GuptcharApp = self.app  # type: ignore[assignment]
        app.chat = self
        for entry in app.entries:
            self.add(entry)
        self.refresh_status()
        self.query_one(Input).focus()
        app.ui.log("warn", T.IP_WARNING)
        app.ui.log("system", T.HINT)

    def add(self, entry: Entry) -> None:
        log = self.query_one("#log", VerticalScroll)
        at_end = log.max_scroll_y - log.scroll_y < 2
        widget = Static(render_entry(entry), id=f"e{entry.id}")
        log.mount(widget)
        if at_end:
            log.scroll_end(animate=False)

    def update_entry(self, entry: Entry) -> None:
        try:
            self.query_one(f"#e{entry.id}", Static).update(render_entry(entry))
        except Exception:
            pass

    def clear(self) -> None:
        self.query_one("#log", VerticalScroll).remove_children()

    def refresh_status(self, asking: str | None = None) -> None:
        s = self.app.session  # type: ignore[attr-defined]
        status = Text(" GUPTCHAR ", style=f"bold {WHITE} on {RED}")
        status.append(f"  v{__version__}  ", style=DIM)
        if s.joined:
            status.append(s.room, style=ORANGE)
            status.append(f"  ·  {len(s.crypto_keys)} key layer{'' if len(s.crypto_keys) == 1 else 's'}", style=DIM)
        else:
            status.append("not in a room", style=DIM)
        self.query_one("#status", Static).update(status)

        prompt = Text()
        if asking:
            prompt.append(asking, style=ORANGE)
        else:
            prompt.append(s.name or "anon", style=RED)
            prompt.append("@", style=DIM)
            prompt.append(s.room if s.joined else "offline", style=ORANGE if s.joined else DIM)
            prompt.append(" >", style=WHITE)
        self.query_one("#prompt", Static).update(prompt)

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        app: GuptcharApp = self.app  # type: ignore[assignment]
        value = event.value
        event.input.value = ""
        if app.pending is not None and not app.pending.done():
            app.pending.set_result(value)
            return
        self.run_worker(run_line(value, app.ui), group="commands")

    def key_escape(self) -> None:
        app: GuptcharApp = self.app  # type: ignore[assignment]
        if app.pending is not None and not app.pending.done():
            app.pending.set_result(None)


class Ui:
    """What commands.py talks to (kept separate from App, whose `log` is Textual's logger)."""

    def __init__(self, app: "GuptcharApp"):
        self.app = app
        self.session = app.session

    def log(self, kind: str, text: str) -> None:
        self.app.add_entry(Entry(kind, text))

    def clear(self) -> None:
        self.app.clear_entries()

    async def ask(self, label: str, password: bool = False) -> str | None:
        return await self.app.ask(label, password)

    async def quit(self) -> None:
        await self.app.quit_app()


class GuptcharApp(App):
    CSS = CSS
    TITLE = "Guptchar"
    ENABLE_COMMAND_PALETTE = False

    def __init__(self, server_url: str = SERVER_URL):
        super().__init__()
        self.entries: list[Entry] = []
        self.chat: ChatScreen | None = None
        self.pending: asyncio.Future | None = None
        self._too_small = False
        self._booted = False
        self.session = Session(
            server_url,
            on_entry=self.add_entry,
            on_update=self._on_update,
            on_status=self._on_status,
            confirm=self.confirm,
            beep=self.bell,
        )
        self.ui = Ui(self)

    async def on_mount(self) -> None:
        await self.push_screen(BootScreen())
        self._booted = True
        self._check_size()

    def on_resize(self) -> None:
        self._check_size()

    def _check_size(self) -> None:
        if not self._booted:
            return
        small = self.size.width < MIN_COLS or self.size.height < MIN_ROWS
        on_top = isinstance(self.screen, TooSmallScreen)
        if small and not on_top:
            self._too_small = True
            self.push_screen(TooSmallScreen())
        elif not small and on_top:
            self._too_small = False
            self.pop_screen()

    # ---- session callbacks
    def add_entry(self, entry: Entry) -> None:
        self.entries.append(entry)
        if self.chat is not None and self.chat.is_attached:
            self.chat.add(entry)

    def _on_update(self, entry: Entry) -> None:
        if self.chat is not None:
            self.chat.update_entry(entry)

    def _on_status(self) -> None:
        if self.chat is not None and self.chat.is_attached:
            self.chat.refresh_status()

    def clear_entries(self) -> None:
        self.entries.clear()
        if self.chat is not None:
            self.chat.clear()

    async def ask(self, label: str, password: bool = False) -> str | None:
        chat = self.chat
        field = chat.query_one(Input)
        self.pending = asyncio.get_running_loop().create_future()
        field.password = password
        field.placeholder = ""
        chat.refresh_status(asking=label)
        try:
            return await self.pending
        finally:
            field.password = False
            field.placeholder = "message or /command — /help"
            self.pending = None
            chat.refresh_status()

    async def confirm(self, text: str) -> bool:
        self.add_entry(Entry("warn", text))
        answer = await self.ask("[y/N]")
        return (answer or "").strip().lower() in ("y", "yes")

    async def quit_app(self) -> None:
        await self.session.close()
        self.exit()

    async def action_quit(self) -> None:
        await self.quit_app()
