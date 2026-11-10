"""
PyAERMOD GUI v2 — the NiceGUI app.

It replaced the Streamlit GUI, which was removed in v2.0. NiceGUI gives us:

- No rerun-on-keystroke model — real reactive state binding
- Real components: AG-Grid tables, Leaflet maps, Plotly plots
- A Python-only dev model
- Optional native desktop window via :mod:`pyaermod.gui_v2.desktop`
  (pywebview wrapper) — single codebase, two delivery modes

Entry points
------------

- ``pyaermod-app`` — :func:`pyaermod.gui_v2.main`: serves the app and
  opens it in a browser tab. ``--host``, ``--port`` and ``--no-browser``
  change where it listens and whether a tab opens (a container binds
  ``0.0.0.0`` and opens none). Needs the ``[gui]`` extra. ``pyaermod gui``
  and ``python -m pyaermod.gui_v2`` are the same command.
- ``pyaermod-desktop`` — :func:`pyaermod.gui_v2.desktop.main`: the same
  app inside a pywebview window. Needs the ``[gui-desktop]`` extra.

Without the packages of its extra, either command stops with one line
that names what to install (:func:`_missing_dependency`).

Both serve the app with :func:`pyaermod.gui_v2.app.build_and_run`.

Module layout::

    gui_v2/
      __init__.py        -- entry point ``main()``
      __main__.py        -- ``python -m pyaermod.gui_v2``
      session.py         -- Session: the project, its runs and change events (no UI)
      state.py           -- _empty_project(), the blank project
      project_io.py      -- JSON save/load for AERMODProject
      app.py             -- top-level shell (tabs, header, one session per tab)
      _live.py           -- live(): page sections rebuilt from the session
      _form.py           -- dataclass field -> widget helper
      _native.py         -- the desktop window, for native dialogs
      run_results.py     -- what Results shows about a run, from its files (no UI)
      results_map.py     -- the Results step's concentration map (matplotlib Agg)
      desktop.py         -- pywebview wrapper (``pyaermod-desktop``)
      pages/
        project.py       -- file menu + project metadata
        sources.py       -- source editor
        receptors.py     -- receptor editor
        meteorology.py   -- AERMET / met-file pathway
        output.py        -- output pathway + chemistry
        run.py           -- AERMOD invocation and the last run's status
        results.py       -- a run's results, downloads and the run history

The shell resolves each browser tab's
:class:`~pyaermod.gui_v2.session.Session` and passes it to every page;
pages rebuild from it through :func:`pyaermod.gui_v2._live.live`.
"""

from __future__ import annotations

import argparse
import socket
import sys
from pathlib import Path
from typing import Optional, Sequence


def _installed_by_conda() -> bool:
    """Whether this pyaermod is a conda package (not pip inside a conda env).

    conda records each package it installs as ``conda-meta/<name>-<version>-
    <build>.json`` in the environment; pip leaves no such record.
    """
    return any((Path(sys.prefix) / "conda-meta").glob("pyaermod-[0-9]*.json"))


def _missing_dependency(package: str, command: str, pip_fix: str,
                        conda_fix: str) -> SystemExit:
    """The exit for a GUI command whose optional package is not installed.

    One line on stderr and exit status 1, not a traceback: the person who
    sees it typed a command. ``pip_fix`` names the pip extra; ``conda_fix``
    is given instead when pyaermod was installed by conda, which has no
    extras.
    """
    fix = conda_fix if _installed_by_conda() else pip_fix
    return SystemExit(f"{command} needs {package}, which is not installed. "
                      f"Install it with {fix}.")


def _require_nicegui(command: str) -> None:
    """Stop with the install hint unless NiceGUI can be imported."""
    try:
        import nicegui  # noqa: F401
    except ImportError as e:
        raise _missing_dependency(
            "NiceGUI", command,
            pip_fix='`pip install "pyaermod[gui]"`',
            conda_fix="`conda install -c conda-forge pyaermod-gui`") from e


def _add_arguments(parser: argparse.ArgumentParser) -> None:
    """The options of ``pyaermod-app``, also given to ``pyaermod gui``."""
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="address to listen on (default: 127.0.0.1, this computer only). "
             "The GUI reads and writes files and runs AERMOD as the user who "
             "started it, for anyone who can reach it: use 0.0.0.0 only in a "
             "container or on a network you trust.")
    parser.add_argument(
        "--port", type=int, default=8080,
        help="port to listen on (default: 8080); choose another when 8080 "
             "is already in use")
    parser.add_argument(
        "--no-browser", action="store_true",
        help="do not open a browser tab (for a container or a remote server)")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyaermod-app",
        description="Serve the PyAERMOD GUI and open it in a browser tab. "
                    "Stop it with Ctrl+C.",
    )
    _add_arguments(parser)
    return parser


def _require_free_port(host: str, port: int) -> None:
    """Stop with one line when ``host:port`` cannot be listened on.

    Otherwise the server logs the operating system's error among its
    start-up lines and exits, and nothing says which option to change.
    """
    family = socket.AF_INET6 if ":" in host else socket.AF_INET
    with socket.socket(family, socket.SOCK_STREAM) as s:
        if sys.platform != "win32":
            # As the server does, so a port just released is not refused.
            # (On Windows the option would let a port in use be bound.)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind((host, port))
        except OSError as e:
            raise SystemExit(
                f"Cannot listen on {host} port {port} ({e.strerror or e}). "
                f"If another program, or another PyAERMOD window, is using the "
                f"port, choose a different one: --port {port + 1}") from e


def _serve(args: argparse.Namespace) -> None:
    """Serve the app as the parsed options say; returns when it is stopped."""
    _require_nicegui("pyaermod-app")
    _require_free_port(args.host, args.port)

    from .app import build_and_run

    build_and_run(host=args.host, port=args.port, show=not args.no_browser)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Launch the NiceGUI application (the ``pyaermod-app`` command).

    ``argv`` is the command line without the program name; ``None`` reads
    ``sys.argv``. Run ``pyaermod-app --help`` for the options.

    Importing :mod:`nicegui` is deferred to call-time so that
    ``import pyaermod`` doesn't pay the NiceGUI import cost when the
    GUI isn't being used.
    """
    _serve(_build_parser().parse_args(argv))


__all__ = ["main"]
