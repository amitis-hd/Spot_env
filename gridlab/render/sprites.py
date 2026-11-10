"""Sprite definitions.

Each sprite is a small transparent PNG in `assets/` (one per object state). They are generated
from the drawing functions below by `python -m gridlab.render.sprites`, and you can replace any PNG
with your own art: the renderer only cares about the file name and the sprite's aspect ratio
(it is scaled to the size given in SIZES).

SIZES gives each sprite's size as a fraction of a cell's width/height when drawn in a cell.
"""
from __future__ import annotations

import math
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).with_name("assets")
RES = 400  # pixels per cell when generating sprites

WOOD, WOOD_D, WOOD_L = (176, 128, 82), (120, 82, 48), (214, 176, 130)
METAL, DARK, CAV = (170, 170, 178), (40, 40, 45), (55, 42, 32)
GOLD = (225, 185, 40)

SIZES: dict[str, tuple[float, float]] = {
    "cabinet_closed": (0.84, 0.31), "cabinet_open": (1.0, 0.37),
    "shelf": (0.84, 0.04),
    "counter": (1.0, 0.50),
    "drawer_closed": (0.76, 0.28), "drawer_open": (0.88, 0.35),
    "table": (0.92, 0.29),
    "book": (0.13, 0.22), "binder": (0.16, 0.34), "pen": (0.24, 0.035), "key": (0.18, 0.07),
    "mug": (0.13, 0.12), "item": (0.15, 0.15),
    "lamp_off": (0.20, 0.28), "lamp_on": (0.26, 0.30),
    "button_up": (0.20, 0.11), "button_pressed": (0.20, 0.08),
    "stool": (0.38, 0.21), "chair": (0.40, 0.42),
    "person": (0.30, 0.86), "dock": (0.72, 0.13),
    "door_closed": (0.56, 0.90), "door_open": (0.56, 0.90),
    "padlock": (0.07, 0.08), "keyhole": (0.05, 0.05), "key_in_lock": (0.13, 0.05),
    "spot": (0.42, 0.42),
}


def _draw(name: str, w: int, h: int) -> Image.Image:
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    lw = max(1, round(w / 120)) if w < h * 3 else max(1, round(h / 30))
    u = min(w, h)

    def R(x0, y0, x1, y1, **kw):
        d.rectangle([x0 * w, y0 * h, x1 * w - 1, y1 * h - 1], **kw)

    def RR(x0, y0, x1, y1, r=0.05, **kw):
        d.rounded_rectangle([x0 * w, y0 * h, x1 * w - 1, y1 * h - 1], radius=r * u, **kw)

    if name == "cabinet_closed":
        R(0, 0, 1, 1, fill=WOOD_D, outline=DARK, width=2 * lw)
        for a, b in ((0.03, 0.495), (0.505, 0.97)):
            R(a, 0.05, b, 0.95, fill=WOOD, outline=WOOD_D, width=lw)
            R(a + 0.05, 0.15, b - 0.05, 0.85, outline=WOOD_L, width=lw)
        RR(0.44, 0.35, 0.47, 0.65, 0.01, fill=METAL, outline=DARK)
        RR(0.53, 0.35, 0.56, 0.65, 0.01, fill=METAL, outline=DARK)
    elif name == "cabinet_open":
        R(0.08, 0.06, 0.92, 0.92, fill=WOOD_D, outline=DARK, width=2 * lw)
        R(0.12, 0.12, 0.88, 0.86, fill=CAV)
        R(0.12, 0.47, 0.88, 0.51, fill=WOOD_L)                                   # inner shelf
        d.polygon([(0.08 * w, 0.06 * h), (0, 0), (0, h), (0.08 * w, 0.92 * h)], fill=WOOD, outline=WOOD_D)
        d.polygon([(0.92 * w, 0.06 * h), (w, 0), (w, h), (0.92 * w, 0.92 * h)], fill=WOOD, outline=WOOD_D)
    elif name == "shelf":
        R(0, 0, 1, 1, fill=WOOD_L, outline=WOOD_D, width=lw)
    elif name == "counter":
        R(0.03, 0.04, 0.97, 0.96, fill=(190, 190, 196), outline=DARK, width=2 * lw)
        R(0, 0, 1, 0.10, fill=(150, 150, 158), outline=DARK, width=lw)            # countertop slab
    elif name == "drawer_closed":
        R(0, 0, 1, 1, fill=WOOD, outline=WOOD_D, width=2 * lw)
        R(0.05, 0.1, 0.95, 0.9, outline=WOOD_L, width=lw)
        RR(0.34, 0.2, 0.66, 0.32, 0.02, fill=METAL, outline=DARK)
    elif name == "drawer_open":
        R(0.07, 0.0, 0.93, 0.29, fill=CAV, outline=WOOD_D, width=2 * lw)           # cavity in the counter
        d.polygon([(0.09 * w, 0.29 * h), (0.91 * w, 0.29 * h), (0.98 * w, 0.57 * h), (0.02 * w, 0.57 * h)],
                  fill=(150, 108, 66), outline=WOOD_D)                             # tray interior
        R(0, 0.57, 1, 1, fill=WOOD, outline=WOOD_D, width=2 * lw)                  # front panel
        RR(0.36, 0.68, 0.64, 0.78, 0.02, fill=METAL, outline=DARK)
    elif name == "table":
        R(0, 0, 1, 0.18, fill=(120, 150, 190), outline=DARK, width=2 * lw)
        R(0.05, 0.18, 0.11, 1, fill=(90, 110, 140), outline=DARK)
        R(0.89, 0.18, 0.95, 1, fill=(90, 110, 140), outline=DARK)
    elif name in ("book", "binder"):
        color = (180, 40, 40) if name == "book" else (60, 90, 170)
        R(0, 0, 1, 1, fill=color, outline=tuple(c // 3 for c in color), width=2 * lw)
        R(0, 0, 0.2, 1, fill=tuple(int(c * 0.7) for c in color))
        for i in range(3):
            y = 0.03 + i * 0.025
            d.line([0.22 * w, y * h, 0.95 * w, y * h], fill=(250, 245, 230), width=lw)
    elif name == "pen":
        R(0, 0, 0.85, 1, fill=(40, 70, 190), outline=DARK)
        d.polygon([(0.85 * w, 0), (w, h / 2), (0.85 * w, h)], fill=(230, 220, 200), outline=DARK)
    elif name in ("key", "key_in_lock"):
        r = h * 0.48
        d.ellipse([0, h / 2 - r, 2 * r, h / 2 + r], fill=GOLD, outline=DARK, width=lw)
        d.ellipse([r * 0.6, h / 2 - r * 0.4, r * 1.4, h / 2 + r * 0.4], fill=CAV)
        d.rectangle([2 * r, h * 0.38, w - 1, h * 0.62], fill=GOLD, outline=DARK)
        for t in (0.6, 0.8):
            d.rectangle([w * t, h * 0.62, w * t + w * 0.07, h * 0.9], fill=GOLD, outline=DARK)
    elif name == "mug":
        R(0, 0.05, 0.78, 1, fill=(240, 240, 240), outline=DARK, width=lw)
        d.arc([0.62 * w, 0.2 * h, 1.0 * w - 1, 0.75 * h], 270, 90, fill=DARK, width=2 * lw)
    elif name == "item":
        R(0, 0, 1, 1, fill=(200, 200, 160), outline=DARK, width=lw)
        d.line([0, 0, w, h], fill=DARK, width=lw)
        d.line([0, h, w, 0], fill=DARK, width=lw)
    elif name in ("lamp_off", "lamp_on"):
        on = name == "lamp_on"
        cx = w / 2
        d.rectangle([cx - 0.3 * w, 0.92 * h, cx + 0.3 * w, h - 1], fill=(60, 60, 66), outline=DARK)
        d.line([cx, 0.92 * h, cx, 0.45 * h], fill=(60, 60, 66), width=3 * lw)
        r = 0.13 * h
        by = 0.38 * h
        if on:
            for i in range(9):
                a = math.pi * (0.1 + 0.8 * i / 8)
                d.line([cx + math.cos(a) * r * 1.4, by + math.sin(a) * r * 1.4,
                        cx + math.cos(a) * r * 2.4, by + math.sin(a) * r * 2.4], fill=(245, 190, 0), width=2 * lw)
        d.ellipse([cx - r, by - r, cx + r, by + r], fill=(255, 235, 80) if on else (200, 200, 205), outline=DARK)
        sw = 0.4 * (w if not on else w * 0.77)
        d.polygon([(cx - sw, by - 0.02 * h), (cx + sw, by - 0.02 * h), (cx + sw * 0.5, 0.05 * h),
                   (cx - sw * 0.5, 0.05 * h)], fill=(40, 120, 110), outline=DARK)
    elif name in ("button_up", "button_pressed"):
        R(0, 0.7 if name == "button_up" else 0.6, 1, 1, fill=METAL, outline=DARK)
        top = 0.0 if name == "button_up" else 0.1
        bottom = 0.72 if name == "button_up" else 0.62
        d.chord([0.15 * w, top * h, 0.85 * w, (top + 2 * (bottom - top)) * h], 180, 360, fill=(220, 40, 40), outline=DARK, width=lw)
        R(0.15, (top + bottom) / 2, 0.85, bottom, fill=(220, 40, 40), outline=DARK)
    elif name == "stool":
        R(0, 0, 1, 0.2, fill=(90, 160, 90), outline=DARK, width=2 * lw)
        d.line([0.12 * w, 0.2 * h, 0.02 * w, h], fill=DARK, width=3 * lw)
        d.line([0.88 * w, 0.2 * h, 0.98 * w, h], fill=DARK, width=3 * lw)
        d.line([0.07 * w, 0.65 * h, 0.93 * w, 0.65 * h], fill=DARK, width=2 * lw)
    elif name == "chair":
        R(0, 0, 0.1, 1, fill=(90, 160, 90), outline=DARK)
        R(0, 0, 0.55, 0.2, fill=(90, 160, 90), outline=DARK)
        R(0, 0.48, 1, 0.58, fill=(90, 160, 90), outline=DARK, width=2 * lw)
        d.line([0.92 * w, 0.58 * h, 0.92 * w, h], fill=DARK, width=3 * lw)
    elif name == "person":
        R(0.30, 0.0, 0.70, 0.22, fill=(245, 200, 160), outline=DARK, width=2 * lw)  # square head
        for ex in (0.42, 0.58):
            R(ex - 0.03, 0.09, ex + 0.03, 0.12, fill=DARK)
        R(0.10, 0.25, 0.90, 0.65, fill=(70, 110, 200), outline=DARK, width=2 * lw)
        R(0.22, 0.65, 0.45, 1.0, fill=(50, 50, 70), outline=DARK)
        R(0.55, 0.65, 0.78, 1.0, fill=(50, 50, 70), outline=DARK)
    elif name == "dock":
        R(0, 0.15, 1, 1, fill=(60, 60, 66), outline=DARK)
        R(0, 0, 1, 0.22, fill=(60, 200, 90))
        x, y, k = w / 2, 0.6 * h, h / 22
        d.polygon([(x + 2 * k, y - 9 * k), (x - 6 * k, y + 1 * k), (x, y + 1 * k), (x - 2 * k, y + 9 * k),
                   (x + 6 * k, y - 1 * k), (x, y - 1 * k)], fill=(255, 220, 0))
    elif name == "door_closed":
        R(0, 0, 1, 1, fill=WOOD, outline=DARK, width=2 * lw)
        R(0.1, 0.06, 0.9, 0.45, outline=WOOD_L, width=lw)
        R(0.1, 0.52, 0.9, 0.94, outline=WOOD_L, width=lw)
        d.ellipse([0.72 * w, 0.47 * h, 0.84 * w, 0.47 * h + 0.12 * w], fill=METAL, outline=DARK)
    elif name == "door_open":
        R(0, 0, 1, 1, fill=(25, 25, 30), outline=DARK, width=2 * lw)                 # dark doorway
        d.polygon([(0, 0), (0.22 * w, 0.06 * h), (0.22 * w, 0.94 * h), (0, h - 1)], fill=WOOD, outline=WOOD_D)
    elif name == "padlock":
        d.arc([0.2 * w, 0, 0.8 * w, 0.7 * h], 180, 360, fill=DARK, width=2 * lw)
        R(0.05, 0.35, 0.95, 1, fill=(210, 60, 50), outline=DARK)
    elif name == "keyhole":
        d.ellipse([0, 0, w - 1, h - 1], fill=(200, 170, 40), outline=DARK)
        d.line([w / 2, 0.2 * h, w / 2, 0.8 * h], fill=DARK, width=max(1, w // 6))
    elif name == "spot":
        R(0.06, 0.14, 0.94, 1, fill=(250, 200, 0), outline=(20, 20, 20), width=2 * lw)
        d.polygon([(0.3 * w, 0.14 * h), (0.7 * w, 0.14 * h), (0.5 * w, 0)], fill=(20, 20, 20))
    else:
        raise KeyError(name)
    return im


def sprite_pixels(name: str) -> tuple[int, int]:
    """Generation size: RES px per cell, but at least 96 px on the short side (keeps small sprites crisp)."""
    fw, fh = SIZES[name]
    k = max(RES, 96 / min(fw, fh)) if min(fw, fh) * RES < 96 and max(fw, fh) / min(fw, fh) < 4 else RES
    return max(4, round(fw * k)), max(4, round(fh * k))


@lru_cache(maxsize=None)
def _base(name: str) -> Image.Image:
    path = ASSETS / f"{name}.png"
    if path.exists():
        return Image.open(path).convert("RGBA")
    if name in SIZES:
        return _draw(name, *sprite_pixels(name))
    return _base("item")          # unknown sprite name: generic box


@lru_cache(maxsize=4096)
def sprite(name: str, w: int, h: int) -> Image.Image:
    """The named sprite scaled to w x h pixels."""
    return _base(name).resize((max(1, w), max(1, h)), Image.LANCZOS)


def make_sprites(out: Path = ASSETS) -> list[Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for name in SIZES:
        p = out / f"{name}.png"
        _draw(name, *sprite_pixels(name)).save(p)
        paths.append(p)
    _base.cache_clear()
    sprite.cache_clear()
    return paths


if __name__ == "__main__":
    for p in make_sprites():
        print(p)
