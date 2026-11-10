# Extending gridlab

## A new object type

Subclass `Thing` (or a closer base such as `Item`, `Container`, `Lockable`, `Climbable`), set class
attributes, and add actions with `@action`. Any class that has been imported can be used in a scenario by its
class name; list its module under `imports:` in the YAML.

```python
from gridlab.core import ActionFailure, Fail, Size, Thing, action

class Plant(Thing):
    kind = "plant"            # name used in observations
    movable = True            # can be picked up
    size = Size.SMALL
    weight = 0.8              # hidden from the planner
    watered = False
    state_props = ("watered",)          # reported in the object's "state"
    sprite = "plant"                    # optional: gridlab/render/assets/plant.png

    @action(free_hand=True)             # reach=True by default: must be in front of the robot
    def water(self, world):
        "Water the plant."              # first docstring line is shown by LIST_ACTIONS
        if self.watered:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is already watered")
        self.watered = True
        world.emit("watered", obj=self.id)
```

```yaml
imports: [my_lab.plants]
objects:
  - {id: fern, type: Plant, on: counter_3}
```

The planner can then send `water fern`. Extra arguments after the target id are passed to the method
(object ids are resolved to objects).

### Class attributes

| attribute | default | meaning |
|---|---|---|
| `kind` | — | type name in observations |
| `movable` | False | `pick_up` allowed |
| `climbable` | False | can be climbed (use `Climbable` as base) |
| `graspable` | False | a fixed thing the gripper can hold on to |
| `blocks_cell` | True | the robot cannot stand in its cell |
| `obstructs_drop` | False | nothing can be put down in its cell (people) |
| `wall_mounted` | False | lives in a wall edge (doors) |
| `size` | SMALL | SMALL / MEDIUM / LARGE |
| `surface_capacity` | None | largest size that can be put on it (None: not a surface) |
| `weight` | 1.0 | hidden |
| `state_props` | () | attributes reported in `state` |
| `hidden_props` | weight, protruding | never reported |

### Action options

`@action(name=None, reach=True, free_hand=False, holding=False)`: `reach` checks the target is in front of
the robot at its level; `free_hand` / `holding` check the gripper. The method gets `(self, world, *args)`
and may return a dict, sent as `data`. Raise `ActionFailure(Fail.X, "short message", "detailed cause")`;
the detailed cause is only sent in verbose mode.

### Hooks

| method | when |
|---|---|
| `contents_visible()` | are things inside it visible (containers: while open) |
| `check_pick_up(world)` | raise to refuse `pick_up` |
| `accept_on(world, obj)` / `accept_in(world, obj)` | raise to refuse `put_on` / `put_in` |
| `on_put_in(world, obj)` | after something was put inside |
| `is_reachable(world)` / `approach_poses(world)` | custom reach / where `go_to` puts the robot |
| `update(world)` | after every successful action (derived state, events; e.g. the lamp) |
| `validate(world)` | when the scenario is loaded; raise `ValueError` for impossible setups |
| `affords(name)` | whether an action is listed in `affordances` |

Useful `world` methods: `children(t, relation)`, `things_at(cell, level)`, `root(t)` (cell, level, held),
`move(t, Location(...))`, `emit(type, **data)`, `resolve(id)`, `robot`.

## Person behaviour

```python
from gridlab.agents import PersonPolicy

class NeedsReason(PersonPolicy):
    def on_ask_to_leave(self, world, person) -> str:
        person.wants_to_leave = True
        return "Fine, I'll go."

    def step(self, world, person):          # after every robot action
        door = world.open_exit()
        if person.wants_to_leave and door is not None:
            person.leave(world, door)
```

```yaml
  - {id: kim, type: Person, cell: [3, 0], policy: {type: my_lab.people.NeedsReason}}
```

## Sprites

`python -m gridlab.render.sprites` regenerates the default PNGs in `gridlab/render/assets/`. Replace any file
with your own art (transparent background); it is scaled to the size listed in `SIZES` in
`gridlab/render/sprites.py`. New sprite names need an entry in `SIZES`, otherwise a default size is used.

## Goals

A goal is any object with `check(world) -> {"achieved": bool, "conditions": {...}}`; register it in
`GOALS` in `gridlab/scenarios/loader.py` to use it from YAML.
