"""Step 2: lab objects and the full close-the-lab task on the default layout."""
from gridlab.agents import StubbornPolicy
from gridlab.core import Fail, Level, WorldConfig
from gridlab.objects import Chair, Key, Person
from gridlab.scenarios import build_default_lab


def ok(resp):
    assert resp["ok"], resp
    return resp


def fails(resp, code):
    assert not resp["ok"] and resp["code"] == code.value, resp
    return resp


def events(resp, type_):
    return [e for e in resp["events"] if e["type"] == type_]


def run(w, *steps):
    return [ok(w.execute(a, list(args))) for a, *args in steps]


# ---------------------------------------------------------------- full task
def test_full_close_down_of_the_default_lab():
    w = build_default_lab()
    assert not w.check_goal()["achieved"]

    # 1. alex leaves through the open door_2
    r = ok(w.execute("ask_to_leave", ["alex"]))
    assert events(r, "person_left") == [{"type": "person_left", "person": "alex", "via": "door_2"}]

    # 2. drawer_2 will not close: the binder sticks out and is too big to push in
    fails(w.execute("close", ["drawer_2"]), Fail.OBSTRUCTED)
    fails(w.execute("push_in", ["binder_1"]), Fail.OBSTRUCTED)
    run(w, ("pick_up", "binder_1"), ("go_to", "counter_3"), ("put_down",),
        ("go_to", "drawer_2"))
    r = ok(w.execute("close", ["drawer_2"]))
    assert events(r, "locked")                                       # auto-lock
    run(w, ("go_to", "door_2"), ("close", "door_2"))                 # needs a free gripper, so before the key

    # 3. the door key is hidden in the HIGH cabinet_2: fetch the stool and climb
    fails(w.execute("pick_up", ["key_door"]), Fail.UNKNOWN_OBJECT)
    run(w, ("go_to", "stool_1"), ("pick_up", "stool_1"), ("go_to", 1, 2, "N"), ("put_down",),
        ("climb", "stool_1"))
    r = ok(w.execute("open", ["cabinet_2"]))
    assert events(r, "discovered")[0]["obj"] == "key_door"
    run(w, ("pick_up", "key_door"), ("climb_down",))
    assert w.robot.cell == (1, 2)

    # 4. close and lock both doors; the robot cannot walk away with the key in the lock
    run(w, ("go_to", "door_2"))
    fails(w.execute("open", ["door_2"]), Fail.HANDS_FULL)            # one arm: the key is in it
    run(w, ("insert_key", "door_2"))
    fails(w.execute("go_to", ["door_1"]), Fail.HOLDING_FIXED)
    run(w, ("turn_key", "door_2"), ("remove_key", "door_2"))
    run(w, ("go_to", "door_1"), ("insert_key", "door_1", "key_door"), ("turn_key", "door_1"),
        ("remove_key", "door_1"))

    # 5. light: the pen is too light, the book works
    run(w, ("turn", "E"), ("put_down",))                             # park the key on the floor at (1,2)
    run(w, ("go_to", "counter_3"), ("pick_up", "pen_1"), ("go_to", "light_button"))
    r = ok(w.execute("put_on", ["light_button"]))
    assert not events(r, "light_on") and not w.get_object("lamp_1")["state"]["on"]
    run(w, ("pick_up", "pen_1"), ("put_on", "table_1"), ("pick_up", "book_1"))
    r = ok(w.execute("put_on", ["book_1", "light_button"]))
    assert events(r, "light_on") and w.get_object("lamp_1")["state"]["on"]

    # 6. dock
    run(w, ("go_to", "dock_1"), ("dock", "dock_1"))
    goal = w.check_goal()
    assert goal == {"achieved": True, "conditions": {"no_people": True, "drawers_closed_locked": True,
                    "doors_closed_locked": True, "light_on": True, "docked": True}}, goal


# ---------------------------------------------------------------- locks and keys
def test_lock_rules():
    w = build_default_lab(WorldConfig(verbose_failures=True))
    fails(w.execute("open", ["drawer_1"]), Fail.NOT_REACHABLE)
    run(w, ("go_to", "drawer_1"))
    fails(w.execute("open", ["drawer_1"]), Fail.LOCKED)
    fails(w.execute("turn_key", ["drawer_1"]), Fail.NO_KEY)
    fails(w.execute("lock", ["drawer_1"]), Fail.NOT_SUPPORTED)     # needs a key, not a thumb-turn
    run(w, ("go_to", "counter_3"), ("pick_up", "pen_1"), ("go_to", "drawer_1"))
    fails(w.execute("insert_key", ["drawer_1"]), Fail.NOT_SUPPORTED)  # a pen is not a key
    run(w, ("go_to", "counter_3"), ("put_down",), ("pick_up", "key_drawer1"), ("go_to", "drawer_1"),
        ("insert_key", "drawer_1"))
    assert w.get_robot()["holding_fixed"] and w.get_object("drawer_1")["state"]["key_inserted"] == "key_drawer1"
    fails(w.execute("open", ["drawer_1"]), Fail.HANDS_FULL)          # gripper is on the key
    run(w, ("turn_key", "drawer_1"), ("release",), ("open", "drawer_1"))
    fails(w.execute("turn_key", ["drawer_1"]), Fail.IS_OPEN)         # cannot lock while open
    fails(w.execute("pick_up", ["key_drawer1"]), Fail.OBSTRUCTED)    # use remove_key
    run(w, ("close", "drawer_1"), ("turn_key", "drawer_1"), ("remove_key", "drawer_1"))
    assert w.get_object("drawer_1")["state"]["locked"] and w.robot.holding.id == "key_drawer1"


def test_wrong_key_does_not_turn():
    w = build_default_lab(WorldConfig(verbose_failures=True))
    run(w, ("go_to", "counter_3"), ("pick_up", "key_drawer1"), ("go_to", "door_1"), ("insert_key", "door_1"))
    r = fails(w.execute("turn_key", ["door_1"]), Fail.WRONG_KEY)
    assert r["detail"] == "key_drawer1 does not open door_1"
    assert not w.get_object("door_1")["state"]["locked"]


def test_manual_and_lockless():
    w = build_default_lab()
    d = w.things["drawer_2"]
    d.lock_type, d.auto_lock = "manual", False
    run(w, ("pick_up", "binder_1"), ("turn", "E"), ("put_down",), ("turn", "N"), ("close", "drawer_2"),
        ("lock", "drawer_2"))
    fails(w.execute("open", ["drawer_2"]), Fail.LOCKED)
    run(w, ("unlock", "drawer_2"), ("open", "drawer_2"))
    fails(w.execute("lock", ["drawer_2"]), Fail.IS_OPEN)


# ---------------------------------------------------------------- obstructions
def test_small_protruding_item_can_be_pushed_in():
    w = build_default_lab(WorldConfig(verbose_failures=True))
    run(w, ("go_to", "counter_3"), ("pick_up", "pen_1"), ("go_to", "drawer_2"), ("put_in", "drawer_2"))
    w.things["pen_1"].protruding = True                              # e.g. set by a harder scenario
    run(w, ("pick_up", "binder_1"), ("turn", "E"), ("put_down",), ("turn", "N"))
    r = fails(w.execute("close", ["drawer_2"]), Fail.OBSTRUCTED)
    assert r["detail"] == "pen_1 is sticking out of drawer_2"
    run(w, ("push_in", "pen_1"), ("close", "drawer_2"))
    fails(w.execute("push_in", ["pen_1"]), Fail.NOT_REACHABLE)       # hidden again, drawer closed


def test_putting_a_big_item_in_a_drawer_leaves_it_sticking_out():
    w = build_default_lab()
    run(w, ("pick_up", "binder_1"), ("turn", "E"), ("put_down",), ("turn", "N"), ("close", "drawer_2"))
    assert "protruding" not in str(w.get_world())                   # never told to the planner
    w2 = build_default_lab()
    run(w2, ("pick_up", "binder_1"), ("put_in", "drawer_2"))
    fails(w2.execute("close", ["drawer_2"]), Fail.OBSTRUCTED)
    run(w2, ("go_to", "stool_1"), ("pick_up", "stool_1"), ("go_to", "drawer_2"))
    fails(w2.execute("put_in", ["drawer_2"]), Fail.CANNOT_SUPPORT)  # stool far too big


def test_object_in_doorway_blocks_door_and_people():
    w = build_default_lab(WorldConfig(verbose_failures=True))
    fails(w.execute("go_to", ["chair_1"]), Fail.NO_ACCESS)           # boxed in by stool, table, dock
    run(w, ("go_to", "stool_1"), ("pick_up", "stool_1"), ("go_to", "door_2"), ("put_in", "door_2"))
    assert w.get_object("stool_1")["location"] == {"relation": "in", "cell": [1, 3], "level": "low", "parent": "door_2"}
    r = fails(w.execute("close", ["door_2"]), Fail.OBSTRUCTED)
    assert r["detail"] == "stool_1 is in the doorway"
    r = ok(w.execute("ask_to_leave", ["alex"]))
    assert events(r, "person_said")[0]["text"] == "OK, but the doors are closed."
    assert "alex" in w.things
    r = ok(w.execute("pick_up", ["stool_1"]))                        # doorway clear -> alex goes
    assert events(r, "person_left")
    run(w, ("turn", "N"), ("put_down",), ("turn", "S"), ("close", "door_2"))


def test_closed_doors_keep_people_until_one_opens():
    w = build_default_lab()
    run(w, ("go_to", "door_2"), ("close", "door_2"), ("ask_to_leave", "alex"))
    assert "alex" in w.things
    r = ok(w.execute("open", ["door_2"]))
    assert events(r, "person_left")


def test_stubborn_person_policy():
    w = build_default_lab()
    w.things["alex"].policy = StubbornPolicy(refusals=1)
    r = ok(w.execute("ask_to_leave", ["alex"]))
    assert events(r, "person_said")[0]["text"] == "Not now, I'm busy." and "alex" in w.things
    r = ok(w.execute("ask_to_leave", ["alex"]))
    assert events(r, "person_left")
    fails(w.execute("ask_to_leave", ["alex"]), Fail.UNKNOWN_OBJECT)


def test_people_block_cells_and_drops():
    w = build_default_lab()
    fails(w.execute("go_to", [1, 2, "N"]), Fail.NO_ACCESS)
    run(w, ("pick_up", "binder_1"), ("turn", "S"))
    fails(w.execute("put_down"), Fail.OBSTRUCTED)


# ---------------------------------------------------------------- light
def test_holding_the_button_keeps_light_on_only_while_held():
    w = build_default_lab()
    run(w, ("go_to", "light_button"))
    fails(w.execute("pick_up", ["light_button"]), Fail.NOT_MOVABLE)
    r = ok(w.execute("grasp", ["light_button"]))
    assert events(r, "light_on")
    fails(w.execute("go_to", ["dock_1"]), Fail.HOLDING_FIXED)
    r = ok(w.execute("release"))
    assert events(r, "light_off")


def test_weights_and_pressed_state_are_hidden():
    w = build_default_lab()
    text = str(w.get_world())
    assert "weight" not in text and "threshold" not in text and "pressed" not in text


def test_light_goes_off_when_book_removed():
    w = build_default_lab()
    run(w, ("go_to", "book_1"), ("pick_up", "book_1"), ("put_on", "light_button"))
    assert w.things["lamp_1"].on
    r = ok(w.execute("pick_up", ["book_1"]))
    assert events(r, "light_off")


# ---------------------------------------------------------------- dock / turn
def test_dock_and_undock():
    w = build_default_lab()
    run(w, ("go_to", "binder_1"), ("pick_up", "binder_1"), ("go_to", "dock_1"))
    fails(w.execute("dock", ["dock_1"]), Fail.HANDS_FULL)
    run(w, ("turn", "N"), ("put_down",), ("go_to", "dock_1"), ("dock", "dock_1"))
    assert w.robot.cell == (3, 3) and w.get_robot()["docked"]
    fails(w.execute("go_to", ["table_1"]), Fail.DOCKED)
    fails(w.execute("turn", ["N"]), Fail.DOCKED)
    r = ok(w.execute("undock"))
    assert w.robot.facing_cell() == (3, 3) and not w.robot.docked
    fails(w.execute("undock"), Fail.ALREADY)


def test_turn_on_stool_reaches_other_high_cells():
    w = build_default_lab()
    run(w, ("ask_to_leave", "alex"), ("go_to", "stool_1"), ("pick_up", "stool_1"),
        ("go_to", 1, 2, "N"), ("put_down",), ("climb", "stool_1"))
    fails(w.execute("pick_up", ["shelf_1"]), Fail.NOT_REACHABLE)
    run(w, ("turn", "E"), ("turn", "N"))
    assert w.robot.level is Level.HIGH
    fails(w.execute("turn", ["N"]), Fail.ALREADY)
    fails(w.execute("turn", ["up"]), Fail.BAD_ARGS)


def test_observation_of_lab_objects():
    w = build_default_lab()
    d = w.get_object("door_1")
    assert d["state"] == {"is_open": False, "locked": False, "lock_type": "key", "auto_lock": False,
                          "key_inserted": None, "side": "W"}
    assert {"open", "close", "insert_key", "turn_key", "remove_key", "grasp"} <= set(d["affordances"])
    assert w.get_object("key_drawer1")["state"] == {"opens": ["drawer_1", "drawer_2"]}
    assert w.get_object("lamp_1")["state"] == {"on": False}
    assert "ask_to_leave" in w.get_object("alex")["affordances"]
