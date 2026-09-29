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

NiceGUI frees a tab's storage ``app.storage.max_tab_storage_age`` (30
days) after the storage itself last changed. The session changes in
place, so every page also records in the tab's storage when its session
was last used (:data:`LAST_USED_KEY`); a tab in daily use keeps its
session.
"""

from __future__ import annotations

import logging
import time
import traceback
from pathlib import PurePath
from typing import TYPE_CHECKING, Any, Dict, MutableMapping, Optional, Set

from .pages import meteorology, output, project, receptors, results, run, sources
from .session import Session, SessionEvent

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

#: The tab-storage key holding when the tab's session was last used.
LAST_USED_KEY = "session_last_used"

#: How often (seconds) a page records that its session is in use.
_TOUCH_INTERVAL_S = 60.0

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


def _is_deleted(client: Client) -> bool:
    """Whether NiceGUI has deleted ``client``.

    ``Client.is_deleted`` exists from NiceGUI 3.13; the package allows 3.0,
    whose clients have only the private flag behind it.
    """
    flag = getattr(client, "is_deleted", None)
    if flag is None:
        flag = getattr(client, "_deleted", False)
    return bool(flag)


def _tab_storage() -> MutableMapping[str, Any]:
    from nicegui import app

    return app.storage.tab


def _session_for(client: Client, tab: Optional[MutableMapping[str, Any]] = None) -> Session:
    """The session this tab works on: its own, an adopted one, or a fork.

    ``tab`` is the tab's storage, ``app.storage.tab`` by default, which
    needs the client's socket to be connected.
    """
    if tab is None:
        tab = _tab_storage()
    session = tab.get("session")
    if not isinstance(session, Session):
        session = tab["session"] = Session(tab_id=client.tab_id)
        return session
    if session.tab_id == client.tab_id:
        return session                      # the same tab, reloaded
    others = [c for c in _OWNERS.get(id(session), ())
              if c is not client and not _is_deleted(c)]
    if others:
        # Another page is still built on it (the original of a duplicated
        # tab, or the lingering page of a desktop reload): copy it.
        session = tab["session"] = session.fork(client.tab_id)
        return session
    session.tab_id = client.tab_id          # every owner is gone: adopt it
    return session


def _keep_in_use(session: Session, client: Client, tab: MutableMapping[str, Any]) -> None:
    """Record in ``tab`` that ``session`` is in use: now, and as it changes.

    Writing a key is what moves the storage's modification time, which is
    what NiceGUI prunes on. At most one write per ``_TOUCH_INTERVAL_S``.
    """
    last = {"at": time.time()}
    tab[LAST_USED_KEY] = last["at"]

    def touch(_change: Any) -> None:
        now = time.time()
        if now - last["at"] >= _TOUCH_INTERVAL_S:
            last["at"] = now
            tab[LAST_USED_KEY] = now

    client.on_delete(session.subscribe(set(SessionEvent), touch))


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
        if _is_deleted(client):
            return
        tab = _tab_storage()
        session = _session_for(client)      # looked up at call time (tests wrap it)
        _claim(session, client)
        _keep_in_use(session, client, tab)

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

        # --- WP-G4: Review & Run's checklist links to other steps. The
        # step ids are run.STEP_IDS, in the order of _TABS; the integrator
        # re-points this at WP-G3's navigation.
        def goto(step_id: str) -> None:
            if step_id in run.STEP_IDS:
                tab_bar.set_value(tab_handles[run.STEP_IDS.index(step_id)])
        # --- end WP-G4

        with ui.tab_panels(tab_bar, value=tab_handles[0]).classes("w-full"):
            for (_name, render), handle in zip(
                _TABS, tab_handles, strict=False,
            ):
                with ui.tab_panel(handle):
                    if render is run.render:    # WP-G4
                        run.render(session, dialogs=page_dialogs, goto=goto)
                    else:
                        render(session, dialogs=page_dialogs)

        # ----- footer / status bar (built last: tests wait for it) ----
        with ui.footer().classes("bg-grey-3 text-grey-9"):
            ui.label("PyAERMOD GUI v2 (NiceGUI)")


class _CancelledUploadFilter(logging.Filter):
    """Drop uvicorn's traceback for an upload the browser cancelled.

    Closing the Open dialog while a file is still being sent aborts the
    request; NiceGUI 3.17's upload route lets Starlette's
    ``ClientDisconnect`` escape, and uvicorn logs it as "Exception in ASGI
    application" with a traceback. Nothing went wrong: the project is
    untouched. Every other record passes.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        if exc is None or not _is_cancelled_upload(exc):
            return True
        logger.info("An upload was cancelled before it finished")
        return False


def _is_cancelled_upload(exc: BaseException) -> bool:
    """True if ``exc`` is a client disconnect raised inside NiceGUI's upload route."""
    try:
        from starlette.requests import ClientDisconnect
    except ImportError:  # pragma: no cover - starlette ships with nicegui
        return False
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    if not isinstance(exc, ClientDisconnect):
        return False
    return any(PurePath(frame.filename).parts[-3:] == ("nicegui", "elements", "upload.py")
               for frame in traceback.extract_tb(exc.__traceback__))


_UPLOAD_FILTER = _CancelledUploadFilter()


def _quiet_cancelled_uploads() -> None:
    """Install :class:`_CancelledUploadFilter` on uvicorn's error log (once)."""
    uvicorn_error = logging.getLogger("uvicorn.error")
    if _UPLOAD_FILTER not in uvicorn_error.filters:
        uvicorn_error.addFilter(_UPLOAD_FILTER)


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
    _quiet_cancelled_uploads()
    ui.run(
        host=host,
        port=port,
        show=show,
        title=title or "PyAERMOD",
        reload=reload,
    )


__all__ = ["build_and_run", "build_app"]
