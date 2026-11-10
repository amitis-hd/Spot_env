"""A minimal Python client (stands in for DIARC when testing).

    python -m gridlab.client --port 9000            # interactive: type commands, see JSON replies
    python -m gridlab.client --port 9000 --script cmds.txt   # send the commands in a file, one per line

    from gridlab.client import GridlabClient
    with GridlabClient(port=9000) as c:
        print(c.send("SENSE_ALL")["world"]["robot"])
        print(c.send("pick_up book_1")["command_result"])
"""
from __future__ import annotations

import argparse
import json
import socket


class GridlabClient:
    def __init__(self, host="127.0.0.1", port=9000, timeout=30.0):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.buf = b""

    def send(self, command: str) -> dict:
        """Send one command and wait for its reply."""
        self.sock.sendall((command.strip() + "\n").encode("utf-8"))
        return self.recv()

    def recv(self) -> dict:
        """Read the next reply line."""
        while b"\n" not in self.buf:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("server closed the connection")
            self.buf += chunk
        line, self.buf = self.buf.split(b"\n", 1)
        return json.loads(line)

    def close(self):
        self.sock.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def _short(resp: dict) -> str:
    cr = resp["command_result"]
    out = f"{cr['result']} {cr['code']} {cr['message']}".rstrip()
    for k in ("events", "detail", "data"):
        if resp.get(k):
            out += f"\n  {k}: {json.dumps(resp[k])}"
    if "photo" in resp:
        out += f"\n  photo: {resp['photo'].get('path', '(inline base64)')}"
    out += f"\n  goal achieved: {resp['goal']['goalAchieved']}  step {resp['step']}  gameOver {resp['gameOver']}"
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m gridlab.client")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--script", help="file with one command per line to send instead of typing")
    ap.add_argument("--raw", action="store_true", help="print full JSON replies")
    a = ap.parse_args(argv)
    with GridlabClient(a.host, a.port) as c:
        if a.script:
            with open(a.script) as f:
                for line in f:
                    if line.strip() and not line.startswith("#"):
                        print(f"> {line.strip()}\n{_short(c.send(line))}")
            return
        print("connected; type commands (SENSE_ALL, pick_up book_1, list_actions, ...); Ctrl-D to quit")
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if not line.strip():
                continue
            resp = c.send(line)
            print(json.dumps(resp, indent=1) if a.raw else _short(resp))
            if resp.get("allDone"):
                break


if __name__ == "__main__":
    main()
