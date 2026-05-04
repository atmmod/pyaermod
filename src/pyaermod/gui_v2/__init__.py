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
      state.py           -- AppState dataclass
      project_io.py      -- JSON save/load for AERMODProject
      app.py             -- top-level shell (tabs, header, status bar)
      pages/
        project.py       -- file menu + project metadata
        sources.py       -- source editor (port of the Streamlit version)
        receptors.py     -- receptor editor
        meteorology.py   -- AERMET / met-file pathway
        output.py        -- output pathway + chemistry
        run.py           -- AERMOD invocation + progress
        results.py       -- POSTFILE viewer + design values

The shell + state layer is in :mod:`pyaermod.gui_v2.app` and
:mod:`pyaermod.gui_v2.state`. Pages are added incrementally — every
page that hasn't been ported yet renders a placeholder banner.
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
