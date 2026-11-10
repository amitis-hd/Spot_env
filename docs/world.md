# How the lab world works

## Space

* The lab is a grid (4 x 4 by default). Cells are `[x, y]`: x grows to the east, y to the south; `y = 0`
  is the north wall.
* Every cell has two levels: **LOW** (floor, counters, drawers, tables) and **HIGH** (wall cabinets, shelves).
* Doors are in the outer walls, on one edge of a border cell (`side` N/E/S/W). The robot uses a door by
  standing in that cell facing the wall.
* Every object blocks its cell: the robot never shares a cell with anything (the only exception is the dock,
  which it drives onto). People block cells too.

## The robot

* Has a cell, a heading (N/E/S/W) and a level. It acts on **the cell in front of it, at its own level**.
* `go_to` teleports: it lands on a free neighbouring cell of the target (the one nearest to where it is) and
  faces the target. There is no path planning and no distance cost. `go_to x y heading` lands on a free cell.
* **One arm.** The gripper holds one thing. Opening and closing need an empty gripper; so do picking up,
  grasping, docking.
* **Fixed grip.** If the gripper holds something fixed in place (a key it has just put into a lock, a door
  handle, the light button) the robot cannot move, turn, climb or dock until it `release`s it (or pulls the
  key out with `remove_key`).
* **Climbing.** To reach the HIGH level of a cell C, put the stool (or chair) on the cell in front of C while
  standing one cell further back, then `climb` it: the robot moves onto the stool's cell at HIGH level, still
  facing C. It can `turn` up there and reach other HIGH cells next to it. It can climb up and down while
  holding something. `climb_down` steps back to where it came from (or another free neighbouring cell) and
  faces the stool. `go_to` is not possible while standing on the stool.
* **Putting things down.** `put_down` puts the held object in front: on a counter/table/shelf there, otherwise
  on the floor. At HIGH level with nothing in front to hold it, the object falls to the LOW level of that cell
  (onto the counter/table below, or the floor) and a `fell` event is reported.
* Sizes: small (pen, key, book, mug), medium (binder), large (stool, chair). Counters, tables and shelves take
  small and medium things; books take small things on top; the light button takes small things.
  Things stacked on an object move with it.

## Drawers, cabinets, doors, locks, keys

* Drawers (in counters, LOW) and wall cabinets (HIGH) hide their contents while closed. Doors have a doorway
  that things can be put into while open.
* Lock types: `none`, `manual` (`lock` / `unlock`, no key) or `key`. `auto_lock: true` locks it whenever it is
  closed. Nothing can be locked while open.
* Keys list what they open (`opens`). With a key lock: `insert_key` (the robot keeps gripping the key, so it
  cannot move), `turn_key` (toggles locked/unlocked; a wrong key goes in but does not turn: `WRONG_KEY`),
  `remove_key` (the robot carries the key again). The key can stay in the lock; the lock still counts as
  locked.

## Obstructions

* **Sticking out of a drawer/cabinet.** A thing one size too big for a container goes in but sticks out, and
  the container then cannot close (`OBSTRUCTED`). Small items that stick out can be `push_in`ed; too-big ones
  (the binder in a drawer) must be taken out. Whether something sticks out is never reported to the
  planner; it is visible in photos.
* **Doorway.** Anything put into an open doorway stops the door from closing and stops people leaving through it.
* **Boxed in.** If every neighbouring cell of an object is occupied, `go_to` fails with `NO_ACCESS`; move
  something first.

## Light

The lamp is on only while its button is pressed: either the things resting on the button weigh enough (a
book does, a pen does not), or the robot holds the button down (`grasp`, which pins the robot in place).
Weights, the threshold and the button's pressed state are hidden; the planner only sees the lamp's `on`.

## People

`ask_to_leave` asks a person to leave. What they do is decided by a person policy (pluggable, see
[extending.md](extending.md)). The default policy agrees and walks out through any open door whose doorway is
clear, as soon as there is one (even several actions later). `stubborn` refuses the first N requests.
People who left are gone from all observations.

## Goal: close down the lab

1. `no_people`: nobody left in the lab
2. `drawers_closed_locked`: every drawer closed and locked (a drawer with lock type `none` only needs to be closed)
3. `doors_closed_locked`: every door closed and locked
4. `light_on`: the lamp is on
5. `docked`: the robot is on the dock

## Graphics

The window (`python -m gridlab.play`, or `--view` on the server) draws each cell as a front view, HIGH level
above LOW level, with name labels, doors on the walls, and a status panel with the goal checklist and the last
action. Photos use exactly the same drawing, bigger and without labels. Sprites are PNG files in
`gridlab/render/assets/` (one per object state) and can be replaced.

## The oracle

`gridlab/tasks/oracle.py` is a scripted solver. It reads the true state (including hidden things) but acts
only through the normal actions, so all rules apply. It is used to check that every generated lab is
solvable and gives a baseline action count per episode (`oracle_actions` in the run summary). It is not
optimal. `python -m gridlab.scenarios solve lab.yaml` prints its solution; `o` in the game window plays it.
