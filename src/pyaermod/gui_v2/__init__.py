"""
PyAERMOD GUI v2 — NiceGUI-based replacement for the Streamlit GUI.

The new GUI ships side-by-side with the legacy Streamlit GUI through
the 1.x cycle. NiceGUI gives us:

- No rerun-on-keystroke model — real reactive state binding
- Real components: AG-Grid tables, Leaflet maps, Plotly plots
- Same Python-only dev model as Streamlit
- Optional native desktop window via :mod:`pyaermod.gui_v2.desktop`
  (pywebview wrapper) — single codebase, two delivery modes

Entry points
------------

- ``pyaermod-app`` — launches NiceGUI in a browser tab
- ``pyaermod-desktop`` — launches NiceGUI inside a pywebview window

Both call :func:`pyaermod.gui_v2.main` under the hood.

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


def main() -> None:
    """Launch the NiceGUI application.

    Importing :mod:`nicegui` is deferred to call-time so that
    ``import pyaermod`` doesn't pay the NiceGUI import cost when the
    GUI isn't being used.
    """
    from .app import build_and_run

    build_and_run()


__all__ = ["main"]
