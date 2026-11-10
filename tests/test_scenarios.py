"""Step 3: YAML scenarios, random generator, oracle solver."""
import pytest

from gridlab.agents import CompliantPolicy
from gridlab.core import Thing, action
from gridlab.scenarios import DEFAULT_LAB, build_default_lab, build_world, load_scenario, read_spec, spec_to_yaml
from gridlab.scenarios.__main__ import main as cli
from gridlab.scenarios.generator import PRESETS, accessibility_problems, generate_spec
from gridlab.tasks.oracle import solve


def test_default_lab_yaml_round_trip():
    spec = read_spec(DEFAULT_LAB)
    assert spec["objects"][9] == {"id": "pen_1", "type": "Pen", "on": "counter_3"}   # 'on' stays a string
    again = read_spec(spec_to_yaml(spec))
    assert again["objects"] == spec["objects"]
    assert build_world(again).describe() == build_default_lab().describe()


def test_oracle_solves_default_lab():
    res = solve(build_default_lab())
    assert res["goal"]["achieved"] and res["steps"] < 60


@pytest.mark.parametrize("difficulty", range(5))
def test_random_labs_are_valid_and_solvable(difficulty):
    for seed in range(25):
        spec = generate_spec(seed, difficulty)
        assert accessibility_problems(spec) == []
        w = build_world(spec)
        assert not w.check_goal()["achieved"]
        assert solve(w)["goal"]["achieved"], (seed, difficulty)


def test_generator_is_deterministic_and_varied():
    assert generate_spec(5, 2) == generate_spec(5, 2)
    layouts = {str(generate_spec(s, 2)["objects"]) for s in range(10)}
    assert len(layouts) == 10


def test_difficulty_knobs_take_effect():
    w = build_world(generate_spec(1, 4))
    people = [t for t in w.things.values() if t.kind == "person"]
    assert len(people) == 3
    assert all(d.locked for d in w.things.values() if d.kind == "door")
    keys = [o for o in w.get_world()["objects"] if o["kind"] == "key"]
    assert keys and all("opens" not in k["state"] for k in keys)          # hide_key_targets
    w0 = build_world(generate_spec(1, 0))
    assert not [t for t in w0.things.values() if t.kind == "person"]
    assert all(d.is_open for d in w0.things.values() if d.kind == "door")


def test_knob_overrides():
    w = build_world(generate_spec(2, 4, people=0, doors="open"))
    assert not [t for t in w.things.values() if t.kind == "person"]
    with pytest.raises(ValueError):
        generate_spec(1, 2, flying=True)
    with pytest.raises(ValueError):
        generate_spec(1, 9)
    assert set(PRESETS[0]) == set(PRESETS[4])


def test_yaml_with_generator_section():
    w = load_scenario("generator: {seed: 4, difficulty: 1}")
    assert w.scenario_name == "random_s4_d1"


class Plant(Thing):
    """A new object type defined outside the package: usable from YAML by class name."""
    kind = "plant"
    movable = True
    watered = False
    state_props = ("watered",)

    @action(free_hand=True)
    def water(self, world):
        "Water the plant."
        self.watered = True


def test_custom_object_types_and_policies_from_yaml():
    w = load_scenario("""
grid: {width: 2, height: 1}
goal: null
robot: {cell: [0, 0], facing: E}
objects:
  - {id: fern, type: Plant, cell: [1, 0]}
""")
    assert w.execute("water", ["fern"])["ok"] and w.get_object("fern")["state"] == {"watered": True}
    w2 = load_scenario("""
grid: {width: 2, height: 1}
objects:
  - {id: bo, type: Person, cell: [1, 0], policy: {type: gridlab.agents.CompliantPolicy}}
""")
    assert isinstance(w2.things["bo"].policy, CompliantPolicy)


def test_loader_reports_bad_scenarios():
    with pytest.raises(ValueError, match="pen_1"):
        load_scenario("objects: [{id: pen_1, type: Pen, on: nowhere}]")
    with pytest.raises(ValueError, match="colour"):
        load_scenario("objects: [{id: pen_1, type: Pen, cell: [0, 0], colour: red}]")
    with pytest.raises(ValueError, match="outer wall"):
        load_scenario("objects: [{id: d, type: Door, cell: [1, 1], side: N}]")


def test_cli(tmp_path, capsys):
    out = tmp_path / "lab.yaml"
    cli(["generate", "--seed", "1", "--difficulty", "3", "--knob", "people=0", "-o", str(out)])
    cli(["solve", str(out)])
    assert "goal reached in" in capsys.readouterr().out
