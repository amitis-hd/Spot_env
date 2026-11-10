"""Grid coordinates, levels and headings.

Coordinates are (x, y) with x growing east (right) and y growing south (down);
row y=0 is the north wall of the lab.
"""
from __future__ import annotations

from enum import Enum

Pos = tuple[int, int]


class Level(str, Enum):
    LOW = "low"    # floor, counters, drawers, tables
    HIGH = "high"  # wall cabinets, shelves; reachable only when standing on something


class Direction(str, Enum):
    N = "N"
    E = "E"
    S = "S"
    W = "W"

    @property
    def delta(self) -> Pos:
        return _DELTA[self]

    @property
    def opposite(self) -> "Direction":
        return _OPPOSITE[self]


_DELTA = {Direction.N: (0, -1), Direction.E: (1, 0), Direction.S: (0, 1), Direction.W: (-1, 0)}
_OPPOSITE = {Direction.N: Direction.S, Direction.S: Direction.N, Direction.E: Direction.W, Direction.W: Direction.E}


def step(pos: Pos, d: Direction) -> Pos:
    dx, dy = d.delta
    return pos[0] + dx, pos[1] + dy


def direction_between(a: Pos, b: Pos) -> Direction | None:
    """Heading that takes you from a to the 4-neighbour b, or None if not adjacent."""
    for d in Direction:
        if step(a, d) == b:
            return d
    return None
