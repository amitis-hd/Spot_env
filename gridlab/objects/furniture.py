"""Fixed furniture (counters, tables, shelves) and climbable furniture (stool, chair)."""
from __future__ import annotations

from ..core.entity import Relation, Size, Thing, action
from ..core.errors import ActionFailure, Fail
from ..core.geometry import Level


class Counter(Thing):
    """Low kitchen-style counter. Fills its cell; things can be put on top."""
    kind = "counter"
    blocks_cell = True
    size = Size.LARGE
    surface_capacity = Size.MEDIUM


class Table(Thing):
    kind = "table"
    blocks_cell = True
    size = Size.LARGE
    surface_capacity = Size.MEDIUM


class Shelf(Thing):
    """Wall-mounted shelf, normally at HIGH level above a counter."""
    kind = "shelf"
    size = Size.LARGE
    surface_capacity = Size.MEDIUM


class Climbable(Thing):
    """Movable furniture the robot can stand on to reach the HIGH level of the next cell."""
    kind = "climbable"
    movable = True
    climbable = True
    size = Size.LARGE
    surface_capacity = Size.MEDIUM
    weight = 4.0

    @action(reach=True)
    def climb(self, world):
        "Climb onto this; the robot ends up at HIGH level in this thing's cell, same heading."
        r = world.robot
        if r.level is Level.HIGH:
            raise ActionFailure(Fail.ALREADY, "the robot is already up")
        if self.loc.relation is not Relation.AT:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} must stand on the floor to be climbed")
        if world.children(self, Relation.ON):
            raise ActionFailure(Fail.OBSTRUCTED, f"cannot climb {self.id}", "something is lying on it")
        cell = self.loc.cell
        others = [t.id for t in world.things_at(cell) if t is not self]
        if others:
            raise ActionFailure(Fail.OBSTRUCTED, f"cannot climb {self.id}", f"{others[0]} is in the same cell")
        r.check_can_move()
        r.came_from = r.cell
        r.cell, r.level, r.standing_on = cell, Level.HIGH, self
        world.emit("robot_climbed", on=self.id, cell=list(cell))


class Stool(Climbable):
    kind = "stool"


class Chair(Climbable):
    kind = "chair"
    weight = 6.0
