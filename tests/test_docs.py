"""The protocol reference must mention every action, failure code, query and event."""
import re
from pathlib import Path

from gridlab.core import Fail
from gridlab.server.session import QUERIES, Session, ServerOptions, episode_specs

DOC = (Path(__file__).parent.parent / "docs" / "protocol.md").read_text()


def test_every_action_documented():
    s = Session(episode_specs(), ServerOptions(log_dir=None, oracle_baseline=False))
    missing = [a for a in s.action_docs() if f"`{a}" not in DOC]
    assert not missing, missing


def test_every_failure_code_and_query_documented():
    assert not [c.value for c in Fail if f"`{c.value}`" not in DOC]
    assert not [q for q in QUERIES if q.upper() not in DOC]


def test_every_event_documented():
    src = "\n".join(p.read_text() for p in Path("gridlab").rglob("*.py"))
    events = set(re.findall(r'emit\("([a-z_]+)"', src)) | {"light_off", "unlocked", "fell"}
    events -= {"rattled"}                         # example in a docstring
    assert not [e for e in events if f"`{e}`" not in DOC]
