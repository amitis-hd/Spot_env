"""Draw the world with PIL.

`render_cell` draws one cell as a front view: HIGH level (wall cabinets, shelves) in the top half,
LOW level (counters, drawers, tables, floor) in the bottom half. The window shows every cell this
way (with name tags); `render_photo` draws the cell in front of the robot the same way, bigger and
without any text, which is what the robot's gripper camera "sees".
"""
from __future__ import annotations

import math
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

from ..core.entity import Relation, Thing
from ..core.geometry import Direction, Level, step
from .sprites import SIZES, sprite

WALL, FLOOR, FLOOR_LINE = (226, 228, 236), (205, 200, 190), (190, 185, 175)
DARK = (40, 40, 45)


@lru_cache(maxsize=64)
def font(px: int, bold: bool = False):
    for name in (("DejaVuSans-Bold.ttf", "Arial Bold.ttf", "arialbd.ttf") if bold else
                 ("DejaVuSans.ttf", "Arial.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            pass
    return ImageFont.load_default(size=px)


# ---------------------------------------------------------------- which sprite for which thing
def sprite_name(world, t: Thing) -> str:
    custom = getattr(t, "sprite", None)
    if isinstance(custom, str):
        return custom
    k = t.kind
    if k == "lamp":
        return "lamp_on" if t.on else "lamp_off"
    if k == "button":
        return "button_pressed" if t.is_pressed(world) else "button_up"
    if k in ("book", "binder", "pen", "key", "mug", "stool", "chair", "person", "dock", "table", "counter", "shelf"):
        return k
    if k in ("drawer", "cabinet"):
        return f"{k}_{'open' if t.is_open else 'closed'}"
    return "item"


def size_of(name: str) -> tuple[float, float]:
    return SIZES.get(name, SIZES["item"])


def label_of(t: Thing) -> str:
    st = []
    if getattr(t, "locked", False):
        st.append("LOCKED")
    elif hasattr(t, "is_open") and t.kind != "door":
        st.append("open" if t.is_open else "closed")
    if t.kind == "lamp":
        st.append("ON" if t.on else "OFF")
    return t.id + (" " + " ".join(st) if st else "")


# ---------------------------------------------------------------- painter
class CellPainter:
    def __init__(self, world, img: Image.Image, box, labels: bool, robot: bool):
        self.w, self.img = world, img
        self.d = ImageDraw.Draw(img)
        self.x0, self.y0, x1, y1 = box
        self.W, self.H = x1 - self.x0, y1 - self.y0
        self.labels, self.robot = labels, robot
        self.tags: list[tuple[str, tuple, tuple]] = []   # (text, (cx, top_y), color)

    def P(self, fx, fy):
        return self.x0 + fx * self.W, self.y0 + fy * self.H

    def paste(self, name, cx, base, fw=None, fh=None, scale=1.0, rotate=None):
        """Draw a sprite bottom-centred at (cx, base); returns its box in cell fractions."""
        sw, sh = size_of(name)
        fw, fh = (fw or sw) * scale, (fh or sh) * scale
        pw, ph = max(1, round(fw * self.W)), max(1, round(fh * self.H))
        im = sprite(name, pw, ph)
        if rotate:
            im = im.rotate(rotate, expand=True)
        x, y = self.P(cx, base)
        self.img.alpha_composite(im, (round(x - im.width / 2), round(y - im.height)))
        return (cx - fw / 2, base - fh, cx + fw / 2, base)

    def tag(self, text, cx, y, color=(0, 0, 0)):
        if self.labels:
            self.tags.append((text, (cx, y), color))

    # ------------------------------------------------------------ background
    def background(self, floor: bool):
        self.d.rectangle([*self.P(0, 0), *self.P(1, 1)], fill=WALL)
        if floor:
            self.d.rectangle([*self.P(0, 0.5), *self.P(1, 1)], fill=FLOOR)
            for i in range(1, 4):
                self.d.line([*self.P(i / 4, 0.5), *self.P(i / 4, 1)], fill=FLOOR_LINE, width=1)

    # ------------------------------------------------------------ rows of things
    def row(self, things, x0, x1, base, scale=1.0, hidden_ok=False, max_h=None):
        things = [t for t in things if hidden_ok or self.w.is_visible(t)]
        if not things:
            return
        names = [sprite_name(self.w, t) for t in things]
        scales = [min(scale, max_h / size_of(n)[1]) if max_h else scale for n in names]
        widths = [size_of(n)[0] * s for n, s in zip(names, scales)]
        total = sum(widths)
        span = x1 - x0
        if total > span * 0.95:
            k = span * 0.95 / total
            scales = [s * k for s in scales]
            widths = [w * k for w in widths]
            total = sum(widths)
        gap = (span - total) / (len(things) + 1)
        x = x0 + gap
        for t, n, w, s in zip(things, names, widths, scales):
            self.thing(t, n, x + w / 2, base, s)
            x += w + gap

    def thing(self, t, name, cx, base, scale=1.0):
        """Draw a thing and whatever rests on it."""
        box = self.paste(name, cx, base, scale=scale)
        if t.kind == "person":
            self.tag(t.id, cx, box[1] - 0.05, (40, 60, 150))
        else:
            self.tag(label_of(t), cx, box[1] - 0.04, (20, 20, 20))
        on_top = self.w.children(t, Relation.ON)
        if on_top:
            width = max(box[2] - box[0], 0.3)
            self.row(on_top, cx - width / 2, cx + width / 2, box[1], scale * 0.9)
        return box

    def lock_marks(self, t, keyhole_xy, padlock_xy):
        if getattr(t, "lock_type", "none") == "key":
            self.paste("keyhole", keyhole_xy[0], keyhole_xy[1] + 0.025)
            k = t.inserted_key(self.w) if hasattr(t, "inserted_key") else None
            if k is not None:
                self.paste("key_in_lock", keyhole_xy[0] + 0.07, keyhole_xy[1] + 0.025)
        if getattr(t, "locked", False):
            self.paste("padlock", *padlock_xy)

    # ------------------------------------------------------------ the cell
    def cell(self, cell):
        w = self.w
        here = w.things_at(cell)
        fixtures = [t for t in here if t.kind in ("counter", "table")]
        self.background(floor=not any(t.kind == "counter" for t in fixtures))
        high = [t for t in here if t.loc.level is Level.HIGH]
        low = [t for t in here if t.loc.level is Level.LOW]

        for t in high:
            if t.kind == "cabinet":
                if t.is_open:
                    self.paste("cabinet_open", 0.5, 0.38)
                    self.row(w.children(t, Relation.IN), 0.16, 0.84, 0.325, 0.8, max_h=0.13)
                else:
                    self.paste("cabinet_closed", 0.5, 0.35)
                    self.lock_marks(t, (0.5, 0.29), (0.5, 0.33))
                self.tag(label_of(t), 0.5, 0.06)
            elif t.kind == "shelf":
                self.paste("shelf", 0.5, 0.34)
                self.tag(t.id, 0.5, 0.36)
                self.row(w.children(t, Relation.ON), 0.1, 0.9, 0.30)
            else:
                self.thing(t, sprite_name(w, t), 0.5, 0.45)

        counters = [t for t in low if t.kind == "counter"]
        tables = [t for t in low if t.kind == "table"]
        drawers = [t for t in low if t.kind == "drawer"]
        rest = [t for t in low if t not in counters + tables + drawers]
        for t in counters:
            self.paste("counter", 0.5, 1.0)
        for t in drawers:
            if t.is_open:
                self.paste("drawer_open", 0.5, 0.95)
                for it in w.children(t, Relation.IN):
                    n = sprite_name(w, it)
                    h = size_of(n)[1]
                    s = max(1.0, (0.80 - 0.44) / h) if it.protruding else 0.6
                    self.paste(n, 0.4 if it.protruding else 0.62, 0.80, scale=s)
                    self.tag(it.id, 0.4 if it.protruding else 0.62, 0.80 - h * s - 0.04, (120, 20, 20))
                self.lock_marks(t, (0.5, 0.905), (0.78, 0.93))
                self.tag(label_of(t), 0.5, 0.965)
            else:
                self.paste("drawer_closed", 0.5, 0.90)
                self.lock_marks(t, (0.5, 0.79), (0.78, 0.83))
                self.tag(label_of(t), 0.5, 0.94)
        for t in counters:          # keep things on the counter below the wall cabinets
            self.row(w.children(t, Relation.ON), 0.04, 0.96, 0.50, 0.85, max_h=0.13)
        for t in tables:
            self.paste("table", 0.5, 0.97)
            self.tag(t.id, 0.5, 0.80)
            self.row(w.children(t, Relation.ON), 0.06, 0.94, 0.685)
        floor_things = [t for t in rest if t.kind != "door"]
        if floor_things:
            self.row(floor_things, 0.03, 0.97, 0.975)

        r = w.robot
        if self.robot and r.cell == tuple(cell):
            cy = 0.25 if r.level is Level.HIGH else 0.72
            if r.docked:
                cy = 0.70
            angle = {Direction.N: 0, Direction.W: 90, Direction.S: 180, Direction.E: 270}[r.facing]
            self.paste("spot", 0.5, cy + 0.21, rotate=angle)
            text = f"SPOT {r.facing.value}" + (" docked" if r.docked else "")
            self.tag(text, 0.5, cy + 0.255)
            if r.holding is not None and not r.holding_fixed:
                n = sprite_name(w, r.holding)
                hw, hh = size_of(n)
                s = min(1.0, 0.3 / max(hw, hh))
                self.paste(n, 0.84, cy + 0.2, scale=s)
            if r.holding is not None:
                self.tag(f"holding {r.holding.id}" + (" (fixed)" if r.holding_fixed else ""), 0.5, cy - 0.25, (120, 0, 120))

    def wall_view(self, door):
        """What the camera sees when facing the outer wall (with a door in it, or not)."""
        self.background(floor=True)
        if door is None:
            return
        if door.is_open:
            self.paste("door_open", 0.5, 0.98)
            self.row(self.w.children(door, Relation.IN), 0.25, 0.75, 0.98)
        else:
            self.paste("door_closed", 0.5, 0.98)
            self.lock_marks(door, (0.68, 0.60), (0.68, 0.70))

    # ------------------------------------------------------------ tags
    def draw_tags(self, px: int):
        f = font(px, True)
        placed: list[tuple] = []
        for text, (fx, fy), color in self.tags:
            x, y = self.P(fx, fy)
            bb = self.d.textbbox((x, y), text, font=f, anchor="mm")
            wdt, hgt = bb[2] - bb[0] + 6, bb[3] - bb[1] + 4
            x = min(max(x, self.x0 + wdt / 2 + 1), self.x0 + self.W - wdt / 2 - 1)
            y = min(max(y, self.y0 + hgt / 2 + 1), self.y0 + self.H - hgt / 2 - 1)
            for _ in range(8):
                rect = (x - wdt / 2, y - hgt / 2, x + wdt / 2, y + hgt / 2)
                hit = next((p for p in placed if not (rect[2] < p[0] or rect[0] > p[2] or rect[3] < p[1] or rect[1] > p[3])), None)
                if hit is None:
                    break
                y = hit[3] + hgt / 2 + 1
                if y + hgt / 2 > self.y0 + self.H:
                    y = hit[1] - hgt / 2 - 1
            rect = (x - wdt / 2, y - hgt / 2, x + wdt / 2, y + hgt / 2)
            placed.append(rect)
            self.d.rounded_rectangle(rect, 3, fill=(255, 255, 255), outline=color, width=1)
            self.d.text((x, y), text, font=f, fill=color, anchor="mm")


# ---------------------------------------------------------------- public API
def render_cell(world, cell, size=200, labels=True, robot=True) -> Image.Image:
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    p = CellPainter(world, img, (0, 0, size, size), labels, robot)
    p.cell(cell)
    p.draw_tags(max(9, size // 17))
    return img


def render_photo(world, size: int = 256) -> Image.Image:
    """The gripper-camera view of the cell in front of the robot: plain picture, no text."""
    r = world.robot
    target = r.facing_cell()
    img = Image.new("RGBA", (size, size), (255, 255, 255, 255))
    p = CellPainter(world, img, (0, 0, size, size), labels=False, robot=False)
    if world.in_bounds(target):
        p.cell(target)
    else:
        door = next((t for t in world.things.values() if t.kind == "door" and t.loc.cell == r.cell
                     and getattr(t, "side", None) == r.facing), None)
        p.wall_view(door)
    return img.convert("RGB")


def render_grid(world, cell_px: int = 140, margin: int = 90, labels: bool = True) -> Image.Image:
    """The whole lab as seen in the window (without the side panel)."""
    W, H = world.width, world.height
    img = Image.new("RGBA", (margin * 2 + W * cell_px, margin * 2 + H * cell_px), (245, 244, 240, 255))
    d = ImageDraw.Draw(img)
    for y in range(H):
        for x in range(W):
            box = (margin + x * cell_px, margin + y * cell_px, margin + (x + 1) * cell_px, margin + (y + 1) * cell_px)
            p = CellPainter(world, img, box, labels, robot=True)
            p.cell((x, y))
            d.rectangle(box, outline=(150, 150, 150))
            d.text((box[2] - 3, box[3] - 2), f"{x},{y}", font=font(10), fill=(120, 120, 120), anchor="rd")
            p.draw_tags(max(9, cell_px // 16))
    d.rectangle([margin, margin, margin + W * cell_px, margin + H * cell_px], outline=(25, 25, 25), width=5)
    for t in world.things.values():
        if t.kind == "door":
            _draw_door(world, d, img, t, margin, cell_px, labels)
    return img


def _draw_door(world, d, img, door, margin, cp, labels):
    (cx, cy), side = door.loc.cell, door.side
    x0, y0 = margin + cx * cp, margin + cy * cp
    a, b = 0.2 * cp, 0.8 * cp
    if side in (Direction.W, Direction.E):
        ex = x0 if side is Direction.W else x0 + cp
        p0, p1 = (ex, y0 + a), (ex, y0 + b)
        out = -1 if side is Direction.W else 1
    else:
        ey = y0 if side is Direction.N else y0 + cp
        p0, p1 = (x0 + a, ey), (x0 + b, ey)
        out = -1 if side is Direction.N else 1
    vertical = side in (Direction.W, Direction.E)
    d.line([p0, p1], fill=(245, 244, 240), width=9)
    if door.is_open:
        leaf_end = (p0[0] + out * 0.45 * cp, p0[1] + 0.2 * cp) if vertical else (p0[0] + 0.2 * cp, p0[1] + out * 0.45 * cp)
        d.line([p0, leaf_end], fill=(120, 82, 48), width=7)
    else:
        color = (90, 60, 35) if door.locked else (176, 128, 82)
        r = [min(p0[0], p1[0]) - 6, min(p0[1], p1[1]) - 6, max(p0[0], p1[0]) + 6, max(p0[1], p1[1]) + 6]
        if vertical:
            r = [p0[0] - 7, p0[1], p0[0] + 7, p1[1]]
        else:
            r = [p0[0], p0[1] - 7, p1[0], p0[1] + 7]
        d.rectangle(r, fill=color, outline=DARK, width=2)
    if labels:
        st = "OPEN" if door.is_open else ("LOCKED" if door.locked else "closed")
        k = door.inserted_key(world)
        text = f"{door.id}\n{st}" + (f"\nkey: {k.id}" if k else "")
        doorway = world.children(door, Relation.IN)
        if doorway:
            text += "\nin doorway:\n" + "\n".join(t.id for t in doorway)
        mx, my = (p0[0] + p1[0]) / 2, (p0[1] + p1[1]) / 2
        if vertical:
            pos, anchor = (mx + out * 12, my), ("rm" if out < 0 else "lm")
        else:
            pos, anchor = (mx + 0.35 * cp, my + out * 30), "mm"
        d.multiline_text(pos, text, font=font(11, True), fill=DARK, anchor=anchor,
                         align="right" if anchor == "rm" else "left")
