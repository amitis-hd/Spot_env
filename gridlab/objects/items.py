"""Small movable items."""
from __future__ import annotations

from ..core.entity import Size, Thing


class Item(Thing):
    kind = "item"
    movable = True
    size = Size.SMALL
    weight = 0.3


class Book(Item):
    kind = "book"
    weight = 1.2
    surface_capacity = Size.SMALL   # a pen or key can rest on a book


class Binder(Item):
    kind = "binder"
    weight = 1.0


class Pen(Item):
    kind = "pen"
    weight = 0.02


class Mug(Item):
    kind = "mug"
    weight = 0.3
