"""Every user-visible string (same wording as the web client, SPEC section 18)."""

ROOM_FULL = "Room is full (10/10). Try again later."
INVALID_ROOM = "Room name: 8–64 characters — letters, numbers, . _ -"
INVALID_NAME = "Name: 1–16 characters — letters, numbers, _ -"
RATE_MSG = "Slow down — max 60 messages per minute."
RATE_FILE = "One file per minute. Please wait."
TOO_LARGE = "Too large — text max 1000 characters, files max 10 MB."
STORAGE_FULL = "Relay is full right now. Try again in a minute."
FILE_EXPIRED = "File expired — files live for 60 seconds."
OFFLINE = "Can't reach the relay. Retrying…"
MISSED = "Some messages expired while you were away."
UNSUPPORTED_CONFIRM = "Metadata can't be removed from this file type. Send anyway?"
RELAY_BUSY = "Relay is busy right now. Try again in a minute."
CAPTCHA_TITLE = "Prove you're human — type the 5 characters below."
CAPTCHA_WRONG = "Wrong answer — here is a new one."
CAPTCHA_REQUIRED = "Please solve the captcha again."
WEAK_KEY = "Key too weak — use 4+ random words or 12+ mixed characters (letters, numbers, symbols)."
EXECUTABLE = "Executable file — only open it if you trust the sender."
AUTO_SAVE_LIMIT = "Auto-save limit reached (50 files / 100 MB this run) — file skipped."


def strength(label: str) -> str:
    return f"Key strength: {label}"

KEY_WARNING = "Use a long, random key — anyone who guesses it can read everything."
IP_WARNING = "The server can see your IP address. Use Tor Browser or a VPN to hide it."

NEED_NAME = "Set your name first: /nick <name>"
NEED_KEY = "Add at least one key first: /key add"
NEED_ROOM = "Usage: /join <room>"
NEED_PATH = "Usage: /send <file path>"
NOT_JOINED = "Not in a room. Use /join <room>."
ALREADY_JOINED = "Already in a room. Use /leave first."
KEYS_LOCKED = "Keys are locked while in a room. Use /leave to change them."
MAX_LAYERS = "Maximum 3 keys."
EMPTY_KEY = "Key cannot be empty."
NO_KEYS = "No keys added yet."
BAD_INDEX = "No key with that number."
NO_FILE = "File not found."
KEY_MOVED = "Key order changed."
DERIVING = "Deriving keys…"
LEFT = "Left the room. Keys stay in memory until you exit."
BACK = "Connection restored."
CANCELLED = "File not sent."
INTEGRITY = "File failed its integrity check and was discarded."
UNKNOWN = "Unknown command. Type /help"
WEB_ONLY = "/mode and /theme exist only in the web app."
LABEL_PROMPT = "Key label (Enter = default):"
KEY_PROMPT = "Key (hidden):"
TOO_SMALL = "Terminal too small (need 60x20). Please enlarge the window."
HINT = "Type /help to see commands. Start with /nick <name>, /key add, /join <room>."


def connected(room: str, layers: int) -> str:
    return f"Joined {room} — {layers} key layer{'' if layers == 1 else 's'}. Messages are end-to-end encrypted."


def name_set(name: str) -> str:
    return f"Name set to {name}."


def key_added(label: str, count: int) -> str:
    return f"Key added: {label} ({count}/3)."


def key_removed(label: str) -> str:
    return f"Key removed: {label}."


def sending(name: str, i: int, n: int) -> str:
    return f"Sending {name}… {i}/{n}"


def sent(name: str) -> str:
    return f"Sent {name}."


def saved(path: str) -> str:
    return f"Saved to {path}"


HELP = [
    "/nick <name>         set your name (1–16: letters, numbers, _ -)",
    "/key add             add a key (hidden typing), max 3 layers",
    "/key list            show key labels",
    "/key remove <n>      remove key n",
    "/key up <n>          move key n up",
    "/key down <n>        move key n down",
    "/join <room>         join a room (8–64: letters, numbers, . _ -)",
    "/send <path>         send a file (max 10 MB)",
    "/leave               leave the room",
    "/clear               clear the screen",
    "/help                this list",
    "/exit                quit",
    "Anything else you type is sent as a message.",
]

API_ERRORS = {
    "room_full": ROOM_FULL,
    "invalid_room": INVALID_ROOM,
    "too_large": TOO_LARGE,
    "storage_full": STORAGE_FULL,
    "relay_busy": RELAY_BUSY,
    "captcha_required": CAPTCHA_REQUIRED,
    "captcha_failed": CAPTCHA_WRONG,
    "file_gone": FILE_EXPIRED,
    "network": OFFLINE,
}
