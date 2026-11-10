"""Load scenarios from YAML (or dicts) and write them back out.

Scenario format::

    name: default_lab
    imports: [my_package.my_objects]        # optional: modules defining extra Thing subclasses
    grid: {width: 4, height: 4}
    config: {verbose_failures: false, hide_key_targets: false}
    goal: {type: close_lab, container_kinds: [drawer]}
    robot: {id: spot, cell: [1, 1], facing: N}
    objects:
      - {id: counter_1, type: Counter, cell: [0, 0]}                  # level defaults to low
      - {id: cabinet_2, type: Cabinet, cell: [1, 0], level: high}
      - {id: key_door, type: Key, inside: cabinet_2, opens: [door_1, door_2]}
      - {id: book_1, type: Book, on: table_1}
      - {id: alex, type: Person, cell: [1, 2], policy: {type: stubborn, refusals: 1}}

Every other key of an object is set as a property (is_open, locked, lock_type, auto_lock,
side, controls, protruding, weight, ...). A file may instead contain
`generator: {seed: 3, difficulty: 2}` to produce a random lab.
"""
from __future__ import annotations

import importlib
import os
from typing import Any

import yaml

from ..agents import CompliantPolicy, PersonPolicy, StubbornPolicy
from ..core import Robot, Thing, World, WorldConfig
from .. import objects as _objects  # noqa: F401  (registers the built-in object types)
from ..tasks import CloseLabGoal

POLICIES: dict[str, type[PersonPolicy]] = {"compliant": CompliantPolicy, "stubborn": StubbornPolicy}
GOALS = {"close_lab": CloseLabGoal}
_PLACEMENT_KEYS = {"id", "type", "cell", "level", "on", "inside"}


def thing_types() -> dict[str, type[Thing]]:
    """All Thing subclasses by class name and by kind (e.g. 'Drawer' and 'drawer')."""
    out, stack = {}, [Thing]
    while stack:
        cls = stack.pop()
        out.setdefault(cls.kind, cls)
        out[cls.__name__] = cls
        stack += cls.__subclasses__()
    return out


def _import_attr(path: str):
    mod, _, attr = path.rpartition(".")
    return getattr(importlib.import_module(mod), attr)


class _Loader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1 booleans like on/off/yes/no (so `on: table_1` stays a string key)."""


_Loader.yaml_implicit_resolvers = {
    ch: [(tag, rx) for tag, rx in resolvers if tag != "tag:yaml.org,2002:bool"]
    for ch, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}
_Loader.add_implicit_resolver("tag:yaml.org,2002:bool", __import__("re").compile(r"^(?:true|True|TRUE|false|False|FALSE)$"),
                              list("tTfF"))


def read_spec(source: str | os.PathLike | dict) -> dict:
    if isinstance(source, dict):
        return source
    text = str(source)
    if os.path.exists(text):
        with open(text) as f:
            return yaml.load(f, Loader=_Loader)
    return yaml.load(text, Loader=_Loader)


def _make_policy(spec) -> PersonPolicy | None:
    if spec is None:
        return None
    spec = dict(spec) if isinstance(spec, dict) else {"type": spec}
    kind = spec.pop("type")
    cls = POLICIES.get(str(kind).lower()) or _import_attr(kind)
    return cls(**spec)


def _props(entry: dict) -> dict:
    return {k: tuple(v) if isinstance(v, list) else v for k, v in entry.items() if k not in _PLACEMENT_KEYS | {"policy"}}


def build_world(spec: dict, config: WorldConfig | None = None) -> World:
    if "generator" in spec:
        from .generator import generate_spec
        spec = generate_spec(**spec["generator"])
    for mod in spec.get("imports", []):
        importlib.import_module(mod)
    types = thing_types()

    grid = spec.get("grid", {})
    cfg = config or WorldConfig(**spec.get("config", {}))
    r = spec.get("robot", {})
    robot = Robot(r.get("id", "spot"), cell=tuple(r.get("cell", (0, 0))), facing=r.get("facing", "N"))
    w = World(grid.get("width", 4), grid.get("height", 4), robot=robot, config=cfg)

    pending = list(spec.get("objects", []))
    while pending:
        progressed, rest = False, []
        for e in pending:
            parent = e.get("on") or e.get("inside")
            if parent is not None and parent not in w.things:
                rest.append(e)
                continue
            cls = types.get(e["type"]) or _import_attr(e["type"])
            try:
                kwargs = _props(e)
                if "policy" in e:
                    kwargs["policy"] = _make_policy(e["policy"])
                thing = cls(e["id"], **kwargs)
                if "cell" in e:
                    w.add(thing, cell=tuple(e["cell"]), level=e.get("level", "low"))
                elif "on" in e:
                    w.add(thing, on=e["on"])
                else:
                    w.add(thing, inside=e["inside"])
            except (TypeError, ValueError, KeyError) as ex:
                raise ValueError(f"object {e.get('id')}: {ex}") from ex
            progressed = True
        if not progressed:
            raise ValueError(f"unknown or circular parents for: {[e['id'] for e in rest]}")
        pending = rest

    g = spec.get("goal", {"type": "close_lab"})
    if g:
        g = dict(g)
        w.goal = GOALS[g.pop("type")](**g)
    w.scenario_name = spec.get("name", "unnamed")
    w.start()
    return w


def load_scenario(source, config: WorldConfig | None = None) -> World:
    """Build a World from a YAML path, YAML text, or a dict."""
    return build_world(read_spec(source), config)


def spec_to_yaml(spec: dict) -> str:
    """YAML text with one object per line (easy to read and diff)."""
    head = {k: v for k, v in spec.items() if k != "objects"}
    text = yaml.safe_dump(head, sort_keys=False, default_flow_style=None)
    lines = ["objects:"]
    for o in spec.get("objects", []):
        lines.append("  - " + yaml.safe_dump(o, default_flow_style=True, sort_keys=False, width=10_000).strip())
    return text + "\n".join(lines) + "\n"
