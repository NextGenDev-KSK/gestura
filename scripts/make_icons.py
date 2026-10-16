"""Generate Gestura's icons (run once; the outputs are committed).

    python scripts/make_icons.py

Writes to ``assets/icons/``:

* ``gestura.ico``         multi-size Windows icon (the .exe, installer and window)
* ``gestura.png``         256 px, active (tray icon while gesture control is on)
* ``gestura_paused.png``  256 px, paused (tray icon while paused)

The mark matches the in-app title bar: a four-point star on the cyan-to-blue accent gradient.
Drawn at 4x and downsampled, so it stays crisp at 16 px in the tray.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw

OUT = Path(__file__).resolve().parents[1] / "assets" / "icons"
SIZE, SCALE = 256, 4
ACCENT, ACCENT2, INK = (0x48, 0xD6, 0xDE), (0x7C, 0x9C, 0xFF), (0x07, 0x20, 0x2A)
GREY, GREY2 = (0x9A, 0xA1, 0xB2), (0x5C, 0x65, 0x77)


def _gradient(size: int, a: tuple, b: tuple) -> Image.Image:
    """Diagonal (top-left -> bottom-right) linear gradient."""
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return img


def _rounded_mask(size: int, radius: int) -> Image.Image:
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return mask


def _star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r_out: float, fill) -> None:
    r_in = r_out * 0.30
    pts = []
    for k in range(8):
        ang = -math.pi / 2 + k * math.pi / 4
        r = r_out if k % 2 == 0 else r_in
        pts.append((cx + r * math.cos(ang), cy + r * math.sin(ang)))
    draw.polygon(pts, fill=fill)


def make(paused: bool) -> Image.Image:
    big = SIZE * SCALE
    base = _gradient(big, *((GREY, GREY2) if paused else (ACCENT, ACCENT2))).convert("RGBA")
    draw = ImageDraw.Draw(base)
    if paused:
        bar_w, bar_h, gap = big * 0.13, big * 0.46, big * 0.10
        top = (big - bar_h) / 2
        for x in ((big - gap) / 2 - bar_w, (big + gap) / 2):
            draw.rounded_rectangle([x, top, x + bar_w, top + bar_h], radius=bar_w * 0.3,
                                   fill=(255, 255, 255, 255))
    else:
        _star(draw, big / 2, big / 2, big * 0.36, (*INK, 255))
    base.putalpha(_rounded_mask(big, int(big * 0.22)))
    return base.resize((SIZE, SIZE), Image.LANCZOS)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    active = make(paused=False)
    active.save(OUT / "gestura.png")
    make(paused=True).save(OUT / "gestura_paused.png")
    active.save(OUT / "gestura.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                                           (128, 128), (256, 256)])
    print(f"Wrote icons to {OUT}")


if __name__ == "__main__":
    main()
