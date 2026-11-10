# Scenarios

A scenario is a YAML file. The default lab is
[`gridlab/scenarios/default_lab.yaml`](../gridlab/scenarios/default_lab.yaml).

```yaml
name: default_lab
imports: [my_package.my_objects]          # optional: modules with your own object classes
grid: {width: 4, height: 4}
config: {verbose_failures: false, hide_key_targets: false, photo_size: 256}
goal: {type: close_lab, container_kinds: [drawer]}
robot: {id: spot, cell: [1, 1], facing: N}
objects:
  - {id: counter_2, type: Counter, cell: [1, 0]}
  - {id: drawer_2, type: Drawer, cell: [1, 0], lock_type: key, auto_lock: true, is_open: true}
  - {id: binder_1, type: Binder, inside: drawer_2, protruding: true}
  - {id: cabinet_2, type: Cabinet, cell: [1, 0], level: high}
  - {id: key_door, type: Key, inside: cabinet_2, opens: [door_1, door_2]}
  - {id: book_1, type: Book, on: table_1}
  - {id: alex, type: Person, cell: [1, 2], policy: {type: stubborn, refusals: 1}}
  - {id: door_1, type: Door, cell: [0, 2], side: W, locked: true}
```

Every object has an `id`, a `type` (class name, e.g. `Drawer`, or kind, e.g. `drawer`) and exactly one
placement:

| placement | meaning |
|---|---|
| `cell: [x, y]` (+ `level: low/high`, default low) | directly in a cell |
| `on: <id>` | on top of another object |
| `inside: <id>` | inside a drawer/cabinet, or in a door's doorway |

Any other key sets a property. Objects may be listed in any order.

## Object types and properties

| type | blocks cell | notes / properties |
|---|---|---|
| `Counter` | yes | surface for small/medium things; put drawers in the same cell |
| `Table` | yes | surface |
| `Shelf` | yes | surface, normally `level: high` above a counter |
| `Drawer` | yes | `is_open`, `locked`, `lock_type` (none/manual/key), `auto_lock`; holds small things |
| `Cabinet` | yes | same; normally `level: high`; holds small and medium things |
| `Door` | no (in the wall) | `side` (N/E/S/W, must face outside), `is_open`, `locked`, `lock_type` (default key), `auto_lock` |
| `Key` | yes | `opens: [ids]` |
| `Book`, `Pen`, `Mug`, `Binder`, `Item` | yes | movable; `weight`, `protruding` (when inside a drawer/cabinet) |
| `Stool`, `Chair` | yes | movable, climbable |
| `LightButton` | yes | `controls: [lamp ids]`, `threshold` (weight needed, default 0.5) |
| `Lamp` | yes | `on` is derived from its buttons |
| `Person` | yes | `policy: {type: compliant}` / `{type: stubborn, refusals: N}` / `{type: my.module.MyPolicy, ...}` |
| `Dock` | yes | the robot drives onto it |

Weights: book 1.2, binder 1.0, mug 0.3, key 0.05, pen 0.02 (all overridable with `weight:`).

`config`: `verbose_failures` (send the exact cause of failures), `hide_key_targets` (do not tell the planner
what keys open), `photo_size` (pixels).

Mistakes are reported with the object id: unknown property, missing parent, a door not on the outer wall,
a thing both open and locked, ...

## Random labs

Random labs keep the fixed furniture of the default lab (counters, drawers, cabinets, shelf, table with lamp
and button, both doors) and place everything else from a seed: robot, dock, stool, chair, people, keys, items,
and the starting state of doors and drawers. `difficulty` 0-4 picks a set of knobs:

| knob | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| `people` | 0 | 1 | 1 | 2 | 3 |
| `stubborn` (refuse once) | 0 | 0 | 0 | 1 | 2 |
| `door_key` | counter | drawer | cabinet | locked_drawer | locked_drawer |
| `drawer_key` | counter | counter | counter | cabinet | cabinet |
| `book` | table | table | table | any | cabinet |
| `protruding` | 0 | 1 | 1 | 1 | 2 |
| `doorway_block` (chair in an open doorway) | no | no | no | yes | yes |
| `doors` | open | mixed | mixed | mixed | locked |
| `decoy_keys` (open nothing) | 0 | 0 | 0 | 1 | 2 |
| `hide_key_targets` | no | no | no | no | yes |

Key ids in random labs are neutral (`key_a`, `key_e`, ...). Every generated lab is checked: a reachability
analysis rejects layouts where something needed can never be reached, people are never placed where the
robot has to work, and the test-suite runs the oracle on hundreds of labs per difficulty.

Oracle action counts (average): difficulty 0 ~37, 1 ~45, 2 ~54, 3 ~77, 4 ~81; default lab 47.

```python
from gridlab.scenarios import build_world, load_scenario, spec_to_yaml
from gridlab.scenarios.generator import generate_spec
spec = generate_spec(seed=7, difficulty=3, people=0)     # any knob can be overridden
open("lab.yaml", "w").write(spec_to_yaml(spec))
w = load_scenario("lab.yaml")
```

A YAML file can also just say `generator: {seed: 7, difficulty: 3}`.

```bash
python -m gridlab.scenarios generate --seed 7 --difficulty 3 --knob people=0 -o lab.yaml
python -m gridlab.scenarios show lab.yaml       # the true state as text
python -m gridlab.scenarios solve lab.yaml      # the oracle's solution
```
