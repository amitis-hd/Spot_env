"""Step 4: rendering, photos and the keyboard game logic."""
import base64
import io
import os

from PIL import Image

from gridlab.play import Game, parse_command
from gridlab.render.commands import suggested_commands
from gridlab.render.scene import render_grid, render_photo
from gridlab.render.sprites import SIZES, make_sprites
from gridlab.scenarios import build_default_lab, build_world
from gridlab.scenarios.generator import generate_spec


def colours(img, box=None):
    return {c for _, c in (img.crop(box) if box else img).convert("RGB").getcolors(1 << 20)}


def test_sprites_regenerate(tmp_path):
    paths = make_sprites(tmp_path)
    assert len(paths) == len(SIZES) and all(p.stat().st_size > 0 for p in paths)


def test_take_photo_returns_png_of_cell_in_front():
    w = build_default_lab()
    r = w.execute("take_photo")
    assert r["ok"] and r["data"]["of_cell"] == [1, 0] and r["data"]["width"] == 256
    img = Image.open(io.BytesIO(base64.b64decode(r["data"]["image_png_base64"])))
    assert img.size == (256, 256)
    assert (60, 90, 170) in colours(img)                  # the blue binder sticking out of drawer_2


def test_photo_has_no_text_and_hides_closed_contents():
    w = build_default_lab()
    # cabinet_2 holds key_door but is closed: no gold key pixels in the photo
    gold = (225, 185, 40)
    assert gold not in colours(render_photo(w))
    w.things["cabinet_2"].is_open = True
    assert gold in colours(render_photo(w))


def test_photo_of_wall_and_door():
    w = build_default_lab()
    w.execute("go_to", ["door_1"])
    wood = (176, 128, 82)
    assert wood in colours(render_photo(w))
    w.execute("turn", ["S"])                              # (0,3) floor, empty
    assert wood not in colours(render_photo(w))


def test_photo_size_config():
    w = build_default_lab()
    w.config.photo_size = 128
    assert w.execute("take_photo")["data"]["width"] == 128


def test_grid_renders_every_random_lab():
    for d in range(5):
        img = render_grid(build_world(generate_spec(d, d)))
        assert img.size == (2 * 90 + 4 * 140,) * 2


def test_game_logic_and_menus():
    g = Game(build_default_lab)
    assert ("close", ["drawer_2"]) in g.ui.menu
    g.choose(g.ui.menu.index(("close", ["drawer_2"])) + 1)
    assert g.ui.last["code"] == "OBSTRUCTED"
    g.arrow("E")                                          # turn
    assert g.world.robot.facing.value == "E"
    g.arrow("E")                                          # step forward
    assert g.world.robot.cell == (2, 1)
    g.show_goto()
    assert ("go_to", ["dock_1"]) in g.ui.menu
    g.console_submit("go_to 3 3 W")
    assert g.ui.last["code"] == "NO_ACCESS"                # the dock is there
    g.console_submit("go_to 3 0 W")
    assert g.world.robot.cell == (3, 0)
    g.console_submit("put_on book_1 light_button")
    assert g.ui.last["code"] == "NOT_HOLDING"
    g.console_submit('say "unbalanced')                    # parse error is reported, not raised
    assert "cannot parse" in g.ui.message
    assert parse_command("go_to 1 -2 N") == ("go_to", [1, -2, "N"])
    g.run("take_photo", [])
    assert "image_png_base64" not in g.ui.last.get("data", {})
    assert g.frame().size[0] > 1000


def test_game_oracle_playback():
    g = Game(build_default_lab)
    g.start_oracle()
    assert g.plan and g.world.step_count == 0             # planned on a copy
    while g.plan:
        g.oracle_step()
    assert g.world.check_goal()["achieved"]


def test_suggestions_when_holding_key_in_lock():
    w = build_default_lab()
    for a in [("go_to", ["counter_3"]), ("pick_up", ["key_drawer1"]), ("go_to", ["drawer_1"]),
              ("insert_key", ["drawer_1"])]:
        assert w.execute(*a)["ok"]
    cmds = suggested_commands(w)
    assert ("release", []) in cmds and ("turn_key", ["drawer_1"]) in cmds and ("put_down", []) not in cmds


def test_pygame_window_smoke(monkeypatch):
    os.environ["SDL_VIDEODRIVER"] = "dummy"
    import pygame
    from gridlab import play
    events = [[pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RIGHT)],
              [pygame.event.Event(pygame.TEXTINPUT, text="p")],
              [pygame.event.Event(pygame.QUIT)]]
    monkeypatch.setattr(pygame.event, "get", lambda: events.pop(0) if events else [pygame.event.Event(pygame.QUIT)])
    play.main([])
