"""
Building blocks every step page shares.

- :func:`step_page`: the page template, a heading, a one-line
  introduction and a column that is as wide as the window up to 1280 px;
- :func:`section`: a titled card inside a step;
- :func:`confirm`: a yes/no question in the page's dialog container;
- :class:`Pager`: which slice of a long table is shown, with Previous /
  Next buttons that have accessible names;
- :func:`plan_view`: the plan-view plot, rebuilt after every change to
  the sources or receptors.

NiceGUI is imported inside the functions, so importing this module does
not import NiceGUI.
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable, Iterator, List, Optional, Sequence

from .session import Session, SessionEvent

#: Rows a table shows per page.
ROWS_PER_PAGE = 25

#: What a step does when it sends the user to another step.
Goto = Callable[[str], None]


def no_goto(_step: str) -> None:
    """The default ``goto`` of a page built without the shell: do nothing."""


@contextlib.contextmanager
def step_page(title: str, intro: str = "") -> Iterator[Any]:
    """The frame of a step: its heading and introduction, then its content."""
    from nicegui import ui

    with ui.column().classes("w-full max-w-screen-xl mx-auto gap-4 q-pa-sm") as column:
        ui.label(title).classes("text-h5").props('role="heading" aria-level="2"')
        if intro:
            ui.label(intro).classes("text-body2 text-grey-8")
        yield column


@contextlib.contextmanager
def section(title: str, intro: str = "") -> Iterator[Any]:
    """A titled card holding one group of a step's controls."""
    from nicegui import ui

    with ui.card().classes("w-full").props("flat bordered") as card:
        ui.label(title).classes("text-subtitle1 text-weight-medium").props(
            'role="heading" aria-level="3"')
        if intro:
            ui.label(intro).classes("text-body2 text-grey-8")
        yield card


def confirm(dialogs: Any, *, question: str, detail: str, yes: str,
            on_yes: Callable[[], Any]) -> None:
    """Ask ``question`` in a dialog; call ``on_yes()`` if the user picks ``yes``.

    The dialog is built in the page's static dialog container (``dialogs``)
    and deletes itself when it closes, like the editors. ``on_yes`` may be
    a coroutine function.
    """
    from nicegui import ui

    async def _yes() -> None:
        # Act first, then close: closing deletes the dialog, and with it the
        # slot any notification from ``on_yes`` would be sent through.
        try:
            result = on_yes()
            if hasattr(result, "__await__"):
                await result
        finally:
            dialog.close()

    with dialogs, ui.dialog().mark("confirm-dialog") as dialog, ui.card():
        ui.label(question).classes("text-h6")
        ui.label(detail).classes("text-body2")
        with ui.row().classes("justify-end w-full q-gutter-sm"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button(yes, on_click=_yes).props("color=negative")
    dialog.on_value_change(lambda e: None if e.value else dialog.delete())
    dialog.open()


class Pager:
    """The page of a long table that is on screen.

    Only that page's rows are sent to the browser, so a project with ten
    thousand receptors costs no more to show than one with ten. The page
    survives rebuilds of the table (it is not part of the project) and is
    kept in range when rows go away. With a ``session``, it goes back to the
    first page whenever the project is replaced (New, Open): build the
    pager before the table's live section, so it is reset before the
    table is rebuilt.
    """

    def __init__(self, per_page: int = ROWS_PER_PAGE, *, session: Optional[Session] = None):
        self.per_page = per_page
        self.page = 0
        if session is not None:
            from nicegui import ui

            def first_page(_change: Any) -> None:
                self.page = 0

            ui.context.client.on_delete(
                session.subscribe(SessionEvent.PROJECT_REPLACED, first_page))

    def pages(self, total: int) -> int:
        return max(1, -(-total // self.per_page))

    def window(self, rows: Sequence[Any]) -> List[Any]:
        self.page = min(self.page, self.pages(len(rows)) - 1)
        start = self.page * self.per_page
        return list(rows[start:start + self.per_page])

    def controls(self, total: int, *, noun: str, refresh: Callable[[], None]) -> None:
        """"Rows 1-25 of 300" with Previous and Next page buttons, when there is more than a page."""
        from nicegui import ui

        if total <= self.per_page:
            return
        first = self.page * self.per_page + 1
        last = min(total, first + self.per_page - 1)

        def move(delta: int) -> None:
            self.page = max(0, min(self.pages(total) - 1, self.page + delta))
            refresh()

        with ui.row().classes("items-center justify-end w-full q-gutter-sm"):
            ui.label(f"{noun} {first}–{last} of {total}").props('aria-live="polite"')
            prev = ui.button(icon="chevron_left", on_click=lambda: move(-1)).props(
                'flat round dense aria-label="Previous page"')
            nxt = ui.button(icon="chevron_right", on_click=lambda: move(1)).props(
                'flat round dense aria-label="Next page"')
            prev.set_enabled(self.page > 0)
            nxt.set_enabled(self.page < self.pages(total) - 1)


def plan_view(session: Session) -> None:
    """The plan-view plot of the session's project, rebuilt after every change.

    It follows the sources and the receptors (and the project being
    replaced), and nothing else.
    """
    from nicegui import ui

    from ._live import live
    from .plan_view import plan_view_svg

    @live(session, SessionEvent.PROJECT_CHANGED, parts={"sources", "receptors"})
    def _plot() -> None:
        ui.html(plan_view_svg(session.project), sanitize=False).classes("w-full").mark("plan-view")


def required_goto(goto: Optional[Goto]) -> Goto:
    return goto if goto is not None else no_goto


__all__ = [
    "ROWS_PER_PAGE",
    "Goto",
    "Pager",
    "confirm",
    "no_goto",
    "plan_view",
    "required_goto",
    "section",
    "step_page",
]
