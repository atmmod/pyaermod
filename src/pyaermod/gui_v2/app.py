"""
NiceGUI app shell: top-level layout, tab navigation, header, status bar.

The shell is intentionally thin. Page modules under
:mod:`pyaermod.gui_v2.pages` register themselves into the tab bar via
:func:`build_app`. Per-session state is created by
:func:`build_and_run` and threaded into each page as a positional
argument.

Page modules each export a single ``render(state)`` callable that the
shell invokes inside the right tab panel.
"""

from __future__ import annotations

from typing import Optional

from .pages import meteorology, output, project, receptors, results, run, sources
from .state import AppState

# Display order for the tab bar.
_TABS = [
    ("Project",    project.render),
    ("Sources",    sources.render),
    ("Receptors",  receptors.render),
    ("Meteorology", meteorology.render),
    ("Output",     output.render),
    ("Run",        run.render),
    ("Results",    results.render),
]


def build_app() -> None:
    """Define the NiceGUI page hierarchy. Called once on app start.

    Per-session state is created when the user opens the page (one
    AppState per browser tab); the shell threads it into every page
    callback.
    """
    from nicegui import ui

    @ui.page("/")
    def index() -> None:
        state = AppState()

        # ----- header -------------------------------------------------
        with ui.header().classes("items-center justify-between"):
            ui.label("PyAERMOD").classes("text-h6 q-mr-md")
            ui.label().bind_text_from(state, "title")

        # ----- tabs + panels -----------------------------------------
        with ui.tabs() as tab_bar:
            tab_handles = [ui.tab(name) for name, _ in _TABS]
        with ui.tab_panels(tab_bar, value=tab_handles[0]).classes("w-full"):
            for (_name, render), handle in zip(
                _TABS, tab_handles, strict=False,
            ):
                with ui.tab_panel(handle):
                    render(state)

        # ----- footer / status bar -----------------------------------
        with ui.footer().classes("bg-grey-3 text-grey-9"):
            ui.label("PyAERMOD GUI v2 (NiceGUI)")


def build_and_run(
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    show: bool = True,
    title: Optional[str] = None,
    reload: bool = False,
) -> None:
    """Launch the NiceGUI server.

    Parameters
    ----------
    host
        Bind address (default loopback).
    port
        Port to bind. Caller can adjust if 8080 is in use.
    show
        Open a browser tab automatically (default True). Set False
        when launching inside a pywebview window.
    title
        Optional window title override.
    reload
        Enable NiceGUI's hot-reload during development.
    """
    from nicegui import ui

    build_app()
    ui.run(
        host=host,
        port=port,
        show=show,
        title=title or "PyAERMOD",
        reload=reload,
    )


__all__ = ["build_and_run", "build_app"]
