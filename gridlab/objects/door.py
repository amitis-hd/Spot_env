"""Doors sit in the outer wall on one edge of a border cell."""
from __future__ import annotations

from ..core.entity import Relation, Size
from ..core.errors import ActionFailure, Fail
from ..core.geometry import Direction, Level, step
from .lockable import Lockable


class Door(Lockable):
    """Reached by standing in `cell` facing `side` (towards the outside).
    Things can be put IN the doorway while it is open; they stop it from closing."""
    kind = "door"
    wall_mounted = True
    blocks_cell = False
    graspable = True
    size = Size.LARGE
    lock_type = "key"
    side = Direction.N
    state_props = Lockable.state_props + ("side",)

    def validate(self, world):
        super().validate(world)
        self.side = Direction(self.side)
        if world.in_bounds(step(self.loc.cell, self.side)):
            raise ValueError(f"{self.id}: doors must be on the outer wall")

    def is_reachable(self, world):
        r = world.robot
        return r.cell == self.loc.cell and r.facing is self.side and r.level is Level.LOW

    def approach_poses(self, world):
        return [(self.loc.cell, self.side)]

    def contents_visible(self):
        return True

    def doorway(self, world):
        return world.children(self, Relation.IN)

    def is_exit_clear(self, world) -> bool:
        return self.is_open and not self.doorway(world)

    def accept_in(self, world, obj):
        if not self.is_open:
            raise ActionFailure(Fail.IS_CLOSED, f"{self.id} is closed")
        if self.doorway(world):
            raise ActionFailure(Fail.OBSTRUCTED, "the doorway is already occupied")

    def check_close(self, world):
        stuck = self.doorway(world)
        if stuck:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} cannot close", f"{stuck[0].id} is in the doorway")
