"""
Building blocks every step page shares.

- :func:`step_page`: the page template, a heading, a one-line
  introduction and a column that is as wide as the window up to 1280 px;
- :func:`section`: a titled card inside a step;
- :func:`confirm`: a yes/no question in the page's dialog container;
- :class:`Pager`: which slice of a long table is shown, with Previous /
  Next buttons that have accessible names;
- :func:`item_table`: the paged table of a step's items, with Edit and
  Delete on every row;
- :func:`plan_view`: the plan-view plot, rebuilt after every change to
  the sources or receptors.

NiceGUI is imported inside the functions, so importing this module does
not import NiceGUI.
"""

from __future__ import annotations

import contextlib
from typing import Any, Callable, Dict, Iterator, List, Optional, Sequence

from .session import Session, SessionEvent

#: Rows a table shows per page.
ROWS_PER_PAGE = 25

#: What a step does when it sends the user to another step.
Goto = Callable[[str], None]


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


def editor_dialog(dialogs: Any, *, title: str, build: Callable[[Callable[[], None]], None],
                  findings: Callable[[], List[str]], refused: Callable[[], List[str]],
                  save: Callable[[], bool], gone: str) -> Any:
    """Open the editor of one source or receptor; return the dialog.

    ``build(on_change)`` builds the fields of the draft and calls
    ``on_change()`` after each edit. The dialog is persistent: a click
    outside it or Esc does not close it, so a draft is discarded only by
    Cancel.

    ``findings()`` are the validator's problems with the draft; they are
    listed in the editor as it opens and again after every edit, so the
    user sees them where the item is edited (Review & Run lists them too).
    Save is refused, with the reasons listed, while a field fails its own
    check (:func:`~pyaermod.gui_v2._form.field_errors`: an emptied number,
    a line of numbers that could not be read, a source ID AERMOD could not
    read) or ``refused()`` names a problem (a duplicate ID). ``save()``
    hands the draft to the session and returns False when the item it
    replaces has gone (``gone`` is then the notice).
    """
    from nicegui import ui

    from ._form import field_errors

    def listing(heading: str, problems: List[str], colour: str) -> None:
        ui.label(heading).classes(f"text-subtitle2 {colour}")
        with ui.element("ul").classes("q-my-none q-pl-md"):
            for problem in problems:
                with ui.element("li"):
                    ui.label(problem[:1].upper() + problem[1:]).classes(f"text-body2 {colour}")

    @ui.refreshable
    def _findings() -> None:
        found = findings()
        if found:
            listing("The checks find these problems (Review & Run lists them until they "
                    "are fixed):", found, "text-negative")

    def on_save() -> None:
        problems = field_errors(fields) + refused()
        if problems:
            refusal.clear()
            with refusal:
                listing("Not saved: correct these first.", problems, "text-negative")
            ui.notify(f"Not saved: {problems[0]}", color="negative")
            return
        if not save():
            ui.notify(gone, color="warning")
        dialog.close()

    with dialogs, ui.dialog().props("persistent").mark("editor-dialog") as dialog, \
            ui.card().classes("w-full max-w-4xl"):
        dialog.props["aria-label"] = title
        ui.label(title).classes("text-h6")
        with ui.column().classes("w-full gap-2") as fields:
            def changed() -> None:
                _findings.refresh()

            build(changed)
        with ui.column().classes("w-full gap-1").props('role="status"').mark("editor-findings"):
            _findings()
        refusal = ui.column().classes("w-full gap-1").props('role="alert"').mark(
            "editor-problems")
        with ui.row().classes("justify-end w-full q-gutter-sm q-mt-md"):
            ui.button("Cancel", on_click=dialog.close).props("flat")
            ui.button("Save", on_click=on_save).props("color=primary")
    # A closed editor is gone for good; the next one is built afresh.
    dialog.on_value_change(lambda e: None if e.value else dialog.delete())
    dialog.open()
    return dialog


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


#: Row actions, with the item named in each button's accessible name.
ROW_ACTIONS_SLOT = """
<q-td :props="props" class="text-right">
  <q-btn dense flat round icon="edit" :aria-label="`Edit ${props.row.name}`"
         @click="$parent.$emit(`edit`, props.row.key)" />
  <q-btn dense flat round icon="delete" color="negative"
         :aria-label="`Delete ${props.row.name}`"
         @click="$parent.$emit(`delete`, props.row.key)" />
</q-td>
"""


def item_table(session: Session, *, part: str, noun: str, columns: List[Dict[str, Any]],
               entries: Callable[[], Sequence[Any]], row: Callable[[Any], Dict[str, Any]],
               on_edit: Callable[[Any], None], on_delete: Callable[[Any], None],
               empty: str) -> None:
    """The table of a step's items, one page at a time, with Edit and Delete on every row.

    A live section rebuilt when ``part`` of the project changes.
    ``entries()`` lists the items and ``row(entry)`` is the table row of
    one that is on the page shown: its ``key`` is what the ``edit`` and
    ``delete`` events carry, its ``name`` what the two buttons say.
    ``noun`` ("Sources") names the table; ``empty`` is shown under it
    while there are no items.
    """
    from nicegui import ui

    from ._live import live

    # Before the live section, so it is reset before the table is rebuilt.
    pager = Pager(session=session)

    @live(session, SessionEvent.PROJECT_CHANGED, parts={part})
    def _table() -> None:
        found = entries()
        table = ui.table(columns=columns, rows=[row(e) for e in pager.window(found)],
                         row_key="key").classes("w-full").props(
            f'flat bordered hide-bottom aria-label="{noun}"').mark(f"{noun.lower()}-table")
        table.add_slot("body-cell-actions", ROW_ACTIONS_SLOT)
        table.on("edit", on_edit)
        table.on("delete", on_delete)
        pager.controls(len(found), noun=noun, refresh=lambda: _table.refresh())
        if not found:
            ui.label(empty).classes("text-grey-8")


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


__all__ = [
    "ROWS_PER_PAGE",
    "ROW_ACTIONS_SLOT",
    "Goto",
    "Pager",
    "confirm",
    "editor_dialog",
    "item_table",
    "plan_view",
    "section",
    "step_page",
]
