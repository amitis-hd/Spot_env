"""Step 5: protocol, session/episodes, logging, and a real socket round trip."""
import copy
import json
import socket
import threading

import pytest

from gridlab.client import GridlabClient
from gridlab.scenarios import build_world, read_spec, DEFAULT_LAB
from gridlab.scenarios.generator import generate_spec
from gridlab.server import GridlabServer, ServerOptions, Session, episode_specs, parse_line
from gridlab.tasks.oracle import solve


def oracle_commands(spec):
    w = build_world(copy.deepcopy(spec))
    solve(w)
    return [" ".join([h["action"], *map(str, h["args"])]) for h in w.history]


def test_parse_line():
    assert parse_line("put_on book_1 light_button") == ("put_on", ["book_1", "light_button"])
    assert parse_line("GO_TO 3 0 W") == ("go_to", [3, 0, "W"])
    assert parse_line('{"action": "pick_up", "args": ["pen_1"]}') == ("pick_up", ["pen_1"])
    assert parse_line('{"command": "SENSE_ALL"}') == ("sense_all", [])


def test_envelope_matches_ng2_style(tmp_path):
    s = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path)))
    r = s.handle("close drawer_2")
    assert set(r) >= {"goal", "command_result", "step", "gameOver"}
    assert r["goal"]["goalType"] == "CLOSE_LAB" and r["goal"]["goalAchieved"] is False
    assert r["goal"]["Distribution"] == "Uninformed"
    assert r["command_result"] == {"command": "close", "argument": "drawer_2", "result": "FAIL",
                                   "message": "drawer_2 cannot close", "stepCost": 1.0, "code": "OBSTRUCTED"}
    assert r["step"] == 1 and r["gameOver"] is False
    bad = s.handle('say "hello')
    assert bad["command_result"]["command"] == "WRONG_CMD" and bad["command_result"]["message"] == "Invalid Command"
    unknown = s.handle("fly")
    assert unknown["command_result"]["code"] == "UNKNOWN_ACTION"


def test_queries_cost_nothing(tmp_path):
    s = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path)))
    r = s.handle("SENSE_ALL")
    assert r["command_result"]["stepCost"] == 0 and r["step"] == 0
    assert "key_door" not in {o["id"] for o in r["world"]["objects"]}
    assert s.handle("sense_robot")["robot"]["cell"] == [1, 1]
    assert s.handle("sense_object lamp_1")["object"]["state"] == {"on": False}
    assert s.handle("sense_object key_door")["command_result"]["code"] == "UNKNOWN_OBJECT"
    assert s.handle("sense_object")["command_result"]["code"] == "BAD_ARGS"
    assert "drawer_1" in {o["id"] for o in s.handle("sense_visible")["visible"]}
    docs = s.handle("list_actions")
    assert "turn_key" in docs["actions"] and "sense_all" in docs["queries"]
    assert s.world.step_count == 0


def test_photos_inline_and_file(tmp_path):
    s = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path), photo_mode="both"))
    p = s.handle("take_photo")["photo"]
    assert p["image_png_base64"] and p["of_cell"] == [1, 0]
    assert open(p["path"], "rb").read(4) == b"\x89PNG"
    s2 = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path), photo_mode="file"))
    assert "image_png_base64" not in s2.handle("take_photo")["photo"]
    log = (s.run_dir / "episode_000.jsonl").read_text()
    assert "image_png_base64" not in log                   # logs keep only the file path


def test_full_episode_game_over_reset_and_summary(tmp_path):
    specs = episode_specs([str(DEFAULT_LAB)], random_n=1, difficulties=[1], seed=5)
    s = Session(specs, ServerOptions(log_dir=str(tmp_path)))
    plan = oracle_commands(specs[0])
    assert s.episode.oracle_steps == len(plan)
    for cmd in plan:
        r = s.handle(cmd)
    assert r["goal"]["goalAchieved"] and r["gameOver"]
    assert s.handle("pick_up pen_1")["command_result"]["code"] == "GAME_OVER"
    assert s.handle("sense_robot")["command_result"]["result"] == "SUCCESS"      # queries still work
    r = s.handle("RESET")
    assert r["episode"] == 1 and r["world"]["robot"]
    s.handle("pick_up nothing")
    r = s.handle("reset")
    assert r["allDone"] and [x["ended_by"] for x in r["summary"]] == ["goal", "reset"]
    summary = json.loads((s.run_dir / "summary.json").read_text())
    assert summary[0]["achieved"] and summary[0]["actions"] == summary[0]["oracle_actions"] == len(plan)
    assert summary[1]["failure_codes"] == {"UNKNOWN_OBJECT": 1} and summary[1]["difficulty"] == 1
    assert (s.run_dir / "summary.csv").read_text().startswith("episode,scenario")
    assert (s.run_dir / "episode_001.yaml").exists()
    assert s.handle("pick_up x")["command_result"]["code"] == "GAME_OVER"


def test_max_steps_ends_episode(tmp_path):
    s = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path), max_steps=3))
    for _ in range(3):
        r = s.handle("turn E")
    assert r["gameOver"] and s.summaries[0]["ended_by"] == "max_steps"


def test_goal_conditions_can_be_hidden(tmp_path):
    s = Session(episode_specs(), ServerOptions(log_dir=None, goal_conditions=False, oracle_baseline=False))
    assert "conditions" not in s.handle("check_goal")["goal"]


def test_socket_round_trip_with_oracle_plan(tmp_path):
    spec = generate_spec(3, 3)
    session = Session([spec], ServerOptions(log_dir=str(tmp_path), verbose_failures=True))
    server = GridlabServer(session, port=0, quiet=True)
    th = threading.Thread(target=server.serve, daemon=True)
    th.start()
    with GridlabClient(port=server.port) as c:
        assert c.send("SENSE_ALL")["world"]["grid"] == {"width": 4, "height": 4, "levels": ["low", "high"]}
        # several commands in one packet are each answered
        c.sock.sendall(b"sense_robot\r\nsense_robot\n")
        assert c.recv()["robot"] == c.recv()["robot"]
        assert c.send("check_goal")["goal"]["goalAchieved"] is False
        for cmd in oracle_commands(spec):
            r = c.send(cmd)
            assert r["command_result"]["result"] == "SUCCESS" or r["command_result"]["code"] in ("OBSTRUCTED",), r
        assert r["goal"]["goalAchieved"] and r["gameOver"]
        assert c.send("RESET")["allDone"]
    th.join(timeout=5)
    assert not th.is_alive()
    assert session.summaries[0]["achieved"]


def test_server_survives_client_reconnect(tmp_path):
    session = Session(episode_specs(), ServerOptions(log_dir=str(tmp_path), oracle_baseline=False))
    server = GridlabServer(session, port=0, quiet=True)
    th = threading.Thread(target=server.serve, daemon=True)
    th.start()
    with GridlabClient(port=server.port) as c:
        c.send("turn E")
    with GridlabClient(port=server.port) as c:
        assert c.send("sense_robot")["robot"]["facing"] == "E"      # same episode continues
        c.send("quit")
    th.join(timeout=5)
    assert not th.is_alive()
