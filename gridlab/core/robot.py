"""The Spot robot: pose, gripper, and the actions that are not aimed at one object."""
from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

from .entity import Entity, Location, Relation, Thing, action
from .errors import ActionFailure, Fail
from .geometry import Direction, Level, Pos, step

if TYPE_CHECKING:
    from .world import World


class Robot(Entity):
    kind = "robot"

    def __init__(self, id: str = "spot", cell: Pos = (0, 0), facing: Direction | str = Direction.N, **props):
        self.cell: Pos = tuple(cell)
        self.facing = Direction(facing)
        self.level = Level.LOW
        self.holding: Thing | None = None
        self.standing_on: Thing | None = None
        self.docked = False
        super().__init__(id, **props)

    def facing_cell(self) -> Pos:
        return step(self.cell, self.facing)

    def public_state(self) -> dict:
        return {
            "cell": list(self.cell),
            "level": self.level.value,
            "facing": self.facing.value,
            "facing_cell": list(self.facing_cell()),
            "holding": self.holding.id if self.holding else None,
            "standing_on": self.standing_on.id if self.standing_on else None,
            "docked": self.docked,
        }

    # ------------------------------------------------------------------ helpers
    def _held(self, world: "World", args) -> Thing:
        if self.holding is None:
            raise ActionFailure(Fail.NOT_HOLDING, "the gripper is empty")
        if len(args) == 2:
            obj = world.resolve(args[0])
            if obj is not self.holding:
                raise ActionFailure(Fail.NOT_HOLDING, f"not holding {obj.id}")
        elif len(args) != 1:
            raise ActionFailure(Fail.BAD_ARGS, "expected ([object], target)")
        return self.holding

    def _ensure_mobile(self):
        if self.level is not Level.LOW:
            raise ActionFailure(Fail.MUST_CLIMB_DOWN, "the robot is standing on something")
        if self.docked:
            raise ActionFailure(Fail.DOCKED, "the robot is docked")

    # ------------------------------------------------------------------ actions
    @action(reach=False)
    def go_to(self, world: "World", *args):
        """go_to(object_id) or go_to(x, y, facing): walk there by the shortest route."""
        self._ensure_mobile()
        if len(args) == 1:
            target = world.resolve(args[0])
            if not isinstance(target, Thing):
                raise ActionFailure(Fail.BAD_ARGS, "cannot go to that")
            if target.loc.relation is Relation.HELD:
                raise ActionFailure(Fail.BAD_ARGS, f"{target.id} is in the gripper")
            goals = list(target.approach_poses(world))
        elif len(args) == 3:
            try:
                cell, facing = (int(args[0]), int(args[1])), Direction(str(args[2]).upper())
            except (ValueError, TypeError):
                raise ActionFailure(Fail.BAD_ARGS, "expected go_to(x, y, facing)")
            if not world.walkable(cell):
                raise ActionFailure(Fail.INVALID_POSITION, f"cannot stand at {cell}")
            goals = [(cell, facing)]
        else:
            raise ActionFailure(Fail.BAD_ARGS, "expected go_to(object_id) or go_to(x, y, facing)")

        path = self._shortest_path({c for c, _ in goals}, world)
        if path is None:
            raise ActionFailure(Fail.NO_PATH, "no route to the target")
        end = path[-1]
        self.cell = end
        self.facing = next(f for c, f in goals if c == end)
        world.emit("robot_moved", cell=list(end), facing=self.facing.value)
        return {"path": [list(p) for p in path]}

    def _shortest_path(self, goal_cells: set, world: "World") -> list[Pos] | None:
        """BFS over walkable cells; ties broken N, E, S, W for determinism."""
        start = self.cell
        prev: dict[Pos, Pos | None] = {start: None}
        q = deque([start])
        while q:
            cur = q.popleft()
            if cur in goal_cells:
                path = [cur]
                while prev[path[-1]] is not None:
                    path.append(prev[path[-1]])
                return path[::-1]
            for d in Direction:
                nxt = step(cur, d)
                if nxt not in prev and world.walkable(nxt):
                    prev[nxt] = cur
                    q.append(nxt)
        return None

    @action(reach=False, holding=True)
    def put_down(self, world: "World"):
        """Put the held object in front of the robot (on the counter/table there, or on the floor)."""
        obj = self.holding
        cell, level = self.facing_cell(), self.level
        if not world.in_bounds(cell):
            raise ActionFailure(Fail.INVALID_POSITION, "there is a wall in front of the robot")
        here = world.things_at(cell, level)
        surfaces = [t for t in here if t.surface_capacity is not None and not t.movable]
        if surfaces:
            surfaces[0].accept_on(world, obj)
            world.move(obj, Location(Relation.ON, parent=surfaces[0]))
            world.emit("put", obj=obj.id, on=surfaces[0].id)
            return
        if level is Level.HIGH:
            raise ActionFailure(Fail.CANNOT_SUPPORT, "there is nothing to put it on")
        if not world.walkable(cell):
            raise ActionFailure(Fail.OBSTRUCTED, "the floor in front of the robot is blocked")
        world.move(obj, Location(Relation.AT, cell=cell, level=Level.LOW))
        world.emit("put", obj=obj.id, cell=list(cell), level="low")

    @action(reach=False, holding=True)
    def put_on(self, world: "World", *args):
        """put_on([object], target): put the held object on top of target."""
        obj = self._held(world, args)
        target = world.resolve(args[-1])
        if target is obj or world.is_ancestor(obj, target):
            raise ActionFailure(Fail.CANNOT_SUPPORT, "cannot put an object on itself")
        world.require_reachable(target)
        target.accept_on(world, obj)
        world.move(obj, Location(Relation.ON, parent=target))
        world.emit("put", obj=obj.id, on=target.id)

    @action(reach=False, holding=True)
    def put_in(self, world: "World", *args):
        """put_in([object], container): put the held object inside an open container."""
        obj = self._held(world, args)
        target = world.resolve(args[-1])
        if target is obj or world.is_ancestor(obj, target):
            raise ActionFailure(Fail.CANNOT_SUPPORT, "cannot put an object in itself")
        world.require_reachable(target)
        target.accept_in(world, obj)
        world.move(obj, Location(Relation.IN, parent=target))
        world.emit("put", obj=obj.id, inside=target.id)

    @action(reach=False)
    def climb_down(self, world: "World"):
        """Step down from the stool/chair the robot is standing on."""
        if self.level is Level.LOW:
            raise ActionFailure(Fail.ALREADY, "the robot is already on the floor")
        self.level = Level.LOW
        self.standing_on = None
        world.emit("robot_climbed_down", cell=list(self.cell))
