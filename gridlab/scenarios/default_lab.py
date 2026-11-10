"""The default lab layout (the approved mockup). Step 3 moves this into a YAML file.

      x=0              x=1                 x=2                    x=3
y=0  counter_1        counter_2           counter_3              .
     drawer_1 LOCKED  drawer_2 OPEN       pen_1, key_drawer1,
     cabinet_1 HIGH   (binder_1 sticks    mug_1; shelf_1 HIGH
                       out; auto-locks)
                      cabinet_2 HIGH (key_door inside)
y=1  .                SPOT facing N       .                      stool_1
y=2  door_1 (W wall)  alex                table_1: lamp_1,       chair_1
     closed                               light_button, book_1
y=3  .                door_2 (S wall)     .                      dock_1
                      OPEN
"""
from __future__ import annotations

from ..core import Robot, World, WorldConfig
from ..objects import (Binder, Book, Cabinet, Chair, Counter, Dock, Door, Drawer, Key, Lamp, LightButton,
                       Mug, Pen, Person, Shelf, Stool, Table)
from ..tasks import CloseLabGoal


def build_default_lab(config: WorldConfig | None = None) -> World:
    w = World(4, 4, robot=Robot("spot", cell=(1, 1), facing="N"), config=config)

    w.add(Counter("counter_1"), cell=(0, 0))
    w.add(Drawer("drawer_1", lock_type="key", locked=True), cell=(0, 0))
    w.add(Cabinet("cabinet_1"), cell=(0, 0), level="high")

    w.add(Counter("counter_2"), cell=(1, 0))
    w.add(Drawer("drawer_2", lock_type="key", auto_lock=True, is_open=True), cell=(1, 0))
    w.add(Binder("binder_1", protruding=True), inside="drawer_2")
    w.add(Cabinet("cabinet_2"), cell=(1, 0), level="high")
    w.add(Key("key_door", opens=("door_1", "door_2")), inside="cabinet_2")

    w.add(Counter("counter_3"), cell=(2, 0))
    w.add(Pen("pen_1"), on="counter_3")
    w.add(Key("key_drawer1", opens=("drawer_1", "drawer_2")), on="counter_3")
    w.add(Mug("mug_1"), on="counter_3")
    w.add(Shelf("shelf_1"), cell=(2, 0), level="high")

    w.add(Table("table_1"), cell=(2, 2))
    w.add(Lamp("lamp_1"), on="table_1")
    w.add(LightButton("light_button", controls=("lamp_1",)), on="table_1")
    w.add(Book("book_1"), on="table_1")

    w.add(Stool("stool_1"), cell=(3, 1))
    w.add(Chair("chair_1"), cell=(3, 2))
    w.add(Person("alex"), cell=(1, 2))
    w.add(Dock("dock_1"), cell=(3, 3))

    w.add(Door("door_1", side="W"), cell=(0, 2))
    w.add(Door("door_2", side="S", is_open=True), cell=(1, 3))

    w.goal = CloseLabGoal()
    w.start()
    return w
