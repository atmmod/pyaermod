"""
Page sections that follow a :class:`~pyaermod.gui_v2.session.Session`.

The rule every page follows (PLAN-gui.md, "Target design"): a widget that
shows or edits part of ``session.project`` is built only inside a
:func:`live` section, and every live section is rebuilt when the project
is replaced. Rebuilding deletes the old widgets and, with them, their
bindings to the old project's objects, so no widget can keep showing or
editing a project the user has discarded (defect D3).

NiceGUI is imported inside the functions, so importing this module does
not import NiceGUI.
"""

from __future__ import annotations

import contextvars
from typing import Any, Callable, Iterable, Optional

from .session import Change, Session, SessionEvent

_BUILDING = contextvars.ContextVar("pyaermod_live_building", default=False)


def live(session: Session, *events: SessionEvent,
         parts: Optional[Iterable[str]] = None) -> Callable[[Callable[[], Any]], Any]:
    """Decorator: build a refreshable section now and rebuild it on change.

    The section is rebuilt on ``PROJECT_REPLACED`` (always) and on each of
    ``events``. For ``PROJECT_CHANGED`` it is rebuilt only when the change
    names one of ``parts`` (all parts when ``parts`` is None); a section
    should not subscribe to the changes its own widgets make, or it would
    rebuild under the user's cursor.

    The refreshable is created per call, inside the current client, so it
    only ever rebuilds that browser tab. Its subscription ends when the
    client is deleted.

    Builders must not call Session methods that emit events (validate()
    included): the section would refresh itself forever. They must not
    call live() either, which would add a subscription on every rebuild
    of the outer section; nesting raises RuntimeError.
    """
    from nicegui import ui

    if _BUILDING.get():
        raise RuntimeError("live() sections cannot be nested")
    wanted = {SessionEvent.PROJECT_REPLACED, *events}
    wanted_parts = None if parts is None else frozenset(parts)

    def decorate(build: Callable[[], Any]) -> Any:
        def guarded() -> Any:
            # A ContextVar, because NiceGUI rebuilds in a task of its own;
            # each task gets a copy of the context, so the flag covers the
            # first build and every rebuild.
            token = _BUILDING.set(True)
            try:
                return build()
            finally:
                _BUILDING.reset(token)

        view = ui.refreshable(guarded)
        view()

        def on_change(change: Change) -> None:
            if (change.event is SessionEvent.PROJECT_CHANGED and wanted_parts is not None
                    and change.part not in wanted_parts):
                return
            # Deferred to a background task; the caller carries on first.
            view.refresh()

        ui.context.client.on_delete(session.subscribe(wanted, on_change))
        return view

    return decorate


__all__ = ["live"]
