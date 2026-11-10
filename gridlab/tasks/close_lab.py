"""Goal of the experiment: close down the lab."""
from __future__ import annotations

from ..objects import Door, Lamp, Lockable, Person


class CloseLabGoal:
    """
    1. no people in the lab
    2. all drawers closed and locked   (`container_kinds`, default only drawers)
    3. all doors closed and locked
    4. the light is on
    5. the robot is docked
    Things without a lock only need to be closed.
    """

    def __init__(self, container_kinds=("drawer",)):
        self.container_kinds = tuple(container_kinds)

    @staticmethod
    def _secured(t: Lockable) -> bool:
        return not t.is_open and (t.locked or t.lock_type == "none")

    def check(self, world) -> dict:
        things = list(world.things.values())
        lamps = [t for t in things if isinstance(t, Lamp)]
        cond = {
            "no_people": not any(isinstance(t, Person) for t in things),
            "drawers_closed_locked": all(self._secured(t) for t in things
                                         if isinstance(t, Lockable) and t.kind in self.container_kinds),
            "doors_closed_locked": all(self._secured(t) for t in things if isinstance(t, Door)),
            "light_on": bool(lamps) and all(l.on for l in lamps),
            "docked": world.robot.docked,
        }
        return {"achieved": all(cond.values()), "conditions": cond}
