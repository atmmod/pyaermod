"""
pywebview wrapper for the NiceGUI app.

Runs the NiceGUI server on the loopback in a background thread, then
opens a native OS window pointed at the local URL. Single codebase,
two delivery modes:

- ``pyaermod-app``     — browser tab (opens default browser)
- ``pyaermod-desktop`` — native OS window (this module)

The desktop entry is the path PyInstaller bundles for distribution
(see ``packaging/pyinstaller.spec`` once v1.9-E lands).

Requires the ``[gui-desktop]`` extra (pywebview).
"""

from __future__ import annotations

import socket
import threading
import time
from typing import Optional


def _free_port() -> int:
    """Return an available high-numbered loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> bool:
    """Poll until ``host:port`` accepts a TCP connection or timeout."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.25)
            try:
                s.connect((host, port))
                return True
            except OSError:
                time.sleep(0.1)
    return False


def main(*, title: str = "PyAERMOD",
         width: int = 1280, height: int = 800,
         port: Optional[int] = None) -> None:
    """Launch NiceGUI in a background thread and open a pywebview window."""
    try:
        import webview
    except ImportError as e:
        raise ImportError(
            "pywebview is required for the desktop GUI. Install with "
            "`pip install pyaermod[gui-desktop]`."
        ) from e

    from . import main as _server_main
    from .app import build_and_run

    chosen_port = port if port is not None else _free_port()

    def _serve() -> None:
        # show=False so NiceGUI doesn't open a browser tab in addition
        # to the pywebview window.
        build_and_run(port=chosen_port, show=False, title=title)

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    if not _wait_for_port("127.0.0.1", chosen_port, timeout=15.0):
        raise RuntimeError(
            f"NiceGUI server did not bind to 127.0.0.1:{chosen_port} "
            f"within 15 seconds."
        )

    webview.create_window(
        title=title,
        url=f"http://127.0.0.1:{chosen_port}",
        width=width, height=height,
    )
    webview.start()  # blocks until window is closed
    _ = _server_main  # keep import for entry-point resolution


__all__ = ["main"]
