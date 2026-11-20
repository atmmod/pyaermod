"""
Sources step.

A table of the project's sources with Edit and Delete on every row, a
plan view of the sources and receptors, and an editor for any of the 13
AERMOD source types. The editor is generated from the source's dataclass
(:mod:`pyaermod.gui_v2._form`): the fields AERMOD's LOCATION and SRCPARAM
cards need come first, the rest under "Advanced". Labels carry units and
the inputs their help text, from the library's field metadata.

New sources start from :data:`~pyaermod.gui_v2.catalog.SOURCE_DEFAULTS`,
placeholder values that pass
``__post_init__`` so the editor opens cleanly; the user overrides them
before Save. The table shows one page of rows at a time
(:class:`pyaermod.gui_v2._layout.Pager`).
"""

from __future__ import annotations

import copy
import dataclasses
from typing import Any, Callable, Dict, List, Optional

from ..._fields import units_of
from .._form import emit_fields
from .._layout import Goto, Pager, editor_dialog, plan_view, section, step_page
from .._live import live
from ..catalog import ADVANCED_FIELDS
from ..catalog import SOURCE_DEFAULTS as _DEFAULTS  # noqa: F401 - the tests read it here
from ..catalog import SOURCE_TYPES as _SOURCE_TYPES
from ..catalog import new_source as _new_source
from ..readiness import item_findings
from ..session import Session, SessionEvent


def _summary_row(src: Any) -> Dict[str, Any]:
    """Compact dict suitable for AG-Grid display."""
    cls_name = type(src).__name__
    if hasattr(src, "x_coord"):
        x, y = src.x_coord, src.y_coord
    elif hasattr(src, "x_start"):
        x, y = src.x_start, src.y_start
    elif hasattr(src, "vertices") and src.vertices:
        x, y = src.vertices[0]
    elif (getattr(src, "line_segments", None)
          and getattr(src.line_segments[0], "x_start", None) is not None):
        # BuoyLineSource: summarise from the first buoyant line segment
        x, y = src.line_segments[0].x_start, src.line_segments[0].y_start
    else:
        x, y = "", ""
    return {
        "id": src.source_id,
        "type": cls_name,
        "x": x,
        "y": y,
        "Q (g/s)": getattr(src, "emission_rate", ""),
    }


# ---------------------------------------------------------------------
# Page render
# ---------------------------------------------------------------------

_COLUMNS = [
    {"name": "id", "label": "ID", "field": "id", "align": "left"},
    {"name": "type", "label": "Type", "field": "type", "align": "left",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "x", "label": "X (m)", "field": "x", "align": "right",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "y", "label": "Y (m)", "field": "y", "align": "right",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "Q (g/s)", "label": "Emission rate", "field": "Q (g/s)", "align": "right"},
    {"name": "units", "label": "Units", "field": "units", "align": "left",
     "classes": "gt-xs", "headerClasses": "gt-xs"},
    {"name": "actions", "label": "Actions", "field": "key", "align": "right"},
]

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


def _emission_units(src: Any) -> str:
    for f in dataclasses.fields(src):
        if f.name == "emission_rate":
            return units_of(f) or ""
    return ""


def split_fields(obj: Any) -> tuple:
    """(basic, advanced) dataclass fields of ``obj`` for the editor."""
    fields = dataclasses.fields(obj)
    return ([f for f in fields if f.name not in ADVANCED_FIELDS],
            [f for f in fields if f.name in ADVANCED_FIELDS])


def editor_body(draft: Any, on_change: Optional[Callable[[], None]] = None) -> None:
    """The editor's fields: the basic ones, then the rest under "Advanced".

    ``on_change()`` is called after each edit.
    """
    from nicegui import ui

    basic, advanced = split_fields(draft)
    emit_fields(draft, basic, on_change=on_change)
    if advanced:
        with ui.expansion("Advanced", icon="tune").classes("w-full"):
            emit_fields(draft, advanced, on_change=on_change)


def render(session: Session, *, dialogs: Any, goto: Optional[Goto] = None) -> None:
    """Render the Sources step.

    The table and its empty-state message are a live section rebuilt when
    the sources change, and so is the plan view. Rows carry the session's
    key for each source; the editor works on a draft (a copy, or a new
    source for Add) that only Save hands to the session.
    """
    from nicegui import ui

    del goto
    pager = Pager(session=session)

    def _open_editor(key: Optional[str], draft: Any) -> None:
        def refused() -> List[str]:
            others = [s.source_id for k, s in session.source_entries() if k != key]
            if draft.source_id in others:
                return [f"Source ID: another source is called {draft.source_id}; AERMOD "
                        "needs a different ID for each"]
            return []

        def save() -> bool:
            if key is None:
                session.add_source(draft)
                return True
            return session.update_source(key, draft)

        # "Edit PointSource — NEW_SRC": the page objects and T1 tests find
        # the editor by its first words.
        editor_dialog(dialogs, title=f"Edit {type(draft).__name__} — {draft.source_id}",
                      build=lambda changed: editor_body(draft, changed),
                      findings=lambda: item_findings(session.project, draft),
                      refused=refused, save=save, gone="That source was removed")

    def _on_edit(e) -> None:
        for key, src in session.source_entries():
            if key == e.args:
                _open_editor(key, copy.deepcopy(src))
                return

    def _on_delete(e) -> None:
        removed = session.delete_source(e.args)
        if removed is not None:      # None: an event from a row already gone
            ui.notify(f"Deleted {removed.source_id}", color="warning")

    with step_page("Sources", "Add every source of the run. The plan view shows them "
                   "with the receptors, in model coordinates."):
        with ui.row().classes("items-end gap-3 w-full flex-wrap"):
            type_select = ui.select(
                options=list(_SOURCE_TYPES.keys()), label="Type", value="PointSource",
            ).classes("w-full sm:w-64")
            ui.button("Add", icon="add",
                      on_click=lambda: _open_editor(None, _new_source(type_select.value)),
                      ).props("color=primary")

        with ui.element("div").classes("grid grid-cols-1 lg:grid-cols-5 gap-4 w-full items-start"):
            with ui.column().classes("lg:col-span-3 min-w-0 w-full gap-2"):
                @live(session, SessionEvent.PROJECT_CHANGED, parts={"sources"})
                def _table() -> None:
                    entries = session.source_entries()
                    rows: List[Dict[str, Any]] = [
                        {**_summary_row(s), "units": _emission_units(s), "key": key,
                         "name": s.source_id}
                        for key, s in pager.window(entries)
                    ]
                    table = ui.table(columns=_COLUMNS, rows=rows, row_key="key").classes(
                        "w-full").props('flat bordered hide-bottom aria-label="Sources"').mark(
                        "sources-table")
                    table.add_slot("body-cell-actions", ROW_ACTIONS_SLOT)
                    table.on("edit", _on_edit)
                    table.on("delete", _on_delete)
                    pager.controls(len(entries), noun="Sources", refresh=lambda: _table.refresh())
                    if not entries:
                        ui.label("No sources yet. Choose a type and click Add.").classes(
                            "text-grey-8")
            with ui.column().classes("lg:col-span-2 min-w-0 w-full"), \
                    section("Plan view"):
                plan_view(session)


__all__ = ["ADVANCED_FIELDS", "editor_body", "render", "split_fields"]
