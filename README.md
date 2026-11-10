# gridlab

A small 4x4 grid world modelling the Spot "close down the lab" experiment, so a DIARC
planner can be evaluated on harder variants without running the real robot.

Status: steps 1-4 of 6 (core model, lab objects, scenarios, graphics + keyboard play). The socket server follows.

```bash
pip install -e .[dev]
python -m pytest -q
```

## Scenarios

The default lab is `gridlab/scenarios/default_lab.yaml`. Random labs keep its fixed furniture and
shuffle everything else; `difficulty` 0-4 selects a preset of knobs (see `gridlab/scenarios/generator.py`).

```bash
python -m gridlab.scenarios generate --seed 3 --difficulty 2 -o lab.yaml   # save a random lab
python -m gridlab.scenarios generate --seed 3 --difficulty 4 --knob people=0
python -m gridlab.scenarios show lab.yaml                                  # true state as text
python -m gridlab.scenarios solve lab.yaml                                 # scripted oracle solution
```

```python
from gridlab.scenarios import build_default_lab, load_scenario
from gridlab.scenarios.generator import generate_spec
w = build_default_lab()                       # or load_scenario("lab.yaml") / build_world(generate_spec(3, 2))
w.execute("go_to", ["drawer_2"])              # -> {"ok": ..., "code": ..., "events": [...], ...}
w.get_world(); w.check_goal()
```

The oracle (`gridlab/tasks/oracle.py`) reads the true state but acts only through `execute`;
every generated lab is checked solvable by it in the tests. Typical oracle action counts:
difficulty 0 ~36, 1 ~44, 2 ~54, 3 ~78, 4 ~82 (default lab: 38).

## Adding an object type

Subclass `Thing`, set class attributes, add `@action` methods; it is then usable in YAML by class
name (put the module under `imports:` in the scenario). See `Plant` in `tests/test_scenarios.py`.

## Play it yourself

```bash
python -m gridlab.play                          # default lab
python -m gridlab.play --seed 3 --difficulty 3  # a random lab
python -m gridlab.play --scenario lab.yaml --verbose
```

| key | does |
|---|---|
| arrows | face that way; press again to step forward (on a stool / docked: turn only) |
| 1-9, PgUp/PgDn | run an action from the menu |
| a / g | menu: actions possible here / go to an object |
| p | take a photo (shown in the panel) |
| `:` or Enter | type any command, e.g. `put_on book_1 light_button`, `go_to 3 0 W` |
| o | watch the oracle solve the lab (any key stops it) |
| r / q | restart / quit |

## Graphics and photos

Every cell is drawn as a front view: HIGH level on top, LOW level below. `take_photo` returns the
cell in front of the robot drawn the same way, as a PNG (base64), with no labels or text.
Sprites live in `gridlab/render/assets/` (one PNG per object state); replace any of them with your
own art, or regenerate the defaults with `python -m gridlab.render.sprites`. A custom object type
can name its own sprite with a class attribute `sprite = "my_sprite"` (file `assets/my_sprite.png`).
