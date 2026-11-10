"""Things that open/close and may lock: drawers, cabinets, doors.

Lock configuration (per object, set in the scenario):
    lock_type = "none"   -> cannot be locked
                "manual" -> lock()/unlock() actions, no key needed
                "key"    -> insert_key, turn_key, remove_key with a Key whose `opens` lists this id
    auto_lock = True     -> locks itself when closed (unlocking still needs the lock's usual method)
"""
from __future__ import annotations

from ..core.entity import Location, Relation, Thing, action
from ..core.errors import ActionFailure, Fail
from .items import Key


class Lockable(Thing):
    kind = "lockable"
    state_props = ("is_open", "locked", "lock_type", "auto_lock", "key_inserted")
    is_open = False
    locked = False
    lock_type = "none"
    auto_lock = False

    def validate(self, world):
        if self.lock_type not in ("none", "manual", "key"):
            raise ValueError(f"{self.id}: lock must be none/manual/key")
        if self.locked and self.is_open:
            raise ValueError(f"{self.id}: cannot start open and locked")
        if self.locked and self.lock_type == "none":
            raise ValueError(f"{self.id}: locked but has no lock")

    # ----------------------------------------------------------------- helpers
    @property
    def key_inserted(self):
        k = getattr(self, "_key", None)
        return k.id if k is not None else None

    def inserted_key(self, world) -> Key | None:
        keys = world.children(self, Relation.INSERTED)
        self._key = keys[0] if keys else None
        return self._key

    def update(self, world):
        self.inserted_key(world)

    def check_open(self, world):
        """Hook: raise ActionFailure if something prevents opening."""

    def check_close(self, world):
        """Hook: raise ActionFailure if something prevents closing."""

    def _hand_free_or(self, world, obj):
        h = world.robot.holding
        if h is not None and h is not obj:
            raise ActionFailure(Fail.HANDS_FULL, f"the gripper is holding {h.id}")

    # ----------------------------------------------------------------- open / close
    @action()
    def open(self, world):
        "Open it (needs an empty gripper, or the gripper on its handle)."
        self._hand_free_or(world, self)
        if self.is_open:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is already open")
        if self.locked:
            raise ActionFailure(Fail.LOCKED, f"{self.id} is locked")
        self.check_open(world)
        self.is_open = True
        world.emit("opened", obj=self.id)

    @action()
    def close(self, world):
        "Close it; locks it too if auto_lock is set."
        self._hand_free_or(world, self)
        if not self.is_open:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is already closed")
        self.check_close(world)
        self.is_open = False
        world.emit("closed", obj=self.id)
        if self.auto_lock and self.lock_type != "none":
            self.locked = True
            world.emit("locked", obj=self.id)

    # ----------------------------------------------------------------- manual lock
    def _need_lock(self, kind):
        if self.lock_type != kind:
            msg = {"none": f"{self.id} has no lock", "key": f"{self.id} needs a key",
                   "manual": f"{self.id} has no keyhole"}[self.lock_type]
            raise ActionFailure(Fail.NOT_SUPPORTED, msg)

    @action(free_hand=True)
    def lock(self, world):
        "Lock a manual lock (no key)."
        self._need_lock("manual")
        if self.is_open:
            raise ActionFailure(Fail.IS_OPEN, f"{self.id} must be closed to lock it")
        if self.locked:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is already locked")
        self.locked = True
        world.emit("locked", obj=self.id)

    @action(free_hand=True)
    def unlock(self, world):
        "Unlock a manual lock (no key)."
        self._need_lock("manual")
        if not self.locked:
            raise ActionFailure(Fail.ALREADY, f"{self.id} is not locked")
        self.locked = False
        world.emit("unlocked", obj=self.id)

    # ----------------------------------------------------------------- key lock
    @action(holding=True)
    def insert_key(self, world, key=None):
        "insert_key(target, [key]): put the held key into the lock; the gripper keeps hold of it."
        r = world.robot
        held = r.holding
        if key is not None and world.resolve(key) is not held:
            raise ActionFailure(Fail.NOT_HOLDING, f"not holding {key}")
        if not isinstance(held, Key):
            raise ActionFailure(Fail.NOT_SUPPORTED, f"{held.id} is not a key")
        if r.holding_fixed:
            raise ActionFailure(Fail.HOLDING_FIXED, f"{held.id} is fixed in place")
        self._need_lock("key")
        if self.inserted_key(world) is not None:
            raise ActionFailure(Fail.OBSTRUCTED, f"there is already a key in {self.id}")
        world.move(held, Location(Relation.INSERTED, parent=self))
        r.holding = held                      # still gripping it: the robot is now anchored
        self._key = held
        world.emit("key_inserted", key=held.id, lock=self.id)

    @action()
    def turn_key(self, world):
        "Turn the key in the lock: locks if unlocked, unlocks if locked. The gripper ends up holding the key."
        k = self.inserted_key(world)
        if k is None:
            raise ActionFailure(Fail.NO_KEY, f"there is no key in {self.id}")
        self._hand_free_or(world, k)
        if self.id not in k.opens:
            raise ActionFailure(Fail.WRONG_KEY, "the key does not turn", f"{k.id} does not open {self.id}")
        if not self.locked and self.is_open:
            raise ActionFailure(Fail.IS_OPEN, f"{self.id} must be closed to lock it")
        world.robot.holding = k
        self.locked = not self.locked
        world.emit("locked" if self.locked else "unlocked", obj=self.id, key=k.id)

    @action()
    def remove_key(self, world):
        "Pull the key out of the lock; the robot then carries it."
        k = self.inserted_key(world)
        if k is None:
            raise ActionFailure(Fail.NO_KEY, f"there is no key in {self.id}")
        self._hand_free_or(world, k)
        world.move(k, Location(Relation.HELD))
        self._key = None
        world.emit("key_removed", key=k.id, lock=self.id)
