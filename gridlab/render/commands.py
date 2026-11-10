"""Suggested commands for a human player: what makes sense to try from the robot's current pose.

This is a convenience for the keyboard UI only (it peeks at true state to keep the list short);
the planner gets no such list. Anything else can still be typed in the command console.
"""
from __future__ import annotations

from ..core.entity import Relation
from ..core.geometry import Level


def _applicable(world, t, a) -> bool:
    r = world.robot
    if a == "pick_up":
        return t.movable and r.holding is None
    if a == "grasp":
        return t.graspable and r.holding is None
    if a == "climb":
        return t.climbable
    if a == "open":
        return not t.is_open
    if a == "close":
        return t.is_open
    if a in ("lock", "unlock"):
        return t.lock_type == "manual"
    if a == "insert_key":
        return (t.lock_type == "key" and t.key_inserted is None and r.holding is not None
                and r.holding.kind == "key" and not r.holding_fixed)
    if a in ("turn_key", "remove_key"):
        return t.key_inserted is not None
    if a == "push_in":
        return t.loc.relation is Relation.IN and t.loc.parent.kind != "door"
    if a == "look_inside":
        return t.is_open
    if a == "ask_to_leave":
        return False                       # listed separately for everyone in the lab
    return True


def suggested_commands(world) -> list[tuple[str, list]]:
    r = world.robot
    reach = [t for tid, t in world.things.items() if tid in world.known and t.is_reachable(world)]
    cmds: list[tuple[str, list]] = []
    for t in reach:
        for a in t.affordances():
            if _applicable(world, t, a):
                cmds.append((a, [t.id]))
    if r.holding is not None:
        if r.holding_fixed:
            cmds.append(("release", []))
        else:
            cmds.append(("put_down", []))
            for t in reach:
                if t is r.holding:
                    continue
                if t.surface_capacity is not None:
                    cmds.append(("put_on", [t.id]))
                if hasattr(t, "is_open") and t.is_open:
                    cmds.append(("put_in", [t.id]))
    if r.level is Level.HIGH:
        cmds.append(("climb_down", []))
    if r.docked:
        cmds.append(("undock", []))
    for t in world.things.values():
        if t.kind == "person":
            cmds.append(("ask_to_leave", [t.id]))
    cmds.append(("take_photo", []))
    return cmds


def goto_commands(world) -> list[tuple[str, list]]:
    return [("go_to", [tid]) for tid, t in sorted(world.things.items())
            if tid in world.known and t.loc.relation is not Relation.HELD]


def fmt(cmd) -> str:
    name, args = cmd
    return f"{name}({', '.join(str(a) for a in args)})"
