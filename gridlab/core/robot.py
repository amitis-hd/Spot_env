"""The Spot robot: pose, gripper, and the actions that are not aimed at one object.

Rules:
- Spot never shares a cell with any object; it acts on the cell in front of it, at its own level.
- go_to teleports: Spot ends up on a free neighbouring cell of the target, facing it.
- If the gripper holds something that is fixed in place (a key in a lock, a door handle),
  Spot cannot move until it lets go (`release`) or frees the object (e.g. `remove_key`).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from .entity import Entity, Location, Relation, Thing, action
from .errors import ActionFailure, Fail
from .geometry import Direction, Level, Pos, direction_between, step

if TYPE_CHECKING:
    from .world import World


class Robot(Entity):
    kind = "robot"

    def __init__(self, id: str = "spot", cell: Pos = (0, 0), facing: Direction | str = Direction.N, **props):
        self.cell: Pos = tuple(cell)
        self.facing = Direction(facing)
        self.level = Level.LOW
        #: object in the gripper; if its location is not HELD, it is fixed in place (grasped, not carried)
        self.holding: Thing | None = None
        self.standing_on: Thing | None = None
        self.came_from: Pos | None = None   # cell Spot climbed from
        self.docked = False
        super().__init__(id, **props)

    def facing_cell(self) -> Pos:
        return step(self.cell, self.facing)

    @property
    def holding_fixed(self) -> bool:
        return self.holding is not None and self.holding.loc.relation is not Relation.HELD

    def public_state(self) -> dict:
        return {
            "cell": list(self.cell),
            "level": self.level.value,
            "facing": self.facing.value,
            "facing_cell": list(self.facing_cell()),
            "holding": self.holding.id if self.holding else None,
            "holding_fixed": self.holding_fixed,
            "standing_on": self.standing_on.id if self.standing_on else None,
            "docked": self.docked,
        }

    # ------------------------------------------------------------------ helpers
    def _held(self, world: "World", args) -> Thing:
        if self.holding is None:
            raise ActionFailure(Fail.NOT_HOLDING, "the gripper is empty")
        if self.holding_fixed:
            raise ActionFailure(Fail.HOLDING_FIXED, f"{self.holding.id} is fixed in place")
        if len(args) == 2:
            obj = world.resolve(args[0])
            if obj is not self.holding:
                raise ActionFailure(Fail.NOT_HOLDING, f"not holding {obj.id}")
        elif len(args) != 1:
            raise ActionFailure(Fail.BAD_ARGS, "expected ([object], target)")
        return self.holding

    def check_can_move(self):
        if self.holding_fixed:
            raise ActionFailure(Fail.HOLDING_FIXED, f"the gripper is holding {self.holding.id}, which is fixed in place")
        if self.docked:
            raise ActionFailure(Fail.DOCKED, "the robot is docked")

    def _free(self, world: "World", cell: Pos) -> bool:
        return cell == self.cell or world.walkable(cell)

    # ------------------------------------------------------------------ actions
    @action(reach=False)
    def go_to(self, world: "World", *args):
        """go_to(object_id) or go_to(x, y, facing): appear next to the target, facing it."""
        self.check_can_move()
        if self.level is not Level.LOW:
            raise ActionFailure(Fail.MUST_CLIMB_DOWN, "the robot is standing on something")
        if len(args) == 1:
            target = world.resolve(args[0])
            if not isinstance(target, Thing):
                raise ActionFailure(Fail.BAD_ARGS, "cannot go to that")
            if target.loc.relation is Relation.HELD:
                raise ActionFailure(Fail.BAD_ARGS, f"{target.id} is in the gripper")
            poses = [(c, f) for c, f in target.approach_poses(world) if self._free(world, c)]
            if not poses:
                raise ActionFailure(Fail.NO_ACCESS, f"no free cell next to {target.id}")
        elif len(args) == 3:
            try:
                cell, facing = (int(args[0]), int(args[1])), Direction(str(args[2]).upper())
            except (ValueError, TypeError):
                raise ActionFailure(Fail.BAD_ARGS, "expected go_to(x, y, facing)")
            if not world.in_bounds(cell):
                raise ActionFailure(Fail.INVALID_POSITION, f"{cell} is outside the lab")
            if not self._free(world, cell):
                raise ActionFailure(Fail.NO_ACCESS, f"{cell} is occupied")
            poses = [(cell, facing)]
        else:
            raise ActionFailure(Fail.BAD_ARGS, "expected go_to(object_id) or go_to(x, y, facing)")

        order = list(Direction)
        cell, facing = min(poses, key=lambda p: (abs(p[0][0] - self.cell[0]) + abs(p[0][1] - self.cell[1]),
                                                 order.index(p[1])))
        self.cell, self.facing = cell, facing
        world.emit("robot_moved", cell=list(cell), facing=facing.value)

    @action(reach=False, holding=True)
    def put_down(self, world: "World"):
        """Put the held object in front: on the counter/table/shelf there, else on the floor.
        At HIGH level with nothing to hold it, the object falls to the LOW level."""
        obj = self._held(world, ["_"])
        cell = self.facing_cell()
        if not world.in_bounds(cell):
            raise ActionFailure(Fail.INVALID_POSITION, "there is a wall in front of the robot")
        if self.level is Level.HIGH:
            if self._place_at_level(world, obj, cell, Level.HIGH, fall=False):
                return
            self._place_at_level(world, obj, cell, Level.LOW, fall=True)
            return
        self._place_at_level(world, obj, cell, Level.LOW, fall=False)

    def _place_at_level(self, world: "World", obj: Thing, cell: Pos, level: Level, fall: bool) -> bool:
        """Place obj in `cell` at `level`. Returns False (HIGH only) if there is nothing there at all."""
        here = world.things_at(cell, level)
        if any(t.obstructs_drop for t in here):
            raise ActionFailure(Fail.OBSTRUCTED, "something is in the way", f"{[t.id for t in here if t.obstructs_drop][0]} is there")
        fixed = [t for t in here if not t.movable]
        surfaces = [t for t in fixed if t.surface_capacity is not None]
        if surfaces:
            surfaces[0].accept_on(world, obj)
            world.move(obj, Location(Relation.ON, parent=surfaces[0]))
            world.emit("fell" if fall else "put", obj=obj.id, on=surfaces[0].id)
            return True
        if fixed:
            raise ActionFailure(Fail.CANNOT_SUPPORT, "there is no place to put it",
                                f"{fixed[0].id} has no surface")
        if level is Level.HIGH:
            return False
        world.move(obj, Location(Relation.AT, cell=cell, level=Level.LOW))
        world.emit("fell" if fall else "put", obj=obj.id, cell=list(cell), level="low")
        return True

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
        target.on_put_in(world, obj)
        world.emit("put", obj=obj.id, inside=target.id)

    @action(reach=False, holding=True)
    def release(self, world: "World"):
        """Let go of something fixed in place (a key in a lock, a door handle). Use put_down for carried objects."""
        if not self.holding_fixed:
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{self.holding.id} is carried; use put_down")
        obj, self.holding = self.holding, None
        world.emit("released", obj=obj.id)

    @action(reach=False)
    def take_photo(self, world: "World"):
        """Picture of the cell in front taken with the gripper camera (HIGH level drawn above LOW)."""
        import base64
        import io

        from ..render.scene import render_photo
        img = render_photo(world, world.config.photo_size)
        world.last_photo = img
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return {"image_png_base64": base64.b64encode(buf.getvalue()).decode("ascii"),
                "width": img.width, "height": img.height,
                "of_cell": list(self.facing_cell()), "robot_level": self.level.value}

    @action(reach=False)
    def turn(self, world: "World", direction):
        """Turn in place to face N/E/S/W (also works while standing on a stool)."""
        try:
            d = Direction(str(direction).upper())
        except ValueError:
            raise ActionFailure(Fail.BAD_ARGS, "direction must be N, E, S or W")
        self.check_can_move()
        if d is self.facing:
            raise ActionFailure(Fail.ALREADY, f"already facing {d.value}")
        self.facing = d
        world.emit("robot_turned", facing=d.value)

    @action(reach=False)
    def undock(self, world: "World"):
        """Leave the charging dock, stepping to a free neighbouring cell facing the dock."""
        if not self.docked:
            raise ActionFailure(Fail.ALREADY, "the robot is not docked")
        if self.holding_fixed:
            raise ActionFailure(Fail.HOLDING_FIXED, f"the gripper is holding {self.holding.id}")
        dock_cell = self.cell
        self._step_off(world)
        self.docked = False
        world.emit("undocked", cell=list(self.cell), facing=self.facing.value)
        return {"from": list(dock_cell)}

    def _step_off(self, world: "World"):
        here = self.cell
        candidates = []
        if self.came_from is not None:
            candidates.append(self.came_from)
        candidates += [step(here, d) for d in (self.facing.opposite, *Direction)]
        target = next((c for c in candidates if world.walkable(c)), None)
        if target is None:
            raise ActionFailure(Fail.NO_ACCESS, "no free cell to step to")
        self.cell, self.came_from = target, None
        self.facing = direction_between(target, here)

    @action(reach=False)
    def climb_down(self, world: "World"):
        """Step down from the stool/chair to a free neighbouring cell (preferably where Spot came from)."""
        if self.level is Level.LOW:
            raise ActionFailure(Fail.ALREADY, "the robot is already on the floor")
        self.check_can_move()
        stool = self.standing_on
        self._step_off(world)
        self.level, self.standing_on = Level.LOW, None
        world.emit("robot_climbed_down", cell=list(self.cell), facing=self.facing.value, off=stool.id if stool else None)
