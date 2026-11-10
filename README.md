# gridlab

A small 4x4 grid world modelling the Spot "close down the lab" experiment, so a DIARC
planner can be evaluated on harder variants without running the real robot.

Status: steps 1-5 of 6 (core model, lab objects, scenarios, graphics + keyboard play, socket server).

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
difficulty 0 ~37, 1 ~45, 2 ~54, 3 ~77, 4 ~81 (default lab: 47).

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

## Connecting DIARC (socket server)

```bash
python -m gridlab.server --port 9000 --view                          # default lab, live window
python -m gridlab.server --port 9000 --scenario lab.yaml --verbose   # detailed failure causes
python -m gridlab.server --port 9000 --random 20 --difficulty 0,2,4 --seed 100 --max-steps 400
python -m gridlab.client --port 9000                                 # type commands by hand
```

Python is the server; the agent connects over TCP. Same style as gym-novel-gridworlds2: the agent
sends one text command per line (UTF-8, `\n`), and gets exactly one JSON line back.

```
put_on book_1 light_button
```
```json
{"goal": {"goalType": "CLOSE_LAB", "goalAchieved": false, "Distribution": "Uninformed",
          "conditions": {"no_people": true, "drawers_closed_locked": false, "doors_closed_locked": false,
                         "light_on": true, "docked": false}},
 "command_result": {"command": "put_on", "argument": "book_1 light_button", "result": "SUCCESS",
                    "message": "", "stepCost": 1.0, "code": "OK"},
 "step": 12, "episode": 0, "gameOver": false,
 "events": [{"type": "put", "obj": "book_1", "on": "light_button"}, {"type": "light_on", "lamp": "lamp_1"}]}
```

* **Actions** (cost 1, advance `step`): every robot/object action, e.g. `go_to drawer_2`, `go_to 3 0 W`,
  `turn E`, `pick_up binder_1`, `put_down`, `put_on [obj] target`, `put_in [obj] container`, `open drawer_1`,
  `close door_2`, `insert_key door_1 [key]`, `turn_key door_1`, `remove_key door_1`, `release`, `grasp light_button`,
  `push_in pen_1`, `look_inside drawer_2`, `climb stool_1`, `climb_down`, `ask_to_leave alex`, `dock dock_1`,
  `undock`, `take_photo`. Failures: `result: FAIL` plus a `code` (LOCKED, OBSTRUCTED, NOT_REACHABLE, ...).
  `take_photo` adds `"photo": {"image_png_base64": ..., "path": ..., "of_cell": [x, y], ...}`.
* **Queries** (cost 0): `SENSE_ALL` (`world`: robot + every known object), `SENSE_ROBOT`, `SENSE_OBJECT <id>`,
  `SENSE_VISIBLE`, `CHECK_GOAL`, `LIST_ACTIONS`.
* **Episodes**: `gameOver` becomes true when the goal is achieved or `--max-steps` is reached; then send
  `RESET` for the next episode (its first `world` comes with the reply). After the last episode the reply has
  `"allDone": true` and the server exits. `QUIT` ends the session early.
* Unparseable commands get `{"command_result": {"command": "WRONG_CMD", "result": "FAIL", "message": "Invalid Command", ...}}`.
* A JSON line also works: `{"action": "put_on", "args": ["book_1", "light_button"]}`.

Each run writes `runs/<timestamp>/`: `episode_NNN.jsonl` (every request and reply), `episode_NNN.yaml`
(the exact scenario, for replay), `photos/*.png`, and `summary.json` / `summary.csv` with per-episode metrics
(achieved, ended_by, actions, failed_actions + codes, queries, photos, cost, oracle_actions baseline, seconds).
