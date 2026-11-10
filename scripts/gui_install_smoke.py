#!/usr/bin/env python
"""Check that an installed pyaermod can serve its GUI.

Run it with the Python of the environment that pyaermod was installed
into, from a directory that is not the checkout (so that ``src/`` cannot
stand in for the installed package)::

    python -m venv /tmp/gui-env
    /tmp/gui-env/bin/python -m pip install "dist/pyaermod-X.Y.Z-py3-none-any.whl[gui]"
    cd /tmp && /tmp/gui-env/bin/python /path/to/scripts/gui_install_smoke.py

It checks, in this order:

1. ``pyaermod`` is imported from the environment, not from a checkout;
2. ``pyaermod --help``, ``pyaermod gui --help``, ``pyaermod-app --help``
   and ``python -m pyaermod.gui_v2 --help`` exit 0 and show the options;
3. ``pyaermod-app --port <free port> --no-browser`` serves ``/`` with
   status 200, and the page, once its socket is connected as a browser
   connects it, shows every step of the step list;
4. ``pyaermod-desktop``: without pywebview it exits 1 with the line that
   names what to install; with pywebview only its import is checked (a
   window needs a display). ``--desktop`` says which is expected.

For a tool-style install (``pipx install``, ``uv tool install``) there is
no environment Python to run this with: pass ``--bin-dir`` with the
directory that holds the commands, and run it with any Python. The checks
that need to import from the environment are then skipped, and say so.

Only the standard library is used, apart from ``socketio``, which NiceGUI
depends on and which is imported from the environment under test.

Exit status: 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import sysconfig
import tempfile
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import List, Optional, Sequence

#: The labels of the step list (pyaermod.gui_v2.steps.STEPS), kept here as
#: text so that the --bin-dir mode needs no import of pyaermod.
STEP_LABELS = ("Project", "Sources", "Receptors", "Meteorology", "Output",
               "Review & Run", "Results")

START_TIMEOUT = 90.0       # seconds for the server to answer; cold Windows runners are slow
RENDER_TIMEOUT = 30.0      # seconds for the page content to arrive over the socket


class Failure(Exception):
    """A check did not pass."""


def _ok(message: str) -> None:
    print(f"  ok    {message}", flush=True)


def _skip(message: str) -> None:
    print(f"  skip  {message}", flush=True)


def _command(bin_dir: Path, name: str) -> str:
    """The path of an installed console script (``name`` or ``name.exe``)."""
    for candidate in (bin_dir / name, bin_dir / f"{name}.exe"):
        if candidate.is_file():
            return str(candidate)
    raise Failure(f"the {name} command is not in {bin_dir}")


def _run(argv: Sequence[str], timeout: float = 120.0) -> subprocess.CompletedProcess:
    return subprocess.run(list(argv), capture_output=True, text=True, timeout=timeout,
                          stdin=subprocess.DEVNULL)


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def check_installed_copy() -> None:
    """pyaermod comes from site-packages, not from a source tree."""
    import pyaermod
    location = Path(pyaermod.__file__).resolve().parent
    if (location.parent.parent / "pyproject.toml").is_file():
        raise Failure(f"pyaermod is imported from a checkout ({location}); "
                      f"run this from outside the repository, against an installed wheel")
    _ok(f"pyaermod {pyaermod.__version__} is imported from {location}")


def check_help(argv: Sequence[str], label: str) -> None:
    """``--help`` exits 0 and lists the GUI's options (it must not start a server)."""
    try:
        done = _run(argv, timeout=60.0)
    except subprocess.TimeoutExpired:
        raise Failure(f"{label} did not return within 60 s (did it start the server?)") from None
    if done.returncode != 0:
        raise Failure(f"{label} exited {done.returncode}:\n{done.stdout}{done.stderr}")
    for option in ("--host", "--port", "--no-browser"):
        if option not in done.stdout:
            raise Failure(f"{label} does not mention {option}:\n{done.stdout}")
    _ok(label)


def check_cli(bin_dir: Path) -> None:
    done = _run([_command(bin_dir, "pyaermod"), "--help"])
    if done.returncode != 0 or "gui" not in done.stdout:
        raise Failure(f"pyaermod --help exited {done.returncode} or does not list "
                      f"the gui subcommand:\n{done.stdout}{done.stderr}")
    _ok("pyaermod --help lists the gui subcommand")
    check_help([_command(bin_dir, "pyaermod"), "gui", "--help"], "pyaermod gui --help")
    check_help([_command(bin_dir, "pyaermod-app"), "--help"], "pyaermod-app --help")


def _get(url: str) -> tuple[int, str]:
    with urllib.request.urlopen(url, timeout=10) as response:
        return response.status, response.read().decode("utf-8", errors="replace")


async def _rendered_text(base_url: str, html: str) -> str:
    """Everything the page sends once its socket is connected.

    NiceGUI serves a shell at ``/`` and sends the page's elements over a
    socket.io connection that the browser opens with the client id found
    in the shell; this opens the same connection.
    """
    import socketio  # a dependency of nicegui

    found = re.search(r"""['"]client_id['"]\s*:\s*['"]([0-9a-f-]{36})['"]""", html)
    if not found:
        raise Failure("the page at / carries no NiceGUI client id")
    query = {"client_id": found.group(1), "next_message_id": 0,
             "tab_id": str(uuid.uuid4()), "document_id": str(uuid.uuid4())}
    received: List[str] = []
    client = socketio.AsyncClient(reconnection=False)

    @client.on("*")
    async def _any(event, *data):       # every server message, whatever its name
        received.append(json.dumps(data, default=str, ensure_ascii=False))

    def missing() -> List[str]:
        text = "".join(received)
        # Labels arrive JSON-encoded; "&" may be escaped by the encoder.
        return [label for label in STEP_LABELS
                if label not in text and label.replace("&", "\\u0026") not in text]

    url = f"{base_url}?" + "&".join(f"{k}={v}" for k, v in query.items())
    await client.connect(url, socketio_path="/_nicegui_ws/socket.io",
                         transports=["websocket"], wait_timeout=20)
    try:
        if not await client.call("handshake", query, timeout=20):
            raise Failure("the GUI refused the socket handshake")
        deadline = time.monotonic() + RENDER_TIMEOUT
        while missing() and time.monotonic() < deadline:
            await asyncio.sleep(0.2)
    finally:
        await client.disconnect()
    if missing():
        raise Failure(f"the page did not show the steps {missing()} within "
                      f"{RENDER_TIMEOUT:.0f} s of connecting")
    return "".join(received)


def check_server(bin_dir: Path, in_env: bool) -> None:
    """Start pyaermod-app, fetch ``/``, look for the step list, stop it."""
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    argv = [_command(bin_dir, "pyaermod-app"), "--port", str(port), "--no-browser"]
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        log_path = Path(tmp) / "server.log"
        with open(log_path, "w", encoding="utf-8") as log:
            server = subprocess.Popen(argv, stdout=log, stderr=subprocess.STDOUT,
                                      stdin=subprocess.DEVNULL, cwd=tmp)
            try:
                html = _wait_for_page(server, base, log_path)
                if "<title>PyAERMOD</title>" not in html:
                    raise Failure(f"GET / is not the PyAERMOD page:\n{html[:500]}")
                _ok(f"pyaermod-app --port {port} --no-browser serves / (200, title PyAERMOD)")
                if in_env and importlib.util.find_spec("socketio") is not None:
                    asyncio.run(_rendered_text(base, html))
                    _ok("the page shows the step list: " + ", ".join(STEP_LABELS))
                else:
                    _skip("step list (needs the environment's Python; --bin-dir was given)")
                if server.poll() is not None:
                    raise Failure(f"the server stopped by itself (exit {server.returncode}):\n"
                                  + log_path.read_text(encoding="utf-8", errors="replace"))
            finally:
                _stop(server)
        log_text = log_path.read_text(encoding="utf-8", errors="replace")
    if "Traceback (most recent call last)" in log_text:
        raise Failure(f"the server logged a traceback:\n{log_text}")
    _ok("the server stopped when asked and logged no traceback")


def _wait_for_page(server: subprocess.Popen, base: str, log_path: Path) -> str:
    deadline = time.monotonic() + START_TIMEOUT
    last: Optional[BaseException] = None
    while time.monotonic() < deadline:
        if server.poll() is not None:
            raise Failure(f"pyaermod-app exited {server.returncode} before serving a page:\n"
                          + log_path.read_text(encoding="utf-8", errors="replace"))
        try:
            status, html = _get(base + "/")
            if status == 200:
                return html
            last = Failure(f"GET / returned {status}")
        except (urllib.error.URLError, OSError) as e:
            last = e
        time.sleep(0.5)
    raise Failure(f"no page at {base}/ after {START_TIMEOUT:.0f} s ({last}):\n"
                  + log_path.read_text(encoding="utf-8", errors="replace"))


def _stop(server: subprocess.Popen) -> None:
    if server.poll() is not None:
        return
    if os.name == "nt":
        # The command is a launcher .exe whose child is the Python that
        # serves; ending only the launcher would leave the server running.
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(server.pid)],
                       capture_output=True, check=False)
    else:
        server.terminate()
    try:
        server.wait(timeout=20)
    except subprocess.TimeoutExpired:
        server.kill()
        server.wait(timeout=20)


def check_module_entry() -> None:
    check_help([sys.executable, "-m", "pyaermod.gui_v2", "--help"],
               "python -m pyaermod.gui_v2 --help")


def check_desktop(bin_dir: Path, expected: str, in_env: bool) -> None:
    """``pyaermod-desktop`` gives the install hint, or pywebview imports."""
    command = _command(bin_dir, "pyaermod-desktop")
    if expected == "auto":
        if not in_env:
            _skip("pyaermod-desktop (say --desktop hint or --desktop installed with --bin-dir)")
            return
        expected = "installed" if importlib.util.find_spec("webview") else "hint"
    if expected == "hint":
        done = _run([command])
        hint = "pyaermod-desktop needs pywebview"
        if done.returncode != 1 or hint not in done.stderr or "Traceback" in done.stderr:
            raise Failure(f"pyaermod-desktop without pywebview should exit 1 with one line "
                          f"saying {hint!r}; it exited {done.returncode}:\n{done.stderr}")
        _ok(f"pyaermod-desktop without pywebview: {done.stderr.strip()}")
    else:
        if not in_env:
            _skip("pywebview import (needs the environment's Python)")
            return
        done = _run([sys.executable, "-c",
                     "import webview, pyaermod.gui_v2.desktop; print(webview.__name__)"])
        if done.returncode != 0:
            raise Failure(f"pywebview is expected but does not import:\n{done.stderr}")
        _ok("pywebview and pyaermod.gui_v2.desktop import (no window is opened)")


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--bin-dir", type=Path,
        help="directory of the installed commands, for a pipx / uv tool install "
             "(default: the scripts directory of the Python running this)")
    parser.add_argument(
        "--desktop", choices=("auto", "hint", "installed"), default="auto",
        help="what pyaermod-desktop should do: 'hint' (pywebview absent: the [gui] "
             "extra), 'installed' ([gui-desktop], [all]); default: whichever "
             "matches the environment")
    args = parser.parse_args(argv)

    in_env = args.bin_dir is None
    bin_dir = args.bin_dir or Path(sysconfig.get_path("scripts"))
    # No browser tab may open, whatever a command under test decides.
    os.environ.setdefault("BROWSER", "true" if os.name != "nt" else "cmd /c rem")

    print(f"GUI install smoke check: Python {sys.version.split()[0]} on {sys.platform}, "
          f"commands in {bin_dir}", flush=True)
    try:
        if in_env:
            check_installed_copy()
        else:
            _skip("import location (--bin-dir was given)")
        check_cli(bin_dir)
        if in_env:
            check_module_entry()
        else:
            _skip("python -m pyaermod.gui_v2 (--bin-dir was given)")
        check_server(bin_dir, in_env)
        check_desktop(bin_dir, args.desktop, in_env)
    except Failure as failure:
        print(f"  FAIL  {failure}", flush=True)
        return 1
    print("GUI install smoke check passed.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
