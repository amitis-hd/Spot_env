"""Random labs for evaluation.

The fixed furniture of the default lab (counters with drawers, wall cabinets, shelf,
table with lamp and light button, the two doors) stays where it is. Everything else is
placed at random from a seed: robot, dock, stool, chair, people, keys, items, and the
starting state of doors and drawers. `difficulty` (0-4) picks a preset of knobs; any
knob can be overridden:

    generate_spec(seed=7, difficulty=3, people=0)

Knobs
    people          number of people in the lab (0-3)
    stubborn        how many of them refuse the first request
    door_key        where the door key is: counter | drawer | cabinet | locked_drawer
    drawer_key      where the drawer key is: counter | drawer | cabinet
    book            where the book (the heavy enough object) is: table | any | cabinet
    protruding      items sticking out of open drawers (0-2); the first is the binder (must be removed),
                    the second a pen (can be pushed in)
    doorway_block   put the chair in an open doorway
    doors           open | mixed | closed | locked
    decoy_keys      keys that open nothing
    hide_key_targets  planner is not told what each key opens
"""
from __future__ import annotations

import random
from copy import deepcopy

from ..core.geometry import Direction, step

PRESETS: dict[int, dict] = {
    0: dict(people=0, stubborn=0, door_key="counter", drawer_key="counter", book="table", protruding=0,
            doorway_block=False, doors="open", decoy_keys=0, hide_key_targets=False),
    1: dict(people=1, stubborn=0, door_key="drawer", drawer_key="counter", book="table", protruding=1,
            doorway_block=False, doors="mixed", decoy_keys=0, hide_key_targets=False),
    2: dict(people=1, stubborn=0, door_key="cabinet", drawer_key="counter", book="table", protruding=1,
            doorway_block=False, doors="mixed", decoy_keys=0, hide_key_targets=False),
    3: dict(people=2, stubborn=1, door_key="locked_drawer", drawer_key="cabinet", book="any", protruding=1,
            doorway_block=True, doors="mixed", decoy_keys=1, hide_key_targets=False),
    4: dict(people=3, stubborn=2, door_key="locked_drawer", drawer_key="cabinet", book="cabinet", protruding=2,
            doorway_block=True, doors="locked", decoy_keys=2, hide_key_targets=True),
}

W, H = 4, 4
COUNTERS = {"counter_1": (0, 0), "counter_2": (1, 0), "counter_3": (2, 0)}
DRAWERS = {"drawer_1": (0, 0), "drawer_2": (1, 0)}
CABINETS = {"cabinet_1": (0, 0), "cabinet_2": (1, 0)}
TABLE = (2, 2)
DOORS = {"door_1": ((0, 2), "W"), "door_2": ((1, 3), "S")}
PEOPLE_NAMES = ["alex", "sam", "kim"]

FIXED_CELLS = set(COUNTERS.values()) | {TABLE}
DOOR_CELLS = {c for c, _ in DOORS.values()}
FLOOR = [(x, y) for y in range(H) for x in range(W) if (x, y) not in FIXED_CELLS]


def _front(cell):
    return step(cell, Direction.S)


# cells the dock must never take: door cells, the cells in front of counters, and the
# second cell in front of each wall cabinet (where the robot stands to climb the stool)
RESERVED = DOOR_CELLS | {_front(c) for c in COUNTERS.values()} | {_front(_front(c)) for c in CABINETS.values()}


class GenerationError(RuntimeError):
    pass


def generate_spec(seed: int = 0, difficulty: int = 2, max_tries: int = 200, **overrides) -> dict:
    if difficulty not in PRESETS:
        raise ValueError("difficulty must be 0-4")
    knobs = {**PRESETS[difficulty], **overrides}
    unknown = set(overrides) - set(PRESETS[0])
    if unknown:
        raise ValueError(f"unknown knobs: {sorted(unknown)}")
    rng = random.Random(seed)
    for _ in range(max_tries):
        spec = _attempt(rng, knobs)
        if spec is not None and accessibility_problems(spec) == []:
            spec["name"] = f"random_s{seed}_d{difficulty}"
            spec["meta"] = {"seed": seed, "difficulty": difficulty, "knobs": deepcopy(knobs)}
            return spec
    raise GenerationError(f"could not generate a valid lab for seed={seed} knobs={knobs}")


def _attempt(rng: random.Random, k: dict) -> dict | None:
    objs: list[dict] = []
    add = objs.append

    # ---------------- fixed furniture
    for cid, cell in COUNTERS.items():
        add({"id": cid, "type": "Counter", "cell": list(cell)})
    add({"id": "shelf_1", "type": "Shelf", "cell": [2, 0], "level": "high"})
    for cid, cell in CABINETS.items():
        add({"id": cid, "type": "Cabinet", "cell": list(cell), "level": "high"})
    add({"id": "table_1", "type": "Table", "cell": list(TABLE)})
    add({"id": "lamp_1", "type": "Lamp", "on": "table_1"})
    add({"id": "light_button", "type": "LightButton", "on": "table_1", "controls": ["lamp_1"]})

    # ---------------- doors
    door_ids = list(DOORS)
    states = {"open": ["open", "open"], "closed": ["closed", "closed"], "locked": ["locked", "locked"],
              "mixed": rng.sample(["open", "closed"], 2)}[k["doors"]]
    door_state = dict(zip(door_ids, states))
    for did, (cell, side) in DOORS.items():
        st = door_state[did]
        add({"id": did, "type": "Door", "cell": list(cell), "side": side,
             "is_open": st == "open", "locked": st == "locked"})
    open_doors = [d for d in door_ids if door_state[d] == "open"]

    # ---------------- drawers (both use the drawer key)
    drawer_ids = list(DRAWERS)
    rng.shuffle(drawer_ids)
    dstate = {d: rng.choice(["open", "closed", "locked"]) for d in drawer_ids}
    if k["door_key"] == "locked_drawer":
        dstate[drawer_ids[0]] = "locked"
    if k["door_key"] == "drawer" or k["drawer_key"] == "drawer":
        if all(dstate[d] == "locked" for d in drawer_ids):
            dstate[drawer_ids[-1]] = "closed"
    openable = [d for d in drawer_ids if not (k["door_key"] == "locked_drawer" and d == drawer_ids[0])]
    n_prot = min(k["protruding"], len(openable))
    for d in openable[:n_prot]:
        dstate[d] = "open"
    for did, cell in DRAWERS.items():
        st = dstate[did]
        add({"id": did, "type": "Drawer", "cell": list(cell), "lock_type": "key",
             "auto_lock": rng.random() < 0.5, "is_open": st == "open", "locked": st == "locked"})

    # ---------------- where small things can go
    def unlocked_closed_drawers():
        return [d for d in drawer_ids if dstate[d] == "closed"]

    def place(where: str) -> dict:
        if where == "counter":
            return {"on": rng.choice(list(COUNTERS))}
        if where == "table":
            return {"on": "table_1"}
        if where == "shelf":
            return {"on": "shelf_1"}
        if where == "cabinet":
            return {"inside": rng.choice(list(CABINETS))}
        if where == "drawer":
            options = unlocked_closed_drawers() or [d for d in drawer_ids if dstate[d] == "open"]
            return {"inside": rng.choice(options)} if options else place("counter")
        if where == "locked_drawer":
            return {"inside": drawer_ids[0]}
        raise ValueError(where)

    # ---------------- keys (neutral names: the id does not say what a key opens)
    key_names = [f"key_{c}" for c in "abcdefg"]
    rng.shuffle(key_names)
    door_key, drawer_key = key_names[0], key_names[1]
    add({"id": door_key, "type": "Key", "opens": door_ids, **place(k["door_key"])})
    drawer_key_where = k["drawer_key"]
    if k["door_key"] == "locked_drawer" and drawer_key_where == "drawer":
        drawer_key_where = "counter"     # the drawer key may not be locked away with the door key
    dk = place(drawer_key_where)
    if dk.get("inside") == drawer_ids[0] and dstate[drawer_ids[0]] == "locked":
        dk = place("counter")
    add({"id": drawer_key, "type": "Key", "opens": list(DRAWERS), **dk})
    for i in range(k["decoy_keys"]):
        add({"id": key_names[2 + i], "type": "Key", "opens": [],
             **place(rng.choice(["counter", "table", "drawer", "shelf"]))})

    # ---------------- items and obstructions
    open_drawers = [d for d in drawer_ids if dstate[d] == "open"]
    prot = open_drawers[:n_prot]
    if prot:
        add({"id": "binder_1", "type": "Binder", "inside": prot[0], "protruding": True})
    else:
        add({"id": "binder_1", "type": "Binder", **place(rng.choice(["counter", "table"]))})
    if len(prot) > 1:
        add({"id": "pen_1", "type": "Pen", "inside": prot[1], "protruding": True})
    else:
        add({"id": "pen_1", "type": "Pen", **place(rng.choice(["counter", "table", "drawer"]))})
    add({"id": "mug_1", "type": "Mug", **place(rng.choice(["counter", "table", "shelf"]))})
    book_where = {"table": "table", "cabinet": "cabinet",
                  "any": rng.choice(["counter", "table", "drawer", "cabinet"])}[k["book"]]
    add({"id": "book_1", "type": "Book", **place(book_where)})

    # ---------------- floor things
    free = [c for c in FLOOR]
    rng.shuffle(free)

    def take(allowed) -> list[int] | None:
        for c in free:
            if c in allowed:
                free.remove(c)
                return list(c)
        return None

    dock = take([c for c in FLOOR if c not in RESERVED])
    if dock is None:
        return None
    add({"id": "dock_1", "type": "Dock", "cell": dock})
    not_door = [c for c in FLOOR if c not in DOOR_CELLS]
    stool = take(not_door)
    add({"id": "stool_1", "type": "Stool", "cell": stool})
    if k["doorway_block"] and open_doors:
        add({"id": "chair_1", "type": "Chair", "inside": rng.choice(open_doors)})
    else:
        add({"id": "chair_1", "type": "Chair", "cell": take(not_door)})
    for i in range(k["people"]):
        policy = {"type": "stubborn", "refusals": 1} if i < k["stubborn"] else {"type": "compliant"}
        cell = take([c for c in FLOOR if c not in RESERVED])   # people never stand where the robot must work
        if cell is None:
            return None
        add({"id": PEOPLE_NAMES[i], "type": "Person", "cell": cell, "policy": policy})
    robot_cell = take(FLOOR)
    if robot_cell is None or stool is None:
        return None

    return {
        "grid": {"width": W, "height": H},
        "config": {"verbose_failures": False, "hide_key_targets": bool(k["hide_key_targets"])},
        "goal": {"type": "close_lab", "container_kinds": ["drawer"]},
        "robot": {"id": "spot", "cell": robot_cell, "facing": rng.choice("NESW")},
        "objects": objs,
    }


def accessibility_problems(spec: dict) -> list[str]:
    """Structural checks that keep a lab solvable.

    A cell is *usable* if the robot can (eventually) stand in it: it is empty, or it holds only
    movable things and a neighbouring cell is usable (so they can be picked up and carried off).
    People count as permanent obstacles (they may be stuck until a door is unlocked) and the
    dock as fixed. Every object the robot may need to work on must have a usable side, and every
    wall cabinet needs two usable cells in a line in front of it (stool + robot)."""
    fixed_types = {"Counter", "Table", "Dock", "Person"}
    occupants: dict[tuple, list[str]] = {}
    for o in spec["objects"]:
        if "cell" in o and o.get("level", "low") == "low" and o["type"] != "Door":
            occupants.setdefault(tuple(o["cell"]), []).append(o["type"])
    blocked = {c for c, types in occupants.items() if any(t in fixed_types for t in types)}

    def inb(c):
        return 0 <= c[0] < W and 0 <= c[1] < H

    usable = {(x, y) for x in range(W) for y in range(H) if (x, y) not in occupants}
    changed = True
    while changed:
        changed = False
        for c in occupants:
            if c not in usable and c not in blocked and any(step(c, d) in usable for d in Direction):
                usable.add(c)
                changed = True

    problems = []
    for o in spec["objects"]:
        if "cell" not in o or o.get("level") == "high" or o["type"] in ("Door", "Person"):
            continue
        c = tuple(o["cell"])
        if not any(step(c, d) in usable for d in Direction):
            problems.append(f"{o['id']} has no reachable side")
    for o in spec["objects"]:
        if o["type"] == "Cabinet":
            front = _front(tuple(o["cell"]))
            if not (inb(front) and front in usable and _front(front) in usable):
                problems.append(f"{o['id']}: no room for stool + robot")
        if o["type"] == "Door" and tuple(o["cell"]) not in usable:
            problems.append(f"{o['id']}: door cell is blocked")
    return problems
