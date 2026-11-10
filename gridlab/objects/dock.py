"""Charging dock: the robot drives onto it from a neighbouring cell."""
from __future__ import annotations

from ..core.entity import Thing, action
from ..core.errors import ActionFailure, Fail
from ..core.geometry import Level


class Dock(Thing):
    kind = "dock"

    @action(free_hand=True)
    def dock(self, world):
        "Drive onto the dock (in front of the robot) and start charging. Gripper must be empty."
        r = world.robot
        if r.docked:
            raise ActionFailure(Fail.ALREADY, "already docked")
        if r.level is not Level.LOW:
            raise ActionFailure(Fail.MUST_CLIMB_DOWN, "the robot is standing on something")
        if world.children(self):
            raise ActionFailure(Fail.OBSTRUCTED, "the dock is not clear", f"{world.children(self)[0].id} is on the dock")
        r.check_can_move()
        r.came_from = r.cell
        r.cell = self.loc.cell
        r.docked = True
        world.emit("docked", dock=self.id)
