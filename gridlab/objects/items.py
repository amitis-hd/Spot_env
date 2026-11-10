"""Small movable items."""
from __future__ import annotations

from ..core.entity import Relation, Size, Thing, action
from ..core.errors import ActionFailure, Fail


class Item(Thing):
    kind = "item"
    movable = True
    size = Size.SMALL
    weight = 0.3

    @action(free_hand=True)
    def push_in(self, world):
        "Push this further into the drawer/cabinet it is sticking out of."
        box = self.loc.parent if self.loc.relation is Relation.IN else None
        if box is None or not hasattr(box, "inner_capacity"):
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{self.id} is not in a drawer or cabinet")
        if not self.protruding:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is already fully inside")
        if self.size > box.inner_capacity:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} does not go in any further",
                                f"{self.id} is too large for {box.id}")
        self.protruding = False
        world.emit("pushed_in", obj=self.id)


class Book(Item):
    kind = "book"
    weight = 1.2
    surface_capacity = Size.SMALL   # a pen or key can rest on a book


class Binder(Item):
    """A thick binder: too tall for a drawer, so it sticks out of one."""
    kind = "binder"
    size = Size.MEDIUM
    weight = 1.0


class Pen(Item):
    kind = "pen"
    weight = 0.02


class Mug(Item):
    kind = "mug"
    weight = 0.3


class Key(Item):
    """A key; `opens` lists the ids of the drawers/cabinets/doors it locks and unlocks."""
    kind = "key"
    weight = 0.05
    opens: tuple = ()
    state_props = ("opens",)

    def check_pick_up(self, world):
        if self.loc.relation is Relation.INSERTED:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} is in a lock; use remove_key")
