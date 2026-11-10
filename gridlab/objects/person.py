"""People in the lab. Their reactions come from a pluggable PersonPolicy."""
from __future__ import annotations

from ..agents.person_policy import CompliantPolicy, PersonPolicy
from ..core.entity import Size, Thing, action


class Person(Thing):
    kind = "person"
    size = Size.LARGE
    obstructs_drop = True
    weight = 70.0

    def __init__(self, id: str, policy: PersonPolicy | None = None, **props):
        self.policy = policy or CompliantPolicy()
        self.wants_to_leave = False
        super().__init__(id, **props)

    @action(reach=False)
    def ask_to_leave(self, world):
        "Ask this person to leave the lab."
        reply = self.policy.on_ask_to_leave(world, self)
        world.emit("person_said", person=self.id, text=reply)

    def update(self, world):
        self.policy.step(world, self)

    def leave(self, world, door):
        world.remove(self)
        world.emit("person_left", person=self.id, via=door.id)
