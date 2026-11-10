"""Drawers and cabinets: lockable containers whose contents are hidden while closed."""
from __future__ import annotations

from ..core.entity import Relation, Size, action
from ..core.errors import ActionFailure, Fail
from .lockable import Lockable


class Container(Lockable):
    kind = "container"
    size = Size.LARGE
    #: largest size that fits completely; one size bigger goes in but sticks out; bigger does not go in
    inner_capacity = Size.SMALL

    def contents_visible(self):
        return self.is_open

    def accept_in(self, world, obj):
        if not self.is_open:
            raise ActionFailure(Fail.IS_CLOSED, f"{self.id} is closed")
        if obj.size > self.inner_capacity + 1:
            raise ActionFailure(Fail.CANNOT_SUPPORT, f"{obj.id} does not fit in {self.id}")

    def on_put_in(self, world, obj):
        obj.protruding = obj.size > self.inner_capacity

    def check_close(self, world):
        stuck = [t for t in world.children(self, Relation.IN) if t.protruding]
        if stuck:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} cannot close", f"{stuck[0].id} is sticking out of {self.id}")

    @action()
    def look_inside(self, world):
        "List what is inside (must be open)."
        if not self.is_open:
            raise ActionFailure(Fail.IS_CLOSED, f"{self.id} is closed")
        return {"contents": [t.id for t in world.children(self, Relation.IN)]}


class Drawer(Container):
    """Pull-out drawer in a counter (LOW level)."""
    kind = "drawer"


class Cabinet(Container):
    """Wall cabinet with doors (normally HIGH level)."""
    kind = "cabinet"
    inner_capacity = Size.MEDIUM
