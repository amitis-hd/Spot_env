# Socket protocol reference

gridlab runs a TCP server; the agent (DIARC) connects to it as a client. The style follows
gym-novel-gridworlds2 / Polycraft, so an agent written for those can be reused.

```bash
python -m gridlab.server --port 9000 [--view] [options]      # see "Server options" below
```

## Messages

* Encoding: UTF-8, one message per line (`\n`; a trailing `\r` is ignored).
* The client sends **one command per line**; the server answers **every** line with **exactly one JSON line**,
  in order. Several commands may be sent in one packet.
* A command is the action or query name followed by space-separated arguments. Names are case-insensitive
  (`SENSE_ALL` = `sense_all`), arguments are not (object ids are lower-case). Whole-number arguments are sent as
  numbers. Quotes group an argument that contains spaces.

  ```
  go_to drawer_2
  go_to 3 0 W
  put_on book_1 light_button
  SENSE_OBJECT lamp_1
  ```
* A JSON line is accepted too: `{"action": "put_on", "args": ["book_1", "light_button"]}` or
  `{"command": "put_on book_1 light_button"}`.
* Only one client at a time. If it disconnects, the server keeps the episode and waits for a new connection.

## Reply

```json
{
  "goal": {
    "goalType": "CLOSE_LAB",
    "goalAchieved": false,
    "Distribution": "Uninformed",
    "conditions": {"no_people": false, "drawers_closed_locked": false, "doors_closed_locked": false,
                   "light_on": false, "docked": false}
  },
  "command_result": {
    "command": "close",
    "argument": "drawer_2",
    "result": "FAIL",
    "message": "drawer_2 cannot close",
    "stepCost": 1.0,
    "code": "OBSTRUCTED"
  },
  "step": 1,
  "episode": 0,
  "gameOver": false,
  "events": []
}
```

| field | meaning |
|---|---|
| `goal.goalAchieved` | all five goal conditions hold |
| `goal.conditions` | the individual conditions (omitted with `--hide-goal-conditions`) |
| `command_result.command` / `argument` | the command as understood (`WRONG_CMD` if it could not be parsed) |
| `command_result.result` | `SUCCESS` or `FAIL` |
| `command_result.code` | `OK` or a failure code (table below) |
| `command_result.message` | short human-readable reason; deliberately vague (e.g. "drawer_2 cannot close") |
| `command_result.stepCost` | 1.0 for actions (configurable), 0 for queries |
| `step` | number of actions executed in this episode (queries do not count) |
| `episode` | index of the current episode |
| `gameOver` | the episode has ended (goal achieved or step limit reached) |
| `events` | what happened as a result of an action (table below) |
| `detail` | only with `--verbose`: the specific cause, e.g. `"binder_1 is sticking out of drawer_2"` |
| `data` | extra result of some actions (`look_inside`: `{"contents": [...]}`, `undock`) |
| `photo` | result of `take_photo` (below) |
| `world` / `robot` / `object` / `visible` / `actions` | results of queries (below) |
| `allDone`, `summary` | after the last episode ended (`RESET` on the last episode, or `QUIT`) |

A line that cannot be parsed gets
`{"command_result": {"command": "WRONG_CMD", "argument": "", "result": "FAIL", "message": "Invalid Command", ...}}`.

## Queries (cost 0, do not advance `step`)

| query | reply field |
|---|---|
| `SENSE_ALL` | `world`: `{"grid": {...}, "step": n, "robot": {...}, "objects": [ ... every known object ... ]}` |
| `SENSE_ROBOT` | `robot` |
| `SENSE_OBJECT <id>` | `object` (fails with `UNKNOWN_OBJECT` for undiscovered or departed ids) |
| `SENSE_VISIBLE` | `visible`: known objects not currently hidden inside a closed drawer/cabinet |
| `CHECK_GOAL` | just the standard envelope (the `goal` field) |
| `LIST_ACTIONS` | `actions`: every action name with a one-line description; `queries` |
| `RESET` | ends the current episode and starts the next; reply carries the new `world` |
| `QUIT` | ends the session (summary is written, server exits) |

### What the agent can know

* Every object that is not inside a closed container is reported from the start ("god's-eye" list of
  what is in the room, for initialising the planner).
* Things inside a closed drawer/cabinet are **unknown** until it is opened: their ids do not appear anywhere,
  and using them gives `UNKNOWN_OBJECT` (the same reply as for an id that does not exist).
  Opening the container produces a `discovered` event. After it is closed again they are still reported,
  with `"visible": false`.
* Never reported: weights, the light button's threshold or pressed state (only the lamp's on/off),
  whether an item is sticking out of a drawer. Optionally (`hide_key_targets`) which locks a key opens.

### Robot

```json
{"id": "spot", "kind": "robot", "cell": [1, 1], "level": "low", "facing": "N", "facing_cell": [1, 0],
 "holding": null, "holding_fixed": false, "standing_on": null, "docked": false,
 "affordances": ["climb_down", "go_to", "put_down", "put_in", "put_on", "release", "take_photo", "turn", "undock"]}
```

`holding_fixed` is true when the gripper holds something that is fixed in place (a key in a lock, a door
handle, the light button); the robot cannot move until it lets go.

### Object

```json
{"id": "drawer_2", "kind": "drawer",
 "location": {"relation": "at", "cell": [1, 0], "level": "low"},
 "visible": true, "movable": false, "climbable": false,
 "state": {"is_open": true, "locked": false, "lock_type": "key", "auto_lock": true, "key_inserted": null},
 "affordances": ["close", "insert_key", "look_inside", "open", "remove_key", "turn_key"]}

{"id": "binder_1", "kind": "binder",
 "location": {"relation": "in", "cell": [1, 0], "level": "low", "parent": "drawer_2"},
 "visible": true, "movable": true, "climbable": false, "state": {}, "affordances": ["pick_up", "push_in"]}
```

`location.relation` is `at` (directly in the cell), `on` (on top of `parent`), `in` (inside `parent`, or in
the doorway of a door), `inserted` (a key in `parent`'s lock) or `held` (in the gripper). `cell` and
`level` always give where the thing physically is. `affordances` lists the actions that make sense for this
kind of object; they can still fail depending on the situation.

| kind | `state` fields |
|---|---|
| drawer, cabinet | `is_open`, `locked`, `lock_type` (`none`/`manual`/`key`), `auto_lock`, `key_inserted` |
| door | the same plus `side` (`N`/`E`/`S`/`W`: the wall the door is in) |
| key | `opens`: ids it locks/unlocks (hidden with `hide_key_targets`) |
| lamp | `on` |
| button | `controls`: lamp ids |
| others | `{}` |

## Actions (cost 1, advance `step`)

Arguments in `[brackets]` are optional. "In front" means the cell the robot faces, at the robot's level.

| action | what it does | needs |
|---|---|---|
| `go_to <id>` | appear on the free neighbouring cell of the object nearest to the robot, facing it (teleport, no path) | on the floor, not docked, not holding something fixed |
| `go_to <x> <y> <N/E/S/W>` | appear on that free cell with that heading | same |
| `turn <N/E/S/W>` | turn in place (also on a stool) | not docked, not holding something fixed |
| `pick_up <id>` | take a movable thing; whatever lies on it comes along | in front, empty gripper |
| `put_down` | put the held thing in front: on the counter/table/shelf there, else on the floor; at HIGH level with nothing there it **falls** to the LOW level | holding |
| `put_on [<held>] <target>` | put the held thing on top of `target` | target in front and big enough |
| `put_in [<held>] <container>` | put it into an open drawer/cabinet, or into an open doorway | container in front |
| `open <id>` / `close <id>` | drawers, cabinets, doors; `close` locks too if `auto_lock` | in front, empty gripper (or gripping that door) |
| `look_inside <id>` | `data.contents` of an open drawer/cabinet | in front |
| `lock <id>` / `unlock <id>` | manual locks (no key) | in front, closed, empty gripper |
| `insert_key <id> [<key>]` | put the held key into `id`'s lock; the gripper keeps hold of it (robot cannot move) | holding a key, in front |
| `turn_key <id>` | turn the key in the lock: locks if unlocked, unlocks if locked | a key in the lock, closed to lock |
| `remove_key <id>` | pull the key out; the robot carries it | a key in the lock |
| `release` | let go of something fixed (key in lock, door handle, button) | holding something fixed |
| `grasp <id>` | hold on to a fixed object (door handle; holding the light button keeps the light on) | in front, empty gripper |
| `push_in <id>` | push an item that sticks out of a drawer/cabinet back in (fails if it is too big) | in front, empty gripper |
| `climb <stool/chair>` | step onto the stool **in front**: the robot moves into its cell at HIGH level, same heading | stool on the floor with nothing on it |
| `climb_down` | step down to a free neighbouring cell (where it came from if possible), facing the stool | standing on something |
| `ask_to_leave <person>` | ask a person to leave (they walk out through an open door with a clear doorway) | — |
| `dock <dock>` | drive onto the dock in front and start charging | empty gripper, on the floor |
| `undock` | leave the dock to a free neighbouring cell, facing it | docked |
| `take_photo` | picture of the cell in front (below) | — |

### Photos

```json
"photo": {"image_png_base64": "iVBORw0KGgo...", "width": 256, "height": 256,
          "of_cell": [1, 0], "robot_level": "low",
          "path": "/abs/path/runs/20261110-154131/photos/ep000_step0002.png"}
```

A plain front view of the cell in front of the robot: its HIGH level (wall cabinets, shelves) drawn above
its LOW level (counter, drawers, table, floor). No text or labels. Closed drawers/cabinets hide their
contents; items sticking out are visible; facing the outer wall shows the wall, or the door with its lock
state. `--photo-mode inline|file|both` chooses whether the base64 data and/or a file path is sent.

## Failure codes

| code | meaning |
|---|---|
| `WRONG_CMD` | the line could not be parsed |
| `UNKNOWN_ACTION` | no such action |
| `NOT_SUPPORTED` | the object does not support this action (e.g. `open table_1`, `insert_key` with a pen) |
| `BAD_ARGS` | wrong number or kind of arguments |
| `UNKNOWN_OBJECT` | no such object, or not discovered yet, or the person has left |
| `NOT_REACHABLE` | the object is not in front of the robot at its level (or is hidden in a closed container) |
| `NOT_HOLDING` | the gripper is empty, or holds something else than named |
| `HANDS_FULL` | the action needs an empty gripper |
| `HOLDING_FIXED` | the gripper holds something fixed in place; `release` (or `remove_key`) first |
| `NOT_MOVABLE` | cannot be picked up |
| `CANNOT_SUPPORT` | cannot be put there (no surface, too big, nothing to hold it) |
| `OBSTRUCTED` | something is in the way (item sticking out, object in doorway, person in front, something on the stool, key already in lock, ...) |
| `LOCKED` | it is locked |
| `WRONG_KEY` | the key goes in but does not turn |
| `IS_OPEN` | must be closed first (cannot lock an open drawer/door) |
| `IS_CLOSED` | must be open first (`look_inside`, `put_in`) |
| `NO_KEY` | no key in that lock |
| `ALREADY` | already in that state (already open, already facing that way, ...) |
| `NO_ACCESS` | no free cell to stand on (target boxed in, or the requested cell is occupied) |
| `INVALID_POSITION` | outside the lab, or a wall in front |
| `MUST_CLIMB_DOWN` | the robot is standing on a stool |
| `DOCKED` | the robot must `undock` first |
| `GAME_OVER` | the episode has ended; send `RESET` |

## Events

| event | fields |
|---|---|
| `robot_moved` | `cell`, `facing` |
| `robot_turned` | `facing` |
| `robot_climbed` / `robot_climbed_down` | `on` / `off`, `cell` (`facing`) |
| `picked_up` | `obj` |
| `put` | `obj` and `on` / `inside` / `cell`+`level` |
| `fell` | `obj` and `on` / `cell`+`level` (put down at HIGH level with nothing to hold it) |
| `opened` / `closed` | `obj` |
| `locked` / `unlocked` | `obj` (`key`) |
| `key_inserted` / `key_removed` | `key`, `lock` |
| `grasped` / `released` | `obj` |
| `pushed_in` | `obj` |
| `discovered` | `obj`, `kind`, `relation`, `parent` (something became known by opening a container) |
| `light_on` / `light_off` | `lamp` |
| `person_said` | `person`, `text` |
| `person_left` | `person`, `via` (door id) |
| `docked` / `undocked` | `dock` / `cell`, `facing` |

## Episodes and logs

An episode ends (`gameOver: true`) when the goal is achieved or after `--max-steps` actions. Actions then
fail with `GAME_OVER`; queries still work. `RESET` starts the next episode. After the last one, the reply
contains `"allDone": true` and the server exits.

Each run writes `runs/<timestamp>/`:

| file | contents |
|---|---|
| `episode_NNN.jsonl` | every request and reply, with a timestamp (photos referenced by path) |
| `episode_NNN.yaml` | the exact scenario, loadable with `--scenario` to replay it |
| `photos/epNNN_stepSSSS.png` | every photo taken |
| `summary.json`, `summary.csv` | per episode: `achieved`, `ended_by` (goal / max_steps / reset / quit / disconnect), `actions`, `failed_actions`, `failure_codes`, `queries`, `photos`, `cost`, `oracle_actions` (baseline from the scripted solver), `seconds`, final `conditions` |

## Server options

| option | default | |
|---|---|---|
| `--host`, `--port` | 127.0.0.1, 9000 | |
| `--scenario FILE` | default lab | repeatable; episodes in the given order |
| `--random N` | 0 | N random labs per difficulty |
| `--difficulty 0,2,4` | 2 | difficulties for `--random` |
| `--seed S` | 0 | first seed for `--random` (seeds S .. S+N-1) |
| `--repeat K` | 1 | repeat the whole episode list |
| `--max-steps` | 300 | actions per episode before `gameOver` |
| `--photo-mode` | inline | `inline`, `file` or `both` |
| `--verbose` | off | add `detail` (the exact cause) to failures |
| `--hide-goal-conditions` | off | only `goalAchieved`, no per-condition breakdown |
| `--no-oracle` | off | skip computing the oracle baseline per episode |
| `--log-dir` | runs | |
| `--view` | off | live window showing the lab and the last command |
| `--quiet` | off | no console log |

A test client: `python -m gridlab.client --port 9000` (interactive) or `--script cmds.txt`.
