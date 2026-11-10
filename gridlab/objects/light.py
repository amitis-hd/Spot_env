"""Light button and lamp.

The button is pressed while the things resting on it weigh at least `threshold`,
or while the robot holds it down (grasp). The planner never sees weights or the
button's pressed state; it only sees whether the lamp is on.
"""
from __future__ import annotations

from ..core.entity import Size, Thing


class LightButton(Thing):
    kind = "button"
    surface_capacity = Size.SMALL
    graspable = True          # grasp = hold it down by hand
    blocks_cell = True
    threshold = 0.5
    controls: tuple = ()      # lamp ids
    hidden_props = Thing.hidden_props | {"threshold"}
    state_props = ("controls",)

    def load(self, world) -> float:
        total, stack = 0.0, world.children(self)
        while stack:
            t = stack.pop()
            total += t.weight
            stack += world.children(t)
        return total

    def is_pressed(self, world) -> bool:
        return world.robot.holding is self or self.load(world) >= self.threshold


class Lamp(Thing):
    kind = "lamp"
    on = False
    state_props = ("on",)

    def update(self, world):
        buttons = [t for t in world.things.values() if isinstance(t, LightButton) and self.id in t.controls]
        now = any(b.is_pressed(world) for b in buttons)
        if now != self.on:
            self.on = now
            world.emit("light_on" if now else "light_off", lamp=self.id)
