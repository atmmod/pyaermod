#!/usr/bin/env python3
"""Serve the browser GUI (webapp/) against CPython instead of Pyodide.

The published GUI runs pyaermod.browser in a Web Worker under Pyodide, with
AERMOD's WebAssembly build. This server runs the same module here and
answers the page's calls over HTTP (``POST /api/call``), so the shell can be
developed and its journeys tested without the WebAssembly build:

    python scripts/wasm/app_dev_server.py [--port 8765] [--replay albany_success]

AERMOD is the ``aermod`` on PATH, or, with ``--replay NAME``, a replay of
the recording ``tests/fixtures/gui/aermod_recordings/NAME`` through
``tests/e2e/fake_aermod.py``. The sample met files are served from
``tests/fixtures``. Listens on 127.0.0.1 only; it is a development tool.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import stat
import sys
import tempfile
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
APP = REPO / "webapp"
FAKE_AERMOD = REPO / "tests" / "e2e" / "fake_aermod.py"


def sample_files() -> dict:
    """URL path under the app -> file on disk, for every sample in samples.json."""
    out = {}
    for sample in json.loads((APP / "samples.json").read_text()):
        for f in sample["files"]:
            out[f["url"]] = REPO / sample["source"] / f["name"]
    return out


def make_handler(samples: dict, lock: threading.Lock):
    from pyaermod import browser

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(APP), **kwargs)

        def log_message(self, fmt, *args):  # quiet
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def do_GET(self):
            path = self.path.split("?", 1)[0].lstrip("/")
            if path == "config.json":
                body = json.dumps({"backend": "http", "api": "api/call",
                                   "samples": json.loads((APP / "samples.json").read_text())})
                return self._send(200, body.encode(), "application/json")
            if path in samples:
                return self._send(200, samples[path].read_bytes(), "application/octet-stream")
            return super().do_GET()

        def do_POST(self):
            if self.path.split("?", 1)[0] != "/api/call":
                return self._send(404, b"not found", "text/plain")
            length = int(self.headers.get("Content-Length") or 0)
            request = json.loads(self.rfile.read(length) or b"{}")
            with lock:                       # one call at a time, as in the worker
                reply = browser.call(request.get("op", ""), json.dumps(request.get("args") or {}))
            return self._send(200, reply.encode(), "application/json")

        def _send(self, code, body, ctype):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return Handler


def use_replay(recording: str, bin_dir: Path) -> None:
    """Make pyaermod.browser run AERMOD as a replay of ``recording``."""
    from pyaermod import browser
    from pyaermod.runner import AERMODRunner

    exe = bin_dir / "aermod"
    exe.write_text(f"#!/bin/sh\nexec {sys.executable} {FAKE_AERMOD} \"$@\"\n")
    exe.chmod(exe.stat().st_mode | stat.S_IEXEC)
    os.environ["PYAERMOD_E2E_RECORDING"] = recording
    browser.RUNNER_FACTORY = lambda: AERMODRunner(executable_path=str(exe), log_level="WARNING")


def serve(port: int, replay: str | None = None, work_dir: Path | None = None,
          ready: threading.Event | None = None) -> ThreadingHTTPServer:
    from pyaermod import browser

    scratch = Path(tempfile.mkdtemp(prefix="pyaermod_app_dev_"))
    browser.WORK_DIR = work_dir or scratch / "work"
    if replay:
        use_replay(replay, scratch)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(sample_files(), threading.Lock()))
    if ready is not None:
        ready.set()
    return server


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--replay", help="replay this AERMOD recording instead of running aermod")
    args = parser.parse_args(argv)
    server = serve(args.port, args.replay)
    print(f"pyaermod browser GUI (CPython backend) at http://127.0.0.1:{server.server_port}/")
    with contextlib.suppress(KeyboardInterrupt):
        server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
