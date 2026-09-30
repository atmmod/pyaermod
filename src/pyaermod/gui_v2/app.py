"""
NiceGUI app shell: the header, the step list and the steps.

The shell resolves the browser tab's
:class:`~pyaermod.gui_v2.session.Session` and builds the page around it:

- a header with the project's name and unsaved-changes marker, a
  one-line readiness summary and a Save button;
- a step list on the left (a drawer the menu button opens on narrow
  windows) with the seven steps of :data:`pyaermod.gui_v2.steps.STEPS`,
  each with a badge (not started, complete, warning, error) computed
  from the session's latest validation and runs. A step's accessible
  name carries its badge: "Sources, complete";
- one panel per step, built by the page module under
  :mod:`pyaermod.gui_v2.pages`. Each page exports ``render(session, *,
  dialogs, goto=None)``; ``goto(step_id)`` shows another step, for pages
  that send the user somewhere (a checklist item that links to Sources).

The shell validates the project when the page is built and again shortly
after every change (:func:`_keep_validated`), so the badges and the
readiness line follow the project. Pages follow the session through
:func:`pyaermod.gui_v2._live.live` sections.

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

import inspect
import logging
import time
import traceback
from pathlib import PurePath
from typing import TYPE_CHECKING, Any, Callable, Dict, MutableMapping, Optional, Set

from ._live import live
from .pages import meteorology, output, project, receptors, results, run, sources
from .session import Session, SessionEvent
from .steps import STEP_IDS, STEPS, StepStatus, readiness, step_accessible_name, step_statuses

if TYPE_CHECKING:  # pragma: no cover - typing only
    from nicegui import Client

logger = logging.getLogger(__name__)

#: The page module that builds each step.
_PAGES: Dict[str, Callable[..., None]] = {
    "project": project.render,
    "sources": sources.render,
    "receptors": receptors.render,
    "meteorology": meteorology.render,
    "output": output.render,
    "run": run.render,
    "results": results.render,
}

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


#: How long the shell waits after an edit before validating again (s), so a
#: burst of keystrokes costs one validation.
VALIDATION_DELAY_S = 0.15

#: The tab-storage key holding the step the tab last showed.
STEP_KEY = "current_step"

#: Badge icon and colour for each step status.
_BADGES = {
    StepStatus.NOT_STARTED: ("radio_button_unchecked", "grey-6"),
    StepStatus.COMPLETE: ("check_circle", "positive"),
    StepStatus.WARNING: ("warning", "warning"),
    StepStatus.ERROR: ("error", "negative"),
}


def _keep_validated(session: Session, client: Client) -> None:
    """Validate the session now, and again shortly after every change to its project.

    The step badges and the header's readiness line follow
    ``session.validation`` (VALIDATION_CHANGED). Met files are checked on
    disk, so a surface file that does not exist marks Meteorology.
    """
    import asyncio

    pending: Dict[str, Any] = {"handle": None}

    def run() -> None:
        pending["handle"] = None
        if _is_deleted(client):
            return
        try:
            session.validate(check_files=True)
        except Exception:                       # a validator bug must not break the page
            logger.exception("validating the project raised")

    def schedule(_change: Any) -> None:
        if pending["handle"] is not None:
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:                    # no event loop (a script): at once
            run()
            return
        pending["handle"] = loop.call_later(VALIDATION_DELAY_S, run)

    run()
    client.on_delete(session.subscribe(
        {SessionEvent.PROJECT_REPLACED, SessionEvent.PROJECT_CHANGED}, schedule))


def _call_render(render: Any, session: Session, **kwargs: Any) -> None:
    """Call a page's ``render`` with the keyword arguments it accepts.

    Every page takes ``dialogs``; ``goto`` and ``actions`` are passed only
    to pages whose ``render`` names them, so a page from another work
    package that does not take them yet still builds.
    """
    params = inspect.signature(render).parameters
    accepted = {k: v for k, v in kwargs.items() if k in params}
    render(session, **accepted)


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
        _keep_validated(session, client)

        # No input may be wider than the window: a page from another work
        # package that fixes a width (w-96) still fits a phone.
        ui.add_css(".q-tab-panel .q-field { max-width: 100%; }")

        # Every dialog a page creates lives here, outside any live section,
        # so no rebuild can delete an open dialog.
        page_dialogs = ui.element("div")
        actions = project.FileActions(session, dialogs=page_dialogs)
        start: Any = tab.get(STEP_KEY) if tab.get(STEP_KEY) in STEP_IDS else STEP_IDS[0]
        # Built below; the header's menu button and goto() use them.
        drawer: Any
        tabs: Any

        def goto(step_id: str) -> None:
            """Show step ``step_id`` (one of :data:`~.steps.STEP_IDS`)."""
            if step_id not in STEP_IDS:
                raise ValueError(f"no step {step_id!r}; expected one of {STEP_IDS}")
            tabs.set_value(step_id)

        def remember(e: Any) -> None:
            tab[STEP_KEY] = e.value

        # ----- header -------------------------------------------------
        with ui.header().classes("items-center gap-x-3 gap-y-0 flex-wrap q-py-xs"):
            ui.button(icon="menu", on_click=lambda: drawer.toggle()).props(
                'flat round color=white aria-label="Steps"').classes("lt-md")
            ui.label().bind_text_from(session, "title").classes(
                "text-subtitle1 text-weight-medium ellipsis min-w-0").mark("header-title")

            @live(session, SessionEvent.VALIDATION_CHANGED)
            def _readiness() -> None:
                ui.label(readiness(session.validation)).classes("text-body2 min-w-0").props(
                    'role="status"').mark("readiness")

            ui.space()
            ui.button("Save", icon="save", on_click=actions.save).props(
                "flat color=white").mark("header-save")

        # ----- step list ----------------------------------------------
        with ui.left_drawer(bordered=True).props(
                f"width=232 breakpoint={DRAWER_BREAKPOINT}") as drawer:
            ui.label("Steps").classes("text-overline text-grey-8 q-px-md q-pt-sm")
            with ui.tabs(value=start, on_change=remember).props(
                    'vertical inline-label no-caps align="left" active-bg-color="blue-1"'
                    ' indicator-color="primary"').classes("w-full") as tabs:
                handles = {}
                badges = {}
                for step in STEPS:
                    with ui.tab(step.id, label=step.label).classes("justify-start") as handle:
                        badges[step.id] = ui.icon("radio_button_unchecked").classes(
                            "q-ml-sm").props('aria-hidden="true"')
                    handles[step.id] = handle
            tabs.on_value_change(lambda e: _close_on_narrow(drawer, e))

        def show_badges(_change: Any = None) -> None:
            statuses = step_statuses(session.project, session.validation, session.runs)
            for step in STEPS:
                status = statuses[step.id]
                icon, colour = _BADGES[status]
                badges[step.id].name = icon
                badges[step.id].props(f"color={colour}")
                handles[step.id].props(f'aria-label="{step_accessible_name(step, status)}"')

        show_badges()
        # Not on PROJECT_CHANGED: the validation that follows every change
        # (VALIDATION_CHANGED) is what the badges read, and reading the old
        # one would flash an error for a source that was just added.
        client.on_delete(session.subscribe(
            {SessionEvent.VALIDATION_CHANGED, SessionEvent.RUN_FINISHED}, show_badges))

        # ----- the steps ----------------------------------------------
        with ui.tab_panels(tabs, value=start).classes("w-full"):
            for step in STEPS:
                with ui.tab_panel(step.id).props(f'aria-label="{step.label}"').classes(
                        "q-pa-sm"):
                    _call_render(_PAGES[step.id], session, dialogs=page_dialogs, goto=goto,
                                 actions=actions)

        # ----- footer / status bar (built last: tests wait for it) ----
        # Not fixed: a fixed footer covers the middle of full-page screenshots.
        with ui.footer(fixed=False).classes("bg-grey-3 text-grey-9 q-py-xs"):
            ui.label("PyAERMOD GUI v2 (NiceGUI)").classes("text-caption")


#: Below this window width the step list is a drawer the menu button opens.
DRAWER_BREAKPOINT = 1024


def _close_on_narrow(drawer: Any, _event: Any) -> None:
    from nicegui import ui

    ui.run_javascript(
        f"if (window.innerWidth < {DRAWER_BREAKPOINT}) getElement({drawer.id}).hide()")


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
