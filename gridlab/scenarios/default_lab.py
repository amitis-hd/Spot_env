"""The default lab, loaded from default_lab.yaml."""
from __future__ import annotations

from pathlib import Path

from ..core import World, WorldConfig
from .loader import load_scenario

DEFAULT_LAB = Path(__file__).with_name("default_lab.yaml")


def build_default_lab(config: WorldConfig | None = None) -> World:
    return load_scenario(DEFAULT_LAB, config)
