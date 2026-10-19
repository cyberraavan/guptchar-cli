# Guptchar CLI

End-to-end encrypted, zero-storage group chat — in your terminal.

- Messages and files are encrypted **on your machine** (Argon2id + AES-256-GCM, up to 3 key layers). The relay only ever sees sealed envelopes.
- No accounts, no database, no history. The relay forgets everything after 60 seconds.
- File metadata (photo GPS/camera, PDF author, Office author/comment names) is removed before encryption.
- Talks to the same rooms as the Guptchar web app.

```
[ 0.00] GUPTCHAR v2.0 — booting
[ 0.12] argon2id ...................... ok
[ 0.31] aes-256-gcm ................... ok
```

## Install

Needs **Python 3.10+** and **git**. Terminal at least **60×20**.

### Linux (main target)

```bash
git clone https://github.com/cyberraavan/guptchar-cli.git
cd guptchar-cli
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python guptchar.py          # or: python -m guptchar
```

Debian/Ubuntu may need `sudo apt install python3-venv` first.

### Android (Termux)

`cryptography` has no ready-made wheel for Android, so take it from Termux's own packages:

```bash
pkg install python git clang libffi openssl python-cryptography
git clone https://github.com/cyberraavan/guptchar-cli.git
cd guptchar-cli
pip install textual==8.2.8 argon2-cffi==25.1.0 pypdf==6.19.0 httpx==0.28.1
python guptchar.py
```

Received files go to `~/Downloads/guptchar/` — run `termux-setup-storage` if you want them in the phone's Downloads.

### macOS

```bash
git clone https://github.com/cyberraavan/guptchar-cli.git
cd guptchar-cli
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python guptchar.py
```

### Windows

Use Windows Terminal (PowerShell):

```powershell
git clone https://github.com/cyberraavan/guptchar-cli.git
cd guptchar-cli
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python guptchar.py
```

## Use

```
/nick raavan            your name (1–16: letters, numbers, _ -)
/key add                add a key (typed hidden) — everyone in the room needs the same keys, same order
/join my-secret-room    join (8–64: letters, numbers, . _ -)
hello                   anything without / is a message
/send ~/photo.jpg       send a file (max 10 MB, one per minute)
/leave   /clear   /help   /exit
```

- Up to **3 keys** = 3 encryption layers. Use long, random keys — anyone who guesses them can read everything.
- Received files are saved automatically to `~/Downloads/guptchar/` (never overwritten: `photo (1).jpg`).
- `Esc` cancels a prompt, `Ctrl+Q` quits.

## What the relay can and cannot see

| | |
|---|---|
| Messages, files, file names, your name | ❌ never — encrypted before they leave your machine |
| Your keys | ❌ never leave your machine |
| Room name, message sizes and timing | ✅ yes |
| Your IP address | ✅ yes — use Tor or a VPN to hide it |

## Verify the web app

The web client's JavaScript is served by the relay, so a hacked server could swap it. `WEB_HASHES.txt` lists the SHA-256 of every served file; compare with the hashes shown in the web app's footer, or download a file and run `sha256sum`.

## Tests

```bash
python -m unittest discover -s tests -t .
```

## License

AGPL-3.0-only — see `LICENSE`.
