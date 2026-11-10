"""Play the lab with the keyboard.

    python -m gridlab.play                         # default lab
    python -m gridlab.play --seed 3 --difficulty 3 # random lab
    python -m gridlab.play --scenario lab.yaml --verbose

Keys
    arrows      face that way; press again to step forward (on a stool / docked: turn only)
    1-9         run the numbered action from the menu        PgUp/PgDn  more of the menu
    g           menu: go to an object                        a          menu: actions here (default)
    p           take a photo (shown in the panel)
    :  or Enter type any command, e.g.  put_on book_1 light_button   /  go_to 3 3 W
    o           let the oracle solve the lab (any key stops it)
    r           restart                                      q / Esc    quit
"""
from __future__ import annotations

import argparse
import copy
import shlex

from .render.commands import goto_commands, suggested_commands
from .render.panel import UIState, render_frame

HELP = "arrows move | 1-9 menu | g go-to | a actions | p photo | : command | o oracle | r restart | q quit"


def parse_command(text: str):
    parts = shlex.split(text)
    if not parts:
        return None
    args = [int(p) if p.lstrip("-").isdigit() else p for p in parts[1:]]
    return parts[0], args


class Game:
    """Keyboard-independent game logic (also used by the tests)."""

    def __init__(self, factory, title=""):
        self.factory = factory
        self.title = title
        self.restart()

    def restart(self):
        self.world = self.factory()
        self.ui = UIState(title=self.title or self.world.scenario_name, help=HELP)
        self.plan: list = []
        self.show_actions()

    def run(self, name, args):
        resp = self.world.execute(name, args)
        if "data" in resp and "image_png_base64" in resp["data"]:
            resp = {**resp, "data": {k: v for k, v in resp["data"].items() if k != "image_png_base64"}}
        self.ui.last = resp
        self.ui.message = ""
        if self.ui.menu_title.startswith("ACTIONS"):
            self.show_actions()
        return resp

    def show_actions(self):
        self.ui.menu_title, self.ui.menu, self.ui.page = "ACTIONS (a)", suggested_commands(self.world), 0

    def show_goto(self):
        self.ui.menu_title, self.ui.menu, self.ui.page = "GO TO (g)", goto_commands(self.world), 0

    def choose(self, n: int):
        items = self.ui.page_items()
        if 1 <= n <= len(items):
            name, args = items[n - 1]
            self.run(name, list(args))
            if name == "go_to":
                self.show_actions()

    def arrow(self, d: str):
        r = self.world.robot
        if r.level.value == "high" or r.docked or r.facing.value != d:
            return self.run("turn", [d])
        from .core.geometry import Direction, step
        nx = step(r.cell, Direction(d))
        return self.run("go_to", [nx[0], nx[1], d])

    def console_submit(self, text: str):
        try:
            cmd = parse_command(text)
        except ValueError as e:
            self.ui.message = f"cannot parse: {e}"
            return
        if cmd:
            self.run(*cmd)

    def start_oracle(self):
        from .tasks.oracle import OracleFailed, solve
        sim = copy.deepcopy(self.world)
        start = len(sim.history)
        try:
            solve(sim)
        except OracleFailed as e:
            self.ui.message = f"oracle failed: {str(e).splitlines()[0]}"
            return
        self.plan = [(h["action"], h["args"]) for h in sim.history[start:]]
        self.ui.message = f"oracle: {len(self.plan)} actions (any key stops)"

    def oracle_step(self):
        if self.plan:
            self.run(*self.plan.pop(0))

    def frame(self):
        return render_frame(self.world, self.ui)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m gridlab.play")
    ap.add_argument("--scenario", help="YAML file (default: the default lab)")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--difficulty", type=int, default=2)
    ap.add_argument("--verbose", action="store_true", help="show the detailed cause of failures")
    a = ap.parse_args(argv)

    import os
    os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
    import pygame

    from .scenarios import build_default_lab, build_world, load_scenario
    from .scenarios.generator import generate_spec

    def factory():
        if a.scenario:
            w = load_scenario(a.scenario)
        elif a.seed is not None:
            w = build_world(generate_spec(a.seed, a.difficulty))
        else:
            w = build_default_lab()
        w.config.verbose_failures = w.config.verbose_failures or a.verbose
        return w

    game = Game(factory)
    pygame.display.init()
    pygame.display.set_caption("gridlab")
    img = game.frame()
    screen = pygame.display.set_mode(img.size)
    clock = pygame.time.Clock()
    pygame.key.set_repeat(300, 60)
    dirty, last_oracle = True, 0
    arrows = {pygame.K_UP: "N", pygame.K_DOWN: "S", pygame.K_LEFT: "W", pygame.K_RIGHT: "E"}

    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                running = False
            elif ev.type == pygame.KEYDOWN:
                dirty = True
                if game.plan and ev.key != pygame.K_o:
                    game.plan = []
                    game.ui.message = "oracle stopped"
                    continue
                if game.ui.console is not None:
                    if ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                        text, game.ui.console = game.ui.console, None
                        game.console_submit(text)
                    elif ev.key == pygame.K_ESCAPE:
                        game.ui.console = None
                    elif ev.key == pygame.K_BACKSPACE:
                        game.ui.console = game.ui.console[:-1]
                    continue
                if ev.key in arrows:
                    game.arrow(arrows[ev.key])
                elif ev.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    game.ui.console = ""
                elif ev.key == pygame.K_PAGEDOWN:
                    game.ui.page = min(game.ui.page + 1, max(0, (len(game.ui.menu) - 1) // UIState.PAGE))
                elif ev.key == pygame.K_PAGEUP:
                    game.ui.page = max(0, game.ui.page - 1)
                elif ev.key == pygame.K_ESCAPE:
                    running = False
            elif ev.type == pygame.TEXTINPUT:
                dirty = True
                ch = ev.text
                if game.ui.console is not None:
                    game.ui.console += ch
                    continue
                if ch.isdigit() and ch != "0":
                    game.choose(int(ch))
                elif ch == ":":
                    game.ui.console = ""
                elif ch == "g":
                    game.show_goto()
                elif ch == "a":
                    game.show_actions()
                elif ch == "p":
                    game.run("take_photo", [])
                elif ch == "o":
                    game.start_oracle()
                elif ch == "r":
                    game.restart()
                elif ch == "q":
                    running = False
        if game.plan and pygame.time.get_ticks() - last_oracle > 350:
            game.oracle_step()
            last_oracle = pygame.time.get_ticks()
            dirty = True
        if dirty:
            img = game.frame()
            if img.size != screen.get_size():
                screen = pygame.display.set_mode(img.size)
            screen.blit(pygame.image.frombytes(img.tobytes(), img.size, "RGB"), (0, 0))
            pygame.display.flip()
            dirty = False
        clock.tick(30)
    pygame.quit()


if __name__ == "__main__":
    main()
