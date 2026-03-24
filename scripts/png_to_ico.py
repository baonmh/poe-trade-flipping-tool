#!/usr/bin/env python3
"""Regenerate static/flipper.ico from static/flipper.png (PyInstaller Windows exe icon)."""
from __future__ import annotations

from pathlib import Path

try:
    from PIL import Image
except ImportError as e:
    raise SystemExit("Install Pillow: pip install Pillow") from e

ROOT = Path(__file__).resolve().parent.parent
PNG = ROOT / "static" / "flipper.png"
ICO = ROOT / "static" / "flipper.ico"


def main() -> None:
    if not PNG.is_file():
        raise SystemExit(f"Missing {PNG}")
    img = Image.open(PNG).convert("RGBA")
    ICO.parent.mkdir(parents=True, exist_ok=True)
    sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(ICO, format="ICO", sizes=sizes)
    print(f"Wrote {ICO}")


if __name__ == "__main__":
    main()
