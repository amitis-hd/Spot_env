"""Base classes for everything that lives in the world.

Adding a new object type = subclass `Thing`, set a few class attributes, and add
methods decorated with `@action`. Example::

    class Box(Thing):
        kind = "box"
        movable = True
        size = Size.MEDIUM
        surface_capacity = Size.SMALL      # small things can be put on it

        @action()
        def shake(self, world):
            "Shake the box."
            world.emit("rattled", obj=self.id)

The decorated method receives the world plus any extra arguments the planner sent
after the target id; raise `ActionFailure` to report a failure.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Any

from .errors import ActionFailure, Fail
from .geometry import Level, Pos

if TYPE_CHECKING:
    from .world import World


class Size(IntEnum):
    SMALL = 1    # pen, key, book, mug
    MEDIUM = 2   # box, binder stack
    LARGE = 3    # stool, chair


class Relation(str, Enum):
    AT = "at"      # directly in a grid cell at a level
    ON = "on"      # on top of another thing
    IN = "in"      # inside a container
    HELD = "held"  # in the robot's gripper


@dataclass
class Location:
    relation: Relation
    cell: Pos | None = None
    level: Level | None = None
    parent: "Thing | None" = None


@dataclass(frozen=True)
class ActionSpec:
    name: str
    reach: bool = True       # target must be within the robot's reach
    free_hand: bool = False  # gripper must be empty
    holding: bool = False    # gripper must hold something
    doc: str = ""


def action(name: str | None = None, *, reach: bool = True, free_hand: bool = False, holding: bool = False):
    """Mark a method as an action the planner can invoke on this entity."""

    def deco(fn):
        doc = (fn.__doc__ or "").strip().splitlines()
        fn._gl_action = ActionSpec(name or fn.__name__, reach, free_hand, holding, doc[0] if doc else "")
        return fn

    return deco


def jsonable(v: Any) -> Any:
    if isinstance(v, Enum):
        return v.value
    if isinstance(v, Entity):
        return v.id
    if isinstance(v, (list, tuple, set, frozenset)):
        return [jsonable(x) for x in v]
    if isinstance(v, dict):
        return {k: jsonable(x) for k, x in v.items()}
    return v


class Entity:
    kind = "entity"
    #: attributes never sent to the planner (e.g. weight: the planner must find out by trying)
    hidden_props: frozenset[str] = frozenset({"weight"})
    #: attributes reported in the "state" field of observations
    state_props: tuple[str, ...] = ()
    #: action name -> (spec, method attribute name); filled in automatically
    _actions: dict[str, tuple[ActionSpec, str]] = {}

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        acts: dict[str, tuple[ActionSpec, str]] = {}
        for klass in reversed(cls.__mro__):
            for attr, val in vars(klass).items():
                spec = getattr(val, "_gl_action", None)
                if spec is not None:
                    acts[spec.name] = (spec, attr)
        cls._actions = acts

    def __init__(self, id: str, **props):
        self.id = id
        self.loc: Location | None = None
        for k, v in props.items():
            if not hasattr(self, k):
                raise TypeError(f"{type(self).__name__} has no property '{k}'")
            setattr(self, k, v)

    @classmethod
    def affordances(cls) -> list[str]:
        return sorted(cls._actions)

    def public_state(self) -> dict:
        return {p: jsonable(getattr(self, p)) for p in self.state_props if p not in self.hidden_props}

    def __repr__(self):
        return f"<{type(self).__name__} {self.id}>"


class Thing(Entity):
    """Anything placed in the grid: furniture, items, containers, people, ..."""

    kind = "thing"
    movable = False
    climbable = False
    graspable = False                      # fixed thing the gripper can hold on to (door handle, ...)
    blocks_cell = True                     # the robot cannot enter a cell holding this
    obstructs_drop = False                 # nothing can be put down in its place (e.g. a person)
    size = Size.SMALL
    surface_capacity: Size | None = None   # largest size that can be put ON this (None = not a surface)
    weight = 1.0

    # ---------------- hooks for subclasses ----------------
    def contents_visible(self) -> bool:
        """Are things IN this entity currently visible (e.g. drawer open)?"""
        return True

    def check_pick_up(self, world: "World") -> None:
        """Raise ActionFailure if this cannot be lifted right now."""

    def accept_on(self, world: "World", obj: "Thing") -> None:
        """Raise ActionFailure if `obj` cannot be put on this."""
        if self.surface_capacity is None:
            raise ActionFailure(Fail.CANNOT_SUPPORT, f"cannot put things on {self.id}")
        if obj.size > self.surface_capacity:
            raise ActionFailure(Fail.CANNOT_SUPPORT, f"{obj.id} does not fit on {self.id}",
                                f"{obj.id} is too large for {self.id}")

    def accept_in(self, world: "World", obj: "Thing") -> None:
        """Raise ActionFailure if `obj` cannot be put inside this."""
        raise ActionFailure(Fail.NOT_SUPPORTED, f"{self.id} is not a container")

    def is_reachable(self, world: "World") -> bool:
        return world.default_reachable(self)

    def approach_poses(self, world: "World"):
        """(cell, facing) poses from which the robot can act on this; used by go_to."""
        return world.default_approach_poses(self)

    def update(self, world: "World") -> None:
        """Called after every successful action; recompute derived state, emit events."""

    def extra_observation(self, world: "World") -> dict:
        return {}

    # ---------------- generic actions ----------------
    @action(free_hand=True)
    def pick_up(self, world: "World"):
        "Pick this up with the gripper."
        if not self.movable:
            raise ActionFailure(Fail.NOT_MOVABLE, f"{self.id} cannot be picked up")
        if world.robot.standing_on is self:
            raise ActionFailure(Fail.OBSTRUCTED, f"cannot pick up {self.id}", "the robot is standing on it")
        self.check_pick_up(world)
        world.move(self, Location(Relation.HELD))
        world.emit("picked_up", obj=self.id)

    @action(free_hand=True)
    def grasp(self, world: "World"):
        "Hold on to this fixed object; the robot cannot move until it releases it."
        if self.movable:
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{self.id} is movable; use pick_up")
        if not self.graspable:
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{self.id} cannot be grasped")
        world.robot.holding = self
        world.emit("grasped", obj=self.id)
