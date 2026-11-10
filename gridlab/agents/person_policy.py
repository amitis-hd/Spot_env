"""How people in the lab react. Subclass PersonPolicy to plug in your own agent.

Hooks:
    on_ask_to_leave(world, person) -> str   reply text; may set person.wants_to_leave
    step(world, person)                     called after every successful robot action
"""
from __future__ import annotations


class PersonPolicy:
    def on_ask_to_leave(self, world, person) -> str:
        return "..."

    def step(self, world, person) -> None:
        pass


class CompliantPolicy(PersonPolicy):
    """Agrees to leave, and walks out as soon as a door is open and its doorway is clear."""

    def on_ask_to_leave(self, world, person) -> str:
        person.wants_to_leave = True
        if world.open_exit() is not None:
            return "Sure, I'm leaving."
        return "OK, but the doors are closed."

    def step(self, world, person) -> None:
        if person.wants_to_leave:
            door = world.open_exit()
            if door is not None:
                person.leave(world, door)


class StubbornPolicy(CompliantPolicy):
    """Refuses the first `refusals` requests, then behaves like CompliantPolicy."""

    def __init__(self, refusals: int = 1):
        self.refusals = refusals

    def on_ask_to_leave(self, world, person) -> str:
        if self.refusals > 0:
            self.refusals -= 1
            return "Not now, I'm busy."
        return super().on_ask_to_leave(world, person)
