"""The window frame: grid view on the left, status panel on the right."""
from __future__ import annotations

from dataclasses import dataclass, field

from PIL import Image, ImageDraw

from .commands import fmt
from .scene import font, render_grid

PANEL_W = 440
BG, INK, MUTED = (255, 255, 255), (30, 30, 35), (110, 110, 120)
OK_C, BAD_C, ACCENT = (20, 130, 60), (200, 30, 30), (40, 70, 170)


@dataclass
class UIState:
    title: str = ""
    last: dict | None = None                  # last execute() response
    menu_title: str = ""
    menu: list = field(default_factory=list)  # [(name, args)]
    page: int = 0
    console: str | None = None                # text being typed, None if console closed
    message: str = ""
    help: str = ""

    PAGE = 9

    def page_items(self):
        start = self.page * self.PAGE
        return self.menu[start:start + self.PAGE]


def render_frame(world, ui: UIState, cell_px: int = 140) -> Image.Image:
    grid = render_grid(world, cell_px=cell_px)
    H = max(grid.height, 760)
    img = Image.new("RGB", (grid.width + PANEL_W, H), (245, 244, 240))
    img.paste(grid.convert("RGB"), (0, 0))
    d = ImageDraw.Draw(img)
    x0 = grid.width
    d.rectangle([x0, 0, x0 + PANEL_W, H], fill=BG)
    d.line([x0, 0, x0, H], fill=(180, 180, 180), width=2)
    x, y = x0 + 16, 12
    f, fb, fs = font(14), font(14, True), font(12)

    def line(text, fnt=f, color=INK, dy=19, indent=0):
        nonlocal y
        d.text((x + indent, y), text, font=fnt, fill=color)
        y += dy

    line(ui.title or world.scenario_name, font(16, True), dy=24)
    r = world.robot.public_state()
    lamps = [t for t in world.things.values() if t.kind == "lamp"]
    line(f"step {world.step_count}   light: {'ON' if lamps and all(l.on for l in lamps) else 'off'}", f, MUTED)
    line(f"spot at {tuple(r['cell'])} {r['level'].upper()} facing {r['facing']}"
         + ("  [docked]" if r["docked"] else "") + (f"  on {r['standing_on']}" if r["standing_on"] else ""))
    held = r["holding"] or "-"
    line(f"holding: {held}" + ("  (fixed in place)" if r["holding_fixed"] else ""))
    y += 6

    goal = world.check_goal()
    line("GOAL" + ("  - ACHIEVED" if goal.get("achieved") else ""), fb, OK_C if goal.get("achieved") else INK)
    for k, v in goal.get("conditions", {}).items():
        line(("[x] " if v else "[ ] ") + k.replace("_", " "), fs, OK_C if v else INK, 17, 8)
    y += 6

    line("LAST ACTION", fb)
    if ui.last:
        L = ui.last
        line(fmt((L["action"], L["args"])), fs, INK, 17, 8)
        if L["ok"]:
            line("OK", fb, OK_C, 18, 8)
        else:
            line(f"FAILED {L['code']}: {L['msg']}"[:60], fs, BAD_C, 17, 8)
            if L.get("detail"):
                line(f"({L['detail']})"[:60], fs, BAD_C, 17, 8)
        for e in L.get("events", [])[:5]:
            txt = e["type"] + " " + " ".join(f"{k}={v}" for k, v in e.items() if k != "type")
            line(txt[:62], fs, MUTED, 16, 8)
    else:
        line("-", fs, MUTED, 17, 8)
    if ui.message:
        line(ui.message[:62], fs, ACCENT, 17, 8)
    y += 6

    pages = max(1, (len(ui.menu) + ui.PAGE - 1) // ui.PAGE)
    line(f"{ui.menu_title}  ({ui.page + 1}/{pages}, PgUp/PgDn)" if pages > 1 else ui.menu_title, fb)
    for i, cmd in enumerate(ui.page_items(), 1):
        line(f"{i}  {fmt(cmd)}"[:56], fs, ACCENT, 17, 8)
    y += 6

    if world.last_photo is not None:
        ph = world.last_photo.resize((150, 150))
        if y + 170 < H - 70:
            line("LAST PHOTO", fb)
            img.paste(ph, (x + 8, y))
            d.rectangle([x + 8, y, x + 158, y + 150], outline=INK)
            y += 158

    if ui.console is not None:
        d.rectangle([x0 + 8, H - 66, x0 + PANEL_W - 8, H - 40], outline=ACCENT, width=2)
        d.text((x0 + 14, H - 61), "> " + ui.console + "_", font=f, fill=INK)
    words, lines_, cur = ui.help.split(" | "), [], ""
    for wd in words:
        if len(cur) + len(wd) > 58:
            lines_.append(cur)
            cur = ""
        cur += (" | " if cur else "") + wd
    lines_.append(cur)
    for i, t in enumerate(lines_[-2:]):
        d.text((x0 + 12, H - 34 + i * 15), t, font=font(11), fill=MUTED)
    return img
