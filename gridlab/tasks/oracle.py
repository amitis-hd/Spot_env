"""A scripted solver for the close-the-lab task.

It cheats on knowledge (it reads the true world state, including hidden container contents,
weights and which key opens what) but it acts only through `world.execute`, so every rule
is enforced. Used to check that generated labs are solvable and as a baseline step count.
It is not a planner and makes no attempt to be optimal.
"""
from __future__ import annotations

from ..core.entity import Relation, Size, Thing
from ..core.geometry import Direction, Level, step
from ..objects import Book, Container, Door, Drawer, Key, Lamp, LightButton, Lockable, Person, Stool


class OracleFailed(RuntimeError):
    pass


class Oracle:
    def __init__(self, world, max_steps: int = 500):
        self.w = world
        self.max_steps = max_steps
        self.steps = 0
        self.depth = 0
        self.protected: set = set()   # cells stash() must not use (e.g. where the stool is being set up)

    # ------------------------------------------------------------------ basics
    @property
    def r(self):
        return self.w.robot

    def do(self, name, *args, allow=()):
        self.steps += 1
        if self.steps > self.max_steps:
            raise OracleFailed("step budget exhausted")
        resp = self.w.execute(name, list(args))
        if not resp["ok"] and resp["code"] not in allow:
            raise OracleFailed(f"{name}{tuple(args)} -> {resp['code']} {resp['msg']}\n{self.w.describe()}")
        return resp

    def _things_at(self, cell):
        return self.w.things_at(cell)

    def _clearable(self, cell, people_ok=False):
        return self.w.in_bounds(cell) and all(t.movable or (people_ok and isinstance(t, Person))
                                              for t in self._things_at(cell))

    # ------------------------------------------------------------------ top level
    def solve(self) -> dict:
        w = self.w
        self.hands_free()
        if self.r.level is Level.HIGH:
            self.do("climb_down")
        for _ in range(3):
            for p in [t for t in w.things.values() if isinstance(t, Person)]:
                self.send_away(p)
            for k in [t for t in w.things.values() if isinstance(t, Key)]:
                if any(isinstance(a, Container) for a in w.ancestors(k)):
                    self.fetch(k)
                    self.stash()
            for d in [t for t in w.things.values() if isinstance(t, Drawer)]:
                self.secure(d)
            for d in [t for t in w.things.values() if isinstance(t, Door)]:
                self.secure(d)
            self.light_on()
            cond = w.check_goal()["conditions"]
            if all(v for k, v in cond.items() if k != "docked"):
                break
        self.dock()
        goal = w.check_goal()
        if not goal["achieved"]:
            raise OracleFailed(f"goal not reached: {goal}")
        return {"steps": w.step_count, "goal": goal}

    # ------------------------------------------------------------------ people
    def send_away(self, p: Person):
        for _ in range(4):
            if p.id not in self.w.things:
                return
            if self.w.open_exit() is None:
                self.make_exit()
            self.do("ask_to_leave", p.id)
        if p.id in self.w.things:
            raise OracleFailed(f"{p.id} will not leave")

    def make_exit(self):
        doors = [t for t in self.w.things.values() if isinstance(t, Door)]
        doors.sort(key=lambda d: (d.locked, not d.is_open))
        d = doors[0]
        self.clear_doorway(d)
        if not d.is_open:
            if d.locked:
                self.use_key(d)
            self.hands_free()
            self.approach(d)
            self.do("open", d.id)

    # ------------------------------------------------------------------ drawers / doors
    def secure(self, c: Lockable):
        if isinstance(c, Door):
            self.clear_doorway(c)
        if c.is_open:
            self.hands_free()
            self.approach(c)
            resp = self.do("close", c.id, allow=("OBSTRUCTED",))
            if not resp["ok"]:
                for t in self.w.children(c, Relation.IN):
                    if t.protruding:
                        self.approach(c)
                        if self.do("push_in", t.id, allow=("OBSTRUCTED",))["ok"]:
                            continue
                        self.fetch(t)
                        self.stash()
                self.hands_free()
                self.approach(c)
                self.do("close", c.id)
        if not c.locked and c.lock_type != "none":
            if c.lock_type == "manual":
                self.hands_free()
                self.approach(c)
                self.do("lock", c.id)
            else:
                self.use_key(c)

    def clear_doorway(self, d: Door):
        for t in self.w.children(d, Relation.IN):
            self.fetch(t)
            self.stash()

    def use_key(self, c: Lockable):
        """Turn the right key once in c's lock (locks or unlocks it), then put the key away."""
        key = next(k for k in self.w.things.values() if isinstance(k, Key) and c.id in k.opens)
        self.deliver(key, c)
        self.do("insert_key", c.id)
        self.do("turn_key", c.id)
        self.do("remove_key", c.id)
        self.stash()

    def deliver(self, obj: Thing, target: Thing):
        """End up holding obj with target within reach."""
        for _ in range(4):
            self.hands_free()
            self.make_accessible(target)
            self.fetch(obj)
            if self.try_position(target):
                return
        raise OracleFailed(f"cannot bring {obj.id} to {target.id}")

    # ------------------------------------------------------------------ light / dock
    def light_on(self):
        lamp = next(t for t in self.w.things.values() if isinstance(t, Lamp))
        if lamp.on:
            return
        button = next(t for t in self.w.things.values() if isinstance(t, LightButton))
        heavy = sorted((t for t in self.w.things.values() if t.movable and t.size <= button.surface_capacity
                        and t.weight >= button.threshold), key=lambda t: not isinstance(t, Book))
        for t in heavy:
            self.deliver(t, button)
            self.do("put_on", button.id)
            if lamp.on:
                return
        raise OracleFailed("could not turn on the light")

    def dock(self):
        self.hands_free()
        if self.r.level is Level.HIGH:
            self.do("climb_down")
        d = next(t for t in self.w.things.values() if t.kind == "dock")
        for t in self.w.children(d):
            self.fetch(t)
            self.stash(avoid={d.loc.cell})
        self.go_near(d)
        self.do("dock", d.id)

    # ------------------------------------------------------------------ getting things
    def hands_free(self):
        if self.r.holding is None:
            return
        if self.r.holding_fixed:
            self.do("release")
        else:
            self.stash()

    def fetch(self, t: Thing):
        """Get t into the gripper."""
        if self.r.holding is t:
            return
        self.depth += 1
        if self.depth > 15:
            raise OracleFailed("recursion too deep")
        try:
            self.hands_free()
            if self.r.level is Level.HIGH:
                self.do("climb_down")
            # unlock / open the containers around it, outermost first
            for c in reversed([a for a in self.w.ancestors(t) if isinstance(a, Container)]):
                if not c.is_open:
                    if c.locked:
                        self.use_key(c)
                    self.hands_free()
                    self.approach(c)
                    self.do("open", c.id)
            self.approach(t)
            self.do("pick_up", t.id)
            if self.r.level is Level.HIGH:
                self.do("climb_down")
        finally:
            self.depth -= 1

    def approach(self, t: Thing):
        """Stand so that t is within reach (climbing the stool for HIGH things). Hands must be free."""
        for _ in range(3):
            if t.is_reachable(self.w):
                return
            self.make_accessible(t)
            if self.try_position(t):
                return
        raise OracleFailed(f"cannot reach {t.id}")

    def make_accessible(self, t: Thing):
        """Clear the way to t (needs free hands; does not leave the robot in position)."""
        if t.is_reachable(self.w):
            return
        if self.r.level is Level.HIGH:
            self.do("climb_down")
        top = self.w.top(t)
        if isinstance(top, Door):
            for x in self._things_at(top.loc.cell):
                self.clear_thing(x, avoid={top.loc.cell})
            return
        cell, level, _ = self.w.root(t)
        if level is Level.HIGH:
            self.place_stool(cell)
            return
        if any(self.w.walkable(step(cell, d)) or step(cell, d) == self.r.cell for d in Direction):
            return
        for people_ok in (False, True):
            for d in Direction:
                n = step(cell, d)
                if self._clearable(n, people_ok):
                    for x in self._things_at(n):
                        self.clear_thing(x, avoid={n, cell})
                    return
        raise OracleFailed(f"cannot clear a side of {t.id}")

    def try_position(self, t: Thing) -> bool:
        """Move next to t without clearing anything (the robot may be carrying something)."""
        if t.is_reachable(self.w):
            return True
        if self.r.level is Level.HIGH:
            self.do("climb_down")
        top = self.w.top(t)
        if isinstance(top, Door):
            return self.do("go_to", top.id, allow=("NO_ACCESS",))["ok"]
        cell, level, _ = self.w.root(t)
        if level is Level.HIGH:
            spot = self.stool_spot(cell)
            if spot is None:
                return False
            back, facing, stool = spot
            if not self.do("go_to", back[0], back[1], facing.value, allow=("NO_ACCESS",))["ok"]:
                return False
            return self.do("climb", stool.id, allow=("OBSTRUCTED", "NOT_REACHABLE"))["ok"] and t.is_reachable(self.w)
        return self.do("go_to", t.id, allow=("NO_ACCESS",))["ok"]

    def go_near(self, t: Thing):
        self.approach(t)

    def clear_thing(self, x: Thing, avoid=frozenset()):
        if isinstance(x, Person):
            self.send_away(x)
        else:
            self.fetch(x)
            self.stash(avoid=set(avoid))

    def _stool(self):
        return next(t for t in self.w.things.values() if isinstance(t, Stool))

    def stool_spot(self, cell):
        """(back cell, facing, stool) if the stool already stands right in front of `cell`."""
        stool = self._stool()
        if stool.loc.relation is not Relation.AT:
            return None
        for d in Direction:
            front, back = step(cell, d), step(step(cell, d), d)
            if stool.loc.cell == front and self.w.in_bounds(back):
                return back, d.opposite, stool
        return None

    def place_stool(self, cell):
        """Put the stool directly in front of `cell` with a free cell behind it for the robot."""
        stool = self._stool()
        options = []
        for d in Direction:
            front, back = step(cell, d), step(step(cell, d), d)
            for people_ok in (False, True):
                if self._clearable(front, people_ok) and self._clearable(back, people_ok):
                    already = stool.loc.relation is Relation.AT and stool.loc.cell == front
                    options.append((people_ok, not already, d, front, back))
                    break
        if not options:
            raise OracleFailed(f"no room to climb towards {cell}")
        _, _, d, front, back = min(options, key=lambda o: o[:2])
        saved = set(self.protected)
        self.protected |= {front, back}
        try:
            self._set_up_stool(stool, d, front, back)
        finally:
            self.protected = saved

    def _set_up_stool(self, stool, d, front, back):
        for x in self._things_at(front):
            if x is not stool:
                self.clear_thing(x, avoid={front, back})
        for x in self._things_at(back):
            if x is not stool:
                self.clear_thing(x, avoid={front, back})
        if not (stool.loc.relation is Relation.AT and stool.loc.cell == front):
            self.fetch(stool)
            self.do("go_to", back[0], back[1], d.opposite.value)
            self.do("put_down")

    # ------------------------------------------------------------------ putting things away
    def stash(self, avoid=frozenset()):
        """Put the carried object somewhere out of the way."""
        obj = self.r.holding
        if obj is None:
            return
        if self.r.level is Level.HIGH:
            self.do("climb_down")
        surfaces = [t for t in self.w.things.values()
                    if not t.movable and t.surface_capacity is not None and t.loc.relation is Relation.AT
                    and t.loc.level is Level.LOW and obj.size <= t.surface_capacity]
        for s in surfaces:
            if self.do("go_to", s.id, allow=("NO_ACCESS",))["ok"]:
                self.do("put_down")
                return
        # floor: prefer cells that matter least (not door cells, few fixed neighbours); relax if needed
        doors = {t.loc.cell for t in self.w.things.values() if isinstance(t, Door)}
        docks = {t.loc.cell for t in self.w.things.values() if t.kind == "dock"}
        for banned in (set(avoid) | self.protected | doors, set(avoid) | self.protected, self.protected):
            cands = []
            for y in range(self.w.height):
                for x in range(self.w.width):
                    c = (x, y)
                    if c in banned or not self.w.walkable(c):
                        continue
                    fixed_nb = sum(1 for d in Direction for t in self.w.things_at(step(c, d)) if not t.movable)
                    near_dock = any(step(c, d) in docks for d in Direction)
                    cands.append((near_dock, fixed_nb, c))
            for _, _, c in sorted(cands):
                for d in Direction:
                    stand = step(c, d)
                    if stand not in self.protected and (self.w.walkable(stand) or stand == self.r.cell):
                        self.do("go_to", stand[0], stand[1], d.opposite.value)
                        self.do("put_down")
                        return
        raise OracleFailed(f"nowhere to put {obj.id}")


def solve(world, max_steps: int = 500) -> dict:
    return Oracle(world, max_steps).solve()
