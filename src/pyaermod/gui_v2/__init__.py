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
  ``0.0.0.0`` and opens none). Needs the ``[gui]`` extra.
- ``pyaermod-desktop`` — :func:`pyaermod.gui_v2.desktop.main`: the same
  app inside a pywebview window. Needs the ``[gui-desktop]`` extra.

Both serve the app with :func:`pyaermod.gui_v2.app.build_and_run`.

Module layout::

    gui_v2/
      __init__.py        -- entry point ``main()``
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
from typing import Optional, Sequence


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyaermod-app",
        description="Serve the PyAERMOD GUI and open it in a browser tab.",
    )
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="address to listen on (default: 127.0.0.1, this computer only). "
             "The GUI reads and writes files and runs AERMOD as the user who "
             "started it, for anyone who can reach it: use 0.0.0.0 only in a "
             "container or on a network you trust.")
    parser.add_argument(
        "--port", type=int, default=8080,
        help="port to listen on (default: 8080)")
    parser.add_argument(
        "--no-browser", action="store_true",
        help="do not open a browser tab (for a container or a remote server)")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Launch the NiceGUI application (the ``pyaermod-app`` command).

    ``argv`` is the command line without the program name; ``None`` reads
    ``sys.argv``. Run ``pyaermod-app --help`` for the options.

    Importing :mod:`nicegui` is deferred to call-time so that
    ``import pyaermod`` doesn't pay the NiceGUI import cost when the
    GUI isn't being used.
    """
    args = _build_parser().parse_args(argv)
    try:
        import nicegui  # noqa: F401
    except ImportError as e:
        raise ImportError(
            "NiceGUI is required for the GUI. Install with "
            '`pip install "pyaermod[gui]"`.'
        ) from e

    from .app import build_and_run

    build_and_run(host=args.host, port=args.port, show=not args.no_browser)


__all__ = ["main"]
