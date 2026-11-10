import pytest

from gridlab.core import Fail, Level, Relation, Size, Thing, World, WorldConfig, action
from gridlab.core.errors import ActionFailure
from gridlab.core.robot import Robot
from gridlab.objects import Book, Counter, Mug, Pen, Shelf, Stool, Table


class Box(Thing):
    """Test-only container: shows how a new object type with its own actions is defined."""
    kind = "box"
    movable = True
    size = Size.MEDIUM
    state_props = ("is_open",)
    is_open = False

    def contents_visible(self):
        return self.is_open

    def accept_in(self, world, obj):
        if not self.is_open:
            raise ActionFailure(Fail.OBSTRUCTED, f"{self.id} is closed")

    @action(free_hand=True)
    def open(self, world):
        "Open the lid."
        if self.is_open:
            raise ActionFailure(Fail.ALREADY, "already open")
        self.is_open = True

    @action(free_hand=True)
    def close(self, world):
        "Close the lid."
        self.is_open = False


def make_world(**cfg) -> World:
    """
    y\\x   0          1            2        3
    0    counter_1  counter_2    .        .
         (book_1,   + shelf_1 HIGH
          pen_1 on   (mug_1 on it)
          book_1)
    1    .          SPOT>N       .        stool_1
    2    .          .            table_1  .
    3    box_1(key_1 inside, closed)
    """
    w = World(robot=Robot("spot", cell=(1, 1), facing="N"), config=WorldConfig(**cfg))
    w.add(Counter("counter_1"), cell=(0, 0))
    w.add(Book("book_1"), on="counter_1")
    w.add(Pen("pen_1"), on="book_1")
    w.add(Counter("counter_2"), cell=(1, 0))
    w.add(Shelf("shelf_1"), cell=(1, 0), level="high")
    w.add(Mug("mug_1"), on="shelf_1")
    w.add(Table("table_1"), cell=(2, 2))
    w.add(Stool("stool_1"), cell=(3, 1))
    w.add(Box("box_1"), cell=(0, 3))
    w.add(Mug("key_1"), inside="box_1")
    w.start()
    return w


def ok(resp):
    assert resp["ok"], resp
    return resp


def fails(resp, code):
    assert not resp["ok"] and resp["code"] == code.value, resp
    return resp


# ---------------------------------------------------------------- observations
def test_world_snapshot_hides_container_contents_and_weights():
    w = make_world()
    snap = w.get_world()
    ids = {o["id"] for o in snap["objects"]}
    assert "key_1" not in ids and {"book_1", "pen_1", "box_1", "mug_1"} <= ids
    pen = next(o for o in snap["objects"] if o["id"] == "pen_1")
    assert pen["location"] == {"relation": "on", "cell": [0, 0], "level": "low", "parent": "book_1"}
    assert "weight" not in str(snap)
    assert snap["robot"]["cell"] == [1, 1] and snap["robot"]["facing_cell"] == [1, 0]
    assert "pick_up" in pen["affordances"]


def test_unknown_object_is_indistinguishable_from_nonexistent():
    w = make_world()
    a = fails(w.execute("pick_up", ["key_1"]), Fail.UNKNOWN_OBJECT)
    b = fails(w.execute("pick_up", ["nope"]), Fail.UNKNOWN_OBJECT)
    assert a["msg"].replace("key_1", "X") == b["msg"].replace("nope", "X")


# ---------------------------------------------------------------- movement
def test_go_to_object_picks_adjacent_pose_facing_it():
    w = make_world()
    r = ok(w.execute("go_to", ["table_1"]))
    rob = w.get_robot()
    assert tuple(rob["facing_cell"]) == (2, 2)
    assert r["data"]["path"][0] == [1, 1]
    assert any(e["type"] == "robot_moved" for e in r["events"])


def test_go_to_coordinates_and_invalid_targets():
    w = make_world()
    ok(w.execute("go_to", [3, 3, "W"]))
    assert w.robot.cell == (3, 3) and w.robot.facing.value == "W"
    fails(w.execute("go_to", [2, 2, "N"]), Fail.INVALID_POSITION)   # table cell
    fails(w.execute("go_to", [9, 9, "N"]), Fail.INVALID_POSITION)
    fails(w.execute("go_to", ["x"]), Fail.UNKNOWN_OBJECT)
    fails(w.execute("go_to", [1, 2]), Fail.BAD_ARGS)


def test_no_path_when_walled_in():
    w = World(width=3, height=1, robot=Robot(cell=(0, 0), facing="E"))
    w.add(Table("t"), cell=(1, 0))
    w.add(Mug("m"), cell=(2, 0))
    w.start()
    fails(w.execute("go_to", [2, 0, "W"]), Fail.NO_PATH)


# ---------------------------------------------------------------- manipulation
def test_reach_rules_and_pick_place():
    w = make_world()
    fails(w.execute("pick_up", ["book_1"]), Fail.NOT_REACHABLE)       # counter_1 is not in front
    fails(w.execute("pick_up", ["mug_1"]), Fail.NOT_REACHABLE)        # HIGH level, robot is LOW
    ok(w.execute("go_to", ["counter_1"]))
    fails(w.execute("pick_up", ["counter_1"]), Fail.NOT_MOVABLE)
    ok(w.execute("pick_up", ["pen_1"]))
    fails(w.execute("pick_up", ["book_1"]), Fail.HANDS_FULL)
    ok(w.execute("put_on", ["book_1"]))                                # back on the book
    ok(w.execute("pick_up", ["book_1"]))                               # pen rides along
    assert w.get_object("pen_1")["location"]["parent"] == "book_1"
    assert w.robot.holding.id == "book_1"
    ok(w.execute("go_to", [1, 2, "S"]))
    ok(w.execute("put_down"))                                          # onto floor (1,3)
    loc = w.get_object("book_1")["location"]
    assert loc["relation"] == "at" and loc["cell"] == [1, 3]
    assert w.get_object("pen_1")["location"]["cell"] == [1, 3]


def test_put_down_on_counter_and_physical_limits():
    w = make_world()
    ok(w.execute("go_to", ["stool_1"]))
    ok(w.execute("pick_up", ["stool_1"]))
    ok(w.execute("go_to", ["table_1"]))
    fails(w.execute("put_down"), Fail.CANNOT_SUPPORT)                  # stool too big for table
    fails(w.execute("put_on", ["table_1"]), Fail.CANNOT_SUPPORT)
    fails(w.execute("put_on", ["stool_1", "stool_1"]), Fail.CANNOT_SUPPORT)
    fails(w.execute("put_on", ["pen_1", "table_1"]), Fail.NOT_HOLDING)
    ok(w.execute("go_to", [0, 1, "N"]))
    fails(w.execute("put_down"), Fail.CANNOT_SUPPORT)                  # counter too small for stool
    ok(w.execute("go_to", [1, 1, "S"]))
    ok(w.execute("put_down"))                                          # stool to floor (1,2)


def test_put_down_targets_counter_wall_or_floor():
    w = make_world()
    ok(w.execute("go_to", ["counter_1"]))            # robot at (0,1) facing N
    ok(w.execute("pick_up", ["pen_1"]))
    ok(w.execute("go_to", [0, 1, "W"]))              # facing the west wall
    fails(w.execute("put_down"), Fail.INVALID_POSITION)
    ok(w.execute("go_to", [1, 1, "N"]))              # facing counter_2 -> lands on the counter
    r = ok(w.execute("put_down"))
    assert {"type": "put", "obj": "pen_1", "on": "counter_2"} in r["events"]
    ok(w.execute("pick_up", ["pen_1"]))
    ok(w.execute("go_to", [1, 1, "E"]))              # empty floor (2,1)
    ok(w.execute("put_down"))
    assert w.get_object("pen_1")["location"] == {"relation": "at", "cell": [2, 1], "level": "low"}
    fails(w.execute("put_down"), Fail.NOT_HOLDING)


# ---------------------------------------------------------------- climbing
def test_stool_climb_reaches_high_level():
    w = make_world()
    ok(w.execute("go_to", ["stool_1"]))
    ok(w.execute("pick_up", ["stool_1"]))
    ok(w.execute("go_to", [1, 2, "N"]))
    ok(w.execute("put_down"))                       # stool now at (1,1), in front of counter_2
    ok(w.execute("climb", ["stool_1"]))
    assert w.robot.cell == (1, 1) and w.robot.level is Level.HIGH
    fails(w.execute("go_to", ["table_1"]), Fail.MUST_CLIMB_DOWN)
    fails(w.execute("pick_up", ["stool_1"]), Fail.NOT_REACHABLE)
    ok(w.execute("pick_up", ["mug_1"]))             # mug on the HIGH shelf
    ok(w.execute("climb_down"))                     # allowed while holding something
    fails(w.execute("climb_down"), Fail.ALREADY)
    ok(w.execute("climb", ["stool_1"]))             # climb in place while holding the mug
    ok(w.execute("put_on", ["shelf_1"]))
    ok(w.execute("climb_down"))
    ok(w.execute("pick_up", ["stool_1"]))           # stool is in the robot's own cell


def test_cannot_climb_with_things_on_it():
    w = make_world()
    ok(w.execute("go_to", ["counter_1"]))
    ok(w.execute("pick_up", ["pen_1"]))
    ok(w.execute("go_to", ["stool_1"]))
    ok(w.execute("put_on", ["stool_1"]))
    fails(w.execute("climb", ["stool_1"]), Fail.OBSTRUCTED)


# ---------------------------------------------------------------- discovery
def test_container_contents_discovered_on_open_and_remembered():
    w = make_world()
    ok(w.execute("go_to", ["box_1"]))
    r = ok(w.execute("open", ["box_1"]))
    assert {"type": "discovered", "obj": "key_1", "kind": "mug", "relation": "in", "parent": "box_1"} in r["events"]
    assert w.get_object("key_1")["visible"]
    ok(w.execute("close", ["box_1"]))
    obs = w.get_object("key_1")
    assert obs["visible"] is False and obs["location"]["parent"] == "box_1"
    fails(w.execute("pick_up", ["key_1"]), Fail.NOT_REACHABLE)
    assert "key_1" not in {o["id"] for o in w.get_visible()}
    assert "key_1" in {o["id"] for o in w.get_world()["objects"]}


def test_put_in_container():
    w = make_world()
    ok(w.execute("go_to", ["counter_1"]))
    ok(w.execute("pick_up", ["pen_1"]))
    ok(w.execute("go_to", ["box_1"]))
    fails(w.execute("put_in", ["box_1"]), Fail.OBSTRUCTED)
    fails(w.execute("open", ["box_1"]), Fail.HANDS_FULL)
    fails(w.execute("put_in", ["table_1"]), Fail.NOT_REACHABLE)


# ---------------------------------------------------------------- dispatch / feedback
def test_dispatch_errors_and_verbosity():
    w = make_world()
    fails(w.execute("fly", []), Fail.UNKNOWN_ACTION)
    fails(w.execute("pick_up", []), Fail.BAD_ARGS)
    fails(w.execute("open", ["table_1"]), Fail.NOT_SUPPORTED)
    fails(w.execute("climb_down", ["x"]), Fail.BAD_ARGS)
    ok(w.execute("go_to", ["stool_1"]))
    ok(w.execute("pick_up", ["stool_1"]))
    ok(w.execute("go_to", ["table_1"]))
    r = fails(w.execute("put_down"), Fail.CANNOT_SUPPORT)
    assert "detail" not in r

    v = make_world(verbose_failures=True)
    v.execute("go_to", ["stool_1"]); v.execute("pick_up", ["stool_1"]); v.execute("go_to", ["table_1"])
    assert v.execute("put_down")["detail"] == "stool_1 is too large for table_1"


def test_history_and_step_counter():
    w = make_world()
    w.execute("go_to", ["table_1"])
    w.execute("pick_up", ["table_1"])
    assert w.step_count == 2 and [h["ok"] for h in w.history] == [True, False]


def test_describe_dump_is_readable():
    text = make_world().describe()
    assert "counter_1{on:book_1{on:pen_1}}" in text and "SPOT>N" in text and "box_1{in:key_1}" in text
