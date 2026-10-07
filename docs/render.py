"""Render the README images from the HTML pages in docs/ with headless Chrome.

    .venv/bin/python docs/render.py            # all images
    .venv/bin/python docs/render.py hero how   # just these

The card screenshots use the real card (frontend/smart-heating-card.js) with a mock house, so
re-run this after changing the card. Pages taller than their content are cropped to it.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
DOCS = Path(__file__).resolve().parent
SCALE = 2
PAD = 48  # css px kept below the content when cropping

# name: (page, css width, css height or None to crop to content)
IMAGES = {
    "hero": ("hero.html", 1200, 570),
    "trio": ("screens.html#trio", 1200, None),
    "rooms": ("screens.html#rooms", 735, None),
    "cal": ("screens.html#cal", 735, None),
    "wizard": ("wizard.html", 800, None),
    "how": ("how.html", 1200, None),
}


def content_bottom(img: Image.Image) -> int:
    """Last row that differs from the background (taken from the row's left edge)."""
    px, (w, h) = img.load(), img.size
    for y in range(h - 1, -1, -1):
        bg = px[2, y]
        for x in range(0, w, 3):
            if sum(abs(a - b) for a, b in zip(px[x, y][:3], bg[:3])) > 24:
                return y
    return h


def render(name: str) -> None:
    page, width, height = IMAGES[name]
    with tempfile.TemporaryDirectory() as tmp:
        shot = Path(tmp) / "shot.png"
        subprocess.run([CHROME, "--headless", "--hide-scrollbars", f"--force-device-scale-factor={SCALE}",
                        "--virtual-time-budget=5000", f"--window-size={width},{height or 1600}",
                        f"--screenshot={shot}", f"file://{DOCS / page}"], check=True, capture_output=True)
        img = Image.open(shot).convert("RGB")
    if height is None:
        img = img.crop((0, 0, img.width, min(img.height, content_bottom(img) + PAD * SCALE)))
    out = DOCS / "images" / f"{name}.jpg"
    img.save(out, quality=88, optimize=True, progressive=True)
    print(f"{out.relative_to(DOCS.parent)}: {img.width}x{img.height}")


if __name__ == "__main__":
    for n in sys.argv[1:] or IMAGES:
        render(n)
