"""TCP server that a DIARC agent connects to.

    python -m gridlab.server --port 9000                       # default lab, one episode
    python -m gridlab.server --port 9000 --view                # with a live window
    python -m gridlab.server --random 20 --difficulty 0,2,4 --seed 100 --max-steps 400

One client at a time; if it disconnects, the server waits for the next one and the current
episode continues where it was. When every episode is done (RESET after the last one, or QUIT)
the server writes the summary and exits.
"""
from __future__ import annotations

import argparse
import json
import os
import selectors
import socket

from .session import ServerOptions, Session, episode_specs


class GridlabServer:
    def __init__(self, session: Session, host="127.0.0.1", port=9000, view=False, quiet=False):
        self.session = session
        self.view = view
        self.quiet = quiet
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((host, port))
        self.sock.listen(1)
        self.sock.setblocking(False)
        self.port = self.sock.getsockname()[1]
        self.conn = None
        self.buf = b""
        self.sel = selectors.DefaultSelector()
        self.sel.register(self.sock, selectors.EVENT_READ, "accept")
        self.running = True
        self._screen = None
        self._last = None

    def log(self, msg):
        if not self.quiet:
            print(f"[gridlab] {msg}", flush=True)

    # ------------------------------------------------------------------ socket handling
    def _accept(self):
        conn, addr = self.sock.accept()
        if self.conn is not None:          # one client at a time
            conn.close()
            return
        conn.setblocking(False)
        self.conn, self.buf = conn, b""
        self.sel.register(conn, selectors.EVENT_READ, "client")
        self.log(f"client connected from {addr[0]}:{addr[1]}")

    def _drop(self):
        self.sel.unregister(self.conn)
        self.conn.close()
        self.conn = None
        self.log("client disconnected; waiting for a new connection")

    def _send(self, obj: dict):
        data = (json.dumps(obj) + "\n").encode("utf-8")
        self.conn.setblocking(True)
        try:
            self.conn.sendall(data)
        finally:
            self.conn.setblocking(False)

    def _read(self):
        try:
            chunk = self.conn.recv(65536)
        except (BlockingIOError, InterruptedError):
            return
        except ConnectionError:
            chunk = b""
        if not chunk:
            self._drop()
            return
        self.buf += chunk
        while b"\n" in self.buf and self.conn is not None:
            raw, self.buf = self.buf.split(b"\n", 1)
            line = raw.decode("utf-8", errors="replace").strip("\r ")
            if not line:
                continue
            resp = self.session.handle(line)
            self._last = resp
            cr = resp["command_result"]
            self.log(f"{line}  ->  {cr['result']} {cr['code']} {cr['message']}".rstrip())
            try:
                self._send(resp)
            except ConnectionError:
                self._drop()
                return
            if resp.get("allDone"):
                self.running = False
            self._redraw()

    # ------------------------------------------------------------------ live view
    def _redraw(self):
        if not self.view:
            return
        import pygame
        from ..render.panel import UIState, render_frame
        last = None
        if self._last:
            cr = self._last["command_result"]
            last = {"action": cr["command"], "args": cr["argument"].split() if cr["argument"] else [],
                    "ok": cr["result"] == "SUCCESS", "code": cr["code"], "msg": cr["message"],
                    "events": self._last.get("events", []), "detail": self._last.get("detail")}
        ui = UIState(title=f"{self.session.world.scenario_name}  (episode {self.session.episode.index})",
                     last=last, menu_title="SOCKET AGENT", help=f"listening on port {self.port} | q quit",
                     message="client connected" if self.conn else "waiting for a client...")
        img = render_frame(self.session.world, ui)
        if self._screen is None or self._screen.get_size() != img.size:
            self._screen = pygame.display.set_mode(img.size)
        self._screen.blit(pygame.image.frombytes(img.tobytes(), img.size, "RGB"), (0, 0))
        pygame.display.flip()

    def _pump_view(self):
        import pygame
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key in (pygame.K_q, pygame.K_ESCAPE)):
                self.running = False

    # ------------------------------------------------------------------ main loop
    def serve(self):
        if self.view:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame
            pygame.display.init()
            pygame.display.set_caption("gridlab server")
            self._redraw()
        self.log(f"listening on port {self.port}; run dir: {self.session.run_dir}")
        try:
            while self.running:
                for key, _ in self.sel.select(timeout=0.05):
                    if key.data == "accept":
                        self._accept()
                        self._redraw()
                    elif self.conn is not None:
                        self._read()
                if self.view:
                    self._pump_view()
        finally:
            self.session.close()
            if self.conn is not None:
                self.conn.close()
            self.sock.close()
            if self.view:
                import pygame
                pygame.quit()
            self.log(f"done; summary in {self.session.run_dir}")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python -m gridlab.server")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=9000)
    ap.add_argument("--scenario", action="append", default=[], help="YAML scenario (repeatable)")
    ap.add_argument("--random", type=int, default=0, help="number of random labs per difficulty")
    ap.add_argument("--difficulty", default="2", help="difficulty for --random, e.g. 0,2,4")
    ap.add_argument("--seed", type=int, default=0, help="first seed for --random")
    ap.add_argument("--repeat", type=int, default=1)
    ap.add_argument("--max-steps", type=int, default=300)
    ap.add_argument("--photo-mode", choices=["inline", "file", "both"], default="inline")
    ap.add_argument("--verbose", action="store_true", help="include the detailed cause of failures")
    ap.add_argument("--hide-goal-conditions", action="store_true")
    ap.add_argument("--no-oracle", action="store_true", help="skip the oracle baseline per episode")
    ap.add_argument("--log-dir", default="runs")
    ap.add_argument("--view", action="store_true", help="show a live window")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args(argv)

    specs = episode_specs(a.scenario, a.random, [int(d) for d in a.difficulty.split(",")], a.seed, a.repeat)
    opt = ServerOptions(max_steps=a.max_steps, photo_mode=a.photo_mode, goal_conditions=not a.hide_goal_conditions,
                        verbose_failures=True if a.verbose else None, log_dir=a.log_dir,
                        oracle_baseline=not a.no_oracle)
    GridlabServer(Session(specs, opt), a.host, a.port, view=a.view, quiet=a.quiet).serve()


if __name__ == "__main__":
    main()
