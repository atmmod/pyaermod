"""
NiceGUI app shell: top-level layout, tab navigation, header, status bar.

The shell is intentionally thin. It resolves the browser tab's
:class:`~pyaermod.gui_v2.session.Session` and hands it to every page
module under :mod:`pyaermod.gui_v2.pages`, each of which exports a
``render(session, *, dialogs)`` callable that builds its tab panel.
Pages follow the session through :func:`pyaermod.gui_v2._live.live`
sections.

One session per browser tab
---------------------------
The session lives in ``app.storage.tab``, NiceGUI's in-memory per-tab
store, so a reload of the tab finds the project and the run history it
left (journey J8). A session belongs to the tab that created it. When a
page is built under another tab id (a duplicated browser tab, whose
storage NiceGUI copies, or a desktop-window reload, which arrives under a
new tab id) the session is adopted only if no page built on it is still
alive; otherwise the new tab gets a fork, an independent copy. A page
counts as alive from when it is built until NiceGUI deletes its client,
which is some seconds after its socket closes. The decision is recorded
in PLAN-gui.md ("Reload decision").
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Dict, Optional, Set

from .pages import meteorology, output, project, receptors, results, run, sources
from .session import Session

if TYPE_CHECKING:  # pragma: no cover - typing only
    from nicegui import Client

logger = logging.getLogger(__name__)

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

# id(session) -> the clients whose pages were built on it and are not yet
# deleted (connected, or disconnected and lingering until NiceGUI reaps them).
_OWNERS: Dict[int, Set[Client]] = {}


def _claim(session: Session, client: Client) -> None:
    """Record that ``client``'s page is built on ``session`` until it is deleted."""
    owners = _OWNERS.setdefault(id(session), set())
    owners.add(client)

    def release() -> None:
        owners.discard(client)
        if not owners and _OWNERS.get(id(session)) is owners:
            del _OWNERS[id(session)]

    client.on_delete(release)


def _session_for(client: Client) -> Session:
    """The session this tab works on: its own, an adopted one, or a fork.

    Must run after the client's socket connected (``app.storage.tab``
    needs it).
    """
    from nicegui import app

    tab = app.storage.tab
    session = tab.get("session")
    if not isinstance(session, Session):
        session = tab["session"] = Session(tab_id=client.tab_id)
        return session
    if session.tab_id == client.tab_id:
        return session                      # the same tab, reloaded
    others = [c for c in _OWNERS.get(id(session), ()) if c is not client and not c.is_deleted]
    if others:
        # Another page is still built on it (the original of a duplicated
        # tab, or the lingering page of a desktop reload): copy it.
        session = tab["session"] = session.fork(client.tab_id)
        return session
    session.tab_id = client.tab_id          # every owner is gone: adopt it
    return session


def _warn_if_redis() -> None:
    from nicegui.storage import Storage

    if Storage.redis_url:
        logger.warning(
            "NICEGUI_REDIS_URL is set: Redis-backed tab storage cannot hold the "
            "GUI's live sessions, so reloading a tab will not restore its project.")


def build_app() -> None:
    """Define the NiceGUI page hierarchy. Called once on app start."""
    from nicegui import ui

    _warn_if_redis()

    @ui.page("/")
    async def index(client: Client) -> None:
        # app.storage.tab exists only once the socket is connected; what is
        # built after this await is sent over the socket.
        await client.connected()
        if client.is_deleted:
            return
        session = _session_for(client)      # looked up at call time (tests wrap it)
        _claim(session, client)

        # Every dialog a page creates lives here, outside any live section,
        # so no rebuild can delete an open dialog.
        page_dialogs = ui.element("div")

        # ----- header -------------------------------------------------
        with ui.header().classes("items-center justify-between"):
            ui.label("PyAERMOD").classes("text-h6 q-mr-md")
            ui.label().bind_text_from(session, "title")

        # ----- tabs + panels -----------------------------------------
        with ui.tabs() as tab_bar:
            tab_handles = [ui.tab(name) for name, _ in _TABS]
        with ui.tab_panels(tab_bar, value=tab_handles[0]).classes("w-full"):
            for (_name, render), handle in zip(
                _TABS, tab_handles, strict=False,
            ):
                with ui.tab_panel(handle):
                    render(session, dialogs=page_dialogs)

        # ----- footer / status bar (built last: tests wait for it) ----
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
