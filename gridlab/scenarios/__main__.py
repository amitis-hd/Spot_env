"""Command line:

    python -m gridlab.scenarios generate --seed 3 --difficulty 2 [-o lab.yaml] [--knob people=0 ...]
    python -m gridlab.scenarios show  <file.yaml>      # text dump of the true state
    python -m gridlab.scenarios solve <file.yaml>      # run the oracle solver
"""
from __future__ import annotations

import argparse
import sys

import yaml

from .generator import generate_spec
from .loader import load_scenario, spec_to_yaml


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m gridlab.scenarios")
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("generate", help="write a random lab as YAML")
    g.add_argument("--seed", type=int, default=0)
    g.add_argument("--difficulty", type=int, default=2)
    g.add_argument("--knob", action="append", default=[], help="override a knob, e.g. people=0")
    g.add_argument("-o", "--out")
    for name in ("show", "solve"):
        p = sub.add_parser(name)
        p.add_argument("file")
    a = ap.parse_args(argv)

    if a.cmd == "generate":
        knobs = {}
        for kv in a.knob:
            k, _, v = kv.partition("=")
            knobs[k] = yaml.safe_load(v)
        text = spec_to_yaml(generate_spec(a.seed, a.difficulty, **knobs))
        if a.out:
            with open(a.out, "w") as f:
                f.write(text)
            print(f"wrote {a.out}")
        else:
            sys.stdout.write(text)
    elif a.cmd == "show":
        print(load_scenario(a.file).describe())
    elif a.cmd == "solve":
        from ..tasks.oracle import solve
        w = load_scenario(a.file)
        res = solve(w)
        for h in w.history:
            print(f"{h['step']:3d} {h['action']}{tuple(h['args'])} {'' if h['ok'] else '-> ' + h['code']}")
        print(f"goal reached in {res['steps']} actions")


if __name__ == "__main__":
    main()
