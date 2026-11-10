"""One evaluation session: a list of episodes (scenarios), command handling, logging, metrics.

Protocol (same style as gym-novel-gridworlds2 / Polycraft, so DIARC's socket code carries over):
the client sends one text command per line; every command gets exactly one JSON line back.

    pick_up book_1                ->  {"goal": {...}, "command_result": {...}, "step": 7, "gameOver": false, ...}
    put_on book_1 light_button
    go_to 3 0 W
    SENSE_ALL                      (query: costs nothing, does not advance the step counter)

A JSON line also works: {"action": "put_on", "args": ["book_1", "light_button"]}.
"""
from __future__ import annotations

import base64
import copy
import csv
import json
import shlex
import time
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from ..core import WorldConfig
from ..core.errors import ActionFailure
from ..scenarios import build_world, read_spec, spec_to_yaml

QUERIES = {
    "sense_all": "everything the robot knows: robot + all known objects",
    "sense_robot": "the robot's pose, gripper and dock state",
    "sense_object": "sense_object <id>: one known object",
    "sense_visible": "known objects that are currently visible (not inside closed containers)",
    "check_goal": "goal status",
    "list_actions": "every action and query with a one-line description",
    "reset": "end this episode and start the next one",
    "quit": "end the session",
}


@dataclass
class ServerOptions:
    max_steps: int = 300                 # an episode ends (gameOver) after this many actions
    action_cost: float = 1.0
    photo_cost: float = 1.0
    photo_mode: str = "inline"           # inline (base64 in the response) | file (path only) | both
    goal_conditions: bool = True         # include the per-condition breakdown in "goal"
    verbose_failures: bool | None = None  # override the scenario's setting
    log_dir: str | None = "runs"
    oracle_baseline: bool = True


@dataclass
class Episode:
    index: int
    spec: dict
    world: object = None
    started: float = 0.0
    ended_by: str | None = None
    queries: int = 0
    failures: Counter = field(default_factory=Counter)
    photos: int = 0
    cost: float = 0.0
    oracle_steps: int | None = None


def parse_line(line: str) -> tuple[str, list]:
    """'put_on book_1 light_button' or '{"action": ..., "args": [...]}' -> (name, args)."""
    line = line.strip()
    if line.startswith("{"):
        msg = json.loads(line)
        if "command" in msg:
            return parse_line(msg["command"])
        return str(msg["action"]).lower(), list(msg.get("args", []))
    parts = shlex.split(line)
    if not parts:
        raise ValueError("empty command")
    args = [int(p) if p.lstrip("-").isdigit() else p for p in parts[1:]]
    return parts[0].lower(), args


class Session:
    def __init__(self, specs: list[dict], options: ServerOptions | None = None):
        if not specs:
            raise ValueError("no scenarios")
        self.specs = specs
        self.opt = options or ServerOptions()
        self.episode: Episode | None = None
        self.summaries: list[dict] = []
        self.done = False
        self.run_dir = None
        if self.opt.log_dir:
            self.run_dir = Path(self.opt.log_dir) / time.strftime("%Y%m%d-%H%M%S")
            n = 1
            while self.run_dir.exists():
                n += 1
                self.run_dir = Path(self.opt.log_dir) / (time.strftime("%Y%m%d-%H%M%S") + f"-{n}")
            (self.run_dir / "photos").mkdir(parents=True)
        self._start(0)

    # ------------------------------------------------------------------ episodes
    @property
    def world(self):
        return self.episode.world

    def _start(self, i: int):
        spec = self.specs[i]
        w = build_world(copy.deepcopy(spec))
        if self.opt.verbose_failures is not None:
            w.config.verbose_failures = self.opt.verbose_failures
        ep = Episode(i, spec, w, started=time.time())
        if self.opt.oracle_baseline:
            from ..tasks.oracle import OracleFailed, solve
            try:
                ep.oracle_steps = solve(copy.deepcopy(w))["steps"]
            except OracleFailed:
                ep.oracle_steps = None
        self.episode = ep
        if self.run_dir:
            (self.run_dir / f"episode_{i:03d}.yaml").write_text(spec_to_yaml(spec))

    def _end(self, reason: str):
        ep = self.episode
        if ep.ended_by is not None:
            return
        ep.ended_by = reason
        w = ep.world
        goal = w.check_goal()
        meta = ep.spec.get("meta", {})
        s = {
            "episode": ep.index,
            "scenario": w.scenario_name,
            "seed": meta.get("seed"),
            "difficulty": meta.get("difficulty"),
            "achieved": goal.get("achieved", False),
            "ended_by": reason,
            "actions": w.step_count,
            "failed_actions": sum(ep.failures.values()),
            "failure_codes": dict(ep.failures),
            "queries": ep.queries,
            "photos": ep.photos,
            "cost": ep.cost,
            "oracle_actions": ep.oracle_steps,
            "seconds": round(time.time() - ep.started, 3),
            "conditions": goal.get("conditions", {}),
        }
        self.summaries.append(s)
        self._write_summary()

    def _write_summary(self):
        if not self.run_dir:
            return
        (self.run_dir / "summary.json").write_text(json.dumps(self.summaries, indent=2))
        cols = ["episode", "scenario", "seed", "difficulty", "achieved", "ended_by", "actions", "failed_actions",
                "queries", "photos", "cost", "oracle_actions", "seconds"]
        with open(self.run_dir / "summary.csv", "w", newline="") as f:
            wr = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            wr.writeheader()
            wr.writerows(self.summaries)

    def game_over(self) -> bool:
        return self.episode.ended_by is not None

    # ------------------------------------------------------------------ responses
    def _goal(self) -> dict:
        g = self.world.check_goal()
        out = {"goalType": "CLOSE_LAB", "goalAchieved": bool(g.get("achieved")), "Distribution": "Uninformed"}
        if self.opt.goal_conditions:
            out["conditions"] = g.get("conditions", {})
        return out

    def _envelope(self, command, args, ok, message="", cost=0.0, code="OK", **extra) -> dict:
        resp = {
            "goal": self._goal(),
            "command_result": {
                "command": command,
                "argument": " ".join(str(a) for a in args),
                "result": "SUCCESS" if ok else "FAIL",
                "message": message,
                "stepCost": cost,
                "code": code,
            },
            "step": self.world.step_count,
            "episode": self.episode.index,
            "gameOver": self.game_over(),
        }
        resp.update(extra)
        return resp

    def wrong_command(self, message="Invalid Command") -> dict:
        return self._envelope("WRONG_CMD", [], False, message, code="WRONG_CMD")

    # ------------------------------------------------------------------ main entry
    def handle(self, line: str) -> dict:
        """Handle one command line and return the JSON-able response."""
        try:
            name, args = parse_line(line)
        except (ValueError, KeyError, json.JSONDecodeError):
            resp = self.wrong_command()
            self._log(line, resp)
            return resp

        if name in QUERIES:
            resp = self._query(name, args)
        elif self.done:
            resp = self._envelope(name, args, False, "the session is over", code="GAME_OVER", allDone=True)
        elif self.game_over():
            resp = self._envelope(name, args, False, "the episode is over; send RESET", code="GAME_OVER")
        else:
            resp = self._action(name, args)
        self._log(line, resp)
        return resp

    def _query(self, name, args) -> dict:
        w = self.world
        if name in ("reset", "quit"):
            if not self.game_over():
                self._end(name)
            if name == "quit" or self.episode.index + 1 >= len(self.specs):
                self.done = True
                return self._envelope(name.upper(), args, True, "all episodes done", allDone=True,
                                      summary=self.summaries)
            self._start(self.episode.index + 1)
            return self._envelope("RESET", args, True, f"episode {self.episode.index} started",
                                  world=self.world.get_world())
        self.episode.queries += 1
        try:
            if name == "sense_all":
                payload = {"world": w.get_world()}
            elif name == "sense_robot":
                payload = {"robot": w.get_robot()}
            elif name == "sense_object":
                if len(args) != 1:
                    return self._envelope(name.upper(), args, False, "usage: sense_object <id>", code="BAD_ARGS")
                payload = {"object": w.get_object(str(args[0]))}
            elif name == "sense_visible":
                payload = {"visible": w.get_visible()}
            elif name == "list_actions":
                payload = {"actions": self.action_docs(), "queries": QUERIES}
            else:  # check_goal
                payload = {}
        except ActionFailure as f:
            return self._envelope(name.upper(), args, False, f.msg, code=f.code.value)
        return self._envelope(name.upper(), args, True, **payload)

    def _action(self, name, args) -> dict:
        w, ep = self.world, self.episode
        r = w.execute(name, args)
        cost = (self.opt.photo_cost if name == "take_photo" else self.opt.action_cost)
        ep.cost += cost
        if not r["ok"]:
            ep.failures[r["code"]] += 1
        extra = {"events": r["events"]}
        data = dict(r.get("data", {}))
        if name == "take_photo" and r["ok"]:
            ep.photos += 1
            photo = {k: v for k, v in data.items() if k != "image_png_base64"}
            path = None
            if self.run_dir:
                path = self.run_dir / "photos" / f"ep{ep.index:03d}_step{w.step_count:04d}.png"
                path.write_bytes(base64.b64decode(data["image_png_base64"]))
                photo["path"] = str(path.resolve())
            if self.opt.photo_mode in ("inline", "both") or path is None:
                photo["image_png_base64"] = data["image_png_base64"]
            extra["photo"] = photo
        elif data:
            extra["data"] = data
        if r.get("detail"):
            extra["detail"] = r["detail"]
        if w.check_goal().get("achieved"):
            self._end("goal")
        elif w.step_count >= self.opt.max_steps:
            self._end("max_steps")
        return self._envelope(name, args, r["ok"], r["msg"], cost, r["code"], **extra)

    def action_docs(self) -> dict:
        from ..core.robot import Robot
        from ..scenarios.loader import thing_types
        docs = {}
        for cls in [Robot, *thing_types().values()]:
            for aname, (spec, attr) in cls._actions.items():
                docs.setdefault(aname, spec.doc)
        return dict(sorted(docs.items()))

    def _log(self, line: str, resp: dict):
        if not self.run_dir:
            return
        logged = resp
        photo = resp.get("photo")
        if photo and "image_png_base64" in photo:
            logged = {**resp, "photo": {k: v for k, v in photo.items() if k != "image_png_base64"}}
        with open(self.run_dir / f"episode_{self.episode.index:03d}.jsonl", "a") as f:
            f.write(json.dumps({"t": round(time.time(), 3), "request": line.strip(), "response": logged}) + "\n")

    def close(self, reason="disconnect"):
        if self.episode and not self.game_over():
            self._end(reason)


# ---------------------------------------------------------------------- building episode lists
def episode_specs(scenarios=(), random_n=0, difficulties=(2,), seed=0, repeat=1) -> list[dict]:
    from ..scenarios import DEFAULT_LAB
    from ..scenarios.generator import generate_spec
    specs = [read_spec(s) for s in scenarios]
    for d in difficulties:
        for i in range(random_n):
            specs.append(generate_spec(seed + i, d))
    if not specs:
        specs = [read_spec(DEFAULT_LAB)]
    return [copy.deepcopy(s) for _ in range(repeat) for s in specs]
