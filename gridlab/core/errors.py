"""Failure codes returned to the planner when an action cannot be carried out."""
from __future__ import annotations

from enum import Enum


class Fail(str, Enum):
    UNKNOWN_ACTION = "UNKNOWN_ACTION"      # no such action name
    NOT_SUPPORTED = "NOT_SUPPORTED"        # the target does not afford this action
    BAD_ARGS = "BAD_ARGS"                  # wrong number / type of arguments
    UNKNOWN_OBJECT = "UNKNOWN_OBJECT"      # id does not exist or has not been discovered yet
    NOT_REACHABLE = "NOT_REACHABLE"        # not in front of the robot at the robot's level
    NOT_HOLDING = "NOT_HOLDING"            # action needs an object in the gripper
    HANDS_FULL = "HANDS_FULL"              # action needs an empty gripper
    NOT_MOVABLE = "NOT_MOVABLE"            # cannot be picked up
    CANNOT_SUPPORT = "CANNOT_SUPPORT"      # cannot be put there (no surface / too big / full)
    OBSTRUCTED = "OBSTRUCTED"              # something is in the way
    LOCKED = "LOCKED"
    WRONG_KEY = "WRONG_KEY"
    ALREADY = "ALREADY"                    # already in the requested state
    NO_ACCESS = "NO_ACCESS"                # go_to/climb_down: no free cell to stand on
    HOLDING_FIXED = "HOLDING_FIXED"        # gripper holds something fixed in place; release it first
    INVALID_POSITION = "INVALID_POSITION"  # outside the grid / not walkable
    MUST_CLIMB_DOWN = "MUST_CLIMB_DOWN"    # robot is standing on something
    DOCKED = "DOCKED"                      # robot must undock first


class ActionFailure(Exception):
    """Raised inside action handlers. `detail` is only sent when the world is in verbose mode."""

    def __init__(self, code: Fail, msg: str, detail: str | None = None):
        super().__init__(msg)
        self.code = code
        self.msg = msg
        self.detail = detail
