"""`python -m guptchar` / `python guptchar.py`."""

import sys


def main() -> None:
    if sys.version_info < (3, 10):
        sys.exit("Guptchar needs Python 3.10 or newer.")
    try:
        from .app import GuptcharApp
    except ImportError as exc:
        sys.exit(f"Missing dependency ({exc.name}). Run: pip install -r requirements.txt")
    GuptcharApp().run()


if __name__ == "__main__":
    main()
