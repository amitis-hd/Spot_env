"""The world: grid, entities, knowledge, action dispatch and observations."""
from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Iterable

from .entity import Entity, Location, Relation, Thing, jsonable
from .errors import ActionFailure, Fail
from .geometry import Direction, Level, Pos, direction_between, step
from .robot import Robot


def all_thing_actions() -> set[str]:
    """Every action name defined by any Thing subclass."""
    names, stack = set(), [Thing]
    while stack:
        cls = stack.pop()
        names |= set(cls._actions)
        stack += cls.__subclasses__()
    return names


@dataclass
class WorldConfig:
    #: include the specific cause of failures (e.g. "binder_1 is sticking out") in responses
    verbose_failures: bool = False
    #: do not tell the planner which locks a key opens (it has to try)
    hide_key_targets: bool = False


class World:
    def __init__(self, width: int = 4, height: int = 4, robot: Robot | None = None,
                 config: WorldConfig | None = None):
        self.width, self.height = width, height
        self.config = config or WorldConfig()
        self.robot = robot or Robot()
        self.things: dict[str, Thing] = {}
        self.known: set[str] = set()        # ids the planner has been told about
        self.step_count = 0
        self.history: list[dict] = []
        self.departed: list[str] = []       # people who left the lab
        self.goal = None                    # object with .check(world) -> dict
        self.scenario_name = "unnamed"
        self._events: list[dict] = []

    # ================================================================ building
    def add(self, thing: Thing, *, cell: Pos | None = None, level: Level | str = Level.LOW,
            on: Thing | str | None = None, inside: Thing | str | None = None) -> Thing:
        if thing.id in self.things or thing.id == self.robot.id:
            raise ValueError(f"duplicate id {thing.id}")
        if sum(x is not None for x in (cell, on, inside)) != 1:
            raise ValueError("give exactly one of cell=, on=, inside=")
        if cell is not None:
            cell = tuple(cell)
            if not self.in_bounds(cell):
                raise ValueError(f"{thing.id}: cell {cell} outside the grid")
            loc = Location(Relation.AT, cell=cell, level=Level(level))
        elif on is not None:
            loc = Location(Relation.ON, parent=self.things[on] if isinstance(on, str) else on)
        else:
            loc = Location(Relation.IN, parent=self.things[inside] if isinstance(inside, str) else inside)
        self.things[thing.id] = thing
        thing.loc = loc
        return thing

    def start(self):
        """Call once the scenario is built: settles derived state and initial knowledge."""
        for t in list(self.things.values()):
            t.validate(self)
        for t in list(self.things.values()):
            t.update(self)
        self._events.clear()
        self.known = {tid for tid, t in self.things.items() if self.is_visible(t)}

    # ================================================================ spatial queries
    def in_bounds(self, cell: Pos) -> bool:
        return 0 <= cell[0] < self.width and 0 <= cell[1] < self.height

    def things_at(self, cell: Pos, level: Level | None = None) -> list[Thing]:
        """Things placed directly in a cell (not on/in other things, not doors in its walls)."""
        return [t for t in self.things.values()
                if t.loc.relation is Relation.AT and t.loc.cell == tuple(cell) and not t.wall_mounted
                and (level is None or t.loc.level is level)]

    def children(self, parent: Thing, relation: Relation | None = None) -> list[Thing]:
        return [t for t in self.things.values()
                if t.loc.parent is parent and (relation is None or t.loc.relation is relation)]

    def ancestors(self, t: Thing) -> list[Thing]:
        out, cur = [], t.loc.parent
        while cur is not None:
            out.append(cur)
            cur = cur.loc.parent
        return out

    def is_ancestor(self, a: Thing, b: Thing) -> bool:
        return a in self.ancestors(b)

    def top(self, t: Thing) -> Thing:
        while t.loc.parent is not None:
            t = t.loc.parent
        return t

    def root(self, t: Thing) -> tuple[Pos, Level, bool]:
        """(cell, level, held) where the thing physically is."""
        cur = t
        while cur.loc.parent is not None:
            cur = cur.loc.parent
        if cur.loc.relation is Relation.HELD:
            return self.robot.cell, self.robot.level, True
        return cur.loc.cell, cur.loc.level, False

    def is_visible(self, t: Thing) -> bool:
        cur = t
        while cur.loc.parent is not None:
            if cur.loc.relation is Relation.IN and not cur.loc.parent.contents_visible():
                return False
            cur = cur.loc.parent
        return True

    def walkable(self, cell: Pos) -> bool:
        if not self.in_bounds(cell):
            return False
        if cell == self.robot.cell:
            return False
        return not any(t.blocks_cell for t in self.things_at(cell))

    def default_reachable(self, t: Thing) -> bool:
        if not self.is_visible(t):
            return False
        top = self.top(t)
        if top is not t and top.wall_mounted:      # e.g. a chair standing in a doorway
            return top.is_reachable(self)
        cell, level, held = self.root(t)
        r = self.robot
        if held or level is not r.level:
            return False
        return cell == r.facing_cell()

    def default_approach_poses(self, t: Thing) -> list[tuple[Pos, Direction]]:
        top = self.top(t)
        if top is not t and top.wall_mounted:
            return top.approach_poses(self)
        cell, _, _ = self.root(t)
        poses = []
        for d in Direction:
            n = step(cell, d)
            if self.walkable(n) or n == self.robot.cell:
                poses.append((n, direction_between(n, cell)))
        return poses

    # ================================================================ mutation
    def move(self, t: Thing, loc: Location):
        """Relocate a thing (things on/in it come along). Moving the held object out of the
        gripper empties it; subclasses that keep a grip (insert_key) set robot.holding again."""
        if self.robot.holding is t:
            self.robot.holding = None
        t.protruding = False
        t.loc = loc
        if loc.relation is Relation.HELD:
            self.robot.holding = t

    def remove(self, t: Thing):
        """Take a thing out of the world (a person leaving the lab)."""
        for child in self.children(t):
            cell, level, _ = self.root(t)
            self.move(child, Location(Relation.AT, cell=cell, level=level))
        del self.things[t.id]
        self.known.discard(t.id)
        self.departed.append(t.id)

    def open_exit(self):
        """A door people can walk out through right now, or None."""
        return next((t for t in self.things.values() if getattr(t, "is_exit_clear", None) and t.is_exit_clear(self)), None)

    def check_goal(self) -> dict:
        if self.goal is None:
            return {"achieved": False, "conditions": {}, "note": "no goal set"}
        return self.goal.check(self)

    def emit(self, type: str, **data):
        self._events.append({"type": type, **jsonable(data)})

    def resolve(self, ref: Any) -> Entity:
        if isinstance(ref, Entity):
            return ref
        ref = str(ref)
        if ref == self.robot.id:
            return self.robot
        t = self.things.get(ref)
        if t is None or ref not in self.known:
            raise ActionFailure(Fail.UNKNOWN_OBJECT, f"unknown object '{ref}'")
        return t

    def require_reachable(self, t: Entity):
        if isinstance(t, Thing) and not t.is_reachable(self):
            raise ActionFailure(Fail.NOT_REACHABLE, f"{t.id} is not within reach")

    def _settle(self):
        """After a successful action: let things react, then reveal newly visible things."""
        for t in list(self.things.values()):
            t.update(self)
        for tid, t in self.things.items():
            if tid not in self.known and self.is_visible(t):
                self.known.add(tid)
                where = t.loc.parent.id if t.loc.parent else None
                self.emit("discovered", obj=tid, kind=t.kind, relation=t.loc.relation.value, parent=where)

    # ================================================================ actions
    def robot_actions(self) -> list[str]:
        return Robot.affordances()

    def execute(self, name: str, args: Iterable[Any] = ()) -> dict:
        """Run one action. Never raises for planner mistakes; returns a response dict."""
        args = list(args)
        self._events = []
        resp: dict[str, Any] = {"action": name, "args": args}
        try:
            data = self._dispatch(name, args)
            self._settle()
            resp.update(ok=True, code="OK", msg="")
            if data:
                resp["data"] = jsonable(data)
        except ActionFailure as f:
            resp.update(ok=False, code=f.code.value, msg=f.msg)
            if self.config.verbose_failures and f.detail:
                resp["detail"] = f.detail
        resp["events"] = self._events
        self._events = []
        self.step_count += 1
        resp["step"] = self.step_count
        self.history.append(resp)
        return resp

    def _dispatch(self, name: str, args: list):
        if name in Robot._actions:
            spec, attr = Robot._actions[name]
            self._check_hand(spec)
            return self._call(getattr(self.robot, attr), args)
        if name not in all_thing_actions():
            raise ActionFailure(Fail.UNKNOWN_ACTION, f"unknown action '{name}'")
        if not args:
            raise ActionFailure(Fail.BAD_ARGS, f"{name} needs a target object")
        target = self.resolve(args[0])
        entry = type(target)._actions.get(name)
        if entry is None:
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{target.id} does not support {name}")
        spec, attr = entry
        if spec.reach:
            self.require_reachable(target)
        self._check_hand(spec)
        rest = [self.resolve(a) if isinstance(a, str) and a in self.things else a for a in args[1:]]
        return self._call(getattr(target, attr), rest)

    def _check_hand(self, spec):
        if spec.free_hand and self.robot.holding is not None:
            raise ActionFailure(Fail.HANDS_FULL, f"the gripper is holding {self.robot.holding.id}")
        if spec.holding and self.robot.holding is None:
            raise ActionFailure(Fail.NOT_HOLDING, "the gripper is empty")

    def _call(self, fn, args):
        try:
            inspect.signature(fn).bind(self, *args)
        except TypeError:
            raise ActionFailure(Fail.BAD_ARGS, f"wrong arguments for {fn.__name__}")
        return fn(self, *args)

    # ================================================================ observations
    def export_location(self, t: Thing) -> dict:
        cell, level, held = self.root(t)
        d = {"relation": t.loc.relation.value, "cell": list(cell), "level": level.value}
        if t.loc.parent is not None:
            d["parent"] = t.loc.parent.id
        return d

    def observe(self, t: Thing) -> dict:
        d = {
            "id": t.id,
            "kind": t.kind,
            "location": self.export_location(t),
            "visible": self.is_visible(t),
            "movable": t.movable,
            "climbable": t.climbable,
            "state": self._state(t),
            "affordances": t.affordances(),
        }
        d.update(jsonable(t.extra_observation(self)))
        return d

    def _state(self, t: Thing) -> dict:
        st = t.public_state()
        if self.config.hide_key_targets:
            st.pop("opens", None)
        return st

    def get_robot(self) -> dict:
        return {"id": self.robot.id, "kind": "robot", **self.robot.public_state(),
                "affordances": self.robot_actions()}

    def get_object(self, ref: str) -> dict:
        t = self.resolve(ref)
        return self.get_robot() if t is self.robot else self.observe(t)

    def get_visible(self) -> list[dict]:
        return [self.observe(t) for tid, t in self.things.items() if tid in self.known and self.is_visible(t)]

    def get_world(self) -> dict:
        """Everything the planner is allowed to know (hidden container contents excluded)."""
        return {
            "grid": {"width": self.width, "height": self.height, "levels": [l.value for l in Level]},
            "step": self.step_count,
            "robot": self.get_robot(),
            "objects": [self.observe(t) for tid, t in self.things.items() if tid in self.known],
        }

    # ================================================================ debugging
    def describe(self) -> str:
        """Plain-text dump of the true world state (god's eye, includes hidden things)."""
        lines = []
        r = self.robot
        for y in range(self.height):
            for x in range(self.width):
                parts = []
                for lvl in Level:
                    names = [self._tree(t) for t in self.things_at((x, y), lvl)]
                    if r.cell == (x, y) and r.level is lvl:
                        names.insert(0, f"SPOT>{r.facing.value}" + (f"[{r.holding.id}]" if r.holding else ""))
                    if names:
                        parts.append(f"{lvl.value}: " + ", ".join(names))
                if parts:
                    lines.append(f"({x},{y}) " + " | ".join(parts))
        for t in self.things.values():
            if t.wall_mounted:
                lines.append(f"{self._tree(t)} in {t.public_state().get('side', '?')} wall of {t.loc.cell}: {t.public_state()}")
        return "\n".join(lines)

    def _tree(self, t: Thing) -> str:
        kids = self.children(t)
        if not kids:
            return t.id
        inner = ", ".join(f"{k.loc.relation.value}:" + self._tree(k) for k in kids)
        return f"{t.id}{{{inner}}}"
